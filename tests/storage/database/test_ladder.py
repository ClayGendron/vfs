"""The ladder's three new rungs through the verbs — ``list``, ``add``, ``contribute``.

The road baseline is the regression pin: every line a caller saw under
the three-rung ladder is unchanged, and a ``list`` grant adds bare rows
exactly where it names them. Then the verb matrices, one row per entry
of the verb-to-rung table, as a named user, as a set of two, and as
anonymous; the search verbs over ``list`` rows; ``rmedge``'s per-row
record on a hidden target; the anonymous gate judged at the addressed
path; and the aliased compiles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import pytest

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind, Result, Severity
from vfs.storage import ResolvedPair
from vfs.storage.backends.database.dialects import SQLITE
from vfs.storage.backends.database.rights import Resolution, Visibility, weight
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import GRANTABLE_LEVELS, GrantRow, resolve
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from vfs.storage.grants import GrantLevel

SYSTEM = Authority.system()
ANN = Authority.of(Principal("ann"))
BOB = Authority.of(Principal("bob"))
CAROL = Authority.of(Principal("carol"))
ANON = Authority.anonymous()
PAIR = Authority.on_behalf_of({Principal("ann"), Principal("bob")}, actor=Principal("bot", kind="service"))

BARE = frozenset({"path", "kind"})

# The road baseline world: ann reads one deep file in a mount everyone holds nothing on.
BASELINE = {
    "/projects/alpha/notes.md": "alpha notes",
    "/projects/alpha/other.md": "alpha other",
    "/projects/beta/secret.md": "beta secret",
    "/pub/readme.md": "public readme",
}


@pytest.fixture
async def storage() -> AsyncIterator[InMemoryStorage]:
    storage = InMemoryStorage()
    yield storage
    await storage.close()


def _kind(result: Result) -> ErrorKind | str:
    assert result.success is False, result
    return result.errors[0].kind


def _paths(result: Result) -> list[str]:
    assert result.success is True, result.errors
    return [str(row.path) for row in result.observations]


def _shown(result: Result) -> dict[str, frozenset[str]]:
    assert result.success is True, result.errors
    return {str(row.path): row.populated for row in result.observations}


async def _seed(storage: InMemoryStorage, files: dict[str, str], root: GrantLevel = "none") -> None:
    entries = [Entry(path=Path(path), content=body) for path, body in files.items()]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    assert (await storage.posture(path=Path("/"), posture=root, authority=SYSTEM)).success is True


async def _grant(storage: InMemoryStorage, path: str, principal: str, level: GrantLevel) -> None:
    result = await storage.grant(path=Path(path), principal=principal, level=level, authority=SYSTEM)
    assert result.success is True, result.errors


async def _write(storage: InMemoryStorage, path: str, who: Authority, body: str = "x", **kw: Any) -> Result:
    return await storage.write(entries=[Entry(path=Path(path), content=body)], authority=who, **kw)


async def _edit(storage: InMemoryStorage, path: str, who: Authority) -> Result:
    return await storage.edit(path=Path(path), edits=[EditOperation("x", "y")], authority=who)


# ---------------------------------------------------------------------------
# The road baseline — unchanged, then a list grant
# ---------------------------------------------------------------------------


async def test_the_road_baseline_is_unchanged_line_for_line(storage: InMemoryStorage) -> None:
    await _seed(storage, BASELINE)
    await _grant(storage, "/projects/alpha/notes.md", "ann", "read")
    assert _shown(await storage.ls(path=Path("/"), authority=ANN)) == {"/projects": BARE}
    assert _shown(await storage.ls(path=Path("/projects"), authority=ANN)) == {"/projects/alpha": BARE}
    listed = _shown(await storage.ls(path=Path("/projects/alpha"), authority=ANN))
    assert set(listed) == {"/projects/alpha/notes.md"} and listed["/projects/alpha/notes.md"] > BARE
    tree = _shown(await storage.tree(path=Path("/"), authority=ANN))
    assert tree["/projects"] == tree["/projects/alpha"] == BARE and tree["/projects/alpha/notes.md"] > BARE
    assert set(tree) == {"/projects", "/projects/alpha", "/projects/alpha/notes.md"}
    assert _shown(await storage.stat(path=Path("/projects"), authority=ANN)) == {"/projects": BARE}
    hidden = await storage.stat(path=Path("/projects/beta"), authority=ANN)
    absent = await storage.stat(path=Path("/projects/gamma"), authority=ANN)
    assert _kind(hidden) == _kind(absent) == ErrorKind.not_found
    assert hidden.errors[0].model_dump(exclude={"path"}) == absent.errors[0].model_dump(exclude={"path"})
    assert _kind(await storage.stat(path=Path("/projects/alpha/other.md"), authority=ANN)) == ErrorKind.not_found
    assert _kind(await storage.read(path=Path("/projects"), authority=ANN)) == ErrorKind.wrong_kind
    assert _paths(await storage.glob(patterns=("/**",), authority=ANN)) == [
        "/projects",
        "/projects/alpha",
        "/projects/alpha/notes.md",
    ]
    assert _paths(await storage.grep(pattern="alpha", allow_scan=True, authority=ANN)) == ["/projects/alpha/notes.md"]
    assert _kind(await storage.mkdir(path=Path("/projects/gamma"), authority=ANN)) == ErrorKind.permission_denied
    assert _kind(await _write(storage, "/projects/alpha/notes.md", ANN)) == ErrorKind.permission_denied


async def test_a_list_grant_adds_exactly_the_bare_rows_it_names(storage: InMemoryStorage) -> None:
    await _seed(storage, BASELINE)
    await _grant(storage, "/projects/alpha/notes.md", "ann", "read")
    await _grant(storage, "/projects/beta", "ann", "list")
    tree = _shown(await storage.tree(path=Path("/"), authority=ANN))
    assert set(tree) == {
        "/projects",
        "/projects/alpha",
        "/projects/alpha/notes.md",
        "/projects/beta",
        "/projects/beta/secret.md",
    }
    assert tree["/projects/beta"] == tree["/projects/beta/secret.md"] == BARE
    assert _shown(await storage.stat(path=Path("/projects/beta/secret.md"), authority=ANN)) == {
        "/projects/beta/secret.md": BARE
    }
    # A list row is visible, so reading it is refused, not absent; a hidden sibling stays absent.
    assert (
        _kind(await storage.read(path=Path("/projects/beta/secret.md"), authority=ANN)) == ErrorKind.permission_denied
    )
    assert _kind(await storage.read(path=Path("/projects/alpha/other.md"), authority=ANN)) == ErrorKind.not_found
    assert _paths(await storage.grep(pattern="secret", allow_scan=True, authority=ANN)) == []


async def test_a_tombstoned_list_row_is_a_plain_not_found_on_the_live_side(storage: InMemoryStorage) -> None:
    await _seed(storage, BASELINE)
    await _grant(storage, "/projects/beta", "ann", "list")
    await _grant(storage, "/pub", "ann", "read")
    assert (await storage.delete(path=Path("/projects/beta/secret.md"), authority=SYSTEM)).success is True
    assert (await storage.delete(path=Path("/pub/readme.md"), authority=SYSTEM)).success is True
    plain = await storage.stat(path=Path("/projects/beta/secret.md"), authority=ANN)
    assert _kind(plain) == ErrorKind.not_found and not plain.errors[0].data
    hinted = await storage.stat(path=Path("/pub/readme.md"), authority=ANN)
    assert _kind(hinted) == ErrorKind.not_found and "vfs.deleted_at" in (hinted.errors[0].data or {})
    # In the trash view the list tombstone shows bare: no deleted_at.
    viewed = _shown(await storage.ls(path=Path("/.vfs/trash"), authority=ANN))
    assert viewed["/projects/beta/secret.md"] == BARE
    assert "deleted_at" in viewed["/pub/readme.md"]


# ---------------------------------------------------------------------------
# The verb matrices — add and contribute, as a user, a set, anonymous
# ---------------------------------------------------------------------------


async def _inbox(storage: InMemoryStorage, level: GrantLevel, *who: str) -> None:
    """``/inbox`` with carol's row in it, granted at *level* to each of *who*; the mount otherwise closed."""
    await _seed(storage, {"/inbox/carol.md": "x", "/elsewhere.md": "x"})
    await _grant(storage, "/inbox", "carol", "read_write")
    for principal in who:
        await _grant(storage, "/inbox", principal, level)


@pytest.mark.parametrize("who", [BOB, PAIR], ids=["user", "set"])
async def test_add_creates_and_alters_only_its_own_rows(storage: InMemoryStorage, who: Authority) -> None:
    await _inbox(storage, "add", "ann", "bob")
    assert (await _write(storage, "/inbox/mine.md", who)).success is True
    assert (await storage.mkdir(path=Path("/inbox/sub"), authority=who)).success is True
    # Another's row: readable, never altered.
    assert (await storage.read(path=Path("/inbox/carol.md"), authority=who)).success is True
    assert _kind(await _write(storage, "/inbox/carol.md", who)) == ErrorKind.permission_denied
    assert _kind(await _edit(storage, "/inbox/carol.md", who)) == ErrorKind.permission_denied
    assert _kind(await storage.delete(path=Path("/inbox/carol.md"), authority=who)) == ErrorKind.permission_denied
    moved = [ResolvedPair(Path("/inbox/carol.md"), Path("/inbox/moved.md"))]
    assert _kind(await storage.move(operations=moved, authority=who)) == ErrorKind.permission_denied
    # A set of two owns nothing it makes; a lone subject does, and alters it by the floor.
    if who is not BOB:
        assert _kind(await _write(storage, "/inbox/mine.md", who, "y")) == ErrorKind.permission_denied
        assert _kind(await storage.delete(path=Path("/inbox/mine.md"), authority=who)) == ErrorKind.permission_denied
        return
    assert (await _write(storage, "/inbox/mine.md", who, "y")).success is True
    assert (await storage.edit(path=Path("/inbox/mine.md"), edits=[EditOperation("y", "z")], authority=who)).success
    assert (await storage.delete(path=Path("/inbox/mine.md"), authority=who)).success is True
    assert (await storage.restore(path=Path("/inbox/mine.md"), authority=who)).success is True
    assert (await storage.delete(path=Path("/inbox/mine.md"), authority=who)).success is True


@pytest.mark.parametrize("who", [BOB, PAIR], ids=["user", "set"])
async def test_contribute_edits_anyones_row_and_trashes_only_its_own(storage: InMemoryStorage, who: Authority) -> None:
    await _inbox(storage, "contribute", "ann", "bob")
    assert (await _write(storage, "/inbox/carol.md", who, "theirs, overwritten")).success is True
    edited = await storage.edit(path=Path("/inbox/carol.md"), edits=[EditOperation("theirs", "ours")], authority=who)
    assert edited.success is True
    # The row stays carol's: a contribution never turns into the right to trash or move it.
    assert _kind(await storage.delete(path=Path("/inbox/carol.md"), authority=who)) == ErrorKind.permission_denied
    moved = [ResolvedPair(Path("/inbox/carol.md"), Path("/inbox/moved.md"))]
    assert _kind(await storage.move(operations=moved, authority=who)) == ErrorKind.permission_denied
    assert (await storage.delete(path=Path("/inbox/carol.md"), authority=CAROL)).success is True
    # Another's tombstone: a write at it is a restore, which contribute lacks.
    assert _kind(await _write(storage, "/inbox/carol.md", who)) == ErrorKind.permission_denied
    assert _kind(await storage.restore(path=Path("/inbox/carol.md"), authority=who)) == ErrorKind.permission_denied
    assert (await _write(storage, "/inbox/carol.md", CAROL)).success is True
    # Its own rows a lone subject trashes and restores by the floor; a set owns none.
    assert (await _write(storage, "/inbox/mine.md", who)).success is True
    trashed = await storage.delete(path=Path("/inbox/mine.md"), authority=who)
    assert trashed.success is (who is BOB)
    if who is BOB:
        assert (await storage.restore(path=Path("/inbox/mine.md"), authority=who)).success is True


async def test_read_write_revives_anothers_tombstone_by_writing_at_it(storage: InMemoryStorage) -> None:
    await _inbox(storage, "read_write", "bob")
    assert (await storage.delete(path=Path("/inbox/carol.md"), authority=CAROL)).success is True
    assert (await _write(storage, "/inbox/carol.md", BOB)).success is True
    assert (await storage.read(path=Path("/inbox/carol.md"), authority=BOB)).success is True


async def test_a_set_holds_a_members_floor_where_every_other_member_holds_the_rung(
    storage: InMemoryStorage,
) -> None:
    # ann holds contribute by grant and bob add: the pair edits bob's own rows at
    # contribute (ann by grant, bob by the floor), nobody else's, and trashes
    # none — ann holds no read_write there to pair with bob's floor.
    await _inbox(storage, "add", "bob")
    await _grant(storage, "/inbox", "ann", "contribute")
    assert (await _write(storage, "/inbox/bob.md", BOB)).success is True
    assert (await _write(storage, "/inbox/bob.md", PAIR, "edited by the pair")).success is True
    assert _kind(await _write(storage, "/inbox/carol.md", PAIR)) == ErrorKind.permission_denied
    assert _kind(await storage.delete(path=Path("/inbox/bob.md"), authority=PAIR)) == ErrorKind.permission_denied
    await _grant(storage, "/inbox", "ann", "read_write")
    assert (await storage.delete(path=Path("/inbox/bob.md"), authority=PAIR)).success is True


@pytest.mark.parametrize("posture", ["add", "contribute"])
async def test_anonymous_creates_under_an_add_posture_and_alters_nothing(
    storage: InMemoryStorage, posture: GrantLevel
) -> None:
    await _seed(storage, {"/inbox/carol.md": "x"})
    assert (await storage.posture(path=Path("/inbox"), posture=posture, authority=SYSTEM)).success is True
    assert (await _write(storage, "/inbox/anon.md", ANON)).success is True
    assert (await storage.read(path=Path("/inbox/anon.md"), authority=ANON)).success is True
    # Anonymous owns nothing, so it never alters or trashes its own creation.
    assert _kind(await storage.delete(path=Path("/inbox/anon.md"), authority=ANON)) == ErrorKind.unauthenticated
    assert _kind(await storage.delete(path=Path("/inbox/carol.md"), authority=ANON)) == ErrorKind.unauthenticated
    overwrite = await _write(storage, "/inbox/carol.md", ANON, "y")
    assert (overwrite.success is True) is (posture == "contribute")
    if posture == "add":
        assert _kind(overwrite) == ErrorKind.unauthenticated
        assert _kind(await _write(storage, "/inbox/anon.md", ANON, "y")) == ErrorKind.unauthenticated


async def test_copy_from_a_list_source_is_denied_file_and_directory_alike(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/team/plan.md": "x", "/team/sub/x.md": "x"})
    await _grant(storage, "/team", "bob", "list")
    await _grant(storage, "/mine", "bob", "add")
    assert (await storage.mkdir(path=Path("/mine"), authority=SYSTEM)).success is True
    file = [ResolvedPair(Path("/team/plan.md"), Path("/mine/plan.md"))]
    tree = [ResolvedPair(Path("/team/sub"), Path("/mine/sub"))]
    assert _kind(await storage.copy(operations=file, authority=BOB)) == ErrorKind.permission_denied
    assert _kind(await storage.copy(operations=tree, authority=BOB)) == ErrorKind.permission_denied
    assert _kind(await storage.read(path=Path("/mine/plan.md"), authority=BOB)) == ErrorKind.not_found
    # A readable source copies, and the copy is bob's.
    await _grant(storage, "/team/plan.md", "bob", "read")
    assert (await storage.copy(operations=file, authority=BOB)).success is True
    assert (await _write(storage, "/mine/plan.md", BOB, "mine now")).success is True


async def test_mkdir_on_a_list_directory_is_denied_with_or_without_exist_ok(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/team/plan.md": "x"})
    await _grant(storage, "/team", "bob", "list")
    assert _kind(await storage.mkdir(path=Path("/team"), authority=BOB)) == ErrorKind.permission_denied
    assert _kind(await storage.mkdir(path=Path("/team"), exist_ok=True, authority=BOB)) == ErrorKind.permission_denied
    assert _kind(await storage.mkdir(path=Path("/team/new"), authority=BOB)) == ErrorKind.permission_denied
    assert _kind(await _write(storage, "/team/plan.md", BOB, overwrite=False)) == ErrorKind.permission_denied


async def test_mkedge_passes_a_list_target_and_a_road_directory(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/mine/note.md": "x", "/team/plan.md": "x", "/deep/dir/file.md": "x", "/hidden.md": "x"})
    await _grant(storage, "/mine", "bob", "read_write")
    await _grant(storage, "/team", "bob", "list")
    await _grant(storage, "/deep/dir/file.md", "bob", "read")
    edges = [
        Edge(source=Path("/mine/note.md"), target=Path("/team/plan.md"), edge_type="cites"),
        Edge(source=Path("/mine/note.md"), target=Path("/deep/dir"), edge_type="in"),
    ]
    assert (await storage.mkedge(edges=edges, authority=BOB)).success is True
    hidden = [Edge(source=Path("/mine/note.md"), target=Path("/hidden.md"), edge_type="cites")]
    assert _kind(await storage.mkedge(edges=hidden, authority=BOB)) == ErrorKind.not_found
    # The source needs contribute or own: bob owns nothing under /team and holds list there.
    reverse = [Edge(source=Path("/team/plan.md"), target=Path("/mine/note.md"), edge_type="cites")]
    assert _kind(await storage.mkedge(edges=reverse, authority=BOB)) == ErrorKind.permission_denied


async def test_grants_on_a_list_path_is_not_found(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/team/plan.md": "x", "/pub/readme.md": "x"})
    await _grant(storage, "/team", "bob", "list")
    await _grant(storage, "/pub", "bob", "read")
    assert _kind(await storage.grants(path=Path("/team"), authority=BOB)) == ErrorKind.not_found
    assert (await storage.grants(path=Path("/pub"), authority=BOB)).success is True


async def test_a_grant_takes_every_rung_but_none(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/d/f.md": "x"})
    for level in GRANTABLE_LEVELS:
        assert (await storage.grant(path=Path("/d"), principal="bob", level=level, authority=SYSTEM)).success is True
    refused = await storage.grant(path=Path("/d"), principal="bob", level="none", authority=SYSTEM)  # type: ignore[arg-type]
    assert (
        _kind(refused) == ErrorKind.invalid
        and "'list', 'read', 'add', 'contribute', 'read_write'" in refused.errors[0].message
    )


# ---------------------------------------------------------------------------
# The search verbs over list rows
# ---------------------------------------------------------------------------


async def test_glob_and_tree_name_list_rows_bare_and_grep_and_glean_never_search_them(
    storage: InMemoryStorage,
) -> None:
    await _seed(
        storage, {"/team/plan.md": "lantern plan", "/team/notes.txt": "lantern notes", "/pub/faq.md": "lantern faq"}
    )
    await _grant(storage, "/team", "bob", "list")
    await _grant(storage, "/pub", "bob", "read")
    assert (await storage.reindex()).success is True
    globbed = _shown(await storage.glob(patterns=("/**",), kind="file", ext=("md",), authority=BOB))
    assert set(globbed) == {"/team/plan.md", "/pub/faq.md"}
    assert globbed["/team/plan.md"] == BARE and globbed["/pub/faq.md"] > BARE
    tree = _shown(await storage.tree(path=Path("/team"), authority=BOB))
    assert set(tree) == {"/team/plan.md", "/team/notes.txt"} and set(tree.values()) == {BARE}
    grepped = await storage.grep(pattern="lantern", allow_scan=True, authority=BOB)
    assert _paths(grepped) == ["/pub/faq.md"] and grepped.errors == []
    gleaned = await storage.glean(query="lantern", authority=BOB)
    assert _paths(gleaned) == ["/pub/faq.md"]
    stats = (gleaned.model_extra or {})["lexical_stats"]
    assert stats["n_docs"] == 1 and stats["terms"]["lantern"]["df"] == 1


async def test_ls_of_a_list_file_and_of_a_list_directory(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/team/plan.md": "x", "/team/sub/deep.md": "x", "/team/other.md": "x"})
    await _grant(storage, "/team/plan.md", "bob", "list")
    await _grant(storage, "/team/sub", "bob", "list")
    await _grant(storage, "/team/sub/deep.md", "bob", "read")
    assert _shown(await storage.ls(path=Path("/team/plan.md"), authority=BOB)) == {"/team/plan.md": BARE}
    listed = _shown(await storage.ls(path=Path("/team"), authority=BOB))
    assert listed == {"/team/plan.md": BARE, "/team/sub": BARE}
    deep = _shown(await storage.ls(path=Path("/team/sub"), authority=BOB))
    assert set(deep) == {"/team/sub/deep.md"} and deep["/team/sub/deep.md"] > BARE


# ---------------------------------------------------------------------------
# rmedge — a hidden target answers as an absent one
# ---------------------------------------------------------------------------


async def test_rmedge_answers_a_hidden_target_exactly_as_an_absent_one(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/priv/deep/d.md": "x", "/priv/secret.md": "x", "/pub/readme.md": "x"})
    await _grant(storage, "/priv/deep/d.md", "bob", "read_write")
    await _grant(storage, "/pub", "bob", "read")
    source = Path("/priv/deep/d.md")
    hidden = Edge(source=source, target=Path("/priv/secret.md"), edge_type="cites")
    absent = Edge(source=source, target=Path("/priv/nope.md"), edge_type="cites")
    good = Edge(source=source, target=Path("/pub/readme.md"), edge_type="cites")
    assert (await storage.mkedge(edges=[hidden, good], authority=SYSTEM)).success is True

    def record(result: Result) -> list[dict[str, Any]]:
        assert result.success is True and result.observations == []
        dumped = [error.model_dump() for error in result.errors]
        for entry in dumped:
            entry["data"] = {key: value for key, value in (entry["data"] or {}).items() if key != "vfs.target"}
        return dumped

    for_hidden = await storage.rmedge(edges=[hidden], authority=BOB)
    for_absent = await storage.rmedge(edges=[absent], authority=BOB)
    assert record(for_hidden) == record(for_absent)
    assert for_hidden.errors[0].severity is Severity.warning and for_hidden.errors[0].kind is ErrorKind.not_found
    assert str(for_hidden.errors[0].path) == str(source)
    assert (for_hidden.errors[0].data or {})["vfs.target"] == "/priv/secret.md"
    # The hidden edge still stands; a mixed batch commits the good edge either way.
    assert (await storage.rmedge(edges=[hidden], authority=SYSTEM)).observations[0].status == "deleted"
    assert (await storage.mkedge(edges=[hidden], authority=SYSTEM)).success is True
    mixed_hidden = await storage.rmedge(edges=[good, hidden], authority=BOB)
    assert (await storage.mkedge(edges=[good], authority=SYSTEM)).success is True
    mixed_absent = await storage.rmedge(edges=[good, absent], authority=BOB)
    for mixed in (mixed_hidden, mixed_absent):
        assert mixed.success is True and [row.status for row in mixed.observations] == ["deleted"]
        assert len(mixed.errors) == 1 and mixed.errors[0].severity is Severity.warning


# ---------------------------------------------------------------------------
# The anonymous gate — judged at the addressed path
# ---------------------------------------------------------------------------


async def _scratch(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/scratch/old.md": "lantern old", "/notes.txt": "lantern notes"})
    assert (await storage.posture(path=Path("/scratch"), posture="read_write", authority=SYSTEM)).success is True


async def test_anonymous_writes_and_reads_under_the_open_folder_and_nowhere_else(storage: InMemoryStorage) -> None:
    await _scratch(storage)
    assert (await _write(storage, "/scratch/hello.txt", ANON, "hi")).success is True
    assert (await storage.read(path=Path("/scratch/hello.txt"), authority=ANON)).success is True
    assert (await storage.mkdir(path=Path("/scratch/sub"), authority=ANON)).success is True
    refused = await _write(storage, "/notes.txt", ANON)
    assert _kind(refused) == ErrorKind.unauthenticated and str(refused.errors[0].path) == "/notes.txt"
    assert _kind(await storage.read(path=Path("/notes.txt"), authority=ANON)) == ErrorKind.unauthenticated
    assert _kind(await storage.mkdir(path=Path("/elsewhere"), authority=ANON)) == ErrorKind.unauthenticated


async def test_anonymous_listings_are_judged_at_the_path_named_and_derive_no_road(storage: InMemoryStorage) -> None:
    await _scratch(storage)
    assert _paths(await storage.ls(path=Path("/scratch"), authority=ANON)) == ["/scratch/old.md"]
    assert _kind(await storage.ls(path=Path("/"), authority=ANON)) == ErrorKind.unauthenticated
    assert _kind(await storage.tree(path=Path("/"), authority=ANON)) == ErrorKind.unauthenticated
    assert _paths(await storage.tree(path=Path("/scratch"), authority=ANON)) == ["/scratch/old.md"]
    assert _paths(await storage.glob(patterns=("/scratch/**",), authority=ANON)) == ["/scratch/old.md"]
    assert _kind(await storage.glob(patterns=("/**",), authority=ANON)) == ErrorKind.unauthenticated
    scoped = await storage.grep(pattern="lantern", globs=("/scratch/**",), allow_scan=True, authority=ANON)
    assert _paths(scoped) == ["/scratch/old.md"]
    assert _kind(await storage.grep(pattern="lantern", allow_scan=True, authority=ANON)) == ErrorKind.unauthenticated
    assert _kind(await storage.glean(query="lantern", authority=ANON)) == ErrorKind.unauthenticated
    # A named nobody lists the root and finds /scratch there; anonymous is refused at /.
    assert _paths(await storage.ls(path=Path("/"), authority=Authority.of(Principal("zed")))) == ["/scratch"]


async def test_anonymous_two_path_verbs_and_batches_are_judged_per_target(storage: InMemoryStorage) -> None:
    await _scratch(storage)
    out = [ResolvedPair(Path("/scratch/old.md"), Path("/moved.md"))]
    into = [ResolvedPair(Path("/notes.txt"), Path("/scratch/notes.txt"))]
    assert _kind(await storage.move(operations=out, authority=ANON)) == ErrorKind.unauthenticated
    assert _kind(await storage.copy(operations=out, authority=ANON)) == ErrorKind.unauthenticated
    assert _kind(await storage.copy(operations=into, authority=ANON)) == ErrorKind.unauthenticated
    within = [ResolvedPair(Path("/scratch/old.md"), Path("/scratch/copy.md"))]
    assert (await storage.copy(operations=within, authority=ANON)).success is True
    batch = [Entry(path=Path("/scratch/a.md"), content="a"), Entry(path=Path("/b.md"), content="b")]
    refused = await storage.write(entries=batch, authority=ANON)
    assert _kind(refused) == ErrorKind.unauthenticated and [str(e.path) for e in refused.errors] == ["/b.md"]
    assert _kind(await storage.stat(path=Path("/scratch/a.md"), authority=SYSTEM)) == ErrorKind.not_found


async def test_rmedge_passes_a_road_directory_as_a_target(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/mine/note.md": "x", "/deep/dir/file.md": "x"})
    await _grant(storage, "/mine", "bob", "read_write")
    await _grant(storage, "/deep/dir/file.md", "bob", "read")
    edge = Edge(source=Path("/mine/note.md"), target=Path("/deep/dir"), edge_type="in")
    assert (await storage.mkedge(edges=[edge], authority=SYSTEM)).success is True
    removed = await storage.rmedge(edges=[edge], authority=BOB)
    assert removed.success is True and [row.status for row in removed.observations] == ["deleted"]


async def test_mkdir_at_a_tombstone_answers_by_what_the_caller_may_read(storage: InMemoryStorage) -> None:
    await _seed(storage, {"/team/gone.md": "x", "/pub/gone.md": "x"})
    await _grant(storage, "/team", "bob", "add")
    await _grant(storage, "/pub", "bob", "read_write")
    await _grant(storage, "/pub/gone.md", "bob", "list")
    assert (await storage.delete(path=Path("/team/gone.md"), authority=SYSTEM)).success is True
    assert (await storage.delete(path=Path("/pub/gone.md"), authority=SYSTEM)).success is True
    hinted = await storage.mkdir(path=Path("/team/gone.md"), authority=BOB)
    assert _kind(hinted) == ErrorKind.not_found and "vfs.deleted_at" in (hinted.errors[0].data or {})
    # A tombstone held only at list: the row stays judged, the hint never rides.
    assert (await storage.posture(path=Path("/pub"), posture="list", authority=SYSTEM)).success is True
    await storage.revoke(path=Path("/pub"), principal="bob", authority=SYSTEM)
    plain = await storage.mkdir(path=Path("/pub/gone.md"), authority=BOB)
    assert _kind(plain) == ErrorKind.not_found and not plain.errors[0].data


GATED_CALLS = {
    "write": lambda s, who: _write(s, "/d/n.md", who),
    "edit": lambda s, who: _edit(s, "/d/f.md", who),
    "delete": lambda s, who: s.delete(path=Path("/d/f.md"), authority=who),
    "restore": lambda s, who: s.restore(path=Path("/d/f.md"), authority=who),
    "sweep": lambda s, who: s.sweep(path=Path("/d"), authority=who),
    "mkdir": lambda s, who: s.mkdir(path=Path("/d/sub"), authority=who),
    "move": lambda s, who: s.move(operations=[ResolvedPair(Path("/d/f.md"), Path("/d/g.md"))], authority=who),
    "copy": lambda s, who: s.copy(operations=[ResolvedPair(Path("/d/f.md"), Path("/d/g.md"))], authority=who),
    "mkedge": lambda s, who: s.mkedge(
        edges=[Edge(source=Path("/d/f.md"), target=Path("/d/f.md"), edge_type="r")], authority=who
    ),
    "rmedge": lambda s, who: s.rmedge(
        edges=[Edge(source=Path("/d/f.md"), target=Path("/d/f.md"), edge_type="r")], authority=who
    ),
    "grants": lambda s, who: s.grants(path=Path("/d"), authority=who),
    "grant": lambda s, who: s.grant(path=Path("/d"), principal="bob", level="read", authority=who),
    "stat": lambda s, who: s.stat(path=Path("/d/f.md"), authority=who),
}


@pytest.mark.parametrize("verb", sorted(GATED_CALLS))
async def test_every_gated_verb_refuses_a_closure_past_the_nesting_bound(storage: InMemoryStorage, verb: str) -> None:
    # The one resolution refusal left: a membership chain deeper than the walk's bound.
    await _seed(storage, {"/d/f.md": "x"}, root="read_write")
    host = storage._host
    chain = ["ann", *(f"group:g{n}" for n in range(12))]
    async with host.session_factory() as session, session.begin():
        await session.execute(
            host.tables.memberships.insert(),
            [
                {"principal_id": inner, "group_id": outer, "granted_by": "system", "granted_at": datetime.now(UTC)}
                for inner, outer in pairwise(chain)
            ],
        )
    assert _kind(await GATED_CALLS[verb](storage, ANN)) == ErrorKind.authority_budget


def test_the_view_answers_the_rung_the_caller_holds() -> None:
    closures = {"ann": frozenset()}
    rows = [GrantRow("ann", "/eng", "contribute"), GrantRow("ann", "/pub", "read")]
    resolution = Resolution.compile(closures, rows, owner_floor=True, pending=())
    tables = build_vfs_tables()
    view = Visibility(resolution, "list", tables, SQLITE, 900, 2_099)
    row = {"path": "/eng/x.md", "owner_id": None, "everyone_level": 0}
    assert view.admits(row) == "contribute" and view.shows(row) and view.reads(row)
    assert view.admits({**row, "path": "/pub/x.md"}) == "read"
    assert view.admits({**row, "path": "/hr/x.md"}) == "none"
    assert view.admits({**row, "path": "/hr/x.md", "everyone_level": 1}) == "list"
    assert view.admits({**row, "path": "/hr/x.md", "owner_id": "ann"}) == "read_write"


# ---------------------------------------------------------------------------
# Aliasing — the compiles between rungs share pieces, never the object
# ---------------------------------------------------------------------------


def test_an_aliased_rung_admits_by_its_own_level_on_shared_pieces() -> None:
    closures = {"ann": frozenset()}
    rows = [GrantRow("ann", "/eng", "read"), GrantRow("ann", "/pub", "read_write")]
    resolution = Resolution.compile(closures, rows, owner_floor=True, pending=())
    listing, reading = resolution.at("list"), resolution.at("read")
    row = ("/other.md", None, 1)
    assert listing.admits(*row) and not reading.admits(*row)
    assert listing.spans is reading.spans and listing.ranges() is reading.ranges()
    assert listing.owner_arms is reading.owner_arms and listing.holes is reading.holes
    assert resolution.at("add").ranges() is resolution.at("contribute").ranges() is resolution.at("read_write").ranges()
    assert resolution.at("read").ranges() is not resolution.at("add").ranges()


def test_a_pending_posture_at_a_rung_compiles_that_rung_on_its_own() -> None:
    closures = {"ann": frozenset()}
    rows = [GrantRow("ann", "/eng", "read"), GrantRow("*", "/", "none"), GrantRow("*", "/zz", "list")]
    resolution = Resolution.compile(closures, rows, owner_floor=True, pending=("/zz",))
    listing, reading = resolution.at("list"), resolution.at("read")
    assert listing.spans is not reading.spans and listing.holes == () and reading.holes != ()
    assert listing.admits("/zz/x.md", None, 0) and not reading.admits("/zz/x.md", None, 2)
    assert listing == resolve(closures, rows, "list", pending=("/zz",))
    assert reading == resolve(closures, rows, "read", pending=("/zz",))


def test_weight_counts_shared_pieces_once() -> None:
    rows = [GrantRow("a", f"/a/{n:04d}", "read_write") for n in range(50)]
    aliased = Resolution.compile({"a": frozenset()}, rows, owner_floor=True, pending=())
    one = aliased.at("read_write")
    alone = Resolution(dict.fromkeys(GRANTABLE_LEVELS, one))
    assert weight(aliased) < 2 * weight(alone)
    assert weight(aliased) == weight(aliased)
