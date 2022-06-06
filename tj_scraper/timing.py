"""Time measurement utilities."""
from time import time
from typing import Callable, TypeVar

Return = TypeVar("Return")


def timeit(function: Callable[..., Return], *args, **kwargs) -> tuple[Return, float]:
    """
    Runs a function and returns how much time in seconds it took to execute it.
    """
    try:
        start = time()
        result = function(*args, **kwargs)
        end = time()
    except TypeError:
        start = time()
        result = function(*args)
        end = time()

    return result, end - start


def report_time(
    function: Callable[..., Return], *args, **kwargs
) -> tuple[Return, float]:
    """
    Same as `timeit`, but prints the ellapsed time.
    """
    result, ellapsed = timeit(function, *args, **kwargs)

    print(f"{function.__name__} took {ellapsed:.2}s to execute.")
    return result, ellapsed
