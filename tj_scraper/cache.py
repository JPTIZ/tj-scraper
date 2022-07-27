"""Deals with cache-related features."""
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import jsonlines

from .process import (
    CNJProcessNumber,
    ProcessJSON,
    get_process_id,
    make_cnj_number_str,
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


def quickfix_db_id_to_cnj_id(cache_path: Path) -> None:
    """."""
    from tj_scraper.errors import InvalidProcessNumber

    def is_invalid_number(item: str) -> bool:
        try:
            id_ = json.loads(item)["codCnj"]
            print(f"::              : {id_}")
            to_cnj_number(id_)
            return False
        except (InvalidProcessNumber, KeyError):
            print("::              : passes custom filter? No")
            return True
        except Exception as error:
            print(f"Failed to use custom filter: {error}")
            raise

    def _get_process_id(json_str: str) -> bool:
        try:
            return json.loads(json_str)["codCnj"]
        except Exception as error:
            print(f"Failed to use custom filter: {error}")
            raise

    def get_process_subject(json_str: str) -> bool:
        try:
            return json.loads(json_str).get("txtAssunto", "")
        except Exception as error:
            print(f"Failed to use custom filter: {error}")
            raise

    with sqlite3.connect(cache_path) as connection:
        connection.create_function("is_invalid_number", 1, is_invalid_number)
        cursor = connection.cursor()

        cursor.execute("delete from Processos where is_invalid_number(json)")

    with sqlite3.connect(cache_path) as connection:
        connection.create_function("get_process_id", 1, _get_process_id)
        cursor = connection.cursor()
        cursor.execute(
            """
            update Processos
            set id = get_process_id(json)
            """
        )

    with sqlite3.connect(cache_path) as connection:
        connection.create_function("get_process_subject", 1, get_process_subject)
        cursor = connection.cursor()
        cursor.execute(
            """
            alter table Processos
            add column subject
            """
        )
        cursor.execute(
            """
            update Processos
            set subject = get_process_subject(json)
            """
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
        ids_to_show = ids
        if len(ids_to_show) > 20:
            ids_to_show = [min(ids), max(ids)]
        print(f":: Restoring IDs: {id_} is in {ids_to_show}? {result}")
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
                    "exclude_ids": ",".join(
                        make_cnj_number_str(id_) for id_ in exclude_ids
                    ),
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
    """
    Result of filtering which CNJ numbers are cached or not. See `filter_cached`.
    """

    not_cached: set[int]
    cached: set[CNJProcessNumber]
    invalid: set[CNJProcessNumber]


def filter_cached(
    sequential_numbers: Sequence[int], year: int, cache_path: Path
) -> Filtered:
    """
    Classifies which processes are already cached based on its NNNNNNN field,
    since it is unique per process. When no cached process has that NNNNNNN, it
    is not possible to know its full number, so in this case only the NNNNNNN
    is returned instead of a full number.
    """
    from tj_scraper.process import JudicialSegment

    sequential_numbers = list(sequential_numbers)
    # print(f"filter_cached({sequential_numbers=}, {cache_path=})")
    cache = load_metadata(cache_path)

    classified = Filtered(not_cached=set(), cached=set(), invalid=set())

    cache_states = {
        cnj_number.sequential_number: (cnj_number, state)
        for raw_number, state in cache.states.items()
        if (cnj_number := to_cnj_number(raw_number)).sequential_number
        in sequential_numbers
        and cnj_number.year == year
    }

    for sequential_number in sequential_numbers:
        cnj_and_state = cache_states.get(
            sequential_number,
            (
                CNJProcessNumber(0, 0, JudicialSegment.JEDFT, tr_code=0, source_unit=0),
                CacheState.NOT_CACHED,
            ),
        )

        match cnj_and_state:
            case (cnj_number, CacheState.CACHED):
                classified.cached |= {cnj_number}
            case (cnj_number, CacheState.INVALID):
                classified.invalid |= {cnj_number}
            case (_, CacheState.NOT_CACHED):
                classified.not_cached |= {sequential_number}

    return classified


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
