"""Deals with cache-related features."""
from pathlib import Path

import jsonlines


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


def filter_cached(ids: list[str], cache_file: Path) -> list[str]:
    """Filters IDs that are already cached."""
    filtered = []
    ids = [*ids]
    cached_ids = set()
    with jsonlines.open(cache_file) as reader:
        for item in reader:  # type: ignore
            match item:
                case {"codProc": cached_id}:
                    cached_ids |= {cached_id}

    for id_ in ids:
        cached = id_ in cached_ids

        if not cached:
            filtered += [id_]
        else:
            print(f"{id_}: Cached")
    return filtered
