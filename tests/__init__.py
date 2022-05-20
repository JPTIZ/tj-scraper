"""Pytest conftest file."""
from pathlib import Path


CACHE_PATH = Path("cache_tests.db")
LOCAL_URL = (
    "https://www3.tjrj.jus.br/consultaprocessual/api/processos/por-numero/publica"
)
REALISTIC_IDS = {
    "1": "2021.001.150000-1",
    "2": "2021.001.150000-2",
    "3": "2021.001.150000-3",
}
MOCK_DB = {
    "1": {
        "cidade": "Rio de Janeiro",
        "codCnj": "0000000-11.2021.4.55.6666",
        "codProc": REALISTIC_IDS["1"],
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
        "codProc": REALISTIC_IDS["2"],
    },
    "3": {
        "idProc": "3",
        "codProc": REALISTIC_IDS["3"],
        "txtAssunto": "Furto (Art. 155 - CP), § 1º E Receptação (Art. 180 - Cp)",
    },
    # "4": {
    #     "idProc": "4",
    #     "codProc": "4",
    # },
}
