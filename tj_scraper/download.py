"""Responsible for handling data downloading."""
import json
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Iterable, Optional, TypeVar

import aiohttp
import jsonlines

from .cache import (
    CacheState,
    DBProcess,
    filter_cached,
    restore_json_for_ids,
    save_to_cache,
)
from .process import (
    REAL_ID_FIELD,
    TJ,
    TJ_INFO,
    CNJProcessNumber,
    IdRange,
    ProcessJSON,
    TJInfo,
    advance,
    all_from,
    get_process_id,
    has_words_in_subject,
    iter_in_range,
    make_cnj_code,
    next_number,
)
from .timing import report_time

FilterFunction = Callable[[ProcessJSON], bool]
DownloadFunction = Callable[
    [list[CNJProcessNumber], Path, Path, bool, FilterFunction], None
]


T = TypeVar("T")


def chunks(iterable: Iterable[T], n: int) -> Iterable[list[T]]:
    iterator = iter(iterable)

    while True:
        chunk = list(x for _, x in zip(range(n), iterator))

        if not chunk:
            return

        yield chunk


def write_to_sink(items: list[ProcessJSON], sink: Path, reason: str) -> None:
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
    ids: list[CNJProcessNumber],
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction,
) -> list[CNJProcessNumber]:
    """
    Write only items with given IDs that are cached into the sink and returns
    which are not cached.
    """
    filtered = report_time(filter_cached, ids, cache_path=cache_path).value

    def cache_filter(item: DBProcess) -> bool:
        return filter_function(item.json)

    cached_items = restore_json_for_ids(
        cache_path,
        list(filtered.cached),
        filter_function=cache_filter,
    )

    write_to_sink(cached_items, sink=sink, reason="Cached")

    return list(filtered.not_cached)


class FetchResultType(Enum):
    CAPTCHA = auto()
    FILTERED = auto()
    INVALID = auto()
    NOT_FOUND = auto()
    SUCCESS = auto()


@dataclass
class FetchResult:
    result_type: FetchResultType
    process: Optional[ProcessJSON]


# pylint: disable=invalid-name
async def fetch_process(
    session: aiohttp.ClientSession,
    cnj_number: CNJProcessNumber,
    tj: TJ,
) -> FetchResult:
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

    cnj_id_str = make_cnj_code(cnj_number)

    # cnj_endpoint
    if tj.name == "rj":
        async with session.post(
            tj.cnj_endpoint,
            json={
                "codCnj": cnj_id_str,
            },
        ) as response:
            partial_data = json.loads(await response.text())

        if partial_data == ["Número do processo inválido."]:
            return FetchResult(result_type=FetchResultType.INVALID, process=None)

        local_id = partial_data["codProc"]
    else:
        local_id = cnj_id_str

    # main_endpoint
    data: dict[str, Any]
    async with session.post(
        tj.main_endpoint,
        json={
            "tipoProcesso": "1",
            "codigoProcesso": local_id,
        },
        ssl=False,  # FIXME: Properly handle TJ's outdated certificate
    ) as response:
        data = json.loads(await response.text())

    match data:
        case ["O processo informado não foi encontrado."]:
            return FetchResult(result_type=FetchResultType.NOT_FOUND, process=None)
        case ["Número do processo inválido."]:
            return FetchResult(result_type=FetchResultType.INVALID, process=None)
        case {
            "status": 412,
            "mensagem": "Erro de validação do Recaptcha. Tente novamente.",
        }:
            return FetchResult(result_type=FetchResultType.CAPTCHA, process=None)

    print(f"Fetched process {cnj_number}: {data.get('txtAssunto', 'Sem Assunto')}")
    return FetchResult(result_type=FetchResultType.SUCCESS, process=data)


def download_from_json(
    ids: list[CNJProcessNumber],
    sink: Path,
    cache_path: Path,
    fetch_all_fields: bool = True,
    filter_function: FilterFunction = lambda _: True,
    # pylint: disable=dangerous-default-value
    tj_info: TJInfo = TJ_INFO,
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
            ids=ids,
            sink=sink,
            cache_path=cache_path,
            filter_function=filter_function,
        )

    tj_by_code = {tj.code: name for name, tj in tj_info.tjs.items()}

    def classify_and_cache(
        fetch_result: FetchResult, cnj_number: CNJProcessNumber
    ) -> FetchResult:
        cnj_id_str = make_cnj_code(cnj_number)

        if fetch_result.result_type == FetchResultType.INVALID:
            print(f"{cnj_number}: Invalid -- Cached now")
            save_to_cache(
                {REAL_ID_FIELD: cnj_id_str},
                cache_path,
                state=CacheState.INVALID,
            )
        elif fetch_result.result_type == FetchResultType.NOT_FOUND:
            print(f"{cnj_number}: Not found -- Cached now")
            save_to_cache(
                {REAL_ID_FIELD: cnj_id_str},
                cache_path,
                state=CacheState.INVALID,
            )
        elif fetch_result.result_type == FetchResultType.CAPTCHA:
            print(f"{cnj_number}: Unfetched, failed on recaptcha.")
        elif fetch_result.process is not None:
            save_to_cache(fetch_result.process, cache_path, state=CacheState.CACHED)

        if fetch_result.process is not None and not filter_function(
            fetch_result.process
        ):
            subject = fetch_result.process.get("txtAssunto", "Sem Assunto")
            print(
                f"{cnj_number}: Filtered  -- ({subject}) -- Cached now ({fetch_result.process=})"
            )
            return FetchResult(result_type=FetchResultType.FILTERED, process=None)

        return fetch_result

    # FIXME: lidar com dígito-verificador != 00
    async def fetch_and_eval(
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        cnj_number: CNJProcessNumber,
    ) -> FetchResult:
        tj = tj_info.tjs[tj_by_code[cnj_number.tr_code]]

        end = next_number(cnj_number)
        if end is None:
            end = CNJProcessNumber(
                number=cnj_number.number,
                digits=99,
                year=cnj_number.year,
                tr_code=cnj_number.tr_code,
                source_unit=tj.source_units[-1].code,
            )
        test_range = IdRange(cnj_number, end)

        await semaphore.acquire()

        fetch_result = None

        # guess_requests = (
        #     fetch_process(session, guess, tj=tj)
        #     for guess in iter_in_range(test_range, tj=tj)
        # )
        # print(guess_requests)
        # guesses = await asyncio.gather(*guess_requests)
        # for guess in guesses:
        #     if guess.result_type == FetchResultType.SUCCESS:
        #         fetch_result = guess
        for guess in iter_in_range(test_range, tj=tj):
            fetch_result = await fetch_process(
                session,
                guess,
                tj=tj,
            )
            if fetch_result.result_type == FetchResultType.SUCCESS:
                break

        assert fetch_result is not None

        fetch_result = classify_and_cache(fetch_result, cnj_number=cnj_number)

        semaphore.release()

        return fetch_result

    async def fetch_all_processes(
        numbers: list[CNJProcessNumber], step: int = 100
    ) -> int:
        total = 0
        async with aiohttp.ClientSession(trust_env=True) as session:
            semaphore = asyncio.Semaphore(value=step)
            requests = (
                fetch_and_eval(session, semaphore, number) for number in numbers
            )
            for i, batch in enumerate(chunks(requests, 1000), start=1):
                print(f"\n--\n-- Wave: {i}")
                results = await asyncio.gather(*batch)
                processes = [
                    result.process for result in results if result.process is not None
                ]

                write_to_sink(processes, sink, reason=f"Fetched (Batch {i})")

                filtered = sum(
                    1 if result.result_type == FetchResultType.FILTERED else 0
                    for result in results
                )
                invalid = sum(
                    1 if result.result_type == FetchResultType.INVALID else 0
                    for result in results
                )

                partial_ids = [get_process_id(process) for process in processes]

                print(
                    f"Partial result: {partial_ids} ({filtered} filtered, {invalid} invalid)"
                )
                total += len(processes)
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
    ids: list[CNJProcessNumber],
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
    ids: list[CNJProcessNumber],
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
    ids = all_from(id_range, tj=TJ_INFO.tjs["rj"])
    download_function(list(ids), sink, cache_path, fetch_all_fields, filter_function)


def processes_by_subject(
    id_range: IdRange,
    words: Collection[str],
    download_function: DownloadFunction,
    output: Path,
    cache_path: Path,
) -> None:
    """Search for processes that contain the given words on its subject."""
    filter_function: Callable[[ProcessJSON], bool]
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
    # all_from_range = set(all_from(id_range, tj=TJ_INFO.tjs["rj"]))
    ids_as_range = range(id_range.start.number, id_range.end.number + 1)

    ids = [
        CNJProcessNumber(**{**id_range.start._asdict(), "number": id_})
        for id_ in ids_as_range
    ]

    download_all_with_ids(
        ids,
        output,
        cache_path,
        filter_function=filter_function,
        download_function=download_function,
    )
