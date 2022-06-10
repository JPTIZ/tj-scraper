"""Tests webapp endpoints."""
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pyright: reportUnusedImport=false
import json
from pathlib import Path
from typing import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from aioresponses import aioresponses

from tj_scraper.cache import load_all
from tj_scraper.process import Process
from tj_scraper.webapp import make_webapp

from . import CACHE_PATH, MOCK_DB, REAL_IDS
from .fixtures import local_tj, results_sink
from .helpers import ignore_unused, has_same_entries, reverse_lookup


ignore_unused(local_tj, results_sink, reason="Fixtures")


@pytest.fixture
def webapp(local_tj: aioresponses, cache_db: Path) -> Generator[Flask, None, None]:
    ignore_unused(local_tj)

    webapp = make_webapp(cache_path=cache_db)
    webapp.config.update({"TESTING": True})

    yield webapp


@pytest.fixture
def client(webapp: Flask) -> FlaskClient:
    return webapp.test_client()


import _pytest.fixtures


# TODO: Put these common function/fixtures in a common place.
@pytest.fixture(autouse=True)
def show_cache_state(
    request: _pytest.fixtures.FixtureRequest,
) -> Generator[None, None, None]:
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


def retrieve_data(results_sink: Path) -> list[dict[str, str]]:
    """Retrieves data collected stored in sink."""
    import jsonlines

    with jsonlines.open(results_sink) as sink:
        return list(sink)


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
            "intervalo_fim": "2021.001.150000-4",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data: list[Process] = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)


def test_same_request_twice(client: FlaskClient) -> None:
    ignore_unused(client)

    expected = MOCK_DB.values()

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "2021.001.150000-0",
            "intervalo_fim": "2021.001.150000-4",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "2021.001.150000-0",
            "intervalo_fim": "2021.001.150000-4",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)


def test_request_two_non_overlapping_returns_only_wanted(client: FlaskClient) -> None:
    ignore_unused(client)

    expected = [
        MOCK_DB[reverse_lookup(REAL_IDS, id_) or id_]
        for id_ in [
            "2021.001.150000-1",
            "2021.001.150000-2",
            "2021.001.150000-3",
        ]
    ]

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

    expected = [
        MOCK_DB[reverse_lookup(REAL_IDS, id_) or id_]
        for id_ in [
            "2021.001.150000-4",
        ]
    ]

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "2021.001.150000-4",
            "intervalo_fim": "2021.001.150000-4",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)
