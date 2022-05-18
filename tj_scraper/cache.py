"""Deals with cache-related features."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import sqlite3

import jsonlines
import toml


from .process import Process


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


def save_to_cache(item: Process, cache_path: Path, state=CacheState.CACHED):
    """Caches (saves) an item into a database of known items."""
    if not cache_path.exists():
        create_database(cache_path)

    if restore_ids(cache_path, ids=[str(item["idProc"])]):
        return

    with sqlite3.connect(cache_path) as connection:
        import json

        cursor = connection.cursor()
        cursor.execute(
            """
            insert into Processos(id, cache_state, assunto, json)
            values(?, ?, ?, ?)
            """,
            (
                item["idProc"],
                state.value,
                item.get("txtAssunto"),
                json.dumps(item),
            ),
        )


def restore_ids(
    cache_path: Path,
    ids: list[str],
) -> list[Process]:
    """
    Loads specific processes from cache with given IDs.
    """
    if not cache_path.exists():
        raise FileNotFoundError(cache_path)

    with sqlite3.connect(cache_path) as connection:
        import json

        cursor = connection.cursor()

        return [
            json.loads(item_json)
            for item_json, in cursor.execute(
                "select json from Processos" " where id in (:ids)",
                {
                    "ids": ",".join(ids),
                },
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
        import json

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


def metadata_path(cache_file: Path) -> Path:
    """Retrieves path for cache-file's metadata."""
    return cache_file.with_name(f"{cache_file.stem}-meta.toml")


def create_metadata(cache_file: Path, output: Optional[Path]):
    """
    Creates a separated cache file that only contains IDs and if they're valid
    and/or stored.
    """
    states = {}
    with jsonl_reader(cache_file) as reader:
        for item in reader:
            match item:
                case {"codProc": cached_id} as item:
                    states[cached_id] = CacheState.CACHED
                case {"invalido": cached_id} as item:
                    print("Found invalid one!")
                    states[cached_id] = CacheState.INVALID

    metadata = CacheMetadata(
        describes=cache_file,
        states=states,
    )

    if not output:
        output = metadata_path(cache_file)

    with open(output, "w", encoding="utf-8") as file_:
        file_.write(
            toml.dumps(
                {
                    "meta": {
                        "describes": metadata.describes.as_posix(),
                    },
                    "states": {
                        cached_id: state.name for cached_id, state in states.items()
                    },
                }
            )
        )


def load_metadata(cache_file: Path) -> CacheMetadata:
    """Returns an object containing a cache-file's metadata."""
    if not cache_file.exists():
        create_database(cache_file)

    with sqlite3.connect(cache_file) as connection:
        cursor = connection.cursor()

        states = {
            process_id: CacheState(cache_state)
            for process_id, cache_state, in cursor.execute(
                "select id, cache_state from Processos"
            )
        }

        return CacheMetadata(
            describes=cache_file,
            states=states,
        )

    return CacheMetadata(describes=cache_file, states={})


def filter_cached(ids: list[str], cache_file: Path) -> tuple[set[str], set[str]]:
    """
    Filters IDs that are already cached. Returns a tuple with uncached and
    cached ids, respectively.
    """
    ids = [*ids]
    cached_ids = set()
    cache = load_metadata(cache_file)

    cached_ids = {
        cached_id
        for cached_id, state in cache.states.items()
        if state == CacheState.CACHED
    }

    filtered_ids = set(ids) - cached_ids

    return filtered_ids, cached_ids
