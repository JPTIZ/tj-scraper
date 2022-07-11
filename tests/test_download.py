"""Tests download functions."""
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pyright: reportUnusedImport=false
import json
from pathlib import Path

from aioresponses import aioresponses

from tj_scraper.download import discover_with_json_api, processes_by_subject
from tj_scraper.process import (
    TJ_INFO,
    CNJNumberCombinations,
    JudicialSegment,
    has_words_in_subject,
)

from .fixtures import results_sink
from .helpers import has_same_entries, ignore_unused
from .mock import MOCKED_TJRJ_BACKEND_DB, REAL_IDS

ignore_unused(results_sink, reason="Fixtures")


def retrieve_data(results_sink: Path) -> list[dict[str, str]]:
    """Retrieves data collected stored in sink."""
    import jsonlines

    with jsonlines.open(results_sink) as sink:
        return list(sink)


def test_sanity(local_tj: Path) -> None:
    """
    Sanity-check. Ensures aioresponses' wrapper's minimal funcionality is
    working accordingly.
    """
    ignore_unused(local_tj)

    import asyncio

    import aiohttp

    id_ = "1"

    async def sanity_check() -> None:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TJ_INFO.tjs["rj"].main_endpoint,
                json={
                    "tipoProcesso": "1",
                    "codigoProcesso": REAL_IDS[id_],
                },
            ) as response:
                data = json.loads(await response.text())

        assert data == MOCKED_TJRJ_BACKEND_DB[id_]

    asyncio.run(sanity_check())


def test_download_single_number(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """Tests if download functions is able to fetch data from a single process."""
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        1, 1, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    discover_with_json_api(
        combinations=combinations,
        sink=results_sink,
        cache_path=cache_db,
    )

    processes = retrieve_data(results_sink)

    has_same_entries(processes, [MOCKED_TJRJ_BACKEND_DB["1"]])


def test_download_all_ids(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """Tests if download functions is able to fetch all data."""
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        1, 4, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    discover_with_json_api(
        combinations=combinations,
        sink=results_sink,
        cache_path=cache_db,
    )

    processes = retrieve_data(results_sink)

    has_same_entries(processes, list(MOCKED_TJRJ_BACKEND_DB.values()))


def test_download_with_subject_filter_one_word(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Tests if download function is able to filter only items that contains one
    specific word on their subjects.
    """
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        1, 4, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    expected = [MOCKED_TJRJ_BACKEND_DB[number] for number in ["1", "4"]]

    discover_with_json_api(
        combinations=combinations,
        cache_path=cache_db,
        sink=results_sink,
        filter_function=lambda process: has_words_in_subject(process, ["furto"]),
    )

    processes = retrieve_data(results_sink)

    assert has_same_entries(processes, expected)


def test_download_with_subject_filter_multiple_word(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Tests if download function is able to filter only items that contains some
    specific words on their subjects.
    """
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        1, 4, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    expected = [MOCKED_TJRJ_BACKEND_DB[number] for number in ["1", "3", "4"]]

    discover_with_json_api(
        combinations=combinations,
        cache_path=cache_db,
        sink=results_sink,
        filter_function=lambda process: has_words_in_subject(
            process, ["furto", "receptação"]
        ),
    )

    processes = retrieve_data(results_sink)

    assert has_same_entries(processes, expected)


def test_processes_by_subject_with_one_word(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        1, 4, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    expected = [MOCKED_TJRJ_BACKEND_DB[number] for number in ["1", "4"]]

    processes_by_subject(
        combinations=combinations,
        words=["furto"],
        download_function=discover_with_json_api,
        output=results_sink,
        cache_path=cache_db,
    )

    processes = retrieve_data(results_sink)

    assert has_same_entries(processes, expected)


def test_processes_by_subject_when_range_includes_invalid_number(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Tests if `processes_with_subject` properly handles combinations that
    include invalid numbers.
    """
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        0, 5, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    expected = [MOCKED_TJRJ_BACKEND_DB[number] for number in ["1", "4"]]

    processes_by_subject(
        combinations=combinations,
        words=["furto"],
        download_function=discover_with_json_api,
        output=results_sink,
        cache_path=cache_db,
    )

    processes = retrieve_data(results_sink)

    assert has_same_entries(processes, expected)


def test_download_same_processes_twice(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    for curr_step in range(2):
        combinations = CNJNumberCombinations(
            0, 5, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
        )

        expected = [MOCKED_TJRJ_BACKEND_DB[number] for number in ["1", "4"]]

        processes_by_subject(
            combinations=combinations,
            words=["furto"],
            download_function=discover_with_json_api,
            output=results_sink,
            cache_path=cache_db,
        )

        data = retrieve_data(results_sink)

        try:
            has_same_entries(data, expected)
        except AssertionError:
            print(f"Failed at step {curr_step}")
            raise

        results_sink.unlink(missing_ok=True)

        print(f"Finished step {curr_step}")


def test_download_processes_by_subject_with_empty_subject(
    cache_db: Path, local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    combinations = CNJNumberCombinations(
        1, 4, tj=TJ_INFO.tjs["rj"], year=2021, segment=JudicialSegment.JEDFT
    )

    expected = list(MOCKED_TJRJ_BACKEND_DB.values())

    processes_by_subject(
        combinations=combinations,
        words="".split(),
        download_function=discover_with_json_api,
        output=results_sink,
        cache_path=cache_db,
    )

    processes = retrieve_data(results_sink)

    assert has_same_entries(processes, expected)
