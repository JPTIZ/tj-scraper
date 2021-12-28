"""Time measurement utilities."""
from time import time
from typing import Callable


def timeit(f: Callable, *args, **kwargs):
    start = time()
    result = f(*args, **kwargs)
    end = time()

    print(f"{f.__name__} took {end - start:.2}s to execute.")
    return result
