"""Runnable demo for the CLI-style query engine."""
# ruff: noqa: T201

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from grover.backends.database import DatabaseFileSystem


async def build_demo_fs() -> DatabaseFileSystem:
    """Create an in-memory filesystem populated with demo data."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    fs = DatabaseFileSystem(engine=engine)

    async with fs._use_session() as session:
        await fs._write_impl("/src/auth.py", "import utils\ndef login(): pass", session=session)
        await fs._write_impl("/src/utils.py", "def helper(): pass", session=session)
        await fs._write_impl("/src/db.py", "import utils\ndef connect(): pass", session=session)
        await fs._write_impl("/src/api.py", "import auth\nimport utils", session=session)
        await fs._write_impl("/src/config.py", "DEBUG = True", session=session)
        await fs._write_impl("/docs/notes.md", "# Notes\n\nAuthentication design notes.", session=session)

    for source, target, connection_type in [
        ("/src/auth.py", "/src/utils.py", "imports"),
        ("/src/auth.py", "/src/db.py", "calls"),
        ("/src/utils.py", "/src/db.py", "imports"),
        ("/src/api.py", "/src/auth.py", "imports"),
        ("/src/api.py", "/src/utils.py", "imports"),
    ]:
        async with fs._use_session() as session:
            await fs._mkconn_impl(source, target, connection_type, session=session)

    return fs


async def show_query(fs: DatabaseFileSystem, query: str) -> None:
    """Print the query, its lowered method list, and rendered output."""
    plan = fs.parse_query(query)
    rendered = await fs.cli(query)

    print("=" * 80)
    print(query)
    print(f"methods: {list(plan.methods)}")
    print("-" * 80)
    print(rendered or "<no output>")
    print()


async def main() -> None:
    fs = await build_demo_fs()
    try:
        print("CLI Query Demo")
        print()
        print("This shows:")
        print("- the query string")
        print("- stage-local args and flags such as --k, --max-results, --depth, --include, and --min")
        print("- the ordered public methods from parse_query()")
        print("- the rendered output from cli()")
        print()

        queries = [
            ("basic listing", "ls /src"),
            ("grep with a stage-local flag", 'grep "import" --max-results 2 | read'),
            ("lexical search with --k", 'lsearch "auth" --k 5 | intersect (glob "/src/*.py")'),
            ("graph traversal with --depth", "nbr /src/auth.py --depth 2"),
            ("tree with metadata opt-in via --include", "tree /src --include connections"),
            ("meeting graph with --min, then ranking", 'grep "import" | meetinggraph --min | pagerank | top 3'),
            ("set union stays query-local", 'grep "import" & grep "DEBUG"'),
            ("pipeline into a path-mutating command", 'grep "import utils" | cp /backup'),
            ("list the copied tree", "ls /backup"),
        ]

        for label, query in queries:
            print(label)
            await show_query(fs, query)
    finally:
        if fs._engine is not None:
            await fs._engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
