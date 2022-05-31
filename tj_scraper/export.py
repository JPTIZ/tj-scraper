"""Deals with export formats."""
from collections.abc import Collection
from pathlib import Path

import openpyxl

from .process import Object, Process


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
    print(process)
    if not process:
        return {}
    result |= {
        "ID do Processo": str(process.pop("codProc")),
        "Assunto": str(process.get("txtAssunto", "Sem Assunto")),
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

    ultimo_movimento: Object = process.get("ultMovimentoProc", {})  # type: ignore
    result["UltimoMovimentoDataAlt"] = str(ultimo_movimento.get("dtAlt", ""))
    result["UltimoMovimentoDescricaoMov"] = str(ultimo_movimento.get("descrMov", ""))
    result["UltimoMovimentoDataMov"] = str(ultimo_movimento.get("dtMovimento", ""))
    result["UltimoMovimentoData"] = str(ultimo_movimento.get("dt", ""))
    print("=" * 80)

    result |= {f"{k[0].upper()}{k[1:]}": str(v) for k, v in process.items()}

    return result


def prepare_to_export(raw_data: Collection[Process]) -> list[Object]:
    """Rearranges data to be in a format easy to iter and export."""
    raw_data = select_fields(
        raw_data,
        [
            "advogados",
            "cidade",
            "codCnj",
            "codProc",
            "dataDis",
            "personagens",
            "txtAssunto",
            "uf",
            "ultMovimentoProc",
        ],
    )
    data = [flatten(item) for item in raw_data]
    return [item for item in data if item]


def export_to_xlsx(raw_data: Collection[Process], path: Path) -> None:
    """Exports data into a XLSX file."""
    data = prepare_to_export(raw_data)

    book = openpyxl.Workbook()

    sheet = book.active

    keys = sorted({key for process in data for key in process.keys()})
    data = [{k: k for k in keys}, *data]

    for row, process in enumerate(data, start=1):
        for col, key in enumerate(keys, start=1):
            # type: ignore
            sheet.cell(column=col, row=row, value=str(process.get(key, "")))

    book.save(path)
