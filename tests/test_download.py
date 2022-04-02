"""Tests download functions."""
# pylint: disable=redefined-outer-name
from aioresponses import aioresponses
import pytest

from tj_scraper.download import download_from_json

LOCAL_URL = (
    "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
)
MOCK_DB = {
    "1": {
        "cidade": "Rio de Janeiro",
        "codCnj": "0000000-11.2021.4.55.6666",
        "codProc": "2021.001.150000-0",
        "dataDis": "01/01/2021",
        "idProc": "1",
        "txtAssunto": "Furto  (Art. 155 - CP)",
        "uf": "RJ",
        "advogados": [{"nomeAdv": "DEFENSOR PÚBLICO", "numOab": "0"}],
        "personagens": [
            {
                "codPers": "1",
                "nome": "MINISTERIO PUBLICO DO ESTADO DO RIO DE JANEIRO",
                "descPers": "Autor",
            },
            {
                "codPers": "2",
                "nome": "EXEMPLO 1",
                "descPers": "Autor do Fato",
            },
        ],
    },
    "2": {
        "idProc": "2",
    },
    "3": {
        "idProc": "3",
        "txtAssunto": "Furto (Art. 155 - CP), § 1º E Receptação (Art. 180 - Cp)",
    },
}


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
    from pathlib import Path

    sink = Path("tests") / "test_results.jsonl"
    yield sink
    sink.unlink(missing_ok=True)


def retrieve_data(results_sink):
    """Retrieves data collected stored in sink."""
    import jsonlines

    with jsonlines.open(results_sink) as sink:
        return list(sink)


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
    ids = MOCK_DB.keys()

    for id_ in ids:
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    download_from_json(
        ids=ids,
        sink=results_sink,
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
        download_from_json(ids=request_ids, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == list(MOCK_DB.values())


def test_download_in_parts_with_overlap(local_tj, results_sink):
    """Tests if download function works when given ID ranges overlap/repeat."""
    ids = list(MOCK_DB.keys())

    request_order = [ids[:2], ids[1:]]

    for id_ in flatten(request_order):
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    for request_ids in request_order:
        download_from_json(ids=request_ids, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == list(MOCK_DB.values())


def test_download_with_subject_filter_one_word(local_tj, results_sink):
    """
    Tests if download function is able to filter only items that contains one
    specific word on their subjects.
    """
    from tj_scraper.process import has_words_in_subject

    expected = {k: v for k, v in MOCK_DB.items() if has_words_in_subject(v, ["furto"])}
    ids = list(expected.keys())

    for id_ in ids:
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    download_from_json(ids=ids, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == expected


def test_download_with_subject_filter_multiple_word(local_tj, results_sink):
    """
    Tests if download function is able to filter only items that contains some
    specific words on their subjects.
    """
    from tj_scraper.process import has_words_in_subject

    expected = {
        k: v
        for k, v in MOCK_DB.items()
        if has_words_in_subject(v, ["furto", "receptação"])
    }
    ids = list(expected.keys())

    for id_ in ids:
        local_tj.post(LOCAL_URL, payload=MOCK_DB[id_])

    download_from_json(ids=ids, sink=results_sink)

    data = retrieve_data(results_sink)

    assert data == expected
