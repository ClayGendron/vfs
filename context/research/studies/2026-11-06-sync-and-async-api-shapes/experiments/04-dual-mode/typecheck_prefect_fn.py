"""Prefect's decorators on a free function rather than a method: does mypy solve the return type then?"""

from typing import reveal_type

from prefect.utilities.asyncutils import sync_compatible


@sync_compatible
async def read(path: str) -> int:
    return 1


def sync_caller() -> None:
    reveal_type(read("a"))
    x: int = read("a")


async def async_caller() -> None:
    reveal_type(await read("a"))
