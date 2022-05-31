"""Responsible for handling data downloading."""
import json
from collections.abc import Collection
from pathlib import Path
from typing import Any, Callable

import aiohttp
import jsonlines

from .cache import CacheState, filter_cached, restore, restore_ids, save_to_cache
from .process import (
    REAL_ID_FIELD,
    IdRange,
    Process,
    all_from,
    get_process_id,
    has_words_in_subject,
)
from .timing import report_time

FilterFunction = Callable[[dict[str, Any]], bool]
DownloadFunction = Callable[[list[str], Path, Path, bool, FilterFunction], None]

BASE_URLS = {
    "rj": (
        "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
    ),
}


def write_to_sink(items: list[Process], sink: Path, reason: str):
    """
    A quick wrapper to write all data into a sink file while reporting about
    it.
    """
    with jsonlines.open(sink, "a") as output_f:
        print(
            f"Writing {[get_process_id(item) for item in items]}\n"
            f"  -> Total items: {len(items)}.\n"
            f"  -> Reason: {reason}."
        )
        output_f.write_all(items)  # type: ignore


def write_cached_to_sink(ids: list[str], sink: Path, cache_path: Path):
    """
    Write only items with given IDs that are cached into the sink and returns
    which are not and which are cached.
    """
    filtered, _ = report_time(filter_cached, ids, cache_path=cache_path)

    def to_list(constructor):
        return lambda items: [constructor(item) for item in items]

    ids, cached_ids = map(to_list(str), filtered)

    cached_items = restore_ids(cache_path, list(cached_ids))

    print(f"Cached_ids: {cached_ids}")

    write_to_sink(cached_items, sink=sink, reason="Cached")

    return ids, cached_ids


# pylint: disable=invalid-name
async def fetch_process(
    session: aiohttp.ClientSession,
    id_: str,
    url: str,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
):
    """
    Fetches a single process from `url`, applying filters and reporting whether
    the result is selected, failed on captcha or etc. Returns the process if it
    is selected, else returns `None`.
    """
    async with session.post(
        url,
        json={
            "tipoProcesso": "1",
            "codigoProcesso": id_,
        },
        ssl=False,  # FIXME: Properly handle TJ's outdated certificate
    ) as response:
        data = json.loads(await response.text())

    match data:
        case ["O processo informado não foi encontrado."]:
            print(f"{id_}: Not found -- Cached now")
            save_to_cache(
                {REAL_ID_FIELD: id_},
                cache_path,
                state=CacheState.INVALID,
            )
            return
        case ["Número do processo inválido."]:
            print(f"{id_}: Invalid -- Cached now")
            save_to_cache(
                {REAL_ID_FIELD: id_},
                cache_path,
                state=CacheState.INVALID,
            )
            return
        case {
            "status": 412,
            "mensagem": "Erro de validação do Recaptcha. Tente novamente.",
        }:
            print(f"{id_}: Unfetched, failed on recaptcha.")
            return

    if not filter_function(data):
        subject = data.get("txtAssunto", "Sem Assunto")
        print(f"{id_}: Filtered  -- ({subject}) -- Cached now ({data=})")
        save_to_cache(data, cache_path, state=CacheState.CACHED)
        return "Filtered"

    save_to_cache(data, cache_path, state=CacheState.CACHED)

    fields = data.keys() if fetch_all_fields else [REAL_ID_FIELD]

    data = {k: v for k, v in data.items() if k in fields}
    print(f"Fetched process {id_}: {data.get('txtAssunto', 'Sem Assunto')}")
    return data


def download_from_json(
    ids: list[str],
    sink: Path,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    # pylint: disable=dangerous-default-value
    base_urls: dict[str, str] = BASE_URLS,
    force_fetch: bool = False,
):
    """
    Downloads data from urls that return JSON values. Previously cached results
    are used by default if `force_fetch` is not set to `True`.
    """
    import asyncio

    if not force_fetch:
        ids, _ = write_cached_to_sink(ids=ids, sink=sink, cache_path=cache_path)

    async def fetch_all_processes(ids, step=100):
        total = 0
        async with aiohttp.ClientSession(trust_env=True) as session:
            for start in range(0, len(ids), step):
                end = min(start + step, len(ids))
                sub_ids = ids[start:end]
                print(
                    "\n--"
                    f"\n-- Wave: {(start // step) + 1}"
                    f"\n    ({sub_ids[0]}..{sub_ids[-1]})"
                )
                requests = (
                    fetch_process(
                        session,
                        id_,
                        base_urls["rj"],
                        cache_path=cache_path,
                        filter_function=filter_function,
                        fetch_all_fields=fetch_all_fields,
                    )
                    for id_ in sub_ids
                )
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

                write_to_sink(data, sink, reason="Fetched")

                partial_ids = [get_process_id(item) for item in data]

                print(
                    f"Partial result: {partial_ids} ({filtered} filtered, {invalid} invalid)"
                )
        return total

    from tj_scraper.timing import timeit

    total, ellapsed = timeit(asyncio.run, fetch_all_processes(ids))
    print(
        f"""
        Finished.
            Ellapsed time:      {ellapsed:.2f}s
            Request count:      {total}
            Time/Request (avg): {ellapsed / max(total, 1):.2f}s
        """
    )


def download_from_html(
    ids: list[str],
    sink: Path,
):
    """Downloads data by crawling through possible URLs. Warning: not updated"""
    from .html import TJRJSpider, run_spider
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
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = download_from_json,
):
    """
    Downloads relevant info from all valid process with ID in `ids` and saves
    it into `sink`. Expects `sink` to be in JSONLines format.
    """
    download_function(ids, sink, cache_path, fetch_all_fields, filter_function)


def download_all_from_range(
    id_range: IdRange,
    sink: Path,
    cache_path: Path,
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
    download_function(list(ids), sink, cache_path, fetch_all_fields, filter_function)


def processes_by_subject(
    id_range: IdRange,
    words: Collection[str],
    download_function: DownloadFunction,
    output: Path = Path("results") / "raw.jsonl",
    cache_path: Path = Path("results") / "cache.db",
):
    """Search for processes that contain the given words on its subject."""
    if words:
        print(f"Filtering by: {words}")
        filter_function = lambda item: has_words_in_subject(item, list(words))
    else:
        print("Empty 'words'. Word filtering will not be applied.")
        filter_function = lambda _: True

    all_from_range = set(all_from(id_range))
    (ids, cached_ids), _ = report_time(
        filter_cached, all_from_range, cache_path=cache_path
    )
    ids = list(ids)
    cached_ids = list(cached_ids)
    cached_processes = [
        item
        for item in restore(cache_path)
        if item.get(REAL_ID_FIELD, "") in cached_ids
        and has_words_in_subject(item, list(words))
    ]

    if not cached_processes:
        print(f"No cached processes for given ID Range ({id_range}).")

    write_to_sink(cached_processes, sink=output, reason="Cached")

    for filtered_id in set(all_from_range) - set(ids):
        print(f"Ignoring {filtered_id} -- Cached")

    download_all_with_ids(
        ids,
        output,
        cache_path,
        filter_function=filter_function,
        download_function=download_function,
    )
