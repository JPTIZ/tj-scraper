'''Tests main module functions in local files'''
from dataclasses import dataclass
from pathlib import Path

import jsonlines
import pytest
from scrapy.crawler import CrawlerProcess

from tj_scraper import TJRJSpider


@dataclass
class Process:
    '''The information we want from a single process from a TJ.'''
    process_id: int
    uf: str           # pylint: disable=invalid-name
    subject: str


class LocalTJRJSpider(TJRJSpider):
    '''
    Simulates TJRJ Spider by fetching local files instead of the real
    website.
    '''
    start_urls = [
        f'file://{Path.cwd() / "samples" / "processo-1.html"}',
    ]

    def parse(self, response, **kwargs):
        subject_xpath = '//form/table/tbody/tr[20]/td[2]/text()'
        subject = response.xpath(subject_xpath).get().strip()

        yield Process(0, 'RJ', subject.replace('\n', ''))


# pylint: disable=redefined-outer-name
@pytest.fixture
def crawler_settings():
    '''Generates most basic settings for crawler.'''
    return {
        'FEEDS': {},
        'FEED_EXPORT_ENCODING': 'utf-8',
    }


# pylint: disable=redefined-outer-name
@pytest.fixture
def items_sink(crawler_settings):
    '''
    Generates a items.json sink file with results and deletes it at the end.
    '''
    sink = Path('items.json')
    crawler_settings['FEEDS'][sink] = {'format': 'jsonlines'}
    yield sink
    sink.unlink(missing_ok=True)


@pytest.fixture
def crawler_process(crawler_settings):
    '''
    Generates a simple CrawlerProcess instance.
    '''
    return CrawlerProcess(settings=crawler_settings)


# pylint: disable=redefined-outer-name
def test_fetch_subject_from_a_process_page(items_sink, crawler_process):
    '''
    Tests if crawling a single process subject page fetches its subject
    correctly.
    '''
    crawler_process.crawl(LocalTJRJSpider)
    crawler_process.start()

    with jsonlines.open(items_sink) as sink_file:
        data = [*sink_file]

    assert data == [{
        'process_id': 0,
        'uf': 'RJ',
        'subject': (
            'Crimes de Tortura (Art. 1º - Lei 9.455/97)'
            ' E Prevaricação (Art. 319 e 319-A - CP)'
            ' E Usurpação de função pública  (Art. 328 - CP)'
        ),
    }]
