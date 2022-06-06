"""Tests download functions."""
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pyright: reportUnusedImport=false
import json
from pathlib import Path

from aioresponses import aioresponses, CallbackResult
import pytest

from tj_scraper.download import download_from_json, processes_by_subject
from tj_scraper.process import has_words_in_subject, get_process_id

from . import CACHE_PATH, LOCAL_URL, MOCK_DB, REAL_IDS
from .conftest import ignore_unused, reverse_lookup


@pytest.fixture()
def local_tj():
    """
    Gives a aioresponses wrapper so aiohttp requests actually fallback to a
    local TJ database.
    """

    def callback(_, **kwargs):
        json = kwargs["json"]
        process_id = reverse_lookup(REAL_IDS, json["codigoProcesso"])
        payload = (
            MOCK_DB[process_id]
            if process_id is not None
            else ["Número do processo inválido."]
        )
        return CallbackResult(status=200, payload=payload)

    with aioresponses() as mocked_aiohttp:
        mocked_aiohttp.post(LOCAL_URL, callback=callback, repeat=True)
        yield mocked_aiohttp


@pytest.fixture()
def results_sink():
    """A sink file for tests' collected download items."""
    sink = Path("tests") / "test_results.jsonl"
    yield sink
    sink.unlink(missing_ok=True)


def retrieve_data(results_sink) -> list[dict[str, str]]:
    """Retrieves data collected stored in sink."""
    import jsonlines

    with jsonlines.open(results_sink) as sink:
        return list(sink)  # type: ignore


def has_same_entries(lhs, rhs):
    """
    Checks if `lhs` and `rhs` contain the same entries even if they're on
    different positions.
    """
    assert sorted(list(lhs), key=get_process_id) == sorted(list(rhs), key=get_process_id)  # type: ignore
    return True


def flatten(list_of_lists):
    """Flattens a list of lists into a simple 1D list."""
    return [item for sublist in list_of_lists for item in sublist]


def test_sanity(local_tj):
    """
    Sanity-check. Ensures aioresponses' wrapper's minimal funcionality is
    working accordingly.
    """
    ignore_unused(local_tj)

    import aiohttp
    import asyncio

    id_ = "1"

    async def sanity_check():
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LOCAL_URL,
                json={
                    "tipoProcesso": "1",
                    "codigoProcesso": REAL_IDS[id_],
                },
            ) as response:
                data = json.loads(await response.text())

        assert data == MOCK_DB[id_]

    asyncio.run(sanity_check())


def test_download_all_ids(local_tj, results_sink):
    """Tests if download functions is able to fetch all data."""
    ignore_unused(local_tj)

    request_ids = list(REAL_IDS.values())

    download_from_json(
        ids=request_ids,
        sink=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    has_same_entries(data, list(MOCK_DB.values()))


@pytest.mark.xfail(reason="Need to decide if sink should have only unique data")
def test_download_in_parts_without_overlap(local_tj, results_sink):
    """Tests if download function works when given ID ranges don't overlap/repeat."""
    ignore_unused(local_tj)

    request_ids = list(REAL_IDS.values())

    request_order = [request_ids[:1], request_ids[1:]]

    for request_ids in request_order:
        download_from_json(ids=request_ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert has_same_entries(data, MOCK_DB.values())


@pytest.mark.xfail(reason="Need to decide if sink should have only unique data")
def test_download_in_parts_with_overlap(local_tj, results_sink):
    """Tests if download function works when given ID ranges overlap/repeat."""
    ignore_unused(local_tj)

    request_ids = list(REAL_IDS.values())

    request_order = [request_ids[:2], request_ids[1:]]

    for request_ids in request_order:
        download_from_json(ids=request_ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)
    expected = list(MOCK_DB.values())

    assert has_same_entries(data, expected)


def test_download_with_subject_filter_one_word(local_tj, results_sink):
    """
    Tests if download function is able to filter only items that contains one
    specific word on their subjects.
    """
    ignore_unused(local_tj)

    # FIXME: This test actually doesn't filter subjects with `processes_with_subject`.
    expected = {k: v for k, v in MOCK_DB.items() if has_words_in_subject(v, ["furto"])}
    ids = [REAL_IDS[key] for key in expected.keys()]
    expected_values = sorted(expected.values(), key=get_process_id)

    download_from_json(ids=ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_download_with_subject_filter_multiple_word(local_tj, results_sink):
    """
    Tests if download function is able to filter only items that contains some
    specific words on their subjects.
    """
    ignore_unused(local_tj)

    expected = {
        v["codProc"]: v
        for _, v in MOCK_DB.items()
        if has_words_in_subject(v, ["furto", "receptação"])
    }
    ids = list(expected.keys())
    expected_values = sorted(expected.values(), key=get_process_id)

    download_from_json(ids=ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_processes_by_subject_one_is_invalid(local_tj, results_sink):
    """
    Tests if `processes_with_subject` properly handles invalid IDs.
    """
    ignore_unused(local_tj)

    expected = {
        REAL_IDS[k]: v for k, v in MOCK_DB.items() if v.get("txtAssunto") is not None
    }
    ids = [get_process_id(v) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_process_id)

    ids = min(ids), max(ids)

    processes_by_subject(
        id_range=ids,
        words=["furto"],
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_processes_by_subject_with_one_word(local_tj, results_sink):
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    expected = {
        REAL_IDS[k]: v for k, v in MOCK_DB.items() if has_words_in_subject(v, ["furto"])
    }
    ids = [get_process_id(v) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_process_id)

    ids = min(ids), max(ids)

    processes_by_subject(
        id_range=ids,
        words=["furto"],
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)


def test_download_same_processes_twice(local_tj, results_sink):
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    for curr_step in range(2):
        expected = {
            REAL_IDS[k]: v
            for k, v in MOCK_DB.items()
            if has_words_in_subject(v, ["furto"])
        }
        ids = [get_process_id(v) for v in expected.values()]
        expected_values = sorted(expected.values(), key=get_process_id)

        ids = min(ids), max(ids)

        processes_by_subject(
            id_range=ids,
            words=["furto"],
            download_function=download_from_json,
            output=results_sink,
            cache_path=CACHE_PATH,
        )

        print(f"Finished step {curr_step}")
        data = retrieve_data(results_sink)

        assert has_same_entries(data, expected_values)

        results_sink.unlink(missing_ok=True)


def test_download_processes_by_subject_with_empty_subject(local_tj, results_sink):
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    ignore_unused(local_tj)

    expected = {REAL_IDS[k]: v for k, v in MOCK_DB.items()}
    ids = [get_process_id(v) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_process_id)

    ids = min(ids), max(ids)

    processes_by_subject(
        id_range=ids,
        words="".split(),
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert has_same_entries(data, expected_values)
