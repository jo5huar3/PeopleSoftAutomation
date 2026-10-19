"""Verify selected CSV class numbers against PeopleSoft Fluid Class Search.

Usage::

    python fluid_class_search.py --environment PRD \
        --course-list prior_results.csv --process-count 10 \
        --diagnostic-output diagnostics.txt --summary-output summary.txt \
        --csv-output class_issues.csv

Exactly one data source is required: ``--csv-path`` or ``--course-list``. A CSV
source must contain SUBJECT, CATALOG_NBR, and CLASS_NBR. A text course list must
contain the clean-summary ``Expected class numbers: ...`` values. Three
explicitly named outputs separate full diagnostics, a readable one-line-per-
issue summary, and structured class-number issues. The diagnostic file is the
only file that contains stack traces. The CSV report is retained only when a
class number is missing or could not be verified.
"""

import argparse
import csv
import os
import re
import sys
import time
import traceback
from multiprocessing import Event, Process, Queue
from queue import Empty

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# Pacing is 0.5 seconds. Explicit waits return immediately when the page is
# ready; PAGE_WAIT_SECONDS is only their maximum on a slow response.
SEARCH_PAUSE_SECONDS = 0.5
PAGE_WAIT_SECONDS = 5
DETAIL_STABILITY_SECONDS = 0.5
DETAIL_POLL_SECONDS = 0.1
RESULT_MESSAGE_SELECTOR = "[id$='divPTS_SEARCHED_KW2']"
RESULT_TITLE_SELECTOR = "a[id^='PTS_LIST_TITLE$']"
RESULT_SUMMARY_SELECTOR = "[id*='divPTS_LIST_SUMMARY$']"
PROCESSING_INDICATOR_SELECTOR = "[id^='WAIT_win']"
DETAIL_GRID_SELECTOR = "[id*='SSR_CLS_DTLS_VWgridc']"
DETAIL_ROW_SELECTOR = (
    "[id*='SSR_CLS_DTLS_VWgridc'] "
    "tr[id^='SSR_CLS_DTLS_VW$'][id*='_row_']"
)
DETAIL_COMPONENT_SELECTOR = (
    "[id*='SSR_CMPNT_DESCR_'][title='Class Number']"
)
COURSE_CSV_COLUMNS = ("SUBJECT", "CATALOG_NBR", "CLASS_NBR")
ISSUE_CSV_COLUMNS = (
    "SUBJECT",
    "CATALOG_NBR",
    "CLASS_NBR",
    "ISSUE",
    "RETURNED_CLASS_NUMBERS",
    "REASON",
)

login_pages = {
    "TST": "https://dev.my.uh.edu:8021/psp/sa92tst/?cmd=login",
    "DEV": "https://dev.my.uh.edu:8042/psp/sa92dev/?cmd=login&languageCd=ENG&",
    "PRD": "https://saprd.my.uh.edu/psp/saprd/?cmd=login&languageCd=ENG&",
}


class Course:
    """Store one subject/catalog pair and its unique source class rows.

    Args:
        subject: Nonblank CSV SUBJECT value.
        course_number: Nonblank CSV CATALOG_NBR value.
        source_row: First source row containing CLASS_NBR.

    Behavior:
        Rows are keyed by CLASS_NBR, preventing duplicate input rows from
        inflating counts or producing duplicate missing-class output.

    Failure behavior:
        Raises ValueError for blank identifiers and KeyError when CLASS_NBR is
        absent from source_row.
    """

    def __init__(self, subject: str, course_number: str,
                 source_row: dict[str, str]) -> None:
        """Normalize identifiers and add the first class row.

        Invalid blank identifiers raise ValueError. Invalid source rows fail
        as documented by Add_Source_Row.
        """
        self.subject = subject.strip().upper()
        self.course_number = course_number.strip().upper()
        if not self.subject or not self.course_number:
            raise ValueError("SUBJECT and CATALOG_NBR cannot be blank")
        self.rows_by_class_number: dict[str, dict[str, str]] = {}
        self.Add_Source_Row(source_row)

    def Add_Source_Row(self, source_row: dict[str, str]) -> None:
        """Add a row unless its CLASS_NBR is already stored.

        source_row must contain a nonblank CLASS_NBR. A missing key raises
        KeyError and a blank value raises ValueError; duplicates are ignored.
        """
        class_number = source_row["CLASS_NBR"].strip()
        if not class_number:
            raise ValueError("CLASS_NBR cannot be blank")
        self.rows_by_class_number.setdefault(class_number, dict(source_row))

    def Get_Subject(self) -> str:
        """Return the normalized subject; this method does not fail."""
        return self.subject

    def Get_Count(self) -> int:
        """Return the unique expected CLASS_NBR count; this cannot fail."""
        return len(self.rows_by_class_number)

    def Get_Course_Number(self) -> str:
        """Return the normalized catalog number; this method does not fail."""
        return self.course_number

    def Get_Class_Numbers(self) -> set[str]:
        """Return a copy of all expected CLASS_NBR values."""
        return set(self.rows_by_class_number)

    def Get_Source_Rows(self, class_numbers: set[str] | None = None
                        ) -> list[dict[str, str]]:
        """Return copies of all or selected source rows.

        Unknown requested numbers are ignored. None selects every stored row,
        and source dictionaries are copied so report code cannot mutate them.
        """
        selected = (self.Get_Class_Numbers() if class_numbers is None
                    else class_numbers)
        return [
            dict(self.rows_by_class_number[number])
            for number in sorted(selected)
            if number in self.rows_by_class_number
        ]


def Normalize_Course_Key(subject: str, course_number: str) -> tuple[str, str]:
    """Return a stripped uppercase subject/catalog key.

    Inputs must be strings. Non-strings raise AttributeError; blanks remain
    blank so the caller can report the relevant file or row location.
    """
    return subject.strip().upper(), course_number.strip().upper()


def Extract_Text_Expected_Class_Numbers(line: str) -> set[str] | None:
    """Extract expected CLASS_NBR values from one summary-report line.

    Args:
        line: Course-prefixed clean-summary line. Current lines use
            ``Expected class numbers:``; older detailed lines may use
            ``CSV class numbers (N):``.

    Returns:
        A set of numeric class-number strings, or None when neither supported
        expected-list marker exists on the line.

    Failure behavior:
        Raises ValueError when a marker exists but its comma-separated value
        contains a nonnumeric or empty class number.
    """
    list_match = re.search(
        r"Expected class numbers:\s*([^.;\r\n]+)",
        line,
        re.IGNORECASE,
    )
    if list_match is None:
        list_match = re.search(
            r"CSV class numbers\s*\(\d+\):\s*([^;\r\n]+)",
            line,
            re.IGNORECASE,
        )
    if list_match is None:
        return None

    values = {value.strip() for value in list_match.group(1).split(",")}
    if not values or "" in values or any(
        not value.isdigit() for value in values
    ):
        raise ValueError(
            "Expected class-number list must contain comma-separated digits"
        )
    return values


def Load_Courses_From_Text_List(
    course_list_path: str,
) -> dict[str, list[Course]]:
    """Build complete Course objects from a clean-summary text file.

    Args:
        course_list_path: Text file with ``SUBJECT CATALOG_NBR:`` lines that
            also include an explicit expected/CSV class-number list.

    Returns:
        Subject keys mapped to Course objects containing every expected class
        number found in the text file.

    Failure behavior:
        Filesystem and decoding errors propagate. ValueError identifies course
        lines lacking class-number lists, malformed lists, or a file with no
        usable courses. This prevents a key-only text list from silently using
        an empty expected set.
    """
    course_pattern = re.compile(
        r"^\s*([A-Z][A-Z0-9]*)\s+([A-Z0-9][A-Z0-9.-]*)\s*:",
        re.IGNORECASE,
    )
    classes: dict[str, list[Course]] = {}
    incomplete_lines: list[int] = []
    with open(course_list_path, "r", encoding="utf-8-sig") as course_file:
        for line_number, line in enumerate(course_file, start=1):
            course_match = course_pattern.match(line)
            if course_match is None:
                continue
            class_numbers = Extract_Text_Expected_Class_Numbers(line)
            if class_numbers is None:
                incomplete_lines.append(line_number)
                continue

            subject, course_number = Normalize_Course_Key(
                course_match.group(1), course_match.group(2)
            )
            course_index = Find_Course_Index(
                classes.get(subject, []), course_number
            )
            for class_number in sorted(class_numbers):
                source_row = {
                    "SUBJECT": subject,
                    "CATALOG_NBR": course_number,
                    "CLASS_NBR": class_number,
                }
                if course_index is None:
                    classes.setdefault(subject, []).append(
                        Course(subject, course_number, source_row)
                    )
                    course_index = len(classes[subject]) - 1
                else:
                    classes[subject][course_index].Add_Source_Row(source_row)

    if incomplete_lines:
        line_preview = ", ".join(
            str(line_number) for line_number in incomplete_lines[:10]
        )
        extra_count = len(incomplete_lines) - 10
        if extra_count > 0:
            line_preview += f" and {extra_count} more"
        raise ValueError(
            "Text course-list entries must include 'Expected class numbers:' "
            "or the older 'CSV class numbers (N):' list; missing on line(s) "
            + line_preview
        )
    if not classes:
        raise ValueError(
            f"No usable course entries found in {course_list_path}"
        )
    return classes


def Find_Course_Index(courses: list[Course], course_number: str) -> int | None:
    """Return the matching Course index, or None when it is absent.

    courses must contain Course objects and course_number should already be
    normalized. Invalid members expose their normal attribute errors.
    """
    for index, course in enumerate(courses):
        if course_number == course.Get_Course_Number():
            return index
    return None


def Load_Courses_From_Csv(
    csv_path: str,
) -> tuple[dict[str, list[Course]], list[str]]:
    """Load unique expected class rows from a standalone CSV source.

    Args:
        csv_path: ``--csv-path`` or CSV ``--course-list`` containing SUBJECT,
            CATALOG_NBR, and CLASS_NBR. Other columns are accepted and ignored
            by the comparison.

    Returns:
        A grouped Course dictionary and the original CSV header order.

    Failure behavior:
        File and CSV errors propagate. ValueError reports absent headers or
        blank required values, or a file with no usable expected class rows.
        Rows marked UNEXPECTED_IN_FLUID in a legacy issue CSV are skipped
        because they were not part of the original expected set.
    """
    classes: dict[str, list[Course]] = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header row: {csv_path}")
        header_lookup = {
            header.strip().upper(): header
            for header in reader.fieldnames
            if header is not None
        }
        missing_columns = [
            column for column in COURSE_CSV_COLUMNS
            if column not in header_lookup
        ]
        if missing_columns:
            raise ValueError(
                "CSV is missing required columns: " + ", ".join(missing_columns)
            )

        for line_number, raw_row in enumerate(reader, start=2):
            row = {
                column: (value or "").strip()
                for column, value in raw_row.items() if column is not None
            }
            # Add canonical core keys even when the CSV used lowercase or
            # whitespace-padded headers.
            for column in COURSE_CSV_COLUMNS:
                row[column] = (
                    raw_row.get(header_lookup[column]) or ""
                ).strip()
            issue_header = header_lookup.get("ISSUE")
            if issue_header and (
                raw_row.get(issue_header) or ""
            ).strip().upper() == "UNEXPECTED_IN_FLUID":
                continue

            blank_columns = [
                column for column in COURSE_CSV_COLUMNS if not row.get(column)
            ]
            if blank_columns:
                raise ValueError(
                    f"CSV line {line_number} has blank required values: "
                    + ", ".join(blank_columns)
                )
            subject, course_number = Normalize_Course_Key(
                row["SUBJECT"], row["CATALOG_NBR"]
            )
            index = Find_Course_Index(classes.get(subject, []), course_number)
            if index is None:
                classes.setdefault(subject, []).append(
                    Course(subject, course_number, row)
                )
            else:
                classes[subject][index].Add_Source_Row(row)
    if not classes:
        raise ValueError(f"CSV contains no usable expected class rows: {csv_path}")
    return classes, list(reader.fieldnames)


def Extract_Advertised_Option_Count(driver) -> int | None:
    """Return the displayed Class Options count, or None if not parseable.

    driver must be on a search-results page. Selenium access errors propagate
    to the per-course handler; absence of a matching summary is not an error.
    """
    for summary in driver.find_elements(By.CSS_SELECTOR, RESULT_SUMMARY_SELECTOR):
        match = re.search(r"\b(\d+)\s+Class Options? Available\b", summary.text)
        if match:
            return int(match.group(1))
    return None


def Find_Exact_Result_Title(driver, current_search: str):
    """Return the PTS_LIST_TITLE link exactly matching SUBJECT CATALOG_NBR.

    driver must display search results and current_search is normalized for
    human display. NoSuchElementException is raised if no exact visible-title
    match exists; other Selenium errors propagate.
    """
    expected = " ".join(current_search.split()).casefold()
    for title in driver.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR):
        if " ".join(title.text.split()).casefold() == expected:
            return title
    raise NoSuchElementException(
        f"No exact {current_search!r} PTS_LIST_TITLE link was returned"
    )


def Read_Detail_Component_State(driver) -> tuple[tuple[str, str, str], ...]:
    """Take an ordered snapshot of every rendered detail component.

    Args:
        driver: Selenium WebDriver currently displaying a course detail grid.

    Returns:
        Tuples containing row ID, component-span ID, and normalized visible
        text for every ``SSR_CMPNT_DESCR_`` Class Number span, ordered from the
        first detail row through the last.

    Failure behavior:
        Returns an empty tuple when rows/components have not rendered yet.
        Selenium access errors propagate to Wait_For_Detail_Load or the
        per-course exception handler.
    """
    component_state: list[tuple[str, str, str]] = []
    for detail_row in driver.find_elements(By.CSS_SELECTOR, DETAIL_ROW_SELECTOR):
        for component in detail_row.find_elements(
            By.CSS_SELECTOR, DETAIL_COMPONENT_SELECTOR
        ):
            component_state.append((
                detail_row.get_attribute("id"),
                component.get_attribute("id"),
                " ".join(component.text.split()),
            ))
    return tuple(component_state)


def Wait_For_Detail_Load(driver) -> None:
    """Wait for PeopleSoft navigation, processing, and grid rendering to end.

    Args:
        driver: Selenium WebDriver immediately after clicking a course result.

    Returns:
        None after the document is complete, the detail grid exists, every
        PeopleSoft ``WAIT_win...`` indicator is hidden, and the complete
        row/component snapshot remains unchanged for 0.5 seconds.

    Failure behavior:
        Raises TimeoutException if the document, grid, processing indicator,
        or grid contents do not reach a completed stable state within their
        configured waits. Other Selenium errors propagate to the per-course
        handler, which records the traceback and marks the search unverified.
    """
    wait = WebDriverWait(driver, PAGE_WAIT_SECONDS)
    wait.until(
        lambda current_driver: current_driver.execute_script(
            "return document.readyState"
        ) == "complete"
    )
    wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, DETAIL_GRID_SELECTOR))
    )

    # PeopleSoft's WAIT_win element begins hidden. Give the postback a moment
    # to expose it before testing for the final hidden state.
    time.sleep(DETAIL_POLL_SECONDS)
    wait.until(
        lambda current_driver: current_driver.execute_script(
            "return Array.from(document.querySelectorAll(arguments[0]))"
            ".every(function(element) {"
            "  var style = window.getComputedStyle(element);"
            "  return style.display === 'none' || "
            "         style.visibility === 'hidden';"
            "});",
            PROCESSING_INDICATOR_SELECTOR,
        )
    )

    # Some Fluid components are inserted just after the processing indicator
    # disappears. Completion is based only on an unchanged DOM snapshot—not on
    # whether any expected CSV number happened to appear.
    deadline = time.monotonic() + PAGE_WAIT_SECONDS
    previous_state: tuple[tuple[str, str, str], ...] | None = None
    stable_since: float | None = None
    while time.monotonic() < deadline:
        current_state = Read_Detail_Component_State(driver)
        now = time.monotonic()
        if current_state and current_state == previous_state:
            if stable_since is not None and (
                now - stable_since >= DETAIL_STABILITY_SECONDS
            ):
                return
        elif current_state:
            previous_state = current_state
            stable_since = now
        else:
            # Do not count time across a transient empty grid as stable.
            previous_state = None
            stable_since = None
        time.sleep(DETAIL_POLL_SECONDS)
    raise TimeoutException(
        "detail component rows did not finish rendering a stable snapshot"
    )


def Extract_Detail_Class_Numbers(driver) -> set[str]:
    """Wait for the completed detail page, then collect its class numbers.

    Args:
        driver: Selenium WebDriver after the exact course result was opened.

    Returns:
        A set built by looping from the first through the last component in one
        final stable grid snapshot. Duplicate component numbers collapse into
        one value before the caller compares this set with the CSV set.

    Failure behavior:
        Wait_For_Detail_Load propagates TimeoutException when the page never
        finishes. ValueError is raised if the completed snapshot contains no
        parseable component number. Other Selenium errors propagate to the
        per-course handler and its traceback report.
    """
    Wait_For_Detail_Load(driver)
    class_numbers: set[str] = set()
    for _, _, component_text in Read_Detail_Component_State(driver):
        match = re.search(r"(?:^|-)\s*(\d+)\s*$", component_text)
        if match:
            class_numbers.add(match.group(1))
    if not class_numbers:
        raise ValueError(
            "detail grid loaded but contained no parseable class numbers"
        )
    return class_numbers


def Format_Number_Set(class_numbers: set[str]) -> str:
    """Format a stable comma-separated set, or ``(none)`` when empty."""
    return ", ".join(sorted(class_numbers)) if class_numbers else "(none)"


def Build_Class_Issue_Rows(
    course: Course,
    class_numbers: set[str],
    issue: str,
    reason: str,
    returned_class_numbers: set[str] | None = None,
) -> list[dict[str, str]]:
    """Build concise CSV issue rows for specified class numbers.

    Args:
        course: Course supplying SUBJECT and CATALOG_NBR.
        class_numbers: Missing or unverified CLASS_NBR values.
        issue: Short machine-readable category such as MISSING_FROM_FLUID.
        reason: Readable explanation without embedded class-number lists.
        returned_class_numbers: Optional class numbers found in Fluid to place
            in the dedicated RETURNED_CLASS_NUMBERS column.

    Returns:
        One dictionary per unique class number containing only the six
        ISSUE_CSV_COLUMNS fields; numbers are emitted in stable sorted order.

    Failure behavior:
        Empty class_numbers returns an empty list. Invalid non-string values
        fail through sorting or dictionary construction rather than producing
        a malformed CSV row.
    """
    return [
        {
            "SUBJECT": course.Get_Subject(),
            "CATALOG_NBR": course.Get_Course_Number(),
            "CLASS_NBR": class_number,
            "ISSUE": issue,
            "RETURNED_CLASS_NUMBERS": (
                Format_Number_Set(returned_class_numbers)
                if returned_class_numbers else ""
            ),
            "REASON": reason,
        }
        for class_number in sorted(class_numbers)
    ]


def Summarize_Exception(exc: Exception, maximum_length: int = 240) -> str:
    """Create a readable one-line exception description without a stack trace.

    Args:
        exc: Exception raised during browser startup or a course search.
        maximum_length: Maximum length of the returned description.

    Returns:
        Exception type plus the first nonblank message line, truncated with an
        ellipsis when needed. Selenium's embedded driver stack is excluded.

    Failure behavior:
        An exception with no readable message returns only its type. Values
        below four for maximum_length can produce a string longer than the
        requested limit because the function preserves a meaningful prefix.
    """
    message_line = next(
        (line.strip() for line in str(exc).splitlines() if line.strip()),
        "",
    )
    if message_line.startswith("Message:"):
        message_line = message_line.removeprefix("Message:").strip()
    summary = type(exc).__name__
    if message_line:
        summary += ": " + message_line
    if len(summary) > maximum_length:
        summary = summary[:maximum_length - 3].rstrip() + "..."
    return summary


def Search_for_Courses(classes: dict[str, list[Course]], result_queue: Queue,
                       issue_queue: Queue, database: str,
                       worker_number: int, ready_queue: Queue,
                       start_event: Event) -> None:
    """Run one independently authenticated Fluid search worker.

    classes holds this worker's courses; result_queue receives separate clean
    and diagnostic text batches while issue_queue receives concise CSV rows.
    database chooses the login URL, worker_number labels messages, ready_queue
    reports startup, and start_event releases all prepared browsers together.

    Each exact result is opened and all unique detail CLASS_NBR values are
    compared with the CSV set. Per-course failures print immediately, retain a
    full traceback only in the diagnostic batch, mark that course's classes
    unverified, and do not stop later courses. Startup failures notify the
    parent. Chrome and both output queues are finalized even when the worker
    fails.
    """
    driver = None
    startup_reported = False
    diagnostic_lines: list[str] = []
    summary_lines: list[str] = []
    issue_rows: list[dict[str, str]] = []
    try:
        options = Options()
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_argument("--log-level=3")
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(PAGE_WAIT_SECONDS)
        driver.get(login_pages[database])
        ready_queue.put((worker_number, ""))
        startup_reported = True
        start_event.wait()

        initial_url = driver.current_url
        if not driver.find_elements(By.ID, "PTS_KEYWORDS3"):
            raise RuntimeError(
                "browser is not on the Fluid Class Search starting page"
            )

        for subject, courses in classes.items():
            for course in courses:
                current_search = f"{subject} {course.Get_Course_Number()}"
                expected = course.Get_Class_Numbers()
                try:
                    search_field = driver.find_element(By.ID, "PTS_KEYWORDS3")
                    search_field.clear()
                    search_field.send_keys(current_search + Keys.ENTER)

                    result_text = " ".join(
                        element.text.strip()
                        for element in driver.find_elements(
                            By.CSS_SELECTOR, RESULT_MESSAGE_SELECTOR
                        ) if element.text.strip()
                    )
                    if "No Courses available" in result_text:
                        reason = "No Courses available for the selected filters"
                        message = (
                            f"{current_search}: Expected {len(expected)}; "
                            f"missing {len(expected)}. "
                            f"{reason}. Expected class numbers: "
                            f"{Format_Number_Set(expected)}.\n"
                        )
                        diagnostic_lines.append(message)
                        summary_lines.append(message)
                        issue_rows.extend(
                            Build_Class_Issue_Rows(
                                course, expected, "MISSING_FROM_FLUID", reason
                            )
                        )
                    else:
                        advertised_count = Extract_Advertised_Option_Count(driver)
                        try:
                            result_title = Find_Exact_Result_Title(
                                driver, current_search
                            )
                        except NoSuchElementException:
                            index_time = driver.find_elements(
                                By.ID, "PTS_SRCH_PTS_INDEXTIME"
                            )
                            if index_time and "No results" in index_time[0].text:
                                reason = index_time[0].text.split(".")[0]
                                message = (
                                    f"{current_search}: Expected "
                                    f"{len(expected)}; missing "
                                    f"{len(expected)}. "
                                    f"{reason}. Expected class numbers: "
                                    f"{Format_Number_Set(expected)}.\n"
                                )
                                diagnostic_lines.append(message)
                                summary_lines.append(message)
                                issue_rows.extend(
                                    Build_Class_Issue_Rows(
                                        course,
                                        expected,
                                        "MISSING_FROM_FLUID",
                                        reason,
                                    )
                                )
                                result_title = None
                            else:
                                raise

                        if result_title is not None:
                            result_title.click()
                            actual = Extract_Detail_Class_Numbers(driver)
                            missing = expected - actual
                            # A set avoids double-counting components repeated
                            # in the HTML or across option rows.
                            if missing:
                                option_count = (
                                    str(advertised_count)
                                    if advertised_count is not None else "unknown"
                                )
                                message = (
                                    f"{current_search}: Expected {len(expected)}; "
                                    f"missing {len(missing)}. Expected class "
                                    f"numbers: {Format_Number_Set(expected)}; "
                                    f"Fluid class numbers across {option_count} "
                                    f"advertised option(s): "
                                    f"{Format_Number_Set(actual)}; missing: "
                                    f"{Format_Number_Set(missing)}.\n"
                                )
                                diagnostic_lines.append(message)
                                summary_lines.append(message)
                                reason = (
                                    "CLASS_NBR was not returned by Fluid "
                                    "Class Search detail"
                                )
                                issue_rows.extend(
                                    Build_Class_Issue_Rows(
                                        course,
                                        missing,
                                        "MISSING_FROM_FLUID",
                                        reason,
                                        actual,
                                    )
                                )
                except Exception as exc:
                    short_reason = Summarize_Exception(exc)
                    detailed_reason = f"{type(exc).__name__}: {exc}"
                    trace = traceback.format_exc()
                    print(
                        f"Worker {worker_number} ERROR searching {current_search}: "
                        f"{short_reason} (URL: {driver.current_url})",
                        file=sys.stderr, flush=True,
                    )
                    diagnostic_lines.append(
                        f"{current_search}: Expected {len(expected)}; missing "
                        f"unknown. Search error: "
                        f"{detailed_reason}.\n{trace}\n"
                    )
                    summary_lines.append(
                        f"{current_search}: Expected {len(expected)}; missing "
                        f"unknown. Search could "
                        f"not be completed; {short_reason}. Expected class numbers: "
                        f"{Format_Number_Set(expected)}.\n"
                    )
                    issue_rows.extend(Build_Class_Issue_Rows(
                        course,
                        expected,
                        "UNVERIFIED",
                        "Search could not verify CLASS_NBR: " + short_reason,
                    ))
                finally:
                    try:
                        driver.get(initial_url)
                    except Exception as exc:
                        print(
                            f"Worker {worker_number} ERROR returning to Fluid "
                            f"Class Search: {type(exc).__name__}: {exc}",
                            file=sys.stderr, flush=True,
                        )
                    time.sleep(SEARCH_PAUSE_SECONDS)

    except Exception as exc:
        exception_summary = Summarize_Exception(exc)
        short_reason = f"Worker {worker_number} failed: {exception_summary}"
        detailed_reason = (
            f"Worker {worker_number} failed: {type(exc).__name__}: {exc}"
        )
        trace = traceback.format_exc()
        if not startup_reported:
            ready_queue.put((worker_number, short_reason))
            startup_reported = True
        print(short_reason, file=sys.stderr, flush=True)
        for subject, courses in classes.items():
            for course in courses:
                current_search = f"{subject} {course.Get_Course_Number()}"
                expected = course.Get_Class_Numbers()
                diagnostic_lines.append(
                    f"{current_search}: Expected {len(expected)}; missing "
                    f"unknown. Search error: "
                    f"{detailed_reason}.\n{trace}\n"
                )
                summary_lines.append(
                    f"{current_search}: Expected {len(expected)}; missing "
                    f"unknown. Search could not "
                    f"be completed; {short_reason}. Expected class numbers: "
                    f"{Format_Number_Set(expected)}.\n"
                )
                issue_rows.extend(Build_Class_Issue_Rows(
                    course,
                    expected,
                    "UNVERIFIED",
                    "Worker could not verify CLASS_NBR: " + short_reason,
                ))
    finally:
        result_queue.put((diagnostic_lines, summary_lines))
        issue_queue.put(issue_rows)
        if driver is not None:
            driver.quit()


def Split_Dictionary(classes: dict[str, list[Course]],
                     classes_p: list[dict[str, list[Course]]],
                     process_count: int) -> None:
    """Distribute individual courses round-robin across worker dictionaries.

    classes_p is modified in place and process_count must be positive. CLI
    validation prevents zero; malformed iterables raise normal Python errors.
    """
    classes_p.extend({} for _ in range(process_count))
    index = 0
    for subject, courses in classes.items():
        for course in courses:
            worker = classes_p[index % process_count]
            worker.setdefault(subject, []).append(course)
            index += 1


def StartProcesses(database: str, classes: dict[str, list[Course]],
                   process_count: int,
                   ) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Open browsers and return diagnostic, summary, and CSV issue results.

    database selects the login page, classes supplies filtered work, and
    process_count sets independent sessions. Returns diagnostic text lines,
    clean summary lines, and concise class issue dictionaries. The function
    waits indefinitely for browser preparation and one Enter press. Startup
    failure raises RuntimeError; parent interruption terminates and joins
    children. Individual course failures do not stop peer workers.
    """
    diagnostic_lines: list[str] = []
    summary_lines: list[str] = []
    issue_rows: list[dict[str, str]] = []
    worker_classes: list[dict[str, list[Course]]] = []
    Split_Dictionary(classes, worker_classes, process_count)
    processes: list[Process] = []
    result_batch_count = 0
    issue_batch_count = 0
    result_queue = Queue()
    issue_queue = Queue()
    ready_queue = Queue()
    start_event = Event()

    print(
        f"Preparing {process_count} independent Chrome sessions. Each browser "
        "uses its own temporary profile and PeopleSoft session."
    )
    try:
        for worker_number, assigned in enumerate(worker_classes, start=1):
            process = Process(
                target=Search_for_Courses,
                args=(assigned, result_queue, issue_queue, database,
                      worker_number, ready_queue, start_event),
            )
            process.start()
            processes.append(process)

        # No timeout: the operator decides how long authentication takes.
        for _ in processes:
            worker_number, error = ready_queue.get()
            if error:
                raise RuntimeError(error)
            print(f"  Worker {worker_number}/{process_count} browser opened.")
        input(
            f"\nSign in and navigate all {process_count} browsers to the Fluid "
            "Class Search starting page.\nPress Enter once when every window "
            "is ready... "
        )
        start_event.set()

        # Continual draining prevents a full multiprocessing pipe from
        # deadlocking a worker as it exits.
        while any(process.is_alive() for process in processes):
            try:
                worker_diagnostics, worker_summaries = result_queue.get(
                    timeout=0.25
                )
                diagnostic_lines.extend(worker_diagnostics)
                summary_lines.extend(worker_summaries)
                result_batch_count += 1
            except Empty:
                pass
            while True:
                try:
                    issue_rows.extend(issue_queue.get_nowait())
                    issue_batch_count += 1
                except Empty:
                    break
        for process in processes:
            process.join()
    except BaseException:
        start_event.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join()
        raise

    # Every worker puts exactly one batch on each queue in its finally block.
    # Count those batches instead of trusting Queue.empty/get_nowait after
    # process exit, because multiprocessing feeder threads can make those
    # methods briefly report an empty queue while a final batch is in transit.
    while result_batch_count < len(processes):
        worker_diagnostics, worker_summaries = result_queue.get(
            timeout=PAGE_WAIT_SECONDS
        )
        diagnostic_lines.extend(worker_diagnostics)
        summary_lines.extend(worker_summaries)
        result_batch_count += 1
    while issue_batch_count < len(processes):
        issue_rows.extend(issue_queue.get(timeout=PAGE_WAIT_SECONDS))
        issue_batch_count += 1
    return diagnostic_lines, summary_lines, issue_rows


def Deduplicate_Issue_Rows(issue_rows: list[dict[str, str]],
                           ) -> list[dict[str, str]]:
    """Return class issue rows once each, preserving first-seen order.

    Args:
        issue_rows: Dictionaries containing every ISSUE_CSV_COLUMNS field.

    Returns:
        Rows deduplicated by subject, catalog, class number, issue, and reason.

    Failure behavior:
        Missing required keys raise KeyError instead of silently producing an
        incomplete or ambiguous report.
    """
    output: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in issue_rows:
        key = tuple(row[column] for column in ISSUE_CSV_COLUMNS)
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def Write_Issue_Csv(output_path: str,
                    issue_rows: list[dict[str, str]]) -> int:
    """Write concise class issues, or retain no CSV when there are none.

    Args:
        output_path: Explicit destination supplied through ``--csv-output``.
        issue_rows: Missing or unverified class-number rows.

    Returns:
        Number of unique rows written, or zero when no file is retained.

    Failure behavior:
        If there are no rows, an old output_path is removed so stale results
        cannot be mistaken for the current run. Filesystem, missing-key, and
        csv.DictWriter errors propagate to the caller.
    """
    unique_rows = Deduplicate_Issue_Rows(issue_rows)
    if not unique_rows:
        if os.path.exists(output_path):
            os.remove(output_path)
        return 0
    with open(output_path, "w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=ISSUE_CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(unique_rows)
    return len(unique_rows)


def Positive_Integer(value: str) -> int:
    """Convert an argparse value to a strictly positive integer.

    Args:
        value: Text supplied to ``--process-count``.

    Returns:
        The parsed integer when it is greater than zero.

    Failure behavior:
        Raises argparse.ArgumentTypeError for nonintegers, zero, or negative
        values. argparse catches that exception, prints usage, and exits with
        status 2 before the script opens a browser.
    """
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "must be a positive integer"
        ) from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def Parse_Arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate the script's required named command-line options.

    Args:
        arguments: Option tokens without the executable/script name. None makes
            argparse read the real command line from ``sys.argv[1:]``.

    Returns:
        A namespace containing every explicit input/output path, environment,
        and process_count.

    Failure behavior:
        argparse prints a usage/error message and raises SystemExit(2) when a
        required option is absent or invalid. ``--help`` raises SystemExit(0)
        after printing the generated help text.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Verify explicitly selected CSV class numbers against "
            "PeopleSoft Fluid Class Search."
        )
    )
    parser.add_argument(
        "--environment",
        required=True,
        type=str.upper,
        choices=sorted(login_pages),
        help="PeopleSoft environment: TST, DEV, or PRD.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--csv-path",
        help=(
            "Primary CSV source containing SUBJECT, CATALOG_NBR, and "
            "CLASS_NBR. Cannot be combined with --course-list."
        ),
    )
    source_group.add_argument(
        "--course-list",
        help=(
            "Standalone source replacing --csv-path: either a CSV containing "
            "SUBJECT, CATALOG_NBR, and CLASS_NBR, or a clean-summary text "
            "report containing explicit expected class-number lists."
        ),
    )
    parser.add_argument(
        "--diagnostic-output",
        required=True,
        help="Text output containing full exception details and tracebacks.",
    )
    parser.add_argument(
        "--summary-output",
        required=True,
        help="Clean one-line-per-issue text output without stack traces.",
    )
    parser.add_argument(
        "--csv-output",
        required=True,
        help=(
            "CSV output containing only incorrect or unverified class-number "
            "fields; no file is retained when there are no issue rows."
        ),
    )
    parser.add_argument(
        "--process-count",
        required=True,
        type=Positive_Integer,
        help="Number of independent Chrome sessions to open.",
    )
    options = parser.parse_args(arguments)

    # The three reports must remain separate, and no report may overwrite an
    # explicit input file. normcase/abspath also catches differently spelled
    # relative paths that resolve to the same Windows file.
    output_paths = {
        os.path.normcase(os.path.abspath(options.diagnostic_output)),
        os.path.normcase(os.path.abspath(options.summary_output)),
        os.path.normcase(os.path.abspath(options.csv_output)),
    }
    if len(output_paths) != 3:
        parser.error(
            "--diagnostic-output, --summary-output, and --csv-output must "
            "name three different files"
        )
    source_path = options.csv_path or options.course_list
    input_paths = {
        os.path.normcase(os.path.abspath(source_path)),
    }
    if output_paths & input_paths:
        parser.error("output files cannot overwrite the selected input source")
    return options


def Main(arguments: list[str] | None = None) -> int:
    """Parse input, run selected courses, and write conditional reports.

    Args:
        arguments: Optional named-option tokens without the script name. None
            reads the actual command line through argparse.

    Returns:
        Zero after a completed run or two for readable source-data errors.

    Failure behavior:
        Parse_Arguments handles invalid command options with SystemExit.
        Browser/runtime failures retain normal tracebacks so an interrupted
        run cannot be mistaken for successful completion.
    """
    options = Parse_Arguments(arguments)
    database = options.environment
    csv_path = options.csv_path
    course_list_path = options.course_list
    diagnostic_output_path = options.diagnostic_output
    summary_output_path = options.summary_output
    csv_output_path = options.csv_output
    process_count = options.process_count

    try:
        # Exactly one standalone source is supplied. CSV course lists use the
        # same complete row loader as --csv-path; text summaries carry their
        # own expected class-number lists.
        if csv_path:
            classes, _ = Load_Courses_From_Csv(csv_path)
            source_path = csv_path
        elif os.path.splitext(course_list_path)[1].lower() == ".csv":
            classes, _ = Load_Courses_From_Csv(course_list_path)
            source_path = course_list_path
        else:
            classes = Load_Courses_From_Text_List(course_list_path)
            source_path = course_list_path
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Input error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    loaded_keys = {
        (subject, course.Get_Course_Number())
        for subject, courses in classes.items() for course in courses
    }
    print(f"Loaded {len(loaded_keys)} course(s) from {source_path}.")
    if classes:
        diagnostic_lines, summary_lines, issue_rows = StartProcesses(
            database, classes, process_count
        )
    else:
        diagnostic_lines, summary_lines, issue_rows = [], [], []

    with open(
        diagnostic_output_path, "w", encoding="utf-8", newline=""
    ) as output:
        output.writelines(diagnostic_lines)
    with open(
        summary_output_path, "w", encoding="utf-8", newline=""
    ) as output:
        output.writelines(summary_lines)
    issue_count = Write_Issue_Csv(csv_output_path, issue_rows)

    print(
        f"Diagnostic results: {diagnostic_output_path} "
        f"({len(diagnostic_lines)} issue(s))"
    )
    print(
        f"Clean summary: {summary_output_path} "
        f"({len(summary_lines)} issue(s))"
    )
    if issue_count:
        print(f"Class issues: {csv_output_path} ({issue_count} row(s))")
    else:
        print("Class issues: none; no CSV was saved.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
