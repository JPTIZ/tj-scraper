"""Tests download functions."""
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pyright: reportUnusedImport=false
import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from tj_scraper.download import download_from_json, processes_by_subject
from tj_scraper.process import (
    TJ_INFO,
    IdRange,
    get_process_id,
    has_words_in_subject,
    to_cnj_number,
)

from .fixtures import results_sink
from .helpers import has_same_entries, ignore_unused
from .mock import CACHE_PATH, CNJ_IDS, MOCKED_TJRJ_BACKEND_DB, REAL_IDS

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


def test_download_single_id(local_tj: aioresponses, results_sink: Path) -> None:
    """Tests if download functions is able to fetch data from a single process."""
    ignore_unused(local_tj)

    request_id = to_cnj_number(CNJ_IDS["1"])

    download_from_json(
        ids=[request_id],
        sink=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)
    print(f"{data=}")

    has_same_entries(data, [MOCKED_TJRJ_BACKEND_DB["1"]])


def test_download_all_ids(local_tj: aioresponses, results_sink: Path) -> None:
    """Tests if download functions is able to fetch all data."""
    ignore_unused(local_tj)

    request_ids = [to_cnj_number(value) for value in CNJ_IDS.values()]

    download_from_json(
        ids=request_ids,
        sink=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    has_same_entries(data, list(MOCKED_TJRJ_BACKEND_DB.values()))


@pytest.mark.xfail(reason="Need to decide if sink should have only unique data")
def test_download_in_parts_without_overlap(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """Tests if download function works when given ID ranges don't overlap/repeat."""
    ignore_unused(local_tj)

    request_ids = [to_cnj_number(value) for value in REAL_IDS.values()]

    request_order = [request_ids[:1], request_ids[1:]]

    for request_ids in request_order:
        download_from_json(ids=request_ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert has_same_entries(data, MOCKED_TJRJ_BACKEND_DB.values())


@pytest.mark.xfail(reason="Need to decide if sink should have only unique data")
def test_download_in_parts_with_overlap(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """Tests if download function works when given ID ranges overlap/repeat."""
    ignore_unused(local_tj)

    request_ids = [to_cnj_number(value) for value in REAL_IDS.values()]

    request_order = [request_ids[:2], request_ids[1:]]

    for request_ids in request_order:
        download_from_json(ids=request_ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)
    expected = list(MOCKED_TJRJ_BACKEND_DB.values())

    assert has_same_entries(data, expected)


def test_download_with_subject_filter_one_word(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Tests if download function is able to filter only items that contains one
    specific word on their subjects.
    """
    ignore_unused(local_tj)

    # FIXME: This test actually doesn't filter subjects with `processes_with_subject`.
    expected = {
        k: v
        for k, v in MOCKED_TJRJ_BACKEND_DB.items()
        if has_words_in_subject(v, ["furto"])
    }
    ids = [to_cnj_number(CNJ_IDS[key]) for key in expected.keys()]
    expected_values = sorted(expected.values(), key=get_process_id)

    download_from_json(ids=ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_download_with_subject_filter_multiple_word(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Tests if download function is able to filter only items that contains some
    specific words on their subjects.
    """
    ignore_unused(local_tj)

    expected = {
        str(v["codCnj"]): v
        for _, v in MOCKED_TJRJ_BACKEND_DB.items()
        if has_words_in_subject(v, ["furto", "receptação"])
    }
    ids = [to_cnj_number(key) for key in expected.keys()]
    expected_values = sorted(expected.values(), key=get_process_id)

    download_from_json(ids=ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_processes_by_subject_one_is_invalid(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Tests if `processes_with_subject` properly handles invalid IDs.
    """
    ignore_unused(local_tj)

    expected = {
        CNJ_IDS[k]: v
        for k, v in MOCKED_TJRJ_BACKEND_DB.items()
        if v.get("txtAssunto") is not None
    }
    ids = [to_cnj_number(get_process_id(v)) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_process_id)

    id_range = IdRange(min(ids), max(ids))

    processes_by_subject(
        id_range=id_range,
        words=["furto"],
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_processes_by_subject_with_one_word(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    expected = {
        REAL_IDS[k]: v
        for k, v in MOCKED_TJRJ_BACKEND_DB.items()
        if has_words_in_subject(v, ["furto"])
    }
    ids = [get_process_id(v) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_process_id)

    id_range = IdRange(to_cnj_number(min(ids)), to_cnj_number(max(ids)))

    processes_by_subject(
        id_range=id_range,
        words=["furto"],
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_download_same_processes_twice(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    for curr_step in range(2):
        expected = {
            REAL_IDS[k]: v
            for k, v in MOCKED_TJRJ_BACKEND_DB.items()
            if has_words_in_subject(v, ["furto"])
        }
        ids = [to_cnj_number(get_process_id(v)) for v in expected.values()]
        expected_values = sorted(expected.values(), key=get_process_id)

        id_range = IdRange(min(ids), max(ids))

        processes_by_subject(
            id_range=id_range,
            words=["furto"],
            download_function=download_from_json,
            output=results_sink,
            cache_path=CACHE_PATH,
        )

        print(f"Finished step {curr_step}")
        data = retrieve_data(results_sink)

        assert has_same_entries(data, expected_values)

        results_sink.unlink(missing_ok=True)


def test_download_processes_by_subject_with_empty_subject(
    local_tj: aioresponses, results_sink: Path
) -> None:
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    expected = {REAL_IDS[k]: v for k, v in MOCKED_TJRJ_BACKEND_DB.items()}
    ids = [to_cnj_number(get_process_id(v)) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_process_id)

    id_range = IdRange(min(ids), max(ids))

    processes_by_subject(
        id_range=id_range,
        words="".split(),
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)
