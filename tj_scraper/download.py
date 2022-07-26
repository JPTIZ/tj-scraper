"""Responsible for handling data downloading."""
import asyncio
import json
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Coroutine, Iterable, Sequence, TypedDict, TypeVar

import aiohttp
import jsonlines

from .cache import (
    CacheState,
    DBProcess,
    filter_cached,
    restore_json_for_ids,
    save_to_cache,
)
from .errors import UnknownTJResponse
from .process import (
    REAL_ID_FIELD,
    TJ,
    CNJNumberCombinations,
    CNJProcessNumber,
    JudicialSegment,
    ProcessJSON,
    get_process_id,
    has_words_in_subject,
    make_cnj_number_str,
)
from .timing import report_time

FilterFunction = Callable[[ProcessJSON], bool]
DownloadFunction = Callable[[CNJNumberCombinations, Path, Path, FilterFunction], None]


T = TypeVar("T")


def chunks(
    iterable: Iterable[T], n: int  # pylint: disable=invalid-name
) -> Iterable[list[T]]:
    """Iters in batches of a maximum of `n` elements."""
    iterator = iter(iterable)

    while True:
        chunk = list(x for _, x in zip(range(n), iterator))

        if not chunk:
            return

        yield chunk


def write_to_sink(items: Sequence[ProcessJSON], sink: Path, reason: str) -> None:
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
    combinations: CNJNumberCombinations,
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction,
) -> list[int]:
    """
    Write only items with given IDs that are cached into the sink and returns
    which are not cached.
    """
    sequence = range(combinations.sequence_start, combinations.sequence_end + 1)
    filtered = report_time(
        filter_cached, sequence, year=combinations.year, cache_path=cache_path
    ).value
    print(f"{filtered=}")

    def cache_filter(item: DBProcess) -> bool:
        return filter_function(item.json)

    cached_items = restore_json_for_ids(
        cache_path,
        list(filtered.cached),
        filter_function=cache_filter,
    )

    write_to_sink(cached_items, sink=sink, reason="Cached")

    return list(filtered.not_cached)


class FetchFailReason(Enum):
    """Reasons for a fetch operation to fail."""

    CAPTCHA = auto()
    FILTERED = auto()
    INVALID = auto()
    NOT_FOUND = auto()
    UNSUPPORTED = auto()


FetchResult = FetchFailReason | ProcessJSON
TJResponse = list[str | ProcessJSON] | ProcessJSON


class TJRequestParams(TypedDict):
    """URL parameters for a request to TJ-RJ page."""

    tipoProcesso: str
    codigoProcesso: str


def classify(
    response: TJResponse,
    cnj_number: CNJProcessNumber,
    tj: TJ,  # pylint: disable=invalid-name
) -> FetchResult:
    """
    Classifies the result of a fetch operation as an expected error type or a
    process' data in JSON format.
    """
    item: ProcessJSON
    items: list[str | ProcessJSON]
    match response:
        case ["O processo informado não foi encontrado."]:
            return FetchFailReason.NOT_FOUND
        case ["Número do processo inválido."]:
            return FetchFailReason.INVALID
        case {
            "status": 412,
            "mensagem": "Erro de validação do Recaptcha. Tente novamente.",
        }:
            return FetchFailReason.CAPTCHA
        case {"urlExterna": _} | {"tipoProcesso": 2}:
            return FetchFailReason.UNSUPPORTED
        case list() as items:
            for process in items:
                assert not isinstance(process, str)

                print(
                    f"Fetched process {make_cnj_number_str(cnj_number)}:"
                    f" {process.get('txtAssunto', 'Sem Assunto')}"
                )
                return process
        case dict() as item if item.get("tipoProcesso", 1) == 1:
            print(
                f"Fetched process {make_cnj_number_str(cnj_number)}:"
                f" {item.get('txtAssunto', 'Sem Assunto')}"
            )
            return item

    from pprint import pformat

    raise UnknownTJResponse(
        f"TJ-{tj.name.upper()} endpoint responded with unknown message format"
        f" ({type(response)=}) for input {cnj_number}:\n"
        f" {pformat(response)}"
    )
    # [{'assunto': 'Antecipação de Tutela / Tutela Específica / Processo e '
    #             'Procedimento / DIREITO PROCESSUAL CIVIL E DO TRABALHO',
    #  'classe': 'AGRAVO DE INSTRUMENTO - CÍVEL',
    #  'codigoCnj': '0015714-63.2021.8.19.0000',
    #  'descricaoServentia': 'DÉCIMA OITAVA CAMARA CIVEL',
    #  'isProcessoVirtual': True,
    #  'nomeComarca': 'Comarca da Capital',
    #  'numProcesso': '2021.002.19959',
    #  'tipoProcesso': 2,
    #  'url': 'https://www3.tjrj.jus.br/ejud/ConsultaProcesso.aspx?N=2021.002.19959'}]


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
    # TODO: É possível criar um "parou aqui" para poder continuar o trabalho em
    # momentos variados: basta salvar o último "batch" (conjunto de NNNNNNN's,
    # DD's e OOOO's).

    cnj_number_str = make_cnj_number_str(cnj_number)

    request_args = TJRequestParams(tipoProcesso="1", codigoProcesso=cnj_number_str)

    # cnj_endpoint
    raw_response: TJResponse
    if tj.name == "rj":
        async with session.post(
            tj.cnj_endpoint,
            json=request_args,
            ssl=False,  # FIXME: Properly handle TJ's outdated certificate
        ) as response:
            raw_response = json.loads(await response.text())

        fetch_result = classify(raw_response, cnj_number, tj)

        if isinstance(fetch_result, FetchFailReason):
            return fetch_result

        request_args = TJRequestParams(
            tipoProcesso=str(fetch_result.get("tipoProcesso")),
            codigoProcesso=str(fetch_result.get("numProcesso")),
        )
    else:
        request_args = TJRequestParams(tipoProcesso="1", codigoProcesso=cnj_number_str)

    # main_endpoint
    async with session.post(
        tj.main_endpoint,
        json=request_args,
        ssl=False,  # FIXME: Properly handle TJ's outdated certificate
    ) as response:
        raw_response = json.loads(await response.text())

    return classify(raw_response, cnj_number, tj)


@dataclass(frozen=True)
class CNJNumberCombination:
    """A combination of values for a specific NNNNNNN value."""

    sequential_number: int
    year: int
    segment: JudicialSegment
    tj: TJ


def classify_and_cache(
    fetch_result: FetchResult,
    cnj_number: CNJProcessNumber,
    cache_path: Path,
    filter_function: FilterFunction,
) -> FetchResult:
    """
    Classifies the result of a fetch operation as an expected error type or a
    process' data in JSON format and then updates cache accordinly.
    """
    cnj_number_str = make_cnj_number_str(cnj_number)

    match fetch_result:
        case FetchFailReason.INVALID:
            print(f"{cnj_number_str}: Invalid -- Cached now")
            save_to_cache(
                {REAL_ID_FIELD: cnj_number_str},
                cache_path,
                state=CacheState.INVALID,
            )
        case FetchFailReason.NOT_FOUND:
            print(f"{cnj_number_str}: Not found -- Cached now")
            save_to_cache(
                {REAL_ID_FIELD: cnj_number_str},
                cache_path,
                state=CacheState.INVALID,
            )
        case FetchFailReason.CAPTCHA:
            print(f"{cnj_number_str}: Unfetched, failed on recaptcha.")
        case FetchFailReason.UNSUPPORTED:
            print(
                f"{cnj_number_str}: Unsupported 2nd instance process. Won't be cached."
            )
        case FetchFailReason.FILTERED:
            raise NotImplementedError(
                "Filtered without running filter function should not be possible."
            )
        case process:

            save_to_cache(process, cache_path, state=CacheState.CACHED)

            if not filter_function(process):
                subject = process.get("txtAssunto", "Sem Assunto")
                print(
                    f"{cnj_number_str}: Filtered"
                    f" -- ({subject}) -- Cached now ({process=})"
                )
                return FetchFailReason.FILTERED

    return fetch_result


async def try_combinations(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    combination: CNJNumberCombination,
    filter_function: FilterFunction,
    cache_path: Path,
) -> FetchResult:
    """
    Attempts to find which combination of values for CNJ number's fields
    result in a real process.
    """
    from contextlib import asynccontextmanager
    from typing import AsyncGenerator

    @asynccontextmanager
    async def ensure_released(
        semaphore: asyncio.Semaphore,
    ) -> AsyncGenerator[None, None]:
        await semaphore.acquire()
        yield
        semaphore.release()

    test_range = CNJNumberCombinations(
        combination.sequential_number,
        combination.sequential_number,
        tj=combination.tj,
        year=combination.year,
        segment=combination.segment,
    )

    async with ensure_released(semaphore):
        fetch_result = None

        for guess in test_range:
            fetch_result = await fetch_process(
                session,
                guess,
                tj=combination.tj,
            )

            fetch_result = classify_and_cache(
                fetch_result, guess, cache_path, filter_function
            )

            if (
                not isinstance(fetch_result, FetchFailReason)
                or fetch_result == FetchFailReason.FILTERED
            ):
                break

    assert fetch_result is not None

    return fetch_result


BatchArgs = Iterable[FetchFailReason | ProcessJSON]


async def run_batch(
    batch: Iterable[Coroutine[BatchArgs, BatchArgs, FetchResult]]
) -> Iterable[FetchResult]:
    """
    Runs a batch of coroutines. Used to isolate async dispatch for sync
    simulation in statistics.py.
    """
    return await asyncio.gather(*batch)


@dataclass(frozen=True)
class BatchSummary:
    """Summary of a batch execution."""

    processes: Sequence[ProcessJSON]
    filtered: int
    invalid: int


def summarize_batch_results(batch_results: Iterable[FetchResult]) -> BatchSummary:
    """Summarizes data about results from a batch of process fetch operations."""
    processes = []
    filtered = 0
    invalid = 0
    for result in batch_results:
        match result:
            case FetchFailReason.FILTERED:
                filtered += 1
            case FetchFailReason.INVALID:
                invalid += 1
            case dict() as process:
                processes.append(process)
    return BatchSummary(
        processes=processes,
        filtered=filtered,
        invalid=invalid,
    )


async def discover_processes(
    sequential_numbers: list[int],
    year: int,
    segment: JudicialSegment,
    tj: TJ,
    filter_function: FilterFunction,
    cache_path: Path,
    sink: Path,
    batch_size: int = 100,
) -> int:
    """
    Discovers valid processes existing in a NNNNNNN interval and returns how
    many were found.
    """
    total = 0
    async with aiohttp.ClientSession(trust_env=True) as session:
        semaphore = asyncio.Semaphore(value=batch_size)
        requests = (
            try_combinations(
                session,
                semaphore,
                CNJNumberCombination(number, year, segment, tj),
                filter_function,
                cache_path,
            )
            for number in sequential_numbers
        )
        for i, batch in enumerate(chunks(requests, 1000), start=1):
            print(f"\n--\n-- Batch: {i}")
            summary = summarize_batch_results(await run_batch(batch))

            write_to_sink(summary.processes, sink, reason=f"Fetched (Batch {i})")

            print(
                f"Partial result: {[get_process_id(p) for p in summary.processes]}"
                f" ({summary.filtered} filtered, {summary.invalid} invalid)"
            )
            total += len(summary.processes)
        return total


def discover_with_json_api(
    combinations: CNJNumberCombinations,
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction = lambda _: True,
    force_fetch: bool = False,
    batch_size: int = 100,
) -> None:
    """
    Downloads data from urls that return JSON values. Previously cached results
    are used by default if `force_fetch` is not set to `True`.
    """
    from pprint import pformat

    print(f"discover_with_json_api({pformat(combinations, depth=2)})")

    not_cached_numbers = (
        list(range(combinations.sequence_start, combinations.sequence_end + 1))
        if force_fetch
        else []
    )
    if not force_fetch:
        not_cached_numbers = write_cached_to_sink(
            combinations=combinations,
            sink=sink,
            cache_path=cache_path,
            filter_function=filter_function,
        )

    from time import time

    start = time()
    result = asyncio.run(
        discover_processes(
            not_cached_numbers,
            combinations.year,
            combinations.segment,
            combinations.tj,
            filter_function,
            cache_path,
            sink,
            batch_size=batch_size,
        )
    )
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

    start_urls = [build_tjrj_process_url(make_cnj_number_str(id_)) for id_ in ids]
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
    combinations: CNJNumberCombinations,
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = discover_with_json_api,
) -> None:
    """
    Downloads relevant info from all valid process with ID in `ids` and saves
    it into `sink`. Expects `sink` to be in JSONLines format.
    """
    from pprint import pformat

    print(f"download_all_with_ids({pformat(combinations, depth=1)})")
    download_function(combinations, sink, cache_path, filter_function)


def download_all_from_range(
    number_range: CNJNumberCombinations,
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction = lambda _: True,
    download_function: DownloadFunction = discover_with_json_api,
) -> None:
    """
    Downloads relevant info from all valid process whose ID is within
    `id_range` and saves it into `sink`. Expects `sink` to be in JSONLines
    format.
    """
    download_function(number_range, sink, cache_path, filter_function)


def processes_by_subject(
    combinations: CNJNumberCombinations,
    words: Collection[str],
    download_function: DownloadFunction,
    output: Path,
    cache_path: Path,
) -> None:
    """Search for processes that contain the given words on its subject."""

    def filter_function(item: ProcessJSON) -> bool:
        return has_words_in_subject(item, list(words)) if words else True

    if words:
        print(f"Filtering by: {words}")
    else:
        print("Empty 'words'. Word filtering will not be applied.")

    download_all_with_ids(
        combinations,
        output,
        cache_path,
        filter_function=filter_function,
        download_function=download_function,
    )
