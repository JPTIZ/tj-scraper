"""Tests download functions."""
# pylint: disable=redefined-outer-name
from pathlib import Path

from aioresponses import aioresponses
import pytest

from tj_scraper.download import download_from_json, processes_by_subject
from tj_scraper.process import has_words_in_subject, get_db_id

from . import CACHE_PATH, LOCAL_URL, MOCK_DB, REALISTIC_IDS


@pytest.fixture(autouse=True)
def show_cache_state(request):
    """Shows current cache state when a test fails."""
    from pprint import pprint

    yield

    if request.node.rep_call.failed:
        print("Download test failed. Cache state:")
        try:
            state = {
                i: {"ID": i, "CacheState": s, "Assunto": a, "JSON": v}
                for (i, s, a, v) in load_all(cache_path=CACHE_PATH)
            }
            pprint(state)
        except Exception as error:  # pylint: disable=broad-except
            print(" [ Failed to fetch cache state. ]")
            print(f" [ Reason: {error}. ]")


def load_all(cache_path: Path):
    """Loads entire database content. For small DBs only (e.g. testing)."""
    import json
    import sqlite3

    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()

        return [
            (id_, cache_state, assunto, json.loads(item_json))
            for id_, cache_state, assunto, item_json, in cursor.execute(
                "select id, cache_state, assunto, json from Processos",
            )
        ]
    return []


@pytest.fixture()
def local_tj():
    """
    Gives a aioresponses wrapper so aiohttp requests actually fallback to a
    local TJ database.
    """
    with aioresponses() as mocked_aiohttp:
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


def flatten(list_of_lists):
    """Flattens a list of lists into a simple 1D list."""
    return [item for sublist in list_of_lists for item in sublist]


def test_sanity(local_tj):
    """Sanity-check. Ensures aioresponses' wrapper is working accordingly."""
    import aiohttp
    import asyncio
    import json

    id_ = "1"

    local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    async def sanity_check():
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LOCAL_URL,
                json={
                    "tipoProcesso": "1",
                    "codigoProcesso": id_,
                },
            ) as response:
                data = json.loads(await response.text())

        assert data == MOCK_DB[id_]

    asyncio.run(sanity_check())


def test_download_all_ids(local_tj, results_sink):
    """Tests if download functions is able to fetch all data."""
    ids = list(MOCK_DB.keys())

    for id_ in ids:
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    download_from_json(
        ids=ids,
        sink=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert data == list(MOCK_DB.values())


def test_download_in_parts_without_overlap(local_tj, results_sink):
    """Tests if download function works when given ID ranges don't overlap/repeat."""
    ids = list(MOCK_DB.keys())

    request_order = [ids[:1], ids[1:]]

    for id_ in flatten(request_order):
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    for request_ids in request_order:
        download_from_json(ids=request_ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == list(MOCK_DB.values())


def test_download_in_parts_with_overlap(local_tj, results_sink):
    """Tests if download function works when given ID ranges overlap/repeat."""
    ids = list(MOCK_DB.keys())

    request_order = [ids[:2], ids[1:]]

    for id_ in flatten(request_order):
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    for request_ids in request_order:
        download_from_json(ids=request_ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)
    expected = list(MOCK_DB.values())

    assert data == expected


def test_download_with_subject_filter_one_word(local_tj, results_sink):
    """
    Tests if download function is able to filter only items that contains one
    specific word on their subjects.
    """
    # FIXME: This test actually doesn't filter subjects with `processes_with_subject`.
    expected = {k: v for k, v in MOCK_DB.items() if has_words_in_subject(v, ["furto"])}
    ids = list(expected.keys())
    expected_values = sorted(expected.values(), key=get_db_id)

    for id_ in ids:
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    download_from_json(ids=ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == expected_values


def test_download_with_subject_filter_multiple_word(local_tj, results_sink):
    """
    Tests if download function is able to filter only items that contains some
    specific words on their subjects.
    """
    expected = {
        k: v
        for k, v in MOCK_DB.items()
        if has_words_in_subject(v, ["furto", "receptação"])
    }
    ids = list(expected.keys())
    expected_values = sorted(expected.values(), key=get_db_id)

    for id_ in ids:
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    download_from_json(ids=ids, cache_path=CACHE_PATH, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == expected_values


def test_processes_by_subject_one_is_invalid(local_tj, results_sink):
    """
    Tests if `processes_with_subject` properly handles invalid IDs.
    """
    expected = {
        REALISTIC_IDS[k]: v
        for k, v in MOCK_DB.items()
        if v.get("txtAssunto") is not None
    }
    ids = [get_db_id(v) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_db_id)

    for expected in MOCK_DB.values():
        if expected.get("txtAssunto") is None:
            expected = ["Número do processo inválido."]
        local_tj.post(LOCAL_URL, payload=expected)

    ids = (REALISTIC_IDS[min(ids)], REALISTIC_IDS[max(ids)])

    processes_by_subject(
        id_range=ids,
        words=["furto"],
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert data == expected_values


def test_processes_by_subject_with_one_word(local_tj, results_sink):
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    expected = {
        REALISTIC_IDS[k]: v
        for k, v in MOCK_DB.items()
        if has_words_in_subject(v, ["furto"])
    }
    ids = [get_db_id(v) for v in expected.values()]
    expected_values = sorted(expected.values(), key=get_db_id)

    for process in MOCK_DB.values():
        local_tj.post(LOCAL_URL, payload=process)

    ids = (REALISTIC_IDS[min(ids)], REALISTIC_IDS[max(ids)])

    processes_by_subject(
        id_range=ids,
        words=["furto"],
        download_function=download_from_json,
        output=results_sink,
        cache_path=CACHE_PATH,
    )

    data = retrieve_data(results_sink)

    assert data == expected_values


def test_download_same_processes_twice(local_tj, results_sink):
    """
    Like `test_download_with_subject_filter_one_word`, but by calling
    `processes_with_subject`.
    """
    # TODO: Transform backend process handling into a function and use it in
    # every test.
    from aioresponses import CallbackResult

    def reverse_lookup(dict_, key):
        for k, value in dict_.items():
            if value == key:
                return k
        return None

    def callback(_, **kwargs):
        json = kwargs["json"]
        process_id = reverse_lookup(REALISTIC_IDS, json["codigoProcesso"])
        payload = (
            MOCK_DB[process_id]
            if process_id is not None
            else ["Número do processo inválido."]
        )
        return CallbackResult(status=200, payload=payload)

    for curr_step in range(2):
        expected = {
            REALISTIC_IDS[k]: v
            for k, v in MOCK_DB.items()
            if has_words_in_subject(v, ["furto"])
        }
        ids = [get_db_id(v) for v in expected.values()]
        expected_values = sorted(expected.values(), key=get_db_id)

        local_tj.post(LOCAL_URL, callback=callback, repeat=True)

        ids = (REALISTIC_IDS[min(ids)], REALISTIC_IDS[max(ids)])

        processes_by_subject(
            id_range=ids,
            words=["furto"],
            download_function=download_from_json,
            output=results_sink,
            cache_path=CACHE_PATH,
        )

        print(f"Finished step {curr_step}")
        data = retrieve_data(results_sink)
        data = sorted(list(data), key=get_db_id)

        assert data == expected_values
