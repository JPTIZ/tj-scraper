"""Tests main module functions in local files"""
from pathlib import Path

import jsonlines
import pytest

from tj_scraper.html import (
    run_spider,
    TJRJSpider,
)


class LocalTJRJSpider(TJRJSpider):
    """
    Simulates TJRJ Spider by fetching local files instead of the real
    website.
    """

    start_urls = [
        f"file://{(Path.cwd() / 'samples' / 'invalid-numProcesso.html').resolve()}",
    ]


# pylint: disable=redefined-outer-name
@pytest.fixture(scope="module")
def crawler_settings():
    """Generates most basic settings for crawler."""
    return {
        "FEEDS": {},
        "FEED_EXPORT_ENCODING": "utf-8",
    }


# pylint: disable=redefined-outer-name
@pytest.fixture
def items_sink(crawler_settings):
    """
    Generates a items.json sink file with results and deletes it at the end.
    """
    sink = Path("items.json")
    crawler_settings["FEEDS"][sink] = {"format": "jsonlines"}
    yield sink
    sink.unlink(missing_ok=True)


# pylint: disable=redefined-outer-name
def test_fetch_subject_from_a_process_page(items_sink, crawler_settings):
    """
    Tests if crawling a single process subject page fetches its subject
    correctly.
    """
    start_urls = [
        f"file://{Path.cwd() / 'samples' / 'processo-1.html'}",
    ]

    run_spider(LocalTJRJSpider, start_urls=start_urls, settings=crawler_settings)

    with jsonlines.open(items_sink) as sink_file:
        data = [*sink_file]

    assert data
    assert data[0]["subject"] == (
        "Crimes de Tortura (Art. 1º - Lei 9.455/97)"
        " E Prevaricação (Art. 319 e 319-A - CP)"
        " E Usurpação de função pública (Art. 328 - CP)"
    )


def test_do_not_include_invalid_process_page(items_sink, crawler_settings):
    """
    Tests if an unexistent proccess ID page is not added to sink.
    """
    start_urls = [
        f"file://{Path.cwd() / 'samples' / 'invalid-numProcesso.html'}",
    ]

    run_spider(
        LocalTJRJSpider,
        start_urls=start_urls,
        settings=crawler_settings,
    )

    with jsonlines.open(items_sink) as sink_file:
        data = [*sink_file]

    assert not data


def test_detect_captcha_page(items_sink, crawler_settings):
    """
    Tests if an unexistent proccess ID page is correctly detected.
    """
    start_urls = [
        f"file://{Path.cwd() / 'samples' / 'with-captcha.html'}",
    ]

    run_spider(
        LocalTJRJSpider,
        start_urls=start_urls,
        settings=crawler_settings,
    )

    with jsonlines.open(items_sink) as sink_file:
        data = [*sink_file]

    assert not data
