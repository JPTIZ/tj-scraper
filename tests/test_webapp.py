"""Tests webapp endpoints."""
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pyright: reportUnusedImport=false
import json
from pathlib import Path
from typing import Generator

import pytest
from aioresponses import aioresponses
from flask import Flask
from flask.testing import FlaskClient

from tj_scraper.process import ProcessJSON
from tj_scraper.webapp import make_webapp

from .fixtures import results_sink
from .helpers import has_same_entries, ignore_unused, reverse_lookup
from .mock import CNJ_IDS, MOCKED_TJRJ_BACKEND_DB, REAL_IDS

ignore_unused(results_sink, reason="Fixtures.")


@pytest.fixture
def webapp(local_tj: aioresponses, cache_db: Path) -> Generator[Flask, None, None]:
    ignore_unused(local_tj)

    webapp = make_webapp(cache_path=cache_db)
    webapp.config.update({"TESTING": True})

    yield webapp


@pytest.fixture
def client(webapp: Flask) -> FlaskClient:
    return webapp.test_client()


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

    expected = MOCKED_TJRJ_BACKEND_DB.values()

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "0000000-00.2021.8.19.0001",
            "intervalo_fim": "0000004-00.2021.8.19.0001",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data: list[ProcessJSON] = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)


def test_same_request_twice(client: FlaskClient) -> None:
    ignore_unused(client)

    expected = MOCKED_TJRJ_BACKEND_DB.values()

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "0000000-00.2021.8.19.0001",
            "intervalo_fim": "0000004-00.2021.8.19.0001",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "0000000-00.2021.8.19.0001",
            "intervalo_fim": "0000004-00.2021.8.19.0001",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)


def test_request_two_non_overlapping_returns_only_wanted(client: FlaskClient) -> None:
    ignore_unused(client)

    expected = [
        MOCKED_TJRJ_BACKEND_DB[reverse_lookup(REAL_IDS, id_) or id_]
        for id_ in [
            "2021.001.150000-1",
            "2021.001.150000-2",
            "2021.001.150000-3",
        ]
    ]

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "0000000-00.2021.8.19.0001",
            "intervalo_fim": "0000003-00.2021.8.19.0001",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)

    expected = [
        MOCKED_TJRJ_BACKEND_DB[reverse_lookup(REAL_IDS, id_) or id_]
        for id_ in [
            "2021.001.150000-4",
        ]
    ]

    response = client.get(
        "/buscar",
        query_string={
            "intervalo_inicio": "0000004-00.2021.8.19.0001",
            "intervalo_fim": "0000004-00.2021.8.19.0001",
            "assunto": "",
            "tipo_download": "json",
        },
    )

    data = json.loads(response.data.decode("utf-8"))

    assert has_same_entries(data, expected)
