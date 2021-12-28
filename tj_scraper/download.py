"""Responsible for handling data downloading."""
from collections.abc import Collection
from pathlib import Path
from typing import Any, Callable

from .process import all_from, IdRange


FilterFunction = Callable[[dict[str, Any]], bool]
DownloadFunction = Callable[[list[str], Path, bool, FilterFunction], None]


def download_from_json(
    ids: list[str],
    sink: Path,
    fetch_all: bool = True,
    filter_function: FilterFunction = lambda _: True,
):
    """Downloads data from urls that return JSON values."""
    import aiohttp
    import asyncio
    import jsonlines
    import json

    results = Path("results")

    def cache(data):
        # with open(results / "cache-valid.json", "w+") as f:
        #     valids = json.load(f)
        #     valids[data[]]

        with jsonlines.open(results / "cache.jsonl", mode="a") as sink_f:
            sink_f.write(data)  # type: ignore

    def is_invalid_process(data):
        return data in (
            ["Número do processo inválido."],
            ["O processo informado não foi encontrado."],
        )

    async def fetch_process(session: aiohttp.ClientSession, id_: str):
        async with session.post(
            base_url,
            json={
                "tipoProcesso": "1",
                "codigoProcesso": id_,
            },
        ) as response:
            data = json.loads(await response.text())

        if is_invalid_process(data):
            # print(f"{id_}: Invalid/Not Found")
            return

        if not filter_function(data):
            cache(data)
            print(
                f"{id_}: Filtered  -- ({data.get('txtAssunto', 'Sem Assunto')}) -- Cached"
            )
            return "Filtered"

        fields = data.keys() if fetch_all else ["idProc", "codProc"]

        data = {k: v for k, v in data.items() if k in fields}
        print(f"{id_}: {data.get('txtAssunto', 'Sem Assunto')}")
        return data

    from time import time

    async def fetch_all_processes(ids):
        step = 100
        start_time = time()
        total = 0
        async with aiohttp.ClientSession() as session:
            for start in range(0, len(ids), step):
                end = min(start + step, len(ids))
                sub_ids = ids[start:end]
                print(
                    f"\n--\n-- Wave: {(start // step) + 1}\n    ({sub_ids[0]}..{sub_ids[-1]})"
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
                Ellapsed time:      {ellapsed:.2}s
                Request count:      {total}
                Time/Request (avg): {ellapsed / total:.2}s
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


def download_all_from_range(
    ids: list[str],
    sink: Path,
    fetch_all: bool = True,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = download_from_json,
):
    """
    Downloads relevant info from all valid process with ID in `ids` and saves
    it into `sink`. Expects `sink` to be in JSONLines format.
    """
    download_function(ids, sink, fetch_all, filter_function)


def skip_cached(ids: list[str], cache_file: Path) -> list[str]:
    """Filters IDs that are already cached."""
    import jsonlines

    filtered = []
    ids = [*ids]
    cached_ids = set()
    with jsonlines.open(cache_file) as reader:
        for item in reader:  # type: ignore
            match item:
                case {"codProc": cached_id}:
                    cached_ids |= {cached_id}

    for id_ in ids[:50]:
        cached = id_ in cached_ids

        if not cached:
            filtered += [id_]
        else:
            print(f"{id_}: Cached")
    return filtered


def processes_by_subject(
    id_range: IdRange,
    words: Collection[str],
    download_function: DownloadFunction,
    output: Path = Path("results") / "raw.jsonl",
    cache_file: Path = Path("results") / "cache.jsonl",
):
    """Search for processes that contain the given words on its subject."""
    from .timing import timeit

    def has_word_in_subject(data: dict[str, Any]):
        return any(
            word.lower() in data.get("txtAssunto", "Sem Assunto").lower()
            for word in words
        )

    print(f"Filtering by: {words}")

    all_from_range = all_from(id_range)
    ids = timeit(filter_cached, all_from_range, cache_file=cache_file)

    download_all_from_range(
        ids,
        output,
        filter_function=has_word_in_subject,
        download_function=download_function,
    )
