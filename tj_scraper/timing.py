"""Time measurement utilities."""
from dataclasses import dataclass
from time import time
from typing import Callable, Generic, ParamSpec, TypeVar

Return = TypeVar("Return")
Args = ParamSpec("Args")


@dataclass(frozen=True, slots=True)
class Timed(Generic[Return]):
    value: Return
    time: float


def timeit(
    function: Callable[Args, Return], *args: Args.args, **kwargs: Args.kwargs
) -> Timed[Return]:
    """
    Runs a function and returns how much time in seconds it took to execute it.
    """
    start = time()
    result = function(*args, **kwargs)
    end = time()

    return Timed(result, end - start)


def report_time(
    function: Callable[Args, Return], *args: Args.args, **kwargs: Args.kwargs
) -> Timed[Return]:
    """
    Same as `timeit`, but prints the ellapsed time.
    """
    result = timeit(function, *args, **kwargs)

    print(f"{function.__name__} took {result.time:.2}s to execute.")
    return result
