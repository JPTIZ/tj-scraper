"""Deals with cache-related features."""
from dataclasses import dataclass
from enum import auto, Enum
from pathlib import Path
from typing import Optional

import jsonlines
import toml


from .process import has_words_in_subject, Process


class CacheState(Enum):
    """
    Describes each possible state of a previously found data:

    CACHED: Data exists externally and is cached.
    OUTDATED: Data exists externally but is locally outdated.
    INVALID: Data does not exists externally (wrong ID or process type).
    NOT_CACHED: There's no cache information for given data.
    """

    CACHED = auto()
    OUTDATED = auto()
    INVALID = auto()
    NOT_CACHED = auto()


@dataclass
class CacheMetadata:
    """
    Describes a cache's data, including which process IDs have which state on the cache.
    """

    describes: Path
    states: dict[str, CacheState]


def sort(cache_file: Path):
    """Sorts data in a cache file so it becomes ordered by ID."""
    raise NotImplementedError(f"Should sort {cache_file}")


def create_metadata(cache_file: Path, output: Optional[Path]):
    """
    Creates a separated cache file that only contains IDs and if they're valid
    and/or stored.
    """
    states = {}
    with jsonlines.open(cache_file, "r") as reader:
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
        output = cache_file.with_name(f"{cache_file.stem}-meta.toml")

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


def dedup_cache(cache_file: Path):
    """Deduplicate cache entries based on their ID. Keeps last one found."""
    old_size = 0
    new_size = 0

    cached_items = {}
    with jsonlines.open(cache_file, "r") as reader:
        for old_size, item in enumerate(reader, start=1):  # type: ignore
            match item:
                case {"codProc": cached_id} as item:
                    cached_items[cached_id] = item

    dedup_cache_file = cache_file.with_stem(f"{cache_file.stem}-dedup")
    with jsonlines.open(dedup_cache_file, "w") as writer:
        items = cached_items.values()
        new_size = len(items)

        writer.write_all(items)  # type: ignore

    print(f"Removed {old_size - new_size} duplicates")


def filter_cached(ids: list[str], cache_file: Path) -> tuple[list[str], list[str]]:
    """
    Filters IDs that are already cached. Returns a tuple with uncached and
    cached ids, respectively.
    """
    filtered = []
    ids = [*ids]
    cached_ids = set()
    with open(
        cache_file.with_name(f"{cache_file.stem}-meta.toml"), encoding="utf-8"
    ) as reader:
        cache = toml.load(reader)

    cached_ids = {
        cached_id
        for cached_id, state in cache["states"].items()
        if state == CacheState.CACHED.name
    }

    filtered = set(ids) - cached_ids

    return list(filtered), list(cached_ids)


def restore(
    cache_file: Path,
    exclude_ids: Optional[list[str]] = None,
    with_subject: Optional[list[str]] = None,
) -> list[Process]:
    """
    Loads cached data of given IDs.
    """
    exclude_ids = exclude_ids or []
    with_subject = with_subject or []

    with jsonlines.open(cache_file) as cache_f:
        data = [
            item
            for item in cache_f
            if item.get("codProc") not in exclude_ids
            and has_words_in_subject(item, with_subject)
        ]

    return data
