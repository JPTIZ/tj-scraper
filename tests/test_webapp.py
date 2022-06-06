"""Tests webapp endpoints."""
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pyright: reportUnusedImport=false
import json
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from aioresponses import CallbackResult, aioresponses

from tj_scraper.process import get_process_id
from tj_scraper.webapp import make_webapp

from . import CACHE_PATH, LOCAL_URL, MOCK_DB, REAL_IDS
from .conftest import ignore_unused, reverse_lookup


@pytest.fixture
def webapp(local_tj, cache_db):
    ignore_unused(local_tj)

    webapp = make_webapp(cache_path=cache_db)
    webapp.config.update({"TESTING": True})

    yield webapp


@pytest.fixture
def client(webapp) -> FlaskClient:
    return webapp.test_client()


# TODO: Put these common function/fixtures in a common place.
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
            pprint(state, depth=3)
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


def test_sanity(client: FlaskClient) -> None:
    """
    Sanity-check. Tests if a straight forward request with all data downloading
    as json returns really all data.
    """
    ignore_unused(client)

    expected = MOCK_DB.values()

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "2021.001.150000-0",
            "intervalo_fim": "2021.001.150000-3",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)


def test_request_twice(client: FlaskClient) -> None:
    ignore_unused(client)

    expected = MOCK_DB.values()

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "2021.001.150000-0",
            "intervalo_fim": "2021.001.150000-3",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "2021.001.150000-0",
            "intervalo_fim": "2021.001.150000-3",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)
