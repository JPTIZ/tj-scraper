"""Responsible for handling data downloading."""
import json
from collections.abc import Collection
from pathlib import Path
from typing import Callable, Optional

import aiohttp
import jsonlines

from .cache import CacheState, DBProcess, filter_cached, restore_ids, save_to_cache
from .process import (
    REAL_ID_FIELD,
    TJRJ,
    IdRange,
    Process,
    ProcessNumber,
    all_from,
    get_process_id,
    has_words_in_subject,
    make_cnj_code,
)
from .timing import report_time

FilterFunction = Callable[[Process], bool]
DownloadFunction = Callable[
    [list[ProcessNumber], Path, Path, bool, FilterFunction], None
]

BASE_URLS = {
    "rj": (
        "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
    ),
}


def write_to_sink(items: list[Process], sink: Path, reason: str) -> None:
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
        output_f.write_all(items)


def write_cached_to_sink(
    ids: list[ProcessNumber],
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction,
) -> list[ProcessNumber]:
    """
    Write only items with given IDs that are cached into the sink and returns
    which are not cached.
    """
    filtered = report_time(filter_cached, ids, cache_path=cache_path).value

    def cache_filter(item: DBProcess) -> bool:
        return filter_function(item.json)

    cached_items = restore_ids(
        cache_path,
        list(filtered.cached),
        filter_function=cache_filter,
    )

    write_to_sink(cached_items, sink=sink, reason="Cached")

    return list(filtered.not_cached)


# pylint: disable=invalid-name
async def fetch_process(
    session: aiohttp.ClientSession,
    id_: ProcessNumber,
    url: str,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
) -> Optional[Process | str]:
    """
    Fetches a single process from `url`, applying filters and reporting whether
    the result is selected, failed on captcha or etc. Returns the process if it
    is selected, else returns `None`.
    """
    from typing import Any

    # TODO: Com a numeração em NNNNNNN.DD, mandar blocos em que cada NNNNNNN
    # seja único e os DDs vão incrementando. Um processo encontrado é
    # substituído por um novo no "backlog" de números, se o DD chegar em 99 e
    # não for encontrado então ele é dado como não existente e é substituído
    # por um novo processo.
    # TODO: Dada a ideia acima, é possível criar um "parou aqui" para poder
    # continuar o trabalho em momentos variados: basta salvar o último "batch"
    # (conjunto de NNNNNNN's, DD's e OOOO's).

    data: dict[str, Any]
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
            return None

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
    ids: list[ProcessNumber],
    sink: Path,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    # pylint: disable=dangerous-default-value
    base_urls: dict[str, str] = BASE_URLS,
    force_fetch: bool = False,
) -> None:
    """
    Downloads data from urls that return JSON values. Previously cached results
    are used by default if `force_fetch` is not set to `True`.
    """
    import asyncio

    print(f"download_from_json({ids=})")

    if not force_fetch:
        ids = write_cached_to_sink(
            ids=ids, sink=sink, cache_path=cache_path, filter_function=filter_function
        )

    async def fetch_all_processes(ids: list[ProcessNumber], step: int = 100) -> int:
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

                data = [item for item in data if isinstance(item, dict)]

                write_to_sink(data, sink, reason="Fetched")

                partial_ids = [get_process_id(item) for item in data]

                print(
                    f"Partial result: {partial_ids} ({filtered} filtered, {invalid} invalid)"
                )
        return total

    from time import time

    start = time()
    result = asyncio.run(fetch_all_processes(ids))
    end = time()

    total_items: int = result
    ellapsed = end - start

    print(
        f"""
        Finished.
            Ellapsed time:      {ellapsed:.2f}s
            Request count:      {total_items}
            Time/Request (avg): {ellapsed / max([total_items, 1]):.2f}s
        """
    )


def download_from_html(
    ids: list[ProcessNumber],
    sink: Path,
) -> None:
    """Downloads data by crawling through possible URLs. Warning: not updated"""
    from .html import TJRJSpider, run_spider
    from .url import build_tjrj_process_url

    start_urls = [build_tjrj_process_url(make_cnj_code(id_)) for id_ in ids]
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
    ids: list[ProcessNumber],
    sink: Path,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = download_from_json,
) -> None:
    """
    Downloads relevant info from all valid process with ID in `ids` and saves
    it into `sink`. Expects `sink` to be in JSONLines format.
    """
    print(f"download_all_with_ids({ids=})")
    download_function(ids, sink, cache_path, fetch_all_fields, filter_function)


def download_all_from_range(
    id_range: IdRange,
    sink: Path,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = download_from_json,
) -> None:
    """
    Downloads relevant info from all valid process whose ID is within
    `id_range` and saves it into `sink`. Expects `sink` to be in JSONLines
    format.
    """
    ids = all_from(id_range, tj=TJRJ)
    download_function(list(ids), sink, cache_path, fetch_all_fields, filter_function)


def processes_by_subject(
    id_range: IdRange,
    words: Collection[str],
    download_function: DownloadFunction,
    output: Path,
    cache_path: Path,
) -> None:
    """Search for processes that contain the given words on its subject."""
    filter_function: Callable[[Process], bool]
    if words:
        print(f"Filtering by: {words}")
        filter_function = lambda item: has_words_in_subject(item, list(words))
    else:
        print("Empty 'words'. Word filtering will not be applied.")
        filter_function = lambda _: True

    # TODO: Utilizar os OOOO segundo o arquivo `sheet` que vai ser versionado.
    #       Reduz 4 dígitos da busca.
    # TODO: Dígitos verificadores vão ser chutados e, achando um válido, já se
    #       avança o número do processo. Reduz X% de 2 dígitos.
    all_from_range = set(all_from(id_range, tj=TJRJ))
    ids = list(all_from_range)

    download_all_with_ids(
        ids,
        output,
        cache_path,
        filter_function=filter_function,
        download_function=download_function,
    )
