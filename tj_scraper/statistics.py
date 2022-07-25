"""Module for statistic data generation."""
import cProfile
import itertools
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import reduce
from pathlib import Path
from pprint import pprint
from pstats import SortKey, Stats
from typing import (
    Any,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Iterator,
    NamedTuple,
    ParamSpec,
    TypeVar,
)

import tj_scraper.download
from tj_scraper.download import BatchArgs, FetchResult, discover_with_json_api
from tj_scraper.process import TJ_INFO, CNJNumberCombinations, JudicialSegment

CACHE_PATH = Path("b.db")
STATS_PATH = Path("profile-stats.stat")


class ProfileParams(NamedTuple):
    as_async: bool
    sequence_start: int
    sequence_len: int
    batch_size: int


@dataclass(frozen=True)
class ProfileParamsSetup:
    """Combinations of parameters that will be used to generate statistics."""

    as_async: list[bool]
    sequence_starts: list[int]
    sequence_lens: list[int]
    batch_sizes: list[int]

    def __iter__(self) -> Iterator[ProfileParams]:
        combinations = itertools.product(*[params for params in asdict(self).values()])
        for params in combinations:
            param = ProfileParams(*params)
            if not param.as_async and param.batch_size > 1:
                continue
            yield param


def download_function(params: ProfileParams) -> None:
    # Useful numbers:
    #     "0015712-81.2021.8.19.0004",
    #     "0005751-35.1978.8.19.0001",
    #     "0196091-26.2021.8.19.0001",
    combinations = CNJNumberCombinations(
        sequence_start=params.sequence_start,
        sequence_end=params.sequence_start + params.sequence_len,
        tj=TJ_INFO.tjs["rj"],
        year=2021,
        segment=JudicialSegment.JEDFT,
    )

    discover_with_json_api(
        combinations=combinations,
        sink=Path("a.jsonl"),
        cache_path=CACHE_PATH,
        batch_size=params.batch_size,
    )


@contextmanager
def autodelete(path: Path) -> Generator[Path, None, None]:
    """Yields a path and then deletes it."""
    yield path
    path.unlink(missing_ok=True)


@contextmanager
def no_stdout() -> Generator[None, None, None]:
    """Stops output for stdout."""
    import os
    import sys

    with open(os.devnull, "w") as devnull:  # pylint: disable=unspecified-encoding
        old_stdout, sys.stdout = sys.stdout, devnull
        yield
        sys.stdout = old_stdout


def io_timer() -> float:
    """Calculates time spent in IO."""
    import os

    timing = os.times()
    return timing.elapsed - (timing.system + timing.user)


cpu_timer = time.process_time

Time = int | float
Timer = Callable[[], Time]

Return = TypeVar("Return")
Args = ParamSpec("Args")


def profile(
    function: Callable[Args, Any],
    timer: Timer | None,
    output: Path,
    keep_cache: bool = False,
    *args: Args.args,
    **kwargs: Args.kwargs,
) -> None:
    """Measures execution time of a function. Time is calculated using `timer`."""
    timer_arg: dict[str, Any] = {"timer": timer} if timer is not None else {}

    profiler = cProfile.Profile(**timer_arg)

    if keep_cache:
        profiler.runcall(function, *args, **kwargs)
    else:
        with autodelete(CACHE_PATH):
            profiler.runcall(function, *args, **kwargs)

    profiler.create_stats()

    stats = Stats(profiler)
    stats.dump_stats(output)

    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats(10)


@dataclass
class ProfileTimes:
    total: float
    network: float


def view_profile(path: Path) -> ProfileTimes | None:
    """Shows previously profiled data."""
    print("👀 (início)")
    try:
        stats = Stats(path.resolve().as_posix())
    except FileNotFoundError:
        print(f"{path.resolve().as_posix()} not found. Skipping...")
        return
    profile_stats = stats.get_stats_profile()
    from pprint import pprint

    total_time = profile_stats.total_tt
    function_profiles = profile_stats.func_profiles

    pprint(
        [value for key, value in profile_stats.func_profiles.items() if "poll" in key]
    )

    network_io_keys = [
        "<method 'poll' of 'select.epoll' objects>",
        "<method 'poll' of 'select.poll' objects>",
    ]

    network_time = -1.0
    for network_io_key in network_io_keys:
        try:
            network_function_profile = function_profiles[network_io_key]
            pprint(network_function_profile)
            network_time = network_function_profile.tottime
        except KeyError:
            pass
    if network_time == -1:
        print("Failed to get network time (now known poll function found).")
        return

    print(f"Total time: {total_time}")
    print(f"Network time: {network_time}")
    print(f"Non-Network time: {total_time - network_time}")
    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats(10)
    print("👀 (fim)")
    return ProfileTimes(total=total_time, network=network_time)


def profile_and_dump(
    function: Callable[[ProfileParams], None],
    timer: Timer | None,
    params_setup: ProfileParamsSetup,
    keep_cache: bool = False,
) -> None:
    run_batch_async = getattr(tj_scraper.download, "run_batch")

    async def run_batch(
        as_async: bool, batch: Iterable[Coroutine[BatchArgs, BatchArgs, FetchResult]]
    ) -> Iterable[FetchResult]:
        if as_async:
            return await run_batch_async(batch)
        else:
            return [await coro for coro in batch]

    for params in params_setup:
        print(f"⬇️ (início -- {params})")
        stats_path = make_stats_path(params)

        setattr(
            tj_scraper.download,
            "run_batch",
            lambda batch: run_batch(params.as_async, batch),
        )

        profile(function, timer, stats_path, keep_cache, params)
        print("⬇️ (fim -- {stats_path.as_posix()})")


def make_stats_path(params: ProfileParams) -> Path:
    sync = "sync" if not params.as_async else "async"
    params_as_dict = params._asdict()
    stem = "-".join(f"{k}_{v}" for k, v in params_as_dict.items() if k != "as_async")
    return STATS_PATH.with_stem(f"{STATS_PATH.stem}-{sync}-{stem}")


Object = dict[Any, Any]


def group_by(mappings: list[dict[Any, Any]], field: Any) -> dict[Any, Any]:
    grouped = {}
    for profile in mappings:
        new_entry = {k: v for k, v in profile.items() if k != field}
        key = profile[field]
        try:
            grouped[key] += [new_entry]
        except KeyError:
            grouped[key] = [new_entry]
    return grouped


def aggregate(
    objects: list[Object],
    agg_function: Callable[[Object, Object], Object],
) -> Object:
    return reduce(agg_function, objects)


def plot_csv(output: Path, csv_data: list[Object]) -> None:
    from csv import DictWriter

    with open(Path(output), "w") as csvfile:
        fieldnames = [k for k in csv_data[0].keys()]
        writer = DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in csv_data:
            writer.writerow(entry)


from typing import TypedDict


class GroupedInner(TypedDict):
    profile: ProfileTimes
    count: int


Grouped = dict[Any, dict[Any, list[GroupedInner]]]
Aggregated = dict[Any, dict[Any, GroupedInner]]


def agg_profiles(grouped: Grouped) -> Aggregated:
    def aggr(agg: GroupedInner, profile: GroupedInner) -> GroupedInner:
        return {
            "profile": ProfileTimes(
                agg["profile"].total + profile["profile"].total,
                agg["profile"].network + profile["profile"].network,
            ),
            "count": agg.get("count", 1) + 1,
        }

    return {
        k: {
            k2: reduce(
                aggr,
                v2,
            )
            for k2, v2 in v.items()
        }
        for k, v in grouped.items()
    }


def cache_op(op: str, timer: Timer | None = None) -> None:
    cache_params = [
        ProfileParams(
            as_async=True, sequence_start=15712, sequence_len=1000, batch_size=100
        ),
        ProfileParams(
            as_async=True, sequence_start=16212, sequence_len=1000, batch_size=100
        ),
    ]

    def make_stats_path_cache(params: ProfileParams) -> Path:
        return Path(
            f"profile-stats-cache-diff-{params.sequence_start}-{params.sequence_len}.stat"
        )

    if op == "dump":
        CACHE_PATH.unlink(missing_ok=True)

        print("A1 & A2...")
        with no_stdout(), autodelete(CACHE_PATH):
            for params in cache_params:
                profile(
                    download_function,
                    timer,
                    make_stats_path_cache(params),
                    True,
                    params,
                )

        print("B...")
        with no_stdout(), autodelete(CACHE_PATH):
            params = cache_params[1]
            profile(
                download_function,
                timer,
                Path("profile-stats-cache-diff-only-second.stat"),
                True,
                params,
            )

        print("C...")
        with no_stdout(), autodelete(CACHE_PATH):
            params = ProfileParams(
                as_async=True,
                sequence_start=cache_params[0].sequence_start,
                sequence_len=1500,
                batch_size=100,
            )
            profile(
                download_function,
                timer,
                Path("profile-stats-cache-diff-full.stat"),
                True,
                params,
            )
            profile(
                download_function,
                timer,
                Path("profile-stats-cache-diff-full-second.stat"),
                True,
                params,
            )
        print("[D]one.")
    elif op == "view":
        cache_profiles_paths = [
            *[make_stats_path_cache(params) for params in cache_params],
            *[
                Path(path)
                for path in [
                    "profile-stats-cache-diff-only-second.stat",
                    "profile-stats-cache-diff-full.stat",
                    "profile-stats-cache-diff-full-second.stat",
                ]
            ],
        ]
        cache_profiles = [
            {path.as_posix(): view_profile(path)} for path in cache_profiles_paths
        ]
        print(f"Cache profiles {cache_params}:")
        pprint(cache_profiles)

        # agg = agg_profiles(cache_profiles)


def main() -> None:
    """Statistics generation."""
    params_setup = ProfileParamsSetup(
        as_async=[True],
        sequence_starts=[15712],
        sequence_lens=[10000],  # [10, 50, 100, 1000],
        batch_sizes=[500],  # 1, 10, 100, 1000
    )

    timer = None  # io_timer

    import sys

    if len(sys.argv) == 1:
        print(f"Usage: {sys.argv[0]} <dump | view | dump-cache | view-cache>")

    _, op, *args = sys.argv

    if op == "dump-cache":
        cache_op("dump", timer)
    if op == "view-cache":
        cache_op("view")
    if op == "dump":
        combs = sum(
            [
                params.sequence_len * params.batch_size
                if params.as_async
                else params.sequence_len
                for params in params_setup
            ]
        )

        if input(f"Combinations: {combs}. Continue? (y/n)") == "n":
            return
        profile_and_dump(download_function, timer, params_setup)
    if op == "view":
        headers = {
            "sequence_len": "Nº de processos",
            "batch_size": "Tamanho do bloco",
            "network_time": "IO de Rede",
            "cpu_time": "CPU",
            "total_time": "IO + CPU",
            "network_time_sync": "IO de Rede (Sync)",
            "cpu_time_sync": "CPU (Sync)",
            "total_time_sync": "IO + CPU (Sync)",
            "network_time_async": "IO de Rede (Async)",
            "cpu_time_async": "CPU (Async)",
            "total_time_async": "IO + CPU (Async)",
        }

        profiles = [
            {**params._asdict(), "profile": profile_data}
            for params in params_setup
            if (profile_data := view_profile(make_stats_path(params))) is not None
        ]

        pprint(profiles)

        csv_data = []

        if "--plot-sync-async" in args:
            grouped = group_by(profiles, "sequence_len")
            grouped = {k: group_by(group, "as_async") for k, group in grouped.items()}
            pprint(grouped)
            grouped = agg_profiles(grouped)

            csv_data = []
            for sequence_len, group in grouped.items():
                sync_group = group[False]
                async_group = group[True]
                sync_profile = sync_group["profile"]
                async_profile = async_group["profile"]

                print(f"{sequence_len=}")
                input("Sync Profile:")
                pprint(sync_group)
                input("Async Profile:")
                pprint(async_group)
                input("Done.")

                csv_data.append(
                    {
                        headers["sequence_len"]: sequence_len,
                        headers["network_time_sync"]: sync_profile.network
                        / sync_group.get("count", 1),
                        headers["cpu_time_sync"]: (
                            sync_profile.total - sync_profile.network
                        )
                        / sync_group.get("count", 1),
                        headers["network_time_async"]: async_profile.network
                        / async_group.get("count", 1),
                        headers["cpu_time_async"]: (
                            async_profile.total - async_profile.network
                        )
                        / async_group.get("count", 1),
                    }
                )
            plot_csv(Path("io_stats-sync-async.csv"), csv_data)

        if "--plot-async-by-batch-size" in args:
            grouped = group_by(profiles, "batch_size")
            grouped = {
                k: [item for item in group if item["as_async"]]
                for k, group in grouped.items()
                if k > 1
            }
            grouped = {
                k: group_by(group, "sequence_len") for k, group in grouped.items()
            }
            grouped = agg_profiles(grouped)
            pprint(grouped)

            csv_data = []
            for batch_size, groups in grouped.items():
                csv_data.append(
                    {
                        headers["batch_size"]: batch_size,
                        **{
                            f"{headers['sequence_len']}: {sequence_len}": group[
                                "profile"
                            ].total
                            for sequence_len, group in groups.items()
                        },
                    }
                )

            pprint(csv_data)
            plot_csv(Path("io_stats-batch-size.csv"), csv_data)

        if "--plot-sync-io-cpu-by-num-proc" in args:
            grouped = group_by(profiles, "as_async")
            grouped = {
                k: group_by(group, "sequence_len")
                for k, group in grouped.items()
                if not k
            }
            grouped = agg_profiles(grouped)

            csv_data = []
            for sequence_len, group in grouped[False].items():
                csv_data.append(
                    {
                        headers["sequence_len"]: sequence_len,
                        headers["network_time"]: group["profile"].network,
                        headers["cpu_time"]: group["profile"].total
                        - group["profile"].network,
                    }
                )
            plot_csv(Path("io_stats-io-cpu-by-num-proc.csv"), csv_data)
    print("👀 (fim de tudo)")


if __name__ == "__main__":
    main()
