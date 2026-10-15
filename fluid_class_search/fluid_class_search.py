"""Compare course counts in a CSV with PeopleSoft Fluid Class Search.

Expected command-line input:
    python fluid_class_search.py <environment> <csv_path> <process_count>

<environment> is TST, DEV, or PRD (the keys in login_pages below).
<csv_path> is a CSV with a header row and at least five columns. The fourth
column (index 3) must contain the subject code, such as MATH; the fifth
column (index 4) must contain the course number, such as 1300. Each data row
represents one class option. Repeated subject/course pairs are counted and
compared with the number of options returned by Fluid Class Search.
<process_count> is the number of independent browser workers to launch.

The script opens all isolated Chrome sessions at once. Sign in and navigate
every browser to Fluid Class Search, then return to the terminal and press
Enter once to start every worker. The script writes discrepancies and search
errors to a text file named after the input CSV with _FluidSearchResult.txt
appended to its base name.
"""

import sys
import csv
import time
from multiprocessing import Event, Process, Queue
from queue import Empty
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

SEARCH_PAUSE_SECONDS = 0.5
RESULT_MESSAGE_SELECTOR = "[id$='divPTS_SEARCHED_KW2']"
CLASS_COUNT_SELECTOR = "[id$='divPTS_LIST_SUMMARY$0']"

login_pages = {
    "TST" : "https://dev.my.uh.edu:8021/psp/sa92tst/?cmd=login",
    "DEV" : "https://dev.my.uh.edu:8042/psp/sa92dev/?cmd=login&languageCd=ENG&",
    "PRD" : "https://saprd.my.uh.edu/psp/saprd/?cmd=login&languageCd=ENG&"
}

class Course:
    """
    Keep a subject/course-number pair and its number of CSV rows.

    subject and course_number come from CSV columns 4 and 5, respectively.
    count starts at 1 for the first row containing that pair.
    """
    def __init__(self, subject : str, course_number : str, count = 1) -> None:
        self.subject = subject
        self.course_number = course_number
        self.count = count

    def Incriment_Count(self):
        self.count = self.count + 1

    def Get_Subject(self):
        return self.subject

    def Get_Count(self):
        return self.count
    
    def Get_Course_Number(self):
        return self.course_number


def Search_for_Courses(
    classes: dict[list[Course]],
    queue: Queue,
    failed_search_queue: Queue,
    database: str,
    worker_number: int,
    ready_queue: Queue,
    start_event: Event,
):
    """Run one independently authenticated Fluid Class Search worker.

    Args:
        classes: Subject keys mapped to the Course objects assigned to this
            worker.
        queue: Multiprocessing queue that receives discrepancy report lines.
        failed_search_queue: Multiprocessing queue that receives failed search
            details for the final report.
        database: A key in ``login_pages`` identifying TST, DEV, or PRD.
        worker_number: One-based number used in operator and error messages.
        ready_queue: Queue notified after this worker's login browser opens.
        start_event: Event set after the operator has signed into this browser
            and navigated it to Fluid Class Search.

    Returns:
        None. Results and failures are placed on their respective queues, and
        the worker's private Chrome session is closed before the process exits.

    Failure behavior:
        Browser startup errors are reported through ``ready_queue``. A browser
        not positioned on Fluid Class Search marks all of its assigned courses
        failed. Individual Selenium/search errors are printed immediately and
        stored in ``failed_search_queue`` without stopping other workers.
    """

    driver = None
    startup_reported = False
    line_buffer = []
    try:
        options = Options()
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_argument("--log-level=3")
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(5)
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
                current_search = (
                    f"{subject} {Course.Get_Course_Number(course)}"
                )
                try:
                    search_field = driver.find_element(By.ID, "PTS_KEYWORDS3")
                    search_field.send_keys(current_search + Keys.ENTER)
                    try:
                        result_element = driver.find_element(
                            By.CSS_SELECTOR,
                            RESULT_MESSAGE_SELECTOR,
                        )
                        if (
                            result_element.text
                            == "No Courses available for the selected filters"
                        ):
                            line_buffer.append(
                                f"{current_search}: {result_element.text}.\n"
                            )
                        else:
                            class_count_element = driver.find_element(
                                By.CSS_SELECTOR,
                                CLASS_COUNT_SELECTOR,
                            )
                            class_count_statement = (
                                class_count_element.text.split("\n")[1]
                            )
                            if str(Course.Get_Count(course)) != (
                                class_count_statement.split(" ")[0]
                            ):
                                line_buffer.append(
                                    f"{current_search}: Appears in "
                                    f"{Course.Get_Count(course)} rows of the "
                                    "csv but fluid search returns: "
                                    f"{class_count_statement}.\n"
                                )
                    except NoSuchElementException:
                        no_result_element = driver.find_element(
                            By.ID,
                            "PTS_SRCH_PTS_INDEXTIME",
                        )
                        line_buffer.append(
                            f"{current_search}: "
                            f"{no_result_element.text.split('.')[0]}.\n"
                        )
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    print(
                        f"Worker {worker_number} ERROR searching "
                        f"{current_search}: {reason} "
                        f"(URL: {driver.current_url})",
                        file=sys.stderr,
                        flush=True,
                    )
                    failed_search_queue.put((subject, course, reason))

                try:
                    driver.get(initial_url)
                except Exception as exc:
                    print(
                        f"Worker {worker_number} ERROR returning to Fluid "
                        f"Class Search: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                time.sleep(SEARCH_PAUSE_SECONDS)

    except Exception as exc:
        reason = f"Worker {worker_number} failed: {type(exc).__name__}: {exc}"
        if not startup_reported:
            ready_queue.put((worker_number, reason))
            startup_reported = True
        print(reason, file=sys.stderr, flush=True)
        for subject, courses in classes.items():
            for course in courses:
                failed_search_queue.put((subject, course, reason))
    finally:
        queue.put(line_buffer)
        if driver is not None:
            driver.quit()

def Split_Dictionary(
    classes: dict[list],
    classes_p: list[dict],
    process_count: int,
):
    """Distribute individual courses evenly across the configured workers.

    Args:
        classes: Subject keys mapped to lists of Course objects.
        classes_p: An initially empty list populated with one subject/course
            dictionary for each worker.
        process_count: Positive number of worker dictionaries to create.

    Returns:
        None. ``classes_p`` is modified in place. Courses are distributed in
        round-robin order rather than keeping a large subject on one worker.

    Failure behavior:
        Invalid or non-iterable inputs raise their normal Python exceptions;
        this function performs no browser or filesystem operations.
    """

    classes_p.extend({} for _ in range(process_count))
    i = 0
    for subject, courses in classes.items():
        for course in courses:
            worker_classes = classes_p[i % process_count]
            worker_classes.setdefault(subject, []).append(course)
            i += 1

def StartProcesses(
    database: str,
    classes: dict[list[Course]],
    process_count: int,
):
    """Launch independent authenticated browsers and run parallel searches.

    Args:
        database: A key in ``login_pages`` identifying TST, DEV, or PRD.
        classes: Subject keys mapped to Course objects built from the input
            CSV.
        process_count: Positive number of independent Chrome workers to run.

    Returns:
        A list of discrepancy and failure lines for the output text file.

    Failure behavior:
        Waits indefinitely for every browser to report that it opened, then
        waits for one Enter press after the operator prepares all browsers.
        Raises RuntimeError if a browser reports a startup failure. Individual
        search failures are printed and returned as error lines instead of
        stopping the remaining workers.
    """

    line_buffer = []
    classes_p = []
    Split_Dictionary(classes, classes_p, process_count)
    process_list = []
    queue = Queue()
    failed_search_queue = Queue()
    ready_queue = Queue()
    start_event = Event()

    print(
        f"Preparing {process_count} independent Chrome sessions. Each "
        "browser uses its own temporary profile and PeopleSoft session."
    )
    failed_searches = []
    try:
        for i, worker_classes in enumerate(classes_p, start=1):
            process = Process(
                target=Search_for_Courses,
                args=(
                    worker_classes,
                    queue,
                    failed_search_queue,
                    database,
                    i,
                    ready_queue,
                    start_event,
                ),
            )
            process.start()
            process_list.append(process)

        # There is deliberately no timeout. The command line waits until
        # every browser reports that its login page has opened.
        for _ in process_list:
            worker_number, error = ready_queue.get()
            if error:
                raise RuntimeError(error)
            print(f"  Worker {worker_number}/{process_count} browser opened.")

        input(
            f"\nSign in and navigate all {process_count} browsers to the "
            "Fluid Class Search starting page.\nPress Enter once when every "
            "window is ready... "
        )
        start_event.set()

        # Drain worker queues while processes are running. This prevents a
        # worker with many failures from blocking on a full multiprocessing
        # queue while the parent is waiting for that worker to exit.
        while any(process.is_alive() for process in process_list):
            try:
                line_buffer.extend(queue.get(timeout=0.25))
            except Empty:
                pass
            while True:
                try:
                    failed_searches.append(
                        failed_search_queue.get_nowait()
                    )
                except Empty:
                    break
        for process in process_list:
            process.join()
    except BaseException:
        start_event.set()
        for process in process_list:
            if process.is_alive():
                process.terminate()
            process.join()
        raise

    while True:
        try:
            line_buffer.extend(queue.get_nowait())
        except Empty:
            break

    while True:
        try:
            failed_searches.append(failed_search_queue.get_nowait())
        except Empty:
            break

    for subject, course, reason in failed_searches:
        line_buffer.append(
            f"{subject} {Course.Get_Course_Number(course)}: "
            f"Error unsuccessful search: {reason}.\n"
        )
    return line_buffer

def Find_Course_Index(courses : list[Course], course_number):
    """
    Return index that matches course_number or return None if it does not exist.

    courses contains Course objects for one subject; course_number is the
    string from CSV column 5.
    """
    for i in range(len(courses)):
        if course_number == courses[i].Get_Course_Number():
            return i
    return None

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: python fluid_class_search.py "
            "<TST|DEV|PRD> <csv_path> <process_count>",
            file=sys.stderr,
        )
        sys.exit(2)

    database = sys.argv[1].upper()
    csv_path = sys.argv[2]
    if database not in login_pages:
        print("Environment must be TST, DEV, or PRD.", file=sys.stderr)
        sys.exit(2)

    try:
        process_count = int(sys.argv[3])
    except ValueError:
        print("process_count must be a positive integer.", file=sys.stderr)
        sys.exit(2)
    if process_count < 1:
        print("process_count must be a positive integer.", file=sys.stderr)
        sys.exit(2)

    classes = {}
    # Argument 2 is the input CSV path. csv.reader returns each row as a list
    # of strings; the first row is a header and is skipped.
    with open(csv_path, 'r') as csv_file:
        # row[3] is the subject code; row[4] is the course number. Each
        # repeated pair adds one to the expected class-option count.
                csv_reader = csv.reader(csv_file)
                next(csv_reader)
                for row in csv_reader:
                    if row[3] in classes.keys():
                        index = Find_Course_Index(classes[row[3]], row[4])
                        if index == None:
                            classes[row[3]].append(Course(row[3], row[4]))
                        else:
                            classes[row[3]][index].Incriment_Count()
                    else:
                       classes[row[3]] = [Course(row[3], row[4])]
         
    output_filename = csv_path.rsplit(".", 1)[0] + "_FluidSearchResult.txt"
    with open(output_filename, 'w') as file:
        # Argument 1 selects the PeopleSoft environment: TST, DEV, or PRD.
       file.writelines(StartProcesses(database, classes, process_count))
    print("Results at " + output_filename)
