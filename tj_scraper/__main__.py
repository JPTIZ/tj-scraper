'''A simple scrapper for Tribunal de Justiça pages.'''
from dataclasses import dataclass
from pathlib import Path

from scrapy.crawler import CrawlerProcess, Spider


@dataclass
class Process:
    '''The information we want from a single process from a TJ.'''
    process_id: int
    uf: str           # pylint: disable=invalid-name
    subject: str


class TJRJSpider(Spider):
    '''Extracts quotes from TJ-RJ page.'''
    name = "quotes"
    start_urls = [
        f'file://{Path.cwd() / "samples" / "processo-1.html"}',
    ]

    def parse(self, response, **kwargs):
        subject_xpath = '//form/table/tbody/tr[20]/td[2]/text()'
        subject = response.xpath(subject_xpath).get().strip()

        yield Process(0, 'RJ', subject)


if __name__ == '__main__':
    process = CrawlerProcess(settings={
        'FEEDS': {
            'items.json': {'format': 'json'}
        }
    })

    process.crawl(TJRJSpider)
    process.start()
