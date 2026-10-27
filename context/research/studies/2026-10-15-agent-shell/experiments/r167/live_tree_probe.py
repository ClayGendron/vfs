"""Review probe for spec 167: check the spec's live-tree claims against the tree as found.

Run from the vfs repo root:

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r167/live_tree_probe.py

Each section prints what the live tree does today. Nothing under src/ or tests/ is touched.
"""

from __future__ import annotations

import asyncio

from vfs import Authority, Principal, VirtualFileSystem
from vfs.models import Entry
from vfs.results import Result
from vfs.results.projection import default_projection
from vfs.storage.backends.memory import InMemoryStorage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def show(label: str, result: Result) -> None:
    rows = [(str(o.path), sorted(o.populated)) for o in result.observations][:6]
    print(f"{label}: success={result.success} ops={result.ops} rows={len(result)}")
    for path, populated in rows:
        print(f"   row {path} populated={populated}")
    for e in result.errors:
        print(f"   {e.severity} {e.kind} path={e.path} msg={e.message!r}")


async def main() -> None:
    vfs = VirtualFileSystem(storage=InMemoryStorage())
    alice = Authority.of(Principal("alice"))
    seed = [
        Entry(path="/src/auth.py", content="x = 1\n"),
        Entry(path="/src/db.py", content="token = auth()\nauth again\n"),
        Entry(path="/src/sub/deep.py", content="pass\n"),
        Entry(path="/src/.hidden.py", content="secret\n"),
        Entry(path="/src/notes.txt", content="no trailing newline"),
        Entry(path="/img/logo.png", data=PNG),
        Entry(path="/d/a.txt", content="a\n"),
        Entry(path="/d/b.txt", content="b\n"),
        Entry(path="/e/one.txt", content="one one one\ntwo one\n"),
    ]
    wrote = await vfs.write(seed, parents=True, authority=alice)
    assert wrote.success, wrote.to_str()
    await vfs.mkdir("/empty", authority=alice)

    banner("1. default projection table today")
    for op in ("run", "cli", "read", "ls", "grep"):
        print(f"   {op!r}: {default_projection(op)}")

    banner("2. a bytes row rendered today (read default columns, then data projected)")
    r = await vfs.read("/img/logo.png", authority=alice)
    show("read png (default columns)", r)
    print(f"   to_str() -> {r.to_str()!r}")
    r2 = await vfs.read("/img/logo.png", columns=frozenset({"data", "mime_type", "size_bytes"}), authority=alice)
    show("read png (data projected)", r2)
    print(f"   to_str() -> {r2.to_str()!r}")
    print(f"   to_payload observations[0] keys -> {sorted(r2.to_payload()['observations'][0])}")
    print(f"   to_payload data value -> {r2.to_payload()['observations'][0].get('data')!r}")
    ls_img = await vfs.ls("/img", authority=alice)
    show("ls /img", ls_img)
    st = await vfs.stat("/img/logo.png", authority=alice)
    show("stat png", st)
    print(f"   stat to_str() -> {st.to_str()!r}")

    banner("3. read of two text rows renders with ==> headers (what a byte seam would carry)")
    two = await vfs.read(observations=(await vfs.ls("/d", authority=alice)).observations, authority=alice)
    print(f"   {two.to_str()!r}")
    one = await vfs.read("/src/notes.txt", authority=alice)
    print(f"   single row without trailing newline -> {one.to_str()!r}")

    banner("4. empty results render as the empty string today")
    print(f"   ls /empty -> {(await vfs.ls('/empty', authority=alice)).to_str()!r}")
    print(f"   grep zzz -> {(await vfs.grep('zzz', authority=alice)).to_str()!r}")

    banner("5. glob: slash-free pattern scoped to /src reaches nested leaves and dotfiles")
    g = await vfs.glob("*.py", paths=("/src",), authority=alice)
    print(f"   glob('*.py', paths=('/src',)) -> {sorted(str(p) for p in g.paths)}")
    g2 = await vfs.glob("/src/*.py", authority=alice)
    print(f"   glob('/src/*.py') -> {sorted(str(p) for p in g2.paths)}")
    g3 = await vfs.glob("*.nomatch", paths=("/src",), authority=alice)
    show("glob no match", g3)
    ls_src = await vfs.ls("/src", authority=alice)
    print(f"   ls /src -> {sorted(str(p) for p in ls_src.paths)}")
    ls_root = await vfs.ls("/", authority=alice)
    print(f"   ls / -> {sorted(str(p) for p in ls_root.paths)}")

    banner("6. rows into grep as observations: content search, not a filter on names")
    listing = await vfs.ls("/src", authority=alice)
    gr = await vfs.grep("auth", observations=listing.observations, authority=alice)
    print(f"   ls /src | grep auth (rows->rows) -> {gr.to_str()!r}")
    print("   bash would print the one name containing 'auth': 'auth.py'")

    banner("7. grep output modes as rendered")
    for mode in ("lines", "files", "count"):
        res = await vfs.grep("one", paths=("/e",), output_mode=mode, authority=alice)  # ty: ignore[invalid-argument-type]
        print(f"   output_mode={mode} -> {res.to_str()!r}")
        if mode == "count":
            print(f"     count row populated={[sorted(o.populated) for o in res.observations]} matches={[o.matches for o in res.observations]}")

    banner("8. copy / move onto an existing destination; copy of a directory")
    show("copy /d/a.txt -> /d/b.txt (dest exists)", await vfs.copy("/d/a.txt", "/d/b.txt", authority=alice))
    show("move /d/a.txt -> /d/b.txt (dest exists)", await vfs.move("/d/a.txt", "/d/b.txt", authority=alice))
    show("copy /d -> /d2 (directory, no -r)", await vfs.copy("/d", "/d2", authority=alice))
    show("copy /d/a.txt -> /empty (dest is a directory)", await vfs.copy("/d/a.txt", "/empty", authority=alice))

    banner("9. edit with a repeated needle (sed s/one/ONE/ without g)")
    show("edit old='one' new='ONE'", await vfs.edit("/e/one.txt", old="one", new="ONE", authority=alice))
    print(f"   body after -> {(await vfs.read('/e/one.txt', authority=alice)).one().content!r}")

    banner("10. delete cascade=False on a non-empty directory; mkdir parents on an existing dir")
    show("delete /d2 cascade=False", await vfs.delete("/d2", cascade=False, authority=alice))
    show("mkdir /src parents=True", await vfs.mkdir("/src", parents=True, authority=alice))
    show("delete /nope", await vfs.delete("/nope", authority=alice))

    banner("11. merge of two terminal rows at the same path (two statements' stdout)")
    a = Result(ops=("cli",), observations=[r.one().model_copy(update={"content": "first\n"})]) if False else None
    del a
    from vfs.models import Observation

    first = Result(ops=("cli",), observations=[Observation(path="/.vfs/run/1/stdout", content="first\n", kind="file")])
    second = Result(ops=("cli",), observations=[Observation(path="/.vfs/run/1/stdout", content="second\n", kind="file")])
    merged = Result.merge([first, second])
    print(f"   merged rows={len(merged)} content={[o.content for o in merged.observations]}")
    cat_twice = Result.merge([one, one])
    print(f"   cat f; cat f merged rows={len(cat_twice)}")
    mixed = Result.merge([ls_src, one])
    print(f"   ls; cat merged op={mixed.op} -> render first 80 chars {mixed.to_str()[:80]!r}")

    banner("12. system actor through the router's default authority")
    sysfs = VirtualFileSystem(storage=InMemoryStorage(), default_authority=Authority.system())
    w = await sysfs.write(path="/x.txt", content="x")
    print(f"   write with authority=None on a default-system router -> success={w.success}")


asyncio.run(main())
