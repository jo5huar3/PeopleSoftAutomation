"""Execute Query Masking Authorized Role entries from a grouped CSV file."""
"""
# Required actions.
# Hit plus button
# <span class="ps-button-wrapper" title="Add a New Value"><a id="PTS_ADDMODE_BTN" class="ps-button" role="button" aria-pressed="false" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'PTS_ADDMODE_BTN');"><img src="/cs/sa92dev/cache/cache082826a/PT_ROW_ADD_32_302.SVG" id="PTS_ADDMODE_BTN$IMG" class="ps-img" alt=""><span class="ps-text">Add</span></a></span>

# Input role name and force the sign on PC to run UHS_CS_DEVINQ
# <input type="text" id="PTS_FILTER_NOOP_PTS_PROMPT2$0" class="ps-edit" sfn="ROLENAME" maxlength="30" pt_fn="ROLENAME" pt_flbl="Role Name" onfocus="javascript:onSmartPromptDataChange(event, this, '', 'onfocus', 'submitAction_win0');" onfocusout="javascript:onSmartPromptDataChange(event, this, '', 'onfocusout');" rn="PTS_FILTER_NOOP" fn="PTS_PROMPT2" pt="PSROLEDEFN" value="" listhdr0="Role Name" listhdr1="Role Type" listhdr2="Role-Query Name" onclick="javascript:cancelBubble(event);" onchange="addchg_win0(this);oChange_win0=this;/*8400,0*/" psnchg="0" validatedflag="true">

# Push the add button 
# <div class="ps_box-button psc_primary pts_padding-top025em" id="win0srchdivPTS_SRCH_BTN"><span id="PTS_SRCH_BTN$span" class="ps-button-wrapper"><a id="PTS_SRCH_BTN" class="ps-button" accesskey="1" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'PTS_SRCH_BTN');" role="button" title="Add" aria-label="Add" ptlinktgt="pt_peoplecode">Add</a></span><!-- PTS_SRCH_BTN --></div>



# Will get transfered to another page where we will add several hundress rows.
# Row: Record Name, Field Name, Access Code. Access Code should be set to Authorized
# ACAD_SUBPL_WHIF, EMPLID, Authorized

# Add record name ADM_T189_PER_EC
# <input type="text" id="RECNAME$0" class="ps-edit" pt_fn="RECNAME" pt_flbl="Record (Table) Name" onfocus="javascript:onSmartPromptDataChange(event, this, '', 'onfocus', 'submitAction_win0');" onfocusout="javascript:onSmartPromptDataChange(event, this, '', 'onfocusout');" rn="EODP_ROLRECFLD" fn="RECNAME" deferred="1" pt="EODP_RECORDLIST" value="" listhdr0="Record (Table) Name" listhdr1="Record Description" maxlength="15" onclick="javascript:cancelBubble(event);" aria-required="true" validatedflag="true">

# Add field name SSN
# <input type="text" id="EODP_ROLRECFLD_FIELDNAME$0" class="ps-edit" pt_fn="FIELDNAME" pt_flbl="Field Name" onfocus="javascript:onSmartPromptDataChange(event, this, '', 'onfocus', 'submitAction_win0');" onfocusout="javascript:onSmartPromptDataChange(event, this, '', 'onfocusout');" rn="EODP_ROLRECFLD" fn="FIELDNAME" deferred="1" dependson0="RECNAME" pt="EODP_FIELDSLIST" value="" skipfn0="RECNAME" listhdr0="Field Name" maxlength="18" onclick="javascript:cancelBubble(event);" aria-required="true">

# Set access code to Authorized
# <select id="EODP_ROLRECFLD_EODP_ACCESS_CD$0" class="ps-dropdown" size="1" onclick="javascript:cancelBubble(event);" fn="EODP_ACCESS_CD" onchange="if (typeof onSmartSelectDataChange === 'function') { onSmartSelectDataChange(this); }" aria-required="true">
# <option value="" selected="selected" aria-invalid="true"> 
# </option><option value="Y">Authorized</option>
# <option value="N">Not Authorized</option>
# </select>

# Hit the plus button to insert another row.
# <span class="ps-button-wrapper" title="Insert Row"><a id="EODP_RRF_WRK_EODP_INSERT_ROW" class="ps-button" role="button" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'EODP_RRF_WRK_EODP_INSERT_ROW');"><img src="/cs/sa92dev/cache/cache082826a/PT_ROW_ADD_32_302.SVG" id="EODP_RRF_WRK_EODP_INSERT_ROW$IMG" class="ps-img" alt="Insert Row"></a></span>

# Add another row with the values ACAD_PLAN EMPLID 

# Hit the save button
# <div class="ps_box-button psc_primary " id="win0divEODP_RRF_WRK_SAVE_PB"><span id="EODP_RRF_WRK_SAVE_PB$span" class="ps-button-wrapper"><a id="EODP_RRF_WRK_SAVE_PB" class="ps-button" role="button" ptlinktgt="pt_peoplecode" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'EODP_RRF_WRK_SAVE_PB');" aria-label="Save" accesskey="S"><abbr class="PTUNDERLINE">S</abbr>ave</a></span><!-- EODP_RRF_WRK_SAVE_PB --></div>


# After hitting save there is an element that displays. Below is me manually setting it to show.
# <div class="psc_processing psc_hidden" id="WAIT_win0" style="visibility: visible; display: block; right: 0px;"><img id="processing" src="/cs/sa92dev/cache/cache082826a/PT_PROCESSING_FMODE_1.gif" alt="Processing... please wait" title="Processing... please wait"></div>

# However when the load is complete it reverts to this state.
# <div class="psc_processing psc_hidden" id="WAIT_win0" style="visibility: hidden; display: none; right: 0px;"><img id="processing" src="/cs/sa92dev/cache/cache082826a/PT_PROCESSING_FMODE_1.gif" alt="Processing... please wait" title="Processing... please wait"></div>

# When the load is complete this indiviual addittion is complete.

# Input CSVs will contain "ROLENAME","RECNAME","FIELDNAME"
# Group rows by role, add all of that role's record/field pairs, and save once.
"""


import argparse
import csv
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

FRAME_IDS = ("ptifrmtgtframe", "main_target_win0")
WAIT_SECONDS = 20
POSTBACK_PAUSE_SECONDS = 0.35
POST_SAVE_MESSAGE_PAUSE_SECONDS = 1.0
DEFAULT_DEBUG_PORT = 9222
ROW_ZERO_SUFFIX = "0"
REQUIRED_CSV_COLUMNS = ("ROLENAME", "RECNAME", "FIELDNAME")


def switch_to_people_soft(driver):
    """Enter the first supported PeopleSoft content frame, when present.

    Args:
        driver: An active Selenium WebDriver positioned on a PeopleSoft page.

    Returns:
        None. The driver's browsing context is left in the matching frame, or
        at the document root when neither known frame exists.

    Raises:
        WebDriverException: Selenium cannot inspect or switch the page context,
        for example because the browser closed or the frame became stale.
    """

    driver.switch_to.default_content()
    for frame_id in FRAME_IDS:
        frames = driver.find_elements(By.ID, frame_id)
        if frames:
            driver.switch_to.frame(frames[0])
            return


def visible_by_id(driver, element_id):
    """Find the first visible element with an exact HTML ID.

    Args:
        driver: An active Selenium WebDriver on a PeopleSoft page.
        element_id: The non-empty string ID of the element to locate.

    Returns:
        The first displayed WebElement with ``element_id``, or ``None`` when
        no matching visible element exists.

    Raises:
        WebDriverException: Selenium cannot switch frames or inspect elements.
    """

    switch_to_people_soft(driver)
    for element in driver.find_elements(By.ID, element_id):
        if element.is_displayed():
            return element
    return None


def raise_for_people_soft_error(driver):
    """Dismiss and raise any visible PeopleSoft message dialog as an error.

    Args:
        driver: An active Selenium WebDriver after a PeopleSoft postback.

    Returns:
        None when no visible message text exists.

    Raises:
        RuntimeError: A visible PeopleSoft dialog exists. Its short message,
        message number, and long message are included in the exception after
        the OK button is clicked.
        WebDriverException: Selenium cannot inspect or dismiss the dialog.
    """

    switch_to_people_soft(driver)
    messages = []
    for element_id in ("shortmsg", "msgnum", "longmsg"):
        for element in driver.find_elements(By.ID, element_id):
            text = element.text.strip()
            if element.is_displayed() and text and text not in messages:
                messages.append(text)

    if not messages:
        return

    for button in driver.find_elements(By.ID, "#ICOK"):
        if button.is_displayed():
            driver.execute_script("arguments[0].click();", button)
            break
    raise RuntimeError("PeopleSoft error: " + " ".join(messages))


def wait_for_processing(driver, wait):
    """Wait until PeopleSoft's processing indicator is no longer displayed.

    Args:
        driver: An active Selenium WebDriver on the page being submitted.
        wait: A configured Selenium WebDriverWait that controls the timeout.

    Returns:
        None after every visible ``WAIT_win0`` indicator has disappeared.

    Raises:
        TimeoutException: The processing indicator remains visible longer than
        the timeout configured on ``wait``.
        WebDriverException: Selenium cannot inspect the page or switch frames.
    """

    # WAIT_win0 starts hidden. Give the postback time to make it visible before
    # testing for its final hidden state.
    time.sleep(POSTBACK_PAUSE_SECONDS)

    def processing_finished(_driver):
        """Report whether all PeopleSoft processing indicators are hidden.

        Args:
            _driver: The WebDriver supplied by WebDriverWait; unused because
            the enclosing function's ``driver`` is the intended browser.

        Returns:
            ``True`` when no displayed processing indicator exists; otherwise
            ``False`` so WebDriverWait continues polling.

        Raises:
            WebDriverException: Selenium cannot switch frames or query the
            processing indicators. Exceptions configured as ignored on the
            enclosing wait are retried; other exceptions end the wait.
        """

        switch_to_people_soft(driver)
        indicators = driver.find_elements(By.ID, "WAIT_win0")
        return not any(indicator.is_displayed() for indicator in indicators)

    wait.until(processing_finished)
    raise_for_people_soft_error(driver)


def click(driver, element):
    """Click a Selenium element through JavaScript.

    Args:
        driver: The active Selenium WebDriver that owns ``element``.
        element: A Selenium WebElement that should receive the click.

    Returns:
        None.

    Raises:
        JavascriptException: The browser cannot execute the click script.
        StaleElementReferenceException: ``element`` is no longer attached to
        the current page.
        WebDriverException: The browser session is unavailable.
    """

    driver.execute_script("arguments[0].click();", element)


def set_text(driver, wait, element_id, value):
    """Replace a visible input's text and wait for its tab-triggered postback.

    Args:
        driver: An active Selenium WebDriver on a PeopleSoft page.
        wait: A configured Selenium WebDriverWait used to find the input and
            wait for PeopleSoft processing.
        element_id: The exact HTML ID of the target text input.
        value: Text, or another Selenium-supported key value, to enter.

    Returns:
        None after the value is entered, focus leaves the input, and the
        resulting PeopleSoft processing finishes.

    Raises:
        TimeoutException: The input never becomes visible or processing does
        not finish before ``wait`` expires.
        InvalidElementStateException: The located input cannot be edited.
        WebDriverException: Any browser interaction or frame operation fails.
    """

    element = wait.until(lambda _driver: visible_by_id(driver, element_id))
    element.click()
    element.send_keys(Keys.CONTROL, "a")
    element.send_keys(value)
    element.send_keys(Keys.TAB)
    wait_for_processing(driver, wait)


def find_role_result(driver, role_name):
    """Find the first displayed results-grid row for an exact role name.

    Args:
        driver: An active Selenium WebDriver on the role search page.
        role_name: The role-name string to match case-insensitively after
            trimming whitespace from the displayed grid value.

    Returns:
        The matching row WebElement, or ``None`` when no visible exact match
        exists.

    Raises:
        NoSuchElementException: A matching role cell is not contained in a
        table row as expected by the PeopleSoft markup.
        WebDriverException: Selenium cannot switch frames or inspect the grid.
    """

    switch_to_people_soft(driver)
    for role_cell in driver.find_elements(By.CSS_SELECTOR, "span[id^='PTS_FLD1$']"):
        if not role_cell.is_displayed():
            continue
        if role_cell.text.strip().casefold() == role_name.casefold():
            return role_cell.find_element(By.XPATH, "./ancestor::tr[1]")
    return None


def add_new_role(driver, wait, role_name):
    """Create and open a Query Masking Authorized Role entry.

    Args:
        driver: An active Selenium WebDriver on the role search page.
        wait: A configured Selenium WebDriverWait for controls and postbacks.
        role_name: The role-name string to enter on the add-new-value form.

    Returns:
        None. On success, the browser is left on the new role's detail page.

    Raises:
        TimeoutException: A required control does not become visible or a
        PeopleSoft postback does not finish within the configured timeout.
        InvalidElementStateException: The role-name field cannot be edited.
        WebDriverException: A click, key entry, or frame operation fails.
    """

    add_new = wait.until(lambda _driver: visible_by_id(driver, "PTS_ADDMODE_BTN"))
    click(driver, add_new)
    wait_for_processing(driver, wait)

    set_text(driver, wait, "PTS_FILTER_NOOP_PTS_PROMPT2$0", role_name)

    add = wait.until(lambda _driver: visible_by_id(driver, "PTS_SRCH_BTN"))
    click(driver, add)
    wait_for_processing(driver, wait)


def open_role(driver, wait, role_name):
    """Open an existing exact-match role, or create it when none is listed.

    Args:
        driver: An active Selenium WebDriver on the role search page.
        wait: A configured Selenium WebDriverWait for postbacks and controls.
        role_name: The role-name string to find or create.

    Returns:
        None. On success, the browser is left on the role detail page.

    Raises:
        TimeoutException: Opening or creating the role does not finish within
        the configured timeout.
        NoSuchElementException: Matching result markup lacks its expected row.
        WebDriverException: Selenium cannot inspect or interact with the page.
    """

    # The results grid can contain several rows for the same role. Clicking any
    # exact match opens that role's detail page.
    role_row = find_role_result(driver, role_name)
    if role_row is not None:
        click(driver, role_row)
        wait_for_processing(driver, wait)
        return

    add_new_role(driver, wait, role_name)


def row_inputs(driver, prefix):
    """Collect visible grid inputs whose IDs end in numeric row suffixes.

    Args:
        driver: An active Selenium WebDriver on a role detail page.
        prefix: The exact string expected before the numeric portion of each
            input ID, such as ``"RECNAME$"``.

    Returns:
        A dictionary mapping each numeric suffix string to its visible
        WebElement. Missing, hidden, and nonconforming inputs are omitted.

    Raises:
        WebDriverException: Selenium cannot switch frames, query inputs, or
        read an input's ID.
    """

    switch_to_people_soft(driver)
    result = {}
    for element in driver.find_elements(By.CSS_SELECTOR, f"input[id^='{prefix}']"):
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", element.get_attribute("id"))
        if match and element.is_displayed():
            result[match.group(1)] = element
    return result


def existing_record_field_pairs(driver):
    """Collect the record/field keys already present in the current role grid.

    Args:
        driver: An active Selenium WebDriver on a role detail page whose grid
            rows are loaded in the DOM.

    Returns:
        A set of case-folded ``(record_name, field_name)`` tuples. Blank or
        incomplete rows are omitted. Case-folding matches PeopleSoft's
        case-insensitive duplicate-key behavior.

    Raises:
        WebDriverException: Selenium cannot inspect the record or field inputs.
    """

    records = row_inputs(driver, "RECNAME$")
    fields = row_inputs(driver, "EODP_ROLRECFLD_FIELDNAME$")
    pairs = set()
    for suffix, record in records.items():
        field = fields.get(suffix)
        if field is None:
            continue

        record_name = (record.get_attribute("value") or "").strip()
        field_name = (field.get_attribute("value") or "").strip()
        if record_name and field_name:
            pairs.add((record_name.casefold(), field_name.casefold()))
    return pairs


def blank_row_suffix(driver):
    """Report whether PeopleSoft grid row zero is enabled and blank.

    Args:
        driver: An active Selenium WebDriver on a role detail page.

    Returns:
        ``"0"`` when the visible record input at row zero is enabled and
        blank, or ``None`` when row zero is absent, disabled, or populated.

    Raises:
        WebDriverException: Selenium cannot inspect the grid or an input's
        enabled state/value.
    """

    record = row_inputs(driver, "RECNAME$").get(ROW_ZERO_SUFFIX)
    if (
        record is not None
        and record.is_enabled()
        and not (record.get_attribute("value") or "").strip()
    ):
        return ROW_ZERO_SUFFIX
    return None


def get_blank_row(driver, wait):
    """Return blank row zero, inserting a new row zero when necessary.

    Args:
        driver: An active Selenium WebDriver on a role detail page.
        wait: A configured Selenium WebDriverWait for controls and postbacks.

    Returns:
        Always ``"0"`` after its visible record input is enabled and blank.
        PeopleSoft inserts new rows at position zero and shifts older entries.

    Raises:
        TimeoutException: The insert control, postback completion, or newly
        blank row is not observed within the configured timeout.
        WebDriverException: Selenium cannot inspect or interact with the grid.
    """

    suffix = blank_row_suffix(driver)
    if suffix is not None:
        return suffix

    insert_row = wait.until(
        lambda _driver: visible_by_id(driver, "EODP_RRF_WRK_EODP_INSERT_ROW")
    )
    click(driver, insert_row)
    wait_for_processing(driver, wait)
    return wait.until(lambda _driver: blank_row_suffix(driver))


def set_row_text(driver, wait, prefix, suffix, value):
    """Replace text in one PeopleSoft grid input and await its postback.

    Args:
        driver: An active Selenium WebDriver on a role detail page.
        wait: A configured Selenium WebDriverWait for the input and postback.
        prefix: The grid input ID prefix, such as ``"RECNAME$"``.
        suffix: The numeric row suffix returned by ``get_blank_row``.
        value: Text, or another Selenium-supported key value, to enter.

    Returns:
        None after the field loses focus and PeopleSoft processing finishes.

    Raises:
        TimeoutException: The row input is not found or processing does not
        finish within the configured timeout.
        InvalidElementStateException: The grid input cannot be edited.
        WebDriverException: Any browser, frame, or element operation fails.
    """

    def row_element(_driver):
        """Return the requested visible row input for a wait poll.

        Args:
            _driver: The WebDriver supplied by WebDriverWait; unused because
            the enclosing function's ``driver`` is the intended browser.

        Returns:
            The matching WebElement, or ``None`` so WebDriverWait keeps polling.

        Raises:
            WebDriverException: Selenium cannot switch frames or inspect the
            grid. Ignored wait exceptions are retried; others end the wait.
        """

        return row_inputs(driver, prefix).get(suffix)

    element = wait.until(row_element)
    element.click()
    element.send_keys(Keys.CONTROL, "a")
    element.send_keys(value)
    element.send_keys(Keys.TAB)
    wait_for_processing(driver, wait)


def add_authorized_record_field(driver, wait, record_name, field_name):
    """Populate one blank role row and set its access code to Authorized.

    Args:
        driver: An active Selenium WebDriver on a role detail page.
        wait: A configured Selenium WebDriverWait for fields and postbacks.
        record_name: The PeopleSoft record/table name to enter.
        field_name: The PeopleSoft field name to authorize for that record.

    Returns:
        None after the record, field, and ``Authorized`` (value ``Y``) access
        code are entered and all triggered processing finishes.

    Raises:
        TimeoutException: A blank row or required control is unavailable, or
        processing exceeds the configured timeout.
        NoSuchElementException: The access dropdown has no option value ``Y``.
        UnexpectedTagNameException: The access element is not a select control.
        WebDriverException: Selenium cannot inspect or modify the page.
    """

    suffix = get_blank_row(driver, wait)
    set_row_text(driver, wait, "RECNAME$", suffix, record_name)
    set_row_text(driver, wait, "EODP_ROLRECFLD_FIELDNAME$", suffix, field_name)

    access_id = f"EODP_ROLRECFLD_EODP_ACCESS_CD${suffix}"
    access = wait.until(lambda _driver: visible_by_id(driver, access_id))
    Select(access).select_by_value("Y")
    access.send_keys(Keys.TAB)
    wait_for_processing(driver, wait)


def initialize_webdriver(debug_port=None):
    """Create a Chrome WebDriver or attach to a debugging-enabled Chrome.

    Args:
        debug_port: Optional local Chrome DevTools port as an integer (or a
            value with an equivalent string representation). When omitted, a
            new maximized Chrome window is started and the user is prompted to
            sign in and navigate to the required PeopleSoft search page.

    Returns:
        A Selenium Chrome WebDriver with implicit waits disabled.

    Raises:
        WebDriverException: Chrome cannot start or Selenium cannot connect to
        the debugging session, including an invalid or unreachable port.
        EOFError: Interactive input is unavailable while starting a new
        browser session without ``debug_port``.
        KeyboardInterrupt: The user cancels the interactive readiness prompt.
    """

    options = Options()

    if debug_port is not None:
        options.debugger_address = f"localhost:{debug_port}"
    else:
        options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(0)

    if debug_port is None:
        input(
            "\nSign in to PeopleSoft and navigate to the Query Masking "
            "Authorized Roles search page.\n"
            "Come back here and press Enter when the page is ready... "
        )

    return driver


def read_csv_roles(csv_path):
    """Read and validate a CSV, grouping its entries by role name.

    Args:
        csv_path: String or Path for a UTF-8 CSV containing the required
            ``ROLENAME``, ``RECNAME``, and ``FIELDNAME`` columns. Header names
            are matched case-insensitively and surrounding spaces are ignored.

    Returns:
        An insertion-ordered dictionary whose keys are role names and whose
        values are lists of dictionaries with ``record_name`` and
        ``field_name`` keys plus the original ``csv_line`` number. CSV row
        order is retained within each role.

    Raises:
        ValueError: The file cannot be read, has no header/data, omits a
        required column, or contains a partially blank data row. The message
        identifies the file or CSV line responsible for the failure.
    """

    path = Path(csv_path)
    try:
        csv_file = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ValueError(f"Could not open CSV '{path}': {exc}") from exc

    roles = {}
    with csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV '{path}' is empty or has no header row.")

        headers = {
            (header or "").strip().upper(): header for header in reader.fieldnames
        }
        missing = [name for name in REQUIRED_CSV_COLUMNS if name not in headers]
        if missing:
            raise ValueError(
                "Missing required CSV column(s): " + ", ".join(missing)
            )

        for csv_line, raw_row in enumerate(reader, start=2):
            values = {
                name: (raw_row.get(headers[name]) or "").strip()
                for name in REQUIRED_CSV_COLUMNS
            }
            if not any(values.values()):
                continue

            blank = [name for name, value in values.items() if not value]
            if blank:
                raise ValueError(
                    f"CSV line {csv_line} has blank required field(s): "
                    + ", ".join(blank)
                )

            roles.setdefault(values["ROLENAME"], []).append(
                {
                    "csv_line": csv_line,
                    "record_name": values["RECNAME"],
                    "field_name": values["FIELDNAME"],
                }
            )

    if not roles:
        raise ValueError(f"CSV '{path}' contains no data rows.")
    return roles


def write_failure_summary(summary_path, failures):
    """Write only the input rows that the automation could not accomplish.

    Args:
        summary_path: String or Path naming the output CSV. Its parent folder
            is created when necessary.
        failures: Iterable of dictionaries containing ``csv_line``,
            ``role_name``, ``record_name``, ``field_name``, and ``reason``.
            An empty iterable produces a header-only summary file.

    Returns:
        The Path object used for the summary file.

    Raises:
        OSError: The destination directory or summary CSV cannot be written.
    """

    path = Path(summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ("CSV_LINE", "ROLENAME", "RECNAME", "FIELDNAME", "REASON")
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        for failure in failures:
            writer.writerow(
                {
                    "CSV_LINE": failure["csv_line"],
                    "ROLENAME": failure["role_name"],
                    "RECNAME": failure["record_name"],
                    "FIELDNAME": failure["field_name"],
                    "REASON": failure["reason"],
                }
            )
    return path


def execute_role(driver, start_url, role_name, record_fields):
    """Authorize a role's missing entries and describe anything not completed.

    Args:
        driver: An authenticated Selenium WebDriver connected to PeopleSoft.
        start_url: URL of the Query Masking Authorized Roles search page; it is
            reloaded before this role so multiple roles can run in one session.
        role_name: The role-name string to open or create.
        record_fields: A non-empty iterable of dictionaries containing
            ``record_name`` and ``field_name`` strings, normally produced by
            ``read_csv_roles``.

    Returns:
        A dictionary containing ``added``, ``satisfied``, and ``failures``.
        Existing pairs count as satisfied. If adding or saving fails, every
        input row not already present is returned as a failure because the
        role's pending changes were not safely saved.

    Raises:
        KeyboardInterrupt: The operator interrupts the run. Ordinary Selenium,
        PeopleSoft, key, and timeout errors are printed and returned through
        ``failures`` so processing can continue with the next role.
    """

    original_pairs = set()
    try:
        driver.get(start_url)

        wait = WebDriverWait(
            driver,
            WAIT_SECONDS,
            poll_frequency=0.25,
            ignored_exceptions=(StaleElementReferenceException,),
        )

        # Open the role once, add every grouped CSV entry, then save once.
        wait.until(lambda _driver: visible_by_id(driver, "PTS_ADDMODE_BTN"))
        open_role(driver, wait, role_name)
        wait.until(lambda _driver: bool(row_inputs(driver, "RECNAME$")))
        original_pairs = existing_record_field_pairs(driver)
        active_pairs = set(original_pairs)
        added = 0
        satisfied = 0

        for entry in record_fields:
            record_name = entry["record_name"]
            field_name = entry["field_name"]
            pair = (record_name.casefold(), field_name.casefold())
            if pair in active_pairs:
                satisfied += 1
                continue

            add_authorized_record_field(
                driver,
                wait,
                record_name,
                field_name,
            )
            active_pairs.add(pair)
            added += 1

        if added:
            save = wait.until(
                lambda _driver: visible_by_id(driver, "EODP_RRF_WRK_SAVE_PB")
            )
            click(driver, save)
            wait_for_processing(driver, wait)
            # Some deferred-validation messages render shortly after the
            # processing indicator disappears. Give the modal time to mount,
            # then turn it into a recorded failure instead of reporting that
            # this role was successfully saved.
            time.sleep(POST_SAVE_MESSAGE_PAUSE_SECONDS)
            raise_for_people_soft_error(driver)

        return {"added": added, "satisfied": satisfied, "failures": []}

    except Exception as exc:
        reason = f"Role was not saved: {type(exc).__name__}: {exc}"
        print(f"ERROR for role {role_name}: {reason}", file=sys.stderr)
        traceback.print_exc()

        failures = []
        satisfied = 0
        for entry in record_fields:
            pair = (
                entry["record_name"].casefold(),
                entry["field_name"].casefold(),
            )
            if pair in original_pairs:
                satisfied += 1
                continue
            failures.append(
                {
                    "csv_line": entry["csv_line"],
                    "role_name": role_name,
                    "record_name": entry["record_name"],
                    "field_name": entry["field_name"],
                    "reason": reason,
                }
            )

        return {"added": 0, "satisfied": satisfied, "failures": failures}


def parse_args(argv=None):
    """Parse and validate command-line options for a CSV automation run.

    Args:
        argv: Optional sequence of arguments excluding the program name. When
            omitted, argparse reads ``sys.argv``.

    Returns:
        An argparse Namespace containing ``csv_path``, the Boolean ``debug``
        flag, ``port`` (9222 unless explicitly overridden), and an optional
        ``summary_file`` destination.

    Raises:
        SystemExit: The command line is invalid or help was requested. Invalid
        ports exit with argparse status 2 and a descriptive message.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Add Query Masking Authorized Role rows from a CSV and save once "
            "per role."
        )
    )
    parser.add_argument(
        "csv_path",
        type=Path,
        help="CSV containing ROLENAME, RECNAME, and FIELDNAME columns",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "attach to an existing Chrome debugging session instead of "
            "opening a new browser"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_DEBUG_PORT,
        help=(
            "Chrome debugging port used with --debug "
            f"(default: {DEFAULT_DEBUG_PORT})"
        ),
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        help=(
            "failure-summary CSV destination; defaults to a timestamped file "
            "beside the input CSV"
        ),
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    return args


def main(argv=None):
    """Load the requested CSV and execute each grouped role in one browser.

    Args:
        argv: Optional command-line arguments excluding the program name. This
            is forwarded to ``parse_args`` and is primarily useful for tests.

    Returns:
        Process status 0 when every input row was added or already satisfied,
        1 when any automation row failed, or 2 when CSV validation fails.

    Raises:
        SystemExit: ``parse_args`` exits for invalid command-line syntax or
        ``--help``. Other expected runtime failures are reported and converted
        to the returned status code.
    """

    args = parse_args(argv)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = args.summary_file or args.csv_path.with_name(
        f"{args.csv_path.stem}_summary_{timestamp}.csv"
    )

    try:
        roles = read_csv_roles(args.csv_path)
    except Exception as exc:
        print(f"CSV error: {exc}", file=sys.stderr)
        failure = {
            "csv_line": "",
            "role_name": "",
            "record_name": "",
            "field_name": "",
            "reason": f"CSV error: {exc}",
        }
        try:
            written_path = write_failure_summary(summary_path, [failure])
            print(f"Failure summary: {written_path} (1 failure)")
        except Exception as summary_exc:
            print(f"Could not write failure summary: {summary_exc}", file=sys.stderr)
            traceback.print_exc()
        return 2

    row_count = sum(len(entries) for entries in roles.values())
    print(
        f"Loaded {row_count} CSV row(s) across {len(roles)} role(s) "
        f"from {args.csv_path}."
    )

    failures = []
    total_added = 0
    total_satisfied = 0
    debug_port = args.port if args.debug else None

    browser = None
    try:
        browser = initialize_webdriver(debug_port=debug_port)
        start_url = browser.current_url
    except Exception as exc:
        reason = f"Automation startup failed: {type(exc).__name__}: {exc}"
        print(reason, file=sys.stderr)
        traceback.print_exc()
        for role_name, entries in roles.items():
            for entry in entries:
                failures.append(
                    {
                        "csv_line": entry["csv_line"],
                        "role_name": role_name,
                        "record_name": entry["record_name"],
                        "field_name": entry["field_name"],
                        "reason": reason,
                    }
                )

    if browser is not None:
        for role_number, (role_name, entries) in enumerate(roles.items(), start=1):
            print(
                f"Role {role_number}/{len(roles)}: {role_name} "
                f"({len(entries)} record/field row(s))"
            )
            try:
                result = execute_role(browser, start_url, role_name, entries)
                total_added += result["added"]
                total_satisfied += result["satisfied"]
                failures.extend(result["failures"])
            except Exception as exc:
                reason = f"Unexpected role failure: {type(exc).__name__}: {exc}"
                print(f"ERROR for role {role_name}: {reason}", file=sys.stderr)
                traceback.print_exc()
                for entry in entries:
                    failures.append(
                        {
                            "csv_line": entry["csv_line"],
                            "role_name": role_name,
                            "record_name": entry["record_name"],
                            "field_name": entry["field_name"],
                            "reason": reason,
                        }
                    )

    try:
        written_path = write_failure_summary(summary_path, failures)
    except Exception as exc:
        print(f"Could not write failure summary: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    print("\nRun summary")
    print(f"  Input rows:       {row_count}")
    print(f"  Added and saved:  {total_added}")
    print(f"  Already satisfied: {total_satisfied}")
    print(f"  Not accomplished: {len(failures)}")
    print(f"  Summary file:     {written_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())


# UHS_CS_SECFORM_CHGS


