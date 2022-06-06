"""Deals with cache-related features."""
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import jsonlines

from .process import Process, get_process_id


class CacheState(Enum):
    """
    Describes each possible state of a previously found data:

    CACHED: Data exists externally and is cached.
    OUTDATED: Data exists externally but is locally outdated.
    INVALID: Data does not exists externally (wrong ID or process type).
    NOT_CACHED: There's no cache information for given data.
    """

    CACHED = "CACHED"
    OUTDATED = "OUTDATED"
    INVALID = "INVALID"
    NOT_CACHED = "NOT_CACHED"


@dataclass
class DBProcess:
    """A process as it is registered in the database."""

    id_: str
    cache_state: CacheState
    assunto: str
    json: dict[str, Any]


def create_database(path: Path):
    """Creates database file and its tables."""
    with sqlite3.connect(path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            create table Processos (
                id text primary key,
                cache_state text,
                assunto text,
                json text
            );
            """
        )


def quickfix_db_id_to_real_id(cache_path: Path):
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


def save_to_cache(item: Process, cache_path: Path, state=CacheState.CACHED):
    """Caches (saves) an item into a database of known items."""
    if not cache_path.exists():
        create_database(cache_path)

    item_db_id = get_process_id(item)

    with sqlite3.connect(cache_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            insert or ignore into Processos(id, cache_state, assunto, json)
            values(?, ?, ?, ?)
            """,
            (
                item_db_id,
                state.value,
                item.get("txtAssunto"),
                json.dumps(item),
            ),
        )


def restore_ids(
    cache_path: Path,
    ids: list[str],
    filter_function: Callable[[DBProcess], bool],
) -> list[Process]:
    """
    Loads specific processes from cache with given IDs.
    """
    if not cache_path.exists():
        raise FileNotFoundError(cache_path)

    def is_id_in_list(id_: str):
        result = id_ in ids
        print(f":: Restoring IDs: {id_} is in {ids}? {result}")
        return result

    def custom_filter(id_: str, state: CacheState, assunto: str, json_str: str) -> bool:
        try:
            _ = id_, assunto, state
            # TODO: process = DBProcess(id_, assunto, json.loads(json_str))
            return filter_function(json.loads(json_str))
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
                "select json from Processos where is_in_list(id) and custom_filter(id, cache_state, assunto, json)",
            )
        ]

    return []


def restore(
    cache_path: Path,
    exclude_ids: Optional[list[str]] = None,
    with_subject: Optional[list[str]] = None,
) -> list[Process]:
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
            extra += f" and upper(assunto) like '%{word.upper()}%'"

        return list(
            json.loads(item_json)
            for item_json, in cursor.execute(
                "select json from Processos"
                " where id not in (:exclude_ids) "
                f"{extra}",
                {
                    "exclude_ids": ",".join(exclude_ids),
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
    return jsonlines.open(path, "r")  # type: ignore


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


def filter_cached(ids: list[str], cache_path: Path) -> tuple[set[str], set[str]]:
    """
    Filters IDs that are already cached. Returns a tuple with uncached and
    cached ids, respectively.
    """
    ids = [*ids]
    cached_ids = set()
    cache = load_metadata(cache_path)

    cached_ids = {
        cached_id
        for cached_id, state in cache.states.items()
        if state == CacheState.CACHED
    }

    filtered_ids = set(ids) - cached_ids

    return filtered_ids, cached_ids


def show_cache_state(cache_path: Path):
    """Shows current cache state when a test fails."""

    def load_all(cache_path: Path):
        """Loads entire database content. For small DBs only (e.g. testing)."""
        with sqlite3.connect(cache_path) as connection:
            cursor = connection.cursor()

            return [
                (id_, cache_state, assunto, json.loads(item_json))
                for id_, cache_state, assunto, item_json, in cursor.execute(
                    "select id, cache_state, assunto, json from Processos",
                )
            ]
        return []

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
