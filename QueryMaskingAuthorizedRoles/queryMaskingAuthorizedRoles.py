r"""Create PeopleSoft Query Masking authorized roles from a CSV file.

The default mode starts a new Chrome window. Sign in, navigate to the Query
Masking Authorized Roles search page, and return to the terminal to press
Enter when the page is ready.

To use an already-running Chrome DevTools session instead::

    python .\queryMaskingAuthorizedRoles.py --browser-port 9222

Limit a test run to the first three CSV data rows::

    python .\queryMaskingAuthorizedRoles.py --browser-port 9222 --limit 3

Select a later slice with one-based data-row numbering (the header is not
counted)::

    python .\queryMaskingAuthorizedRoles.py --start-row 61 --limit 10

The CSV must contain the columns ROLENAME, RECNAME, and FIELDNAME. For each
role, the script opens Add a New Value, enters the role name, adds every
selected record/field pair with access code Authorized, and saves the role.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select, WebDriverWait


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "queryMaskingAuthorizedRoles.csv"
FRAME_IDS = ("ptifrmtgtframe", "main_target_win0")

ADD_NEW_ID = "PTS_ADDMODE_BTN"
ROLE_NAME_ID = "PTS_FILTER_NOOP_PTS_PROMPT2$0"
ADD_ROLE_ID = "PTS_SRCH_BTN"
RECORD_PREFIX = "RECNAME$"
FIELD_PREFIX = "EODP_ROLRECFLD_FIELDNAME$"
ACCESS_PREFIX = "EODP_ROLRECFLD_EODP_ACCESS_CD$"
INSERT_ROW_PREFIX = "EODP_RRF_WRK_EODP_INSERT_ROW"
SAVE_ID = "EODP_RRF_WRK_SAVE_PB"
PROCESSING_ID = "WAIT_win0"

T = TypeVar("T")


class AutomationError(RuntimeError):
    """Raised when PeopleSoft is not in the state expected by the script."""


@dataclass(frozen=True)
class CsvRow:
    data_row: int
    csv_line: int
    role_name: str
    record_name: str
    field_name: str


@dataclass(frozen=True)
class Failure:
    data_row: int | str
    csv_line: int | str
    role_name: str
    record_name: str
    field_name: str
    stage: str
    error: str


@dataclass
class RunStats:
    selected: int = 0
    saved: int = 0
    failed: int = 0


def read_csv_rows(csv_path: Path) -> list[CsvRow]:
    """Load and validate all nonblank data rows from *csv_path*."""

    try:
        csv_file = csv_path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ValueError(f"Could not open CSV '{csv_path}': {exc}") from exc

    rows: list[CsvRow] = []
    with csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError("The CSV is empty or has no header row.")

        normalized_headers = {
            (header or "").strip().upper(): header for header in reader.fieldnames
        }
        required = ("ROLENAME", "RECNAME", "FIELDNAME")
        missing = [header for header in required if header not in normalized_headers]
        if missing:
            raise ValueError(
                "Missing required CSV column(s): " + ", ".join(missing)
            )

        for csv_line, raw_row in enumerate(reader, start=2):
            if raw_row is None or not any((value or "").strip() for value in raw_row.values()):
                continue

            values = {
                header: (raw_row.get(normalized_headers[header]) or "").strip()
                for header in required
            }
            empty = [header for header, value in values.items() if not value]
            if empty:
                raise ValueError(
                    f"CSV line {csv_line} has blank required field(s): "
                    + ", ".join(empty)
                )

            rows.append(
                CsvRow(
                    data_row=len(rows) + 1,
                    csv_line=csv_line,
                    role_name=values["ROLENAME"],
                    record_name=values["RECNAME"],
                    field_name=values["FIELDNAME"],
                )
            )

    if not rows:
        raise ValueError("The CSV contains no data rows.")
    return rows


def select_rows(rows: list[CsvRow], start_row: int, limit: int | None) -> list[CsvRow]:
    start_index = start_row - 1
    return rows[start_index:] if limit is None else rows[start_index : start_index + limit]


def group_rows(rows: list[CsvRow]) -> OrderedDict[str, list[CsvRow]]:
    grouped: OrderedDict[str, list[CsvRow]] = OrderedDict()
    for row in rows:
        grouped.setdefault(row.role_name, []).append(row)
    return grouped


def configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("query_masking_authorized_roles")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def write_failures(path: Path, failures: list[Failure]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            (
                "DATA_ROW",
                "CSV_LINE",
                "ROLENAME",
                "RECNAME",
                "FIELDNAME",
                "STAGE",
                "ERROR",
            )
        )
        for failure in failures:
            writer.writerow(
                (
                    failure.data_row,
                    failure.csv_line,
                    failure.role_name,
                    failure.record_name,
                    failure.field_name,
                    failure.stage,
                    failure.error,
                )
            )


class PeopleSoftQueryMaskingAutomation:
    """Drive the controls documented in the original script comments."""

    def __init__(
        self,
        driver: webdriver.Chrome,
        start_url: str,
        logger: logging.Logger,
        wait_seconds: float,
        pause_seconds: float,
    ) -> None:
        self.driver = driver
        self.start_url = start_url
        self.logger = logger
        self.wait_seconds = wait_seconds
        self.pause_seconds = pause_seconds
        self.wait = WebDriverWait(
            driver,
            wait_seconds,
            poll_frequency=0.2,
            ignored_exceptions=(StaleElementReferenceException,),
        )

    def _enter_content(self) -> None:
        """Switch to the PeopleSoft target frame, or remain in top-level content."""

        self.driver.switch_to.default_content()
        for frame_id in FRAME_IDS:
            frames = self.driver.find_elements(By.ID, frame_id)
            if frames:
                self.driver.switch_to.frame(frames[0])
                return

    def _wait_for(self, finder: Callable[[], T | None], description: str) -> T:
        try:
            return self.wait.until(lambda _driver: finder() or False)
        except TimeoutException as exc:
            raise AutomationError(
                f"Timed out after {self.wait_seconds:g}s waiting for {description}."
            ) from exc

    def _visible_by_id(self, element_id: str) -> WebElement | None:
        self._enter_content()
        for element in self.driver.find_elements(By.ID, element_id):
            if element.is_displayed():
                return element
        return None

    def _wait_visible_by_id(self, element_id: str, description: str) -> WebElement:
        return self._wait_for(lambda: self._visible_by_id(element_id), description)

    def _processing_is_complete(self) -> bool:
        self._enter_content()
        indicators = self.driver.find_elements(By.ID, PROCESSING_ID)
        return not any(indicator.is_displayed() for indicator in indicators)

    def _wait_for_processing(self) -> None:
        # PeopleSoft displays WAIT_win0 synchronously for postbacks. This small
        # pause prevents checking its initial hidden state before the postback starts.
        if self.pause_seconds:
            time.sleep(self.pause_seconds)
        self._wait_for(
            lambda: self._processing_is_complete(),
            "PeopleSoft processing to finish",
        )

    def _click(self, element: WebElement) -> None:
        self.driver.execute_script("arguments[0].click();", element)

    def _dismiss_error_if_present(self) -> None:
        """Raise visible JavaScript or PeopleSoft dialog text as an error."""

        try:
            alert = self.driver.switch_to.alert
            text = alert.text.strip() or "PeopleSoft displayed a browser alert."
            alert.accept()
            raise AutomationError(text)
        except NoAlertPresentException:
            pass

        self.driver.switch_to.default_content()
        buttons = self.driver.find_elements(By.ID, "#ALERTOK")
        visible_buttons = [button for button in buttons if button.is_displayed()]
        if not visible_buttons:
            return

        message = "PeopleSoft rejected the requested change."
        for message_id in ("alertmsg", "alertmsgdialog", "ptpopupmsg"):
            for element in self.driver.find_elements(By.ID, message_id):
                if element.is_displayed() and element.text.strip():
                    message = element.text.strip()
                    break
        self._click(visible_buttons[0])
        raise AutomationError(message)

    def _set_text(self, element_id: str, value: str, description: str) -> None:
        element = self._wait_visible_by_id(element_id, description)
        element.click()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(value)
        element.send_keys(Keys.TAB)
        self._wait_for_processing()
        self._dismiss_error_if_present()

        current = self._wait_visible_by_id(element_id, description)
        actual = (current.get_attribute("value") or "").strip()
        if actual.casefold() != value.casefold():
            raise AutomationError(
                f"PeopleSoft did not retain {description}: expected {value!r}, "
                f"found {actual!r}."
            )

    @staticmethod
    def _row_suffix(element_id: str) -> str | None:
        match = re.search(r"\$(\d+)$", element_id)
        return match.group(1) if match else None

    def _row_fields(self, prefix: str) -> dict[str, WebElement]:
        self._enter_content()
        fields: dict[str, WebElement] = {}
        for element in self.driver.find_elements(By.CSS_SELECTOR, f"[id^='{prefix}']"):
            if not element.is_displayed():
                continue
            suffix = self._row_suffix(element.get_attribute("id") or "")
            if suffix is not None:
                fields[suffix] = element
        return fields

    def _blank_row_suffix(self) -> str | None:
        record_fields = self._row_fields(RECORD_PREFIX)
        for suffix in sorted(record_fields, key=int):
            value = (record_fields[suffix].get_attribute("value") or "").strip()
            if record_fields[suffix].is_enabled() and not value:
                return suffix
        return None

    def _insert_row_button(self) -> WebElement | None:
        self._enter_content()
        controls = self.driver.find_elements(
            By.CSS_SELECTOR, f"[id^='{INSERT_ROW_PREFIX}']"
        )
        for control in controls:
            if (
                control.is_displayed()
                and control.is_enabled()
                and control.tag_name.casefold() in {"a", "button", "input"}
            ):
                return control
        return None

    def _get_or_add_blank_row(self) -> str:
        suffix = self._blank_row_suffix()
        if suffix is not None:
            return suffix

        old_suffixes = set(self._row_fields(RECORD_PREFIX))
        button = self._wait_for(
            self._insert_row_button,
            "the Query Masking Insert Row button",
        )
        self._click(button)
        self._wait_for_processing()
        self._dismiss_error_if_present()

        def new_blank_suffix() -> str | None:
            candidate = self._blank_row_suffix()
            if candidate is not None:
                return candidate
            new_suffixes = set(self._row_fields(RECORD_PREFIX)) - old_suffixes
            return sorted(new_suffixes, key=int)[0] if new_suffixes else None

        return self._wait_for(new_blank_suffix, "a new Query Masking row")

    def _wait_for_row_element(self, prefix: str, suffix: str, description: str) -> WebElement:
        return self._wait_for(
            lambda: self._row_fields(prefix).get(suffix),
            description,
        )

    def _set_row_text(self, prefix: str, suffix: str, value: str, label: str) -> None:
        element = self._wait_for_row_element(prefix, suffix, label)
        element.click()
        element.send_keys(Keys.CONTROL, "a")
        element.send_keys(value)
        element.send_keys(Keys.TAB)
        self._wait_for_processing()
        self._dismiss_error_if_present()

        refreshed = self._wait_for_row_element(prefix, suffix, label)
        actual = (refreshed.get_attribute("value") or "").strip()
        if actual.casefold() != value.casefold():
            raise AutomationError(
                f"PeopleSoft did not retain {label}: expected {value!r}, "
                f"found {actual!r}."
            )

    def _set_authorized(self, suffix: str) -> None:
        element = self._wait_for_row_element(
            ACCESS_PREFIX,
            suffix,
            "the Access Code list",
        )
        Select(element).select_by_value("Y")
        element.send_keys(Keys.TAB)
        self._wait_for_processing()
        self._dismiss_error_if_present()

        refreshed = self._wait_for_row_element(
            ACCESS_PREFIX,
            suffix,
            "the Access Code list",
        )
        if (refreshed.get_attribute("value") or "") != "Y":
            raise AutomationError("PeopleSoft did not retain Access Code 'Authorized'.")

    def open_new_role(self, role_name: str) -> None:
        self.driver.get(self.start_url)
        add_new = self._wait_visible_by_id(
            ADD_NEW_ID,
            "Add a New Value; confirm the saved start page is the Query Masking "
            "Authorized Roles search page",
        )
        self._click(add_new)
        self._wait_for_processing()
        self._dismiss_error_if_present()

        self._set_text(ROLE_NAME_ID, role_name, "the Role Name field")
        add_role = self._wait_visible_by_id(ADD_ROLE_ID, "the Add button")
        self._click(add_role)
        self._wait_for_processing()
        self._dismiss_error_if_present()

        self._wait_for(
            lambda: bool(self._row_fields(RECORD_PREFIX)),
            "the Query Masking role detail page",
        )

    def add_authorized_row(self, row: CsvRow) -> None:
        suffix = self._get_or_add_blank_row()
        self._set_row_text(
            RECORD_PREFIX,
            suffix,
            row.record_name,
            f"Record Name for CSV line {row.csv_line}",
        )
        self._set_row_text(
            FIELD_PREFIX,
            suffix,
            row.field_name,
            f"Field Name for CSV line {row.csv_line}",
        )
        self._set_authorized(suffix)

    def save_role(self) -> None:
        save = self._wait_visible_by_id(SAVE_ID, "the Save button")
        self._click(save)
        self._wait_for_processing()
        self._dismiss_error_if_present()
        self._wait_visible_by_id(SAVE_ID, "the saved Query Masking role page")

    def process_role(self, role_name: str, rows: list[CsvRow]) -> None:
        self.logger.info("Role %s: creating with %d row(s)", role_name, len(rows))
        self.open_new_role(role_name)
        for index, row in enumerate(rows, start=1):
            self.logger.info(
                "Role %s: adding %d/%d - %s.%s (CSV data row %d)",
                role_name,
                index,
                len(rows),
                row.record_name,
                row.field_name,
                row.data_row,
            )
            try:
                self.add_authorized_row(row)
            except Exception as exc:
                raise AutomationError(
                    f"CSV data row {row.data_row} ({row.record_name}."
                    f"{row.field_name}) failed: {exc}"
                ) from exc
        self.save_role()
        self.logger.info("Role %s: saved successfully", role_name)


def start_browser(browser_port: int | None) -> tuple[webdriver.Chrome, bool]:
    """Return (driver, owns_browser)."""

    options = Options()
    if browser_port is not None:
        options.debugger_address = f"localhost:{browser_port}"
        try:
            return webdriver.Chrome(options=options), False
        except Exception as exc:
            raise AutomationError(
                f"Could not attach to Chrome on localhost:{browser_port}. Start "
                "Chrome with --remote-debugging-port set to that port and try again."
            ) from exc

    options.add_argument("--start-maximized")
    try:
        return webdriver.Chrome(options=options), True
    except Exception as exc:
        raise AutomationError(f"Could not start Chrome: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create Query Masking authorized roles in PeopleSoft from a CSV file."
        )
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV,
        help="input CSV (default: the CSV beside this script)",
    )
    parser.add_argument(
        "--browser-port",
        type=int,
        metavar="PORT",
        help=(
            "attach to Chrome's remote-debugging port (for example, 9222); "
            "without this option the script opens a new Chrome window"
        ),
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=1,
        help="one-based CSV data row at which to start (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="maximum number of CSV data rows to process",
    )
    parser.add_argument(
        "--start-url",
        help="override the start page URL instead of using the browser's current URL",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=30.0,
        help="maximum seconds to wait for each PeopleSoft action (default: %(default)s)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.35,
        help="seconds to pause before checking PeopleSoft processing (default: %(default)s)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="log destination (default: timestamped file beside the script)",
    )
    parser.add_argument(
        "--failure-file",
        type=Path,
        help="failure CSV destination (default: timestamped file beside the script)",
    )
    parser.add_argument(
        "--keep-browser-open",
        action="store_true",
        help="leave a script-started Chrome window open when finished",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and display the selected CSV rows without opening Chrome",
    )

    args = parser.parse_args(argv)
    if args.browser_port is not None and not 1 <= args.browser_port <= 65535:
        parser.error("--browser-port must be between 1 and 65535")
    if args.start_row < 1:
        parser.error("--start-row must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.wait <= 0:
        parser.error("--wait must be greater than zero")
    if args.pause < 0:
        parser.error("--pause cannot be negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = args.log_file or SCRIPT_DIR / f"queryMaskingAuthorizedRoles_{timestamp}.log"
    failure_path = (
        args.failure_file
        or SCRIPT_DIR / f"queryMaskingAuthorizedRoles_failures_{timestamp}.csv"
    )
    logger = configure_logging(log_path)

    try:
        all_rows = read_csv_rows(args.csv_path)
    except ValueError as exc:
        logger.error("CSV error: %s", exc)
        return 2

    selected_rows = select_rows(all_rows, args.start_row, args.limit)
    if not selected_rows:
        logger.error(
            "No rows selected: the CSV has %d data row(s), but --start-row is %d.",
            len(all_rows),
            args.start_row,
        )
        return 2

    grouped = group_rows(selected_rows)
    logger.info(
        "Selected %d of %d CSV row(s), data rows %d-%d, across %d role(s).",
        len(selected_rows),
        len(all_rows),
        selected_rows[0].data_row,
        selected_rows[-1].data_row,
        len(grouped),
    )
    logger.info("Detailed log: %s", log_path)

    if args.dry_run:
        for role_name, rows in grouped.items():
            logger.info("%s: %d row(s)", role_name, len(rows))
            for row in rows:
                logger.info(
                    "  data row %d: %s, %s",
                    row.data_row,
                    row.record_name,
                    row.field_name,
                )
        return 0

    driver: webdriver.Chrome | None = None
    owns_browser = False
    failures: list[Failure] = []
    stats = RunStats(selected=len(selected_rows))

    try:
        driver, owns_browser = start_browser(args.browser_port)
        driver.implicitly_wait(0)

        if owns_browser:
            if args.start_url:
                driver.get(args.start_url)
            try:
                input(
                    "\nSign in to PeopleSoft and navigate to the Query Masking "
                    "Authorized Roles search page.\nPress Enter here when the page "
                    "is ready... "
                )
            except EOFError as exc:
                raise AutomationError(
                    "The new-browser mode requires an interactive terminal so you can "
                    "press Enter. Use --browser-port for DevTools mode in a "
                    "non-interactive session."
                ) from exc

        start_url = args.start_url or driver.current_url
        if not start_url or start_url.startswith(("about:", "data:", "chrome:")):
            raise AutomationError(
                "The browser is not on the PeopleSoft Query Masking Authorized Roles "
                "search page. Navigate there and run the script again."
            )
        logger.info("Using start page: %s", start_url)

        automation = PeopleSoftQueryMaskingAutomation(
            driver=driver,
            start_url=start_url,
            logger=logger,
            wait_seconds=args.wait,
            pause_seconds=args.pause,
        )

        for role_name, role_rows in grouped.items():
            try:
                automation.process_role(role_name, role_rows)
                stats.saved += len(role_rows)
            except Exception as exc:
                stats.failed += len(role_rows)
                logger.exception("Role %s failed: %s", role_name, exc)
                for row in role_rows:
                    failures.append(
                        Failure(
                            data_row=row.data_row,
                            csv_line=row.csv_line,
                            role_name=row.role_name,
                            record_name=row.record_name,
                            field_name=row.field_name,
                            stage="role_not_saved",
                            error=str(exc),
                        )
                    )

        if failures:
            write_failures(failure_path, failures)
            logger.error("Failure report: %s", failure_path)

        logger.info(
            "Complete: %d selected, %d saved, %d failed.",
            stats.selected,
            stats.saved,
            stats.failed,
        )
        return 1 if failures else 0

    except Exception as exc:
        logger.exception("Automation stopped: %s", exc)
        failures.append(
            Failure("", "", "", "", "", "startup", str(exc))
        )
        write_failures(failure_path, failures)
        logger.error("Failure report: %s", failure_path)
        return 1
    finally:
        if driver is not None and owns_browser and not args.keep_browser_open:
            try:
                driver.quit()
            except Exception:
                logger.debug("Chrome did not close cleanly.", exc_info=True)


if __name__ == "__main__":
    sys.exit(main())
