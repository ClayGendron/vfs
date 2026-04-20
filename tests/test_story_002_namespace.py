from __future__ import annotations

import pytest

from vfs.paths import (
    base_path,
    chunk_path,
    decompose_edge,
    edge_in_path,
    edge_out_path,
    endpoint_root,
    meta_root,
    parent_path,
    validate_mutation_path,
    version_path,
)
from vfs.query.ast import MkedgeCommand
from vfs.query.parser import QuerySyntaxError, parse_query


def test_story_002_path_helpers_use_hidden_root_namespace() -> None:
    assert chunk_path("/src/a.py", "login") == "/.vfs/src/a.py/__meta__/chunks/login"
    assert version_path("/src/a.py", 3) == "/.vfs/src/a.py/__meta__/versions/3"
    assert edge_out_path("/src/a.py", "/src/b.py", "imports") == "/.vfs/src/a.py/__meta__/edges/out/imports/src/b.py"
    assert edge_in_path("/src/a.py", "/src/b.py", "imports") == "/.vfs/src/b.py/__meta__/edges/in/imports/src/a.py"


def test_story_002_meta_root_exact_matching() -> None:
    assert meta_root("/src/a.py") == "/.vfs/src/a.py"
    assert meta_root("/.vfs/src/a.py/__meta__/chunks/login") == "/.vfs/src/a.py/__meta__/chunks/login"
    assert meta_root("/.vfsbar/src/a.py") == "/.vfs/.vfsbar/src/a.py"
    with pytest.raises(ValueError):
        meta_root("/.vfs")


def test_story_002_metadata_paths_can_be_edge_endpoints() -> None:
    target = "/.vfs/src/target.py/__meta__/chunks/login"
    out_path = edge_out_path("/src/file.py", target, "references")
    in_path = edge_in_path("/src/file.py", target, "references")

    assert out_path == "/.vfs/src/file.py/__meta__/edges/out/references/.vfs/src/target.py/__meta__/chunks/login"
    assert in_path == "/.vfs/src/target.py/__meta__/chunks/login/__meta__/edges/in/references/src/file.py"
    assert decompose_edge(in_path) is not None
    assert endpoint_root(in_path) == target
    assert base_path(in_path) == "/src/target.py"
    assert parent_path(in_path) == "/.vfs/src/target.py/__meta__/chunks/login/__meta__/edges/in/references/src"


def test_story_002_reserved_mutation_paths_are_rejected() -> None:
    ok, err = validate_mutation_path("/.vfs/tmp.txt", kind="file")
    assert not ok
    assert "reserved metadata space" in err


def test_story_002_query_parser_accepts_mkedge_source_target_type_order() -> None:
    plan = parse_query("mkedge /src/a.py /src/b.py imports")
    assert plan.methods == ("mkedge",)
    assert isinstance(plan.ast, MkedgeCommand)
    assert plan.ast.source == "/src/a.py"
    assert plan.ast.target == "/src/b.py"
    assert plan.ast.edge_type == "imports"


def test_story_002_query_parser_rejects_removed_mkconn_alias() -> None:
    with pytest.raises(QuerySyntaxError, match="Unknown command"):
        parse_query("mkconn /src/a.py /src/b.py imports")

    ok, err = validate_mutation_path("/.vfs/src/a.py/random", kind="file")
    assert not ok
    assert "reserved metadata space" in err


@pytest.mark.asyncio
async def test_story_002_file_write_materializes_vfs_namespace(db) -> None:
    result = await db.write("/src/a.py", "print('hi')")
    assert result.success

    stat = await db.stat("/.vfs/src/a.py")
    assert stat.success
    assert stat.entries[0].kind == "directory"

    listed = await db.ls("/.vfs/src/a.py")
    assert listed.paths == ("/.vfs/src/a.py/__meta__",)


@pytest.mark.asyncio
async def test_story_002_chunk_write_uses_vfs_tree(db) -> None:
    await db.write("/src/a.py", "print('hi')")
    chunk = await db.write("/.vfs/src/a.py/__meta__/chunks/login", "chunk body")
    assert chunk.success

    listed = await db.ls("/.vfs/src/a.py/__meta__/chunks")
    assert listed.paths == ("/.vfs/src/a.py/__meta__/chunks/login",)
    assert listed.entries[0].kind == "chunk"


@pytest.mark.asyncio
async def test_story_002_mkedge_writes_canonical_out_projection(db) -> None:
    await db.write("/src/a.py", "print('a')")
    await db.write("/src/b.py", "print('b')")

    result = await db.mkedge("/src/a.py", "/src/b.py", "imports")
    assert result.success
    assert result.function == "mkedge"
    assert result.paths == ("/.vfs/src/a.py/__meta__/edges/out/imports/src/b.py",)
    assert result.entries[0].kind == "edge"


@pytest.mark.asyncio
async def test_story_002_inverse_projection_attaches_when_target_exists(db) -> None:
    await db.write("/src/a.py", "print('a')")
    await db.mkedge("/src/a.py", "/src/b.py", "imports")

    missing = await db.stat("/.vfs/src/b.py/__meta__/edges/in/imports/src/a.py")
    assert not missing.success

    await db.write("/src/b.py", "print('b')")

    inverse = await db.stat("/.vfs/src/b.py/__meta__/edges/in/imports/src/a.py")
    assert inverse.success
    assert inverse.entries[0].kind == "edge"

    listed = await db.ls("/.vfs/src/b.py/__meta__/edges/in/imports/src")
    assert listed.paths == ("/.vfs/src/b.py/__meta__/edges/in/imports/src/a.py",)


@pytest.mark.asyncio
async def test_story_002_move_updates_vfs_metadata_paths(db) -> None:
    await db.write("/src/a.py", "print('a')")
    await db.write("/src/b.py", "print('b')")
    await db.write("/.vfs/src/a.py/__meta__/chunks/login", "chunk body")
    await db.mkedge("/src/a.py", "/src/b.py", "imports")

    moved = await db.move("/src/a.py", "/src/c.py")
    assert moved.success

    assert (await db.read("/src/c.py")).success
    assert not (await db.read("/src/a.py")).success
    assert (await db.read("/.vfs/src/c.py/__meta__/chunks/login")).success
    assert (await db.read("/.vfs/src/c.py/__meta__/edges/out/imports/src/b.py")).success
    assert (await db.stat("/.vfs/src/b.py/__meta__/edges/in/imports/src/c.py")).success
