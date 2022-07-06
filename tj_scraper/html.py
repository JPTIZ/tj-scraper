"""
Tools to fetch information from full-html pages (generally through scraping
tools).
"""
import multiprocessing
from pathlib import Path
from typing import Any, Callable, Generator

from scrapy.crawler import CrawlerRunner, Spider
from scrapy.http import Response
from twisted.internet import reactor

from .errors import InvalidProcessNumber
from .process import ProcessJSON
from .url import build_tjrj_process_url


def check_for_captcha(process_id: str, response: Response) -> tuple[str, Response]:
    """
    Raises a `BlockedByCaptcha` if response page has a captcha on it.
    """
    return process_id, response


def check_for_valid_id(process_id: str, response: Response) -> None:
    """
    Raises an `BadProcessId` if response page is an error page stating the
    process_id is invalid
    """
    error_xpath = "//title/text()"
    try:
        h3_content = response.xpath(error_xpath).get().strip()
    except AttributeError:
        return

    if h3_content.lower() == "erro":
        raise InvalidProcessNumber(process_id)


def extract_process_id(response: Response) -> str:
    """
    Extracts process ID from response HTML.
    """

    def try_or_false(function: Callable[[], str]) -> str:
        try:
            return function()
        except (AttributeError, IndexError):
            return ""

    def assume_good_page() -> str:
        xpath = "//form/table/tbody/tr[3]/td[1]/h2/text()"
        return str(response.xpath(xpath)[1].get()).strip()

    if _id := try_or_false(assume_good_page):
        return _id

    return ""


def extract_field(response: Response, field_text: str) -> str:
    """Extracts the value for a given process' field in page."""
    field_xpath = f"//td[text()='{field_text}:']/following-sibling::td/text()"
    return str(response.xpath(field_xpath).get()).strip()


def extract_page_content(response: Response) -> tuple[str, str]:
    """
    Extracts page content. Raises exceptions if not a valid process page.
    """
    process_id = extract_process_id(response)

    check_for_captcha(process_id, response)
    check_for_valid_id(process_id, response)

    try:
        content = extract_field(response, "Assunto")
        return process_id, content
    except AttributeError:
        failed_page = Path("results/failed.html")
        failed_page.parent.mkdir(parents=True, exist_ok=True)
        with open(failed_page, "wb") as failed_file:
            failed_file.write(response.body)
        raise


class TJRJSpider(Spider):  # type: ignore
    """Extracts quotes from TJ-RJ page."""

    build_process_url = build_tjrj_process_url

    name = "tjrj-spider"
    start_urls = [build_process_url("2007.001.209836-2")]

    def parse(self, response: Response, **_: Any) -> Generator[ProcessJSON, None, None]:
        process_id, page_content = extract_page_content(response)

        yield {
            "process_id": process_id,
            "uf": "RJ",
            "subject": page_content.replace("\n", " "),
            "lawyers": [],
            "extras": [],
        }


def run_spider(spider: type[Spider], **kwargs: Any) -> None:
    """
    Runs a spider in a separated subprocess, enabling to run multiple spiders
    in a single run.
    """
    from queue import Queue

    def _run_spider(queue: Queue[Any]) -> None:
        runner = CrawlerRunner(kwargs.get("settings", {}))
        deferred = runner.crawl(spider, **kwargs)
        # Just to shut mypy errors due to bad Twisted design
        reactor.stop = reactor.stop or (lambda: None)  # type: ignore
        reactor.run = reactor.run or (lambda: None)  # type: ignore
        # --
        deferred.addBoth(lambda _: reactor.stop())  # type: ignore
        reactor.run()  # type: ignore
        queue.put(None)

    queue: Queue[Any] = multiprocessing.Queue()
    process = multiprocessing.Process(target=_run_spider, args=(queue,))
    process.start()
    result = queue.get()
    process.join()

    if result is not None:
        raise result
