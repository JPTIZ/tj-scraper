'''A package of tools for brazilian Tribunal de Justiça pages.'''
from dataclasses import dataclass
from importlib_metadata import version

from scrapy.crawler import CrawlerProcess, Spider


__version__ = version(__package__)


__all__ = [
    '__version__',
    'TJRJSpider',
    'Spider',
]


def build_url(page, params):
    '''Builds URL with correct query string. For API purposes.'''
    query_string = '&'.join(f'{p}={v}' for p, v in params.items())

    return f'{page}?{query_string}'


@dataclass
class Process:
    '''The information we want from a single process from a TJ.'''
    process_id: int
    uf: str           # pylint: disable=invalid-name
    subject: str


class TJRJSpider(Spider):
    '''Extracts quotes from TJ-RJ page.'''

    @staticmethod
    def _build_process_url(process_id):
        '''Creates process info page url from process_id.'''
        root = "http://www4.tjrj.jus.br"
        page = "consultaProcessoWebV2/consultaMov.do"

        params = {
            'numProcesso': process_id,
        }
        return build_url(f'{root}/{page}', params=params)

    build_process_url = _build_process_url.__func__

    name = "tjrj-spider"
    start_urls = [
        build_process_url("2007.001.209836-2")
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
