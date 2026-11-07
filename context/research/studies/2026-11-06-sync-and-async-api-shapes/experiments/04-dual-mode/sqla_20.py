"""SQLAlchemy 2.0.52 (the vfs venv) bridge: await_only and the deprecated await_fallback in settings 1 and 2."""

import asyncio
import warnings

import sqlalchemy
from sqlalchemy.util import await_fallback, await_only, greenlet_spawn

warnings.simplefilter("always")


async def aread() -> str:
    await asyncio.sleep(0)
    return "value"


def attempt(label: str, fn) -> None:
    try:
        print(label, "->", fn())
    except Exception as exc:  # noqa: BLE001
        print(label, "-> RAISED", type(exc).__name__, str(exc)[:110])


print("sqlalchemy", sqlalchemy.__version__)
attempt("s1 await_only, no loop", lambda: await_only(aread()))
attempt("s1 await_fallback, no loop", lambda: await_fallback(aread()))


async def main() -> None:
    attempt("s2 await_only on loop thread", lambda: await_only(aread()))
    attempt("s2 await_fallback on loop thread", lambda: await_fallback(aread()))
    print("s2 under greenlet_spawn ->", await greenlet_spawn(lambda: await_only(aread())))


asyncio.run(main())
