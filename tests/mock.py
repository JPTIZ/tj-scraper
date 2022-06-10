"""Mocked data for unit tests."""
from pathlib import Path
from typing import Mapping


CACHE_PATH = Path("cache_tests.db")
LOCAL_URLS = {
    "rj": "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica",
}

Object = Mapping[str, str]
MOCKED_TJRJ_BACKEND_DB: Mapping[str, Mapping[str, str | list[Object]]] = {
    "1": {
        "cidade": "Rio de Janeiro",
        "codCnj": "0000001-00.2021.8.19.0001",
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
        "codCnj": "0000002-00.2021.8.19.0001",
        "codProc": "2021.001.150000-2",
    },
    "3": {
        "idProc": "3",
        "codCnj": "0000003-00.2021.8.19.0001",
        "codProc": "2021.001.150000-3",
        "txtAssunto": "Furto (Art. 155 - CP), § 1º E Receptação (Art. 180 - Cp)",
    },
    "4": {
        "idProc": "4",
        "codCnj": "0000004-00.2021.8.19.0001",
        "codProc": "2021.001.150000-4",
        "txtAssunto": "Furto (Art. 155 - CP), § 1º E Receptação (Art. 180 - Cp)",
    },
}

REAL_IDS = {k: str(v["codProc"]) for k, v in MOCKED_TJRJ_BACKEND_DB.items()}
CNJ_IDS = {k: str(v["codCnj"]) for k, v in MOCKED_TJRJ_BACKEND_DB.items()}
