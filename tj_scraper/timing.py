"""Time measurement utilities."""
from time import time
from typing import Callable


def timeit(function: Callable, *args, **kwargs):
    """
    Runs a function and returns how much time in seconds it took to execute it.
    """
    start = time()
    result = function(*args, **kwargs)
    end = time()

    return result, end - start


def report_time(function: Callable, *args, **kwargs):
    """
    Same as `timeit`, but prints the ellapsed time.
    """
    result, ellapsed = timeit(function, *args, **kwargs)

    print(f"{function.__name__} took {ellapsed:.2}s to execute.")
    return result, ellapsed
