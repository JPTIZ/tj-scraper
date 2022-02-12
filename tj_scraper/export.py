"""Deals with export formats."""
from collections.abc import Collection
from functools import partial
from pathlib import Path
from typing import Callable, Union

import openpyxl


Value = str
Object = dict[str, str]
ProcessField = Union[str, list[Object]]
Process = dict[str, ProcessField]


def select_fields(
    processes: Collection[Process], fields: Collection[str]
) -> Collection[Process]:
    """
    Returns a new collection of process containing only fields described in
    `fields.`
    """
    return [{k: v for k, v in process.items() if k in fields} for process in processes]


def flatten(process: Process) -> dict[str, str]:
    """Normalizes a process info from JSON to a simple string -> string mapping."""
    # Info that is not in input
    result = {
        "UF": "RJ",
    }

    # Relevant and already flat fields
    result |= {
        "ID do Processo": str(process.pop("idProc")),
        "Assunto": str(process.pop("txtAssunto")),
    }
    print(f"Flattening {result['ID do Processo']}")

    # Fields to split
    if "advogados" in process:
        advs: list[Object]
        for i, advs in enumerate(process.pop("advogados"), start=1):  # type: ignore
            result[f"Advogado{i}Nome"] = str(advs.pop("nomeAdv"))  # type: ignore
            result[f"Advogado{i}NumOAB"] = str(advs.pop("numOab"))  # type: ignore

    if "audiencia" in process:
        audiencia: Object = process.pop("audiencia")  # type: ignore
        result["AudienciaData"] = str(audiencia["dtAud"])
        result["AudienciaHora"] = str(audiencia["hrAud"])
        result["AudienciaCódigoDoTipo"] = str(audiencia["codTipAud"])
        result["AudienciaDescrição"] = str(audiencia["descr"])
        result["AudienciaCódigoResultado"] = str(audiencia["codResultAud"])

    if "dividaAtivas" in process:
        divida: list[Object]
        for i, divida in enumerate(process.pop("dividaAtivas"), start=1):  # type: ignore
            result[f"DividaAtiva{i}AnoExerc"] = str(divida.pop("anoExerc"))  # type: ignore
            assert not divida

    if "mandado" in process:
        mandado: Object
        for i, mandado in enumerate(process.pop("mandado"), start=1):  # type: ignore
            result[f"CodResultadoMandado{i}"] = str(mandado["codResultadoMandado"])
            result[f"DescricaoResultadoMandado{i}"] = str(
                mandado["descricaoResultadoMandado"]
            )
            result[f"Devolucao{i}"] = str(mandado.get("devolucao", ""))
            result[f"DevolucaoOJA{i}"] = str(mandado.get("devolucaoOJA", ""))

    if "personagens" in process:
        personagem: Object
        for personagem in process.pop("personagens"):  # type: ignore
            info = {
                # "Código": personagem["codPers"],
                "Nome": personagem["nome"],
                # "TipoPolo": personagem["tipoPolo"],
            }
            category = personagem["descPers"]
            for field, value in info.items():
                result[f"{category}{field}"] = value

    ultimo_movimento: Object = process.pop("ultMovimentoProc")  # type: ignore
    result["UltimoMovimentoDataAlt"] = str(ultimo_movimento.get("dtAlt", ""))
    result["UltimoMovimentoDescricaoMov"] = str(ultimo_movimento.pop("descrMov"))
    result["UltimoMovimentoDataMov"] = str(ultimo_movimento.pop("dtMovimento"))
    result["UltimoMovimentoData"] = str(ultimo_movimento.get("dt", ""))
    print("=" * 80)

    result |= {f"{k[0].upper()}{k[1:]}": str(v) for k, v in process.items()}

    return result


def prepare_to_export(data: Collection[Process]) -> list[Object]:
    """Rearranges data to be in a format easy to iter and export."""

    def merge(
        values: list[dict[str, str]],
        operation: Callable[[Object, Object], Object],
        condition: Callable[[Object], bool],
    ) -> dict[str, str]:
        merged: Object = {}
        for value in values:
            print(f"{value=}")
            if condition(value):
                merged = operation(merged, value)
        return merged

    def nomes_together(obj, new):
        print(f"{obj=} + {new=}")
        autores = [
            name
            for name in (obj.get("autores", ""), new["nome"])
            if name and new["descPers"] == "Autor"
        ]
        reus = [
            name
            for name in (obj.get("réus", ""), new["nome"])
            if name and new["descPers"] == "Réu"
        ]
        return {
            "autores": ", ".join(autores),
            "réus": ", ".join(reus),
        }

    special_cases = {
        "personagens": partial(
            merge,
            operation=nomes_together,
            condition=lambda obj: obj["descPers"] in ["Autor", "Réu"],
        ),
    }

    def value_or_special(k: str, value: ProcessField) -> list[tuple[str, str]]:
        if k in special_cases:
            print(f"{k} is special :3")
            replaced_fields = list(
                (k_, v_) for k_, v_ in special_cases[k](value).items()
            )
            print(f"{replaced_fields=}")
            return replaced_fields
        return [(k, str(value))]

    return [
        dict(value for k, v in item.items() for value in value_or_special(k, v))
        for item in data
    ]


def export_to_xlsx(raw_data: Collection[Process], path: Path) -> None:
    """Exports data into a XLSX file."""
    # data = prepare_to_export(raw_data)
    raw_data = select_fields(
        raw_data,
        [
            "advogados",
            "cidade",
            "codCnj",
            "dataDis",
            "idProc",
            "personagens",
            "txtAssunto",
            "uf",
            "ultMovimentoProc",
        ],
    )
    data = [flatten(item) for item in raw_data]

    book = openpyxl.Workbook()

    sheet = book.active

    keys = sorted({key for process in data for key in process.keys()})
    data = [{k: k for k in keys}, *data]

    for row, process in enumerate(data, start=1):
        for col, key in enumerate(keys, start=1):
            # type: ignore
            sheet.cell(column=col, row=row, value=str(process.get(key, "")))

    book.save(path)
