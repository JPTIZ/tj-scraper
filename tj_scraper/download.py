"""Responsible for handling data downloading."""
from collections.abc import Collection
from pathlib import Path
from typing import Any, Callable

from .cache import CacheState
from .process import all_from, IdRange


FilterFunction = Callable[[dict[str, Any]], bool]
DownloadFunction = Callable[[list[str], Path, bool, FilterFunction], None]


def download_from_json(
    ids: list[str],
    sink: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
):
    """Downloads data from urls that return JSON values."""
    import aiohttp
    import asyncio
    import jsonlines
    import json

    results = Path("results")

    def cache(data, state: CacheState):
        print(f'Saving "{data}" to cache with state {state}.')
        with jsonlines.open(results / "cache.jsonl", mode="a") as sink_f:
            sink_f.write(data)  # type: ignore

    async def fetch_process(session: aiohttp.ClientSession, id_: str):
        async with session.post(
            base_url,
            json={
                "tipoProcesso": "1",
                "codigoProcesso": id_,
            },
        ) as response:
            data = json.loads(await response.text())

        print(data)

        match data:
            case ["O processo informado não foi encontrado."]:
                print(f"{id_}: Not found -- Cached now")
                cache({"invalido": id_}, state=CacheState.INVALID)
                return
            case ["Número do processo inválido."]:
                print(f"{id_}: Invalid -- Cached now")
                cache({"invalido": id_}, state=CacheState.INVALID)
                return

        if not filter_function(data):
            cache(data, state=CacheState.CACHED)
            subject = data.get("txtAssunto", "Sem Assunto")
            print(f"{id_}: Filtered  -- ({subject}) -- Cached now")
            return "Filtered"

        fields = data.keys() if fetch_all_fields else ["idProc", "codProc"]

        data = {k: v for k, v in data.items() if k in fields}
        print(f"{id_}: {data.get('txtAssunto', 'Sem Assunto')}")
        return data

    from time import time

    async def fetch_all_processes(ids):
        step = 100
        start_time = time()
        total = 0
        ids = list(ids)
        async with aiohttp.ClientSession() as session:
            for start in range(0, len(ids), step):
                end = min(start + step, len(ids))
                sub_ids = ids[start:end]
                print(
                    "\n--"
                    f"\n-- Wave: {(start // step) + 1}"
                    f"\n    ({sub_ids[0]}..{sub_ids[-1]})"
                )
                requests = (fetch_process(session, id_) for id_ in sub_ids)
                data = await asyncio.gather(
                    *requests,
                )

                total += len(data)
                filtered = sum(
                    1 if item != "Filtered" else 0 for item in data if item is not None
                )
                invalid = sum(1 if item is None else 0 for item in data)

                data = [
                    item for item in data if item is not None and item != "Filtered"
                ]

                with jsonlines.open(sink, mode="a") as sink_f:
                    sink_f.write_all(data)  # type: ignore

                print(
                    f"Partial result: {data} ({filtered} filtered, {invalid} invalid)"
                )
        end_time = time()
        ellapsed = end_time - start_time
        print(
            f"""
            Finished.
                Ellapsed time:      {ellapsed:.2f}s
                Request count:      {total}
                Time/Request (avg): {ellapsed / total:.2f}s
        """
        )

    base_url = (
        "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
    )

    asyncio.run(fetch_all_processes(ids))


def download_from_html(
    ids: list[str],
    sink: Path,
):
    """Downloads data by crawling through possible URLs. Warning: not updated"""
    from .html import run_spider, TJRJSpider
    from .url import build_tjrj_process_url

    start_urls = [build_tjrj_process_url(id_) for id_ in ids]
    print(f"{start_urls=}")

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


def download_all_with_ids(
    ids: list[str],
    sink: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = download_from_json,
):
    """
    Downloads relevant info from all valid process with ID in `ids` and saves
    it into `sink`. Expects `sink` to be in JSONLines format.
    """
    download_function(ids, sink, fetch_all_fields, filter_function)


def download_all_from_range(
    id_range: IdRange,
    sink: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = download_from_json,
):
    """
    Downloads relevant info from all valid process whose ID is within
    `id_range` and saves it into `sink`. Expects `sink` to be in JSONLines
    format.
    """
    ids = all_from(id_range)
    download_function(ids, sink, fetch_all_fields, filter_function)


def processes_by_subject(
    id_range: IdRange,
    words: Collection[str],
    download_function: DownloadFunction,
    output: Path = Path("results") / "raw.jsonl",
    cache_file: Path = Path("results") / "cache.jsonl",
):
    """Search for processes that contain the given words on its subject."""
    from .cache import filter_cached
    from .timing import report_time

    def has_word_in_subject(data: dict[str, Any]):
        return any(
            word.lower() in data.get("txtAssunto", "Sem Assunto").lower()
            for word in words
        )

    print(f"Filtering by: {words}")

    all_from_range = set(all_from(id_range))
    ids = report_time(filter_cached, all_from_range, cache_file=cache_file)
    for filtered_id in set(all_from_range) - set(ids):
        print(f"Ignoring {filtered_id} -- Cached")

    download_all_with_ids(
        ids,
        output,
        filter_function=has_word_in_subject,
        download_function=download_function,
    )
