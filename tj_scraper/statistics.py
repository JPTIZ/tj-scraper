"""Module for statistic data generation."""
import cProfile
import json
import time
from contextlib import contextmanager
from pathlib import Path
from pstats import SortKey, Stats
from typing import Any, Callable, Generator, Iterable, ParamSpec, TypeVar

import requests

# import tj_scraper.download


def qualquer_merda(*args: Any, **kwargs: Any) -> None:
    print(f"qualquer_merda({args=}, {kwargs=})")


# setattr(tj_scraper.download, "download_from_json", qualquer_merda)

from tj_scraper.download import (
    FetchFailReason,
    FetchResult,
    FilterFunction,
    TJRequestParams,
    TJResponse,
    chunks,
    classify_and_cache,
    write_cached_to_sink,
    write_to_sink,
)
from tj_scraper.errors import UnknownTJResponse
from tj_scraper.process import (
    TJ,
    TJ_INFO,
    CNJProcessNumber,
    IdRange,
    TJInfo,
    get_process_id,
    iter_in_range,
    make_cnj_code,
    next_number,
)


def fetch_process(
    session: requests.Session,
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

    def classify(response: TJResponse) -> FetchResult:
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
            case ([success] | success) if isinstance(success, dict):
                print(
                    f"Fetched process {cnj_number}: {success.get('txtAssunto', 'Sem Assunto')}"
                )
                return success
        raise UnknownTJResponse(
            f"TJ-{tj.name.upper()} endpoint responded with unknown message format: {response}"
        )

    cnj_number_str = make_cnj_code(cnj_number)

    request_args = TJRequestParams(tipoProcesso="1", codigoProcesso=cnj_number_str)

    # cnj_endpoint
    raw_response: TJResponse
    if tj.name == "rj":
        with session.post(
            tj.cnj_endpoint,
            json=request_args,
            verify=False,  # FIXME: Properly handle TJ's outdated certificate
        ) as response:
            raw_response = json.loads(response.text)

        fetch_result = classify(raw_response)

        print(f"{request_args=} = {fetch_result}")

        if isinstance(fetch_result, FetchFailReason):
            return fetch_result

        request_args = TJRequestParams(
            tipoProcesso=str(fetch_result["tipoProcesso"]),
            codigoProcesso=str(fetch_result["numProcesso"]),
        )
    else:
        request_args = TJRequestParams(tipoProcesso="1", codigoProcesso=cnj_number_str)

    # main_endpoint
    with session.post(
        tj.main_endpoint,
        json=request_args,
        verify=False,  # FIXME: Properly handle TJ's outdated certificate
    ) as response:
        raw_response = json.loads(response.text)

    return classify(raw_response)


def download_from_json(
    ids: list[CNJProcessNumber],
    sink: Path,
    cache_path: Path,
    filter_function: FilterFunction = lambda _: True,
    # pylint: disable=dangerous-default-value
    tj_info: TJInfo = TJ_INFO,
    force_fetch: bool = False,
) -> None:
    """
    Downloads data from urls that return JSON values. Previously cached results
    are used by default if `force_fetch` is not set to `True`.
    """
    import requests

    print(f"download_from_json({ids=})")

    if not force_fetch:
        ids = write_cached_to_sink(
            ids=ids,
            sink=sink,
            cache_path=cache_path,
            filter_function=filter_function,
        )

    tj_by_code = {tj.code: name for name, tj in tj_info.tjs.items()}

    def fetch_and_eval(
        session: requests.Session,
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

        fetch_result = None

        for i, guess in enumerate(iter_in_range(test_range, tj=tj)):
            fetch_result = fetch_process(
                session,
                guess,
                tj=tj,
            )
            if not isinstance(fetch_result, FetchFailReason):
                break

            if i > 100:
                break

        assert fetch_result is not None

        fetch_result = classify_and_cache(
            fetch_result, cnj_number, cache_path, filter_function
        )

        return fetch_result

    def fetch_all_processes(numbers: list[CNJProcessNumber]) -> int:
        total = 0
        with requests.Session() as session:
            requests_ = (fetch_and_eval(session, number) for number in numbers)
            for i, batch in enumerate(chunks(requests_, 1000), start=1):
                print(f"\n--\n-- Wave: {i}")
                results: Iterable[FetchResult] = batch
                processes = []
                filtered = 0
                invalid = 0
                for result in results:
                    match result:
                        case FetchFailReason.FILTERED:
                            filtered += 1
                        case FetchFailReason.INVALID:
                            invalid += 1
                        case dict() as process:
                            print(f"{process=}")
                            processes.append(process)

                write_to_sink(processes, sink, reason=f"Fetched (Batch {i})")

                partial_ids = [get_process_id(process) for process in processes]

                print(
                    f"Partial result: {partial_ids} ({filtered} filtered, {invalid} invalid)"
                )
                total += len(processes)
            return total

    from time import time

    start = time()
    result = fetch_all_processes(ids)
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


# from .download import download_from_json
from .process import to_cnj_number

CACHE_PATH = Path("b.db")


@contextmanager
def autodelete(path: Path) -> Generator[Path, None, None]:
    yield path
    path.unlink(missing_ok=True)


@contextmanager
def no_stdout() -> Generator[None, None, None]:
    import os
    import sys

    # yield
    # return

    with open(os.devnull, "w") as devnull:
        old_stdout, sys.stdout = sys.stdout, devnull
        yield
        sys.stdout = old_stdout


def io_timer() -> float:
    import os

    timing = os.times()
    return timing.elapsed - (timing.system + timing.user)


def fake_download_from_json(*_: Any, **__: Any) -> None:
    print("fake")
    import time

    x: list[int] = []
    for i in range(100):
        x.insert(i, 0)
    time.sleep(1)


cpu_timer = time.process_time

STATS_PATH = Path("profile-stats.txt")

Time = int | float
Timer = Callable[[], Time]

Return = TypeVar("Return")
Args = ParamSpec("Args")


def profile(function: Callable[Args, Any], timer: Timer | None) -> None:
    timer_arg: dict[str, Any] = {"timer": timer} if timer is not None else {}

    profiler = cProfile.Profile(**timer_arg)

    with autodelete(CACHE_PATH):
        profiler.runcall(function)

    profiler.create_stats()

    stats = Stats(profiler)
    stats.dump_stats(STATS_PATH)

    profiler.print_stats(sort="cumtime")


def view_profile(path: Path) -> None:
    stats = Stats(path.resolve().as_posix())
    profile = stats.get_stats_profile()
    from pprint import pprint

    total_time = profile.total_tt
    function_profiles = profile.func_profiles

    pprint([value for key, value in profile.func_profiles.items() if "poll" in key])

    network_io_keys = [
        "<method 'poll' of 'select.epoll' objects>",
        "<method 'poll' of 'select.poll' objects>",
    ]

    network_time = -1
    for network_io_key in network_io_keys:
        try:
            network_function_profile = function_profiles[network_io_key]
            pprint(network_function_profile)
            network_time = network_function_profile.tottime
        except KeyError:
            pass
    if network_time == -1:
        print("Failed to get network time (now known poll function found).")
        return

    print(f"Total time: {total_time}")
    print(f"Network time: {network_time}")
    print(f"Non-Network time: {total_time - network_time}")
    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats()


if __name__ == "__main__":
    ids = [
        to_cnj_number(number)
        for number in [
            "0015712-81.2021.8.19.0004",
            # "0005751-35.1978.8.19.0001",
            # "0196091-26.2021.8.19.0001",
        ]
    ]
    function = lambda: download_from_json(
        ids=ids, sink=Path("a.jsonl"), cache_path=CACHE_PATH
    )
    timer = io_timer

    import sys

    if len(sys.argv) == 1:
        print(f"Usage: {sys.argv[0]} <dump | view>")

    if sys.argv[1] == "dump":
        print("⬇️ (início)")
        profile(function, timer)
        print("⬇️ (fim)")
    if sys.argv[1] == "view":
        print("👀 (início)")
        view_profile(STATS_PATH)
        print("👀 (fim)")
