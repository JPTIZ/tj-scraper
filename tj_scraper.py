"""A package of tools for brazilian Tribunal de Justiça pages."""
import multiprocessing as mp
import sys
from dataclasses import dataclass
from collections.abc import Collection
from pathlib import Path
from typing import Callable

from importlib_metadata import version

from scrapy.crawler import CrawlerRunner, Spider
from scrapy.http import Response
from twisted.internet import reactor


__version__ = version(__package__)


__all__ = [
    "__version__",
    "TJRJSpider",
    "Spider",
]


class BadProcessId(Exception):
    """Thrown when an invalid Process ID/Number is used in a request."""


class BlockedByCaptcha(Exception):
    """
    Thrown when trying to access a page that contains a captcha (thus stopping
    this crawler of going forward).
    """


def build_url(page: str, params: dict[str, str]):
    """Builds URL with correct query string. For API purposes."""
    query_string = "&".join(f"{p}={v}" for p, v in params.items())

    return f"{page}?{query_string}"


@dataclass
class Process:
    """The information we want from a single process from a TJ."""

    process_id: str
    uf: str  # pylint: disable=invalid-name
    subject: str


def check_for_captcha(process_id: str, response: Response):
    """
    Raises a `BlockedByCaptcha` if response page has a captcha on it.
    """
    return process_id, response


def check_for_valid_id(process_id: str, response: Response):
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
        raise BadProcessId(process_id)


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
        return response.xpath(xpath)[1].get().strip()

    if _id := try_or_false(assume_good_page):
        return _id

    return ""


def extract_page_content(response: Response):
    """
    Extracts page content. Raises exceptions if not a valid process page.
    """
    process_id = extract_process_id(response)

    check_for_captcha(process_id, response)
    check_for_valid_id(process_id, response)

    subject_xpath = "//td[text()='Assunto:']/following-sibling::td/text()"
    try:
        content = response.xpath(subject_xpath).get().strip()
        return process_id, content
    except AttributeError:
        failed_page = Path("results/failed.html")
        failed_page.parent.mkdir(parents=True, exist_ok=True)
        with open(failed_page, "wb") as failed_file:
            failed_file.write(response.body)
        raise


def build_tjrj_process_url(process_id):
    """Creates process info page url from process_id."""
    root = "http://www4.tjrj.jus.br"
    page = "consultaProcessoWebV2/consultaMov.do"

    params = {
        "numProcesso": process_id,
        "acessoIP": "internet",
    }
    return build_url(f"{root}/{page}", params=params)


class TJRJSpider(Spider):
    """Extracts quotes from TJ-RJ page."""

    build_process_url = build_tjrj_process_url

    name = "tjrj-spider"
    start_urls = [build_process_url("2007.001.209836-2")]

    def parse(self, response: Response, **kwargs):
        process_id, page_content = extract_page_content(response)

        yield Process(process_id, "RJ", page_content.replace("\n", ""))


def run_spider(spider, **kwargs):
    """
    Runs a spider in a separated subprocess, enabling to run multiple spiders
    in a single run.
    """

    def _run_spider(queue):
        runner = CrawlerRunner(kwargs.get("settings", {}))
        deferred = runner.crawl(spider, **kwargs)
        # Just to shut mypy errors due to bad Twisted design
        reactor.stop = reactor.stop or (lambda x: x)
        reactor.run = reactor.run or (lambda x: x)
        # --
        deferred.addBoth(lambda _: reactor.stop())
        reactor.run()
        queue.put(None)

    queue = mp.Queue()
    process = mp.Process(target=_run_spider, args=(queue,))
    process.start()
    result = queue.get()
    process.join()

    if result is not None:
        raise result


def processes_by_subject(words: Collection[str]) -> Collection[Process]:
    """Search for processes that contain the given words on its subject."""
    print(words)
    return []


def main(*args: str):
    """Program's start point. May be used to simulate program execution."""
    try:
        _, process_id = args
    except IndexError:
        print(f"Uso: {args[0]} <Nº do processo>")
        sys.exit(0)
    start_urls = [build_tjrj_process_url(process_id)]

    sink = Path("items.json")
    crawler_settings = {
        "FEED_EXPORT_ENCODING": "utf-8",
        "FEEDS": {
            sink: {"format": "jsonlines"},
        },
    }

    run_spider(
        TJRJSpider,
        start_urls=start_urls,
        settings=crawler_settings,
    )


if __name__ == "__main__":
    main(*sys.argv)
