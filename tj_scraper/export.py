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


def export_to_xlsx(raw_data: Collection[Process], path: Path):
    """Exports data into a XLSX file."""
    data = prepare_to_export(raw_data)

    book = openpyxl.Workbook()

    sheet = book.active

    keys = sorted({key for process in data for key in process.keys()})
    data = [{k: k for k in keys}, *data]

    for row, process in enumerate(data, start=1):
        for col, key in enumerate(keys, start=1):
            sheet.cell(column=col, row=row, value=str(process.get(key, "")))

    book.save(path)
