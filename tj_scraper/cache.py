"""Deals with cache-related features."""
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import jsonlines

from .process import (
    CNJProcessNumber,
    ProcessJSON,
    get_process_id,
    make_cnj_code,
    to_cnj_number,
)


class CacheState(Enum):
    """
    Describes each possible state of a previously found data:

    CACHED: Data exists externally and is cached.
    INVALID: Data does not exists externally (wrong ID or process type).
    NOT_CACHED: There's no cache information for given data.
    """

    CACHED = "CACHED"
    INVALID = "INVALID"
    NOT_CACHED = "NOT_CACHED"


@dataclass
class DBProcess:
    """A process as it is registered in the database."""

    id_: str
    cache_state: CacheState
    subject: str
    json: Mapping[str, Any]


def create_database(path: Path) -> None:
    """Creates database file and its tables.

    Process table's fields description:
    - id: CNJ process number.
    - local_id: ID used locally in process' TJ.
    - cache_state: Relative to `CacheState`.
    - subject: Quick-access to process's subject field.
    - json: Process data in JSON format as returned by TJ server.
    """
    with sqlite3.connect(path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            create table Processos (
                id text primary key,
                local_id text,
                cache_state text,
                subject text,
                json text
            );
            """
        )


def quickfix_db_id_to_real_id(cache_path: Path) -> None:
    """."""
    data = restore(cache_path)

    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()
        for item in data:
            cursor.execute(
                """
                update Processos
                set id = ?
                where id = ?
                """,
                (
                    get_process_id(item),
                    item.get("idProc", item["codProc"]),
                ),
            )


def save_to_cache(
    item: ProcessJSON, cache_path: Path, state: CacheState = CacheState.CACHED
) -> None:
    """Caches (saves) an item into a database of known items."""
    if not cache_path.exists():
        create_database(cache_path)

    item_db_id = get_process_id(item)

    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            insert or ignore into Processos(id, cache_state, subject, json)
            values(?, ?, ?, ?)
            """,
            (
                item_db_id,
                state.value,
                item.get("txtAssunto"),
                json.dumps(item),
            ),
        )


def restore_json_for_ids(
    cache_path: Path,
    ids: list[CNJProcessNumber],
    filter_function: Callable[[DBProcess], bool],
) -> list[ProcessJSON]:
    """
    Loads specific processes from cache with given IDs.
    """
    if not cache_path.exists():
        raise FileNotFoundError(cache_path)

    def is_id_in_list(id_: str) -> bool:
        result = to_cnj_number(id_) in ids
        print(f":: Restoring IDs: {id_} is in {ids}? {result}")
        return result

    def custom_filter(id_: str, state: CacheState, subject: str, json_str: str) -> bool:
        try:
            process = DBProcess(
                id_, cache_state=state, subject=subject, json=json.loads(json_str)
            )
            result = filter_function(process)
            print(f"::              : {id_} passes custom filter? {result}")
            return result
        except Exception as error:
            print(f"Failed to use custom filter: {error}")
            raise

    with sqlite3.connect(cache_path) as connection:
        connection.create_function("is_in_list", 1, is_id_in_list)
        connection.create_function("custom_filter", 4, custom_filter)
        cursor = connection.cursor()

        return [
            json.loads(item_json)
            for item_json, in cursor.execute(
                "select json from Processos"
                " where is_in_list(id)"
                " and custom_filter(id, cache_state, subject, json)",
            )
        ]

    return []


def restore(
    cache_path: Path,
    exclude_ids: Optional[list[CNJProcessNumber]] = None,
    with_subject: Optional[list[str]] = None,
) -> list[ProcessJSON]:
    """
    Loads cached data.
    """
    if not cache_path.exists():
        raise FileNotFoundError(cache_path)

    exclude_ids = exclude_ids or []
    with_subject = with_subject or []

    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()

        extra = ""
        for word in with_subject:
            extra += f" and upper(subject) like '%{word.upper()}%'"

        return list(
            json.loads(item_json)
            for item_json, in cursor.execute(
                "select json from Processos"
                " where id not in (:exclude_ids) "
                f"{extra}",
                {
                    "exclude_ids": ",".join(make_cnj_code(id_) for id_ in exclude_ids),
                    "subject": ",".join(with_subject),
                },
            ).fetchall()
        )

    return []


@dataclass
class CacheMetadata:
    """
    Describes a cache's data, including which process IDs have which state on the cache.
    """

    describes: Path
    states: dict[str, CacheState]


def jsonl_reader(path: Path) -> jsonlines.Reader:
    """
    Wrapper for `jsonlines.open` to make it easier to ignore mypy errors about
    Reader|Writer.
    """
    return jsonlines.open(path, "r")


def metadata_path(cache_path: Path) -> Path:
    """Retrieves path for cache-file's metadata."""
    return cache_path.with_name(f"{cache_path.stem}-meta.toml")


def load_metadata(cache_path: Path) -> CacheMetadata:
    """Returns an object containing a cache-file's metadata."""
    if not cache_path.exists():
        create_database(cache_path)

    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()

        states = {
            process_id: CacheState(cache_state)
            for process_id, cache_state, in cursor.execute(
                "select id, cache_state from Processos"
            )
        }

        return CacheMetadata(
            describes=cache_path,
            states=states,
        )

    return CacheMetadata(describes=cache_path, states={})


@dataclass
class Filtered:
    not_cached: set[CNJProcessNumber]
    cached: set[CNJProcessNumber]
    invalid: set[CNJProcessNumber]


def filter_cached(ids: list[CNJProcessNumber], cache_path: Path) -> Filtered:
    """
    Filters IDs that are already cached. Returns a tuple with uncached and
    cached ids, respectively.
    """
    ids = [*ids]
    cached_ids = set()
    cache = load_metadata(cache_path)

    cached_ids = {
        cached_id
        for raw_cached_id, state in cache.states.items()
        if state == CacheState.CACHED
        and (cached_id := to_cnj_number(raw_cached_id)) in ids
    }

    invalid_ids = {
        cached_id
        for raw_cached_id, state in cache.states.items()
        if state == CacheState.INVALID
        and (cached_id := to_cnj_number(raw_cached_id)) in ids
    }

    filtered_ids = set(ids) - (cached_ids | invalid_ids)

    return Filtered(
        not_cached=filtered_ids,
        cached=cached_ids,
        invalid=invalid_ids,
    )


def load_all(cache_path: Path) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Loads entire database content. For small DBs only (e.g. testing)."""
    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()

        return [
            (id_, cache_state, subject, json.loads(item_json))
            for id_, cache_state, subject, item_json, in cursor.execute(
                "select id, cache_state, subject, json from Processos",
            )
        ]
    return []


def show_cache_state(cache_path: Path) -> None:
    """Shows current cache state when a test fails."""

    from pprint import pprint

    print("Cache state:")
    try:
        state = {
            i: {"ID": i, "CacheState": s, "Assunto": a}
            for (i, s, a, _) in load_all(cache_path=cache_path)
        }
        pprint(state)
    except Exception as error:  # pylint: disable=broad-except
        print(" [ Failed to fetch cache state. ]")
        print(f" [ Reason: {error}. ]")
