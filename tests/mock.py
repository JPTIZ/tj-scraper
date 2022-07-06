"""Mocked data for unit tests."""
from pathlib import Path
from typing import Any, Generator, Mapping

import pytest
from aioresponses import CallbackResult, aioresponses

from tj_scraper.process import TJ_INFO

from .helpers import reverse_lookup

CACHE_PATH = Path("cache_tests.db")

Object = Mapping[str, str]
MOCKED_TJRJ_BACKEND_DB: Mapping[str, Mapping[str, str | list[Object]]] = {
    "1": {
        "cidade": "Rio de Janeiro",
        "codCnj": "0000001-03.2021.8.19.0001",
        "codProc": "2021.001.150000-1",
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
        "codCnj": "0000002-99.2021.8.19.0001",
        "codProc": "2021.001.150000-2",
    },
    "3": {
        "idProc": "3",
        "codCnj": "0000003-22.2021.8.19.0001",
        "codProc": "2021.001.150000-3",
        "txtAssunto": "Furto (Art. 155 - CP), § 1º E Receptação (Art. 180 - Cp)",
    },
    "4": {
        "idProc": "4",
        "codCnj": "0000004-40.2021.8.19.0021",
        "codProc": "2021.001.150000-4",
        "txtAssunto": "Furto (Art. 155 - CP), § 1º E Receptação (Art. 180 - Cp)",
    },
}

REAL_IDS = {k: str(v["codProc"]) for k, v in MOCKED_TJRJ_BACKEND_DB.items()}
CNJ_IDS = {k: str(v["codCnj"]) for k, v in MOCKED_TJRJ_BACKEND_DB.items()}


def select_fields(json_object: Mapping[str, Any], fields: list[str]) -> dict[str, Any]:
    """Returns a new dictionary with only specified fields (keys)."""
    return {k: v for k, v in json_object.items() if k in fields}


Payload = dict[str, Any] | list[str]


@pytest.fixture()
def local_tj() -> Generator[aioresponses, None, None]:
    """
    Gives a aioresponses wrapper so aiohttp requests actually fallback to a
    local TJ database.
    """

    def tjrj_cnj_callback(
        _: Any, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> CallbackResult:
        _ = kwargs

        json = json if json is not None else {}
        cnj_id = json["codCnj"]
        db_id = reverse_lookup(CNJ_IDS, cnj_id) if cnj_id is not None else None
        if db_id is not None:
            process = MOCKED_TJRJ_BACKEND_DB[db_id]
            # print(f"MOCKED_TJRJ_BACKEND_DB has no key {db_id}")
            payload: Payload = {
                "tipoProcesso": "1",
                **select_fields(process, ["codCnj", "codProc"]),
            }
        else:
            # print(f"CNJ_IDS has no key {cnj_id}")
            payload = ["Número do processo inválido."]

        return CallbackResult(status=200, payload=payload)  # type: ignore

    def tjrj_main_callback(
        _: Any, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> CallbackResult:
        _ = kwargs

        json = json if json is not None else {}
        process_id = reverse_lookup(REAL_IDS, json["codigoProcesso"])
        payload = (
            MOCKED_TJRJ_BACKEND_DB[process_id]
            if process_id is not None
            else ["Número do processo inválido."]
        )
        return CallbackResult(status=200, payload=payload)  # type: ignore

    with aioresponses() as mocked_aiohttp:  # type: ignore
        mocked_aiohttp.post(
            TJ_INFO.tjs["rj"].cnj_endpoint, callback=tjrj_cnj_callback, repeat=True
        )
        mocked_aiohttp.post(
            TJ_INFO.tjs["rj"].main_endpoint, callback=tjrj_main_callback, repeat=True
        )
        yield mocked_aiohttp
