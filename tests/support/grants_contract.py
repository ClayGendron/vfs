"""Row-level grants conformance — what each authority sees and may write.

``GrantsContract`` mixes into every ``StorageContract`` leg, so the same
triples — *(authority shape, row state, verb) → answer* — run on the
in-memory, SQLite-file and server engines alike. Every test builds the
same small world through the public verbs, as the system actor:

    /eng/spec.md            group:eng holds read_write on /eng; ann is a member
    /eng/secret/plan.md
    /pub/readme.md          bob and ann hold read on /pub
    /pub/deep/x.md          carol holds read_write on /pub/deep only
    /hr/case.md             owned by ann (the owner floor)
    /hr/other.md

with the root posture ``private``: a caller holds only what its own,
its groups' and its ownership give it. The pair authority acts for ann
and bob at once, so it holds only what both hold.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, Protocol

import pytest

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry
from vfs.paths import Path
from vfs.results import Result, Severity, VFSErrorKind
from vfs.storage import (
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGlean,
    SupportsGrants,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsReindex,
)
from vfs.storage.grants import MAX_GROUP_DEPTH
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

needs = pytest.mark.needs

SYSTEM = Authority.system()
ANON = Authority.anonymous()
ANN = Authority.of(Principal("ann"))
BOB = Authority.of(Principal("bob"))
CAROL = Authority.of(Principal("carol"))
DAVE = Authority.of(Principal("dave"))
PAIR = Authority.on_behalf_of({Principal("ann"), Principal("bob")}, actor=Principal("bot", kind="service"))

FILES = {
    "/eng/spec.md": "the spec names the lantern",
    "/eng/secret/plan.md": "the plan names the lantern",
    "/pub/readme.md": "the readme names the lantern",
    "/pub/deep/x.md": "deep text",
    "/hr/other.md": "other text",
}


# The planted-ladder probe word and the known counts of its ladder words.
PROBE = "e48213"
LADDER = (1, 2, 3, 4)


# One call per gated verb, made as anonymous on the private world.
ANONYMOUS_CALLS: dict[str, Callable[[GrantsBackend], Awaitable[Result]]] = {
    "read": lambda s: s.read(path=Path("/pub/readme.md"), authority=ANON),
    "ls": lambda s: s.ls(path=Path("/"), authority=ANON),
    "glob": lambda s: s.glob(patterns=("/**",), authority=ANON),
    "grep": lambda s: s.grep(pattern="x", allow_scan=True, authority=ANON),
    "glean": lambda s: s.glean(query="x", authority=ANON),
    "write": lambda s: s.write(entries=[Entry(path=Path("/n.md"), content="x")], authority=ANON),
    "edit": lambda s: s.edit(path=Path("/pub/readme.md"), edits=[EditOperation("a", "b")], authority=ANON),
    "delete": lambda s: s.delete(path=Path("/pub/readme.md"), authority=ANON),
    "restore": lambda s: s.restore(path=Path("/pub/readme.md"), authority=ANON),
    "sweep": lambda s: s.sweep(path=Path("/pub"), authority=ANON),
    "mkdir": lambda s: s.mkdir(path=Path("/d"), authority=ANON),
    "move": lambda s: s.move(operations=[ResolvedPair(Path("/pub/readme.md"), Path("/r.md"))], authority=ANON),
    "copy": lambda s: s.copy(operations=[ResolvedPair(Path("/pub/readme.md"), Path("/r.md"))], authority=ANON),
    "mkedge": lambda s: s.mkedge(edges=[Edge(source=Path("/a"), target=Path("/b"), edge_type="r")], authority=ANON),
    "rmedge": lambda s: s.rmedge(edges=[Edge(source=Path("/a"), target=Path("/b"), edge_type="r")], authority=ANON),
    "grants": lambda s: s.grants(path=Path("/pub"), authority=ANON),
    "grant": lambda s: s.grant(path=Path("/pub"), principal="bob", level="read", authority=ANON),
}


class GrantsBackend(
    StorageBackend, SupportsPatternSearch, SupportsGlean, SupportsMutation, SupportsGrants, SupportsClose, Protocol
):
    """The verb surface the grants suite calls."""


async def _world(storage: GrantsBackend) -> None:
    """Seed the module docstring's world; every step must succeed."""
    entries = [Entry(path=Path(path), content=content) for path, content in FILES.items()]
    steps = [
        await storage.write(entries=entries, parents=True, authority=SYSTEM),
        await storage.write(entries=[Entry(path=Path("/hr/case.md"), content="case")], authority=ANN),
        await storage.posture(path=Path("/"), posture="private", authority=SYSTEM),
        await storage.add_member(group="group:eng", member="ann", authority=SYSTEM),
        await storage.grant(path=Path("/eng"), principal="group:eng", level="read_write", authority=SYSTEM),
        await storage.grant(path=Path("/pub"), principal="bob", level="read", authority=SYSTEM),
        await storage.grant(path=Path("/pub"), principal="ann", level="read", authority=SYSTEM),
        await storage.grant(path=Path("/pub/deep"), principal="carol", level="read_write", authority=SYSTEM),
    ]
    for step in steps:
        assert step.success is True, step.errors


def _paths(result: Result) -> set[str]:
    return {str(o.path) for o in result.observations}


def _kind(result: Result) -> VFSErrorKind | str | None:
    assert result.success is False, result
    return result.errors[0].kind


class GrantsContract:
    """Row-level grants behaviour every grant-capable backend shares."""

    # ------------------------------------------------------------------
    # Reads — a hidden row is a missing row
    # ------------------------------------------------------------------

    @needs("grant", "read")
    async def test_a_group_grant_shows_its_subtree(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.read(path=Path("/eng/spec.md"), authority=ANN)
        assert result.success is True
        assert result.one().content == FILES["/eng/spec.md"]

    @needs("grant", "read")
    async def test_a_hidden_row_reads_exactly_as_a_missing_one(self, storage: GrantsBackend) -> None:
        await _world(storage)
        hidden = await storage.read(path=Path("/eng/spec.md"), authority=BOB)
        missing = await storage.read(path=Path("/eng/nope.md"), authority=BOB)
        nowhere = await storage.read(path=Path("/nope/spec.md"), authority=BOB)
        assert _kind(hidden) == _kind(missing) == _kind(nowhere) == VFSErrorKind.not_found
        assert hidden.errors[0].message.replace("spec.md", "X") == missing.errors[0].message.replace("nope.md", "X")

    @needs("grant", "stat")
    async def test_the_system_actor_sees_every_row(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.stat(path=Path("/hr/other.md"), authority=SYSTEM)
        assert result.success is True

    @needs("grant", "ls")
    async def test_ls_lists_only_what_the_caller_may_see(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert _paths(await storage.ls(path=Path("/"), authority=BOB)) == {"/pub"}
        assert _paths(await storage.ls(path=Path("/"), authority=ANN)) == {"/eng", "/pub", "/hr"}
        assert _paths(await storage.ls(path=Path("/hr"), authority=ANN)) == {"/hr/case.md"}

    @needs("grant", "stat")
    async def test_a_road_directory_shows_as_a_bare_name(self, storage: GrantsBackend) -> None:
        # carol sees /pub/deep, so /pub is on her road: path and kind only.
        await _world(storage)
        result = await storage.stat(path=Path("/pub"), authority=CAROL)
        assert result.success is True
        row = result.one()
        assert row.kind == "directory"
        assert row.populated == frozenset({"path", "kind"})
        assert row.version is None and row.size_bytes is None
        assert _kind(await storage.read(path=Path("/pub"), authority=CAROL)) == VFSErrorKind.wrong_kind

    @needs("grant", "ls")
    async def test_a_road_directory_lists_only_its_visible_children(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert _paths(await storage.ls(path=Path("/pub"), authority=CAROL)) == {"/pub/deep"}

    @needs("grant", "stat")
    async def test_a_directory_with_nothing_visible_beneath_is_hidden(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert _kind(await storage.stat(path=Path("/eng"), authority=BOB)) == VFSErrorKind.not_found
        assert _kind(await storage.stat(path=Path("/eng/secret"), authority=CAROL)) == VFSErrorKind.not_found

    @needs("grant", "tree")
    async def test_tree_walks_only_the_visible_and_the_road(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.tree(path=Path("/"), authority=CAROL)
        assert result.success is True
        assert _paths(result) <= {"/", "/pub", "/pub/deep", "/pub/deep/x.md"}
        assert "/pub/deep/x.md" in _paths(result)

    @needs("grant", "tree")
    async def test_tree_never_admits_a_sibling_that_sorts_inside_a_grant(self, storage: GrantsBackend) -> None:
        # "/pub-x" sorts between "/pub" and "/pub/", "/pub0" just past them:
        # a grant on /pub read as one byte range would leak either.
        await _world(storage)
        traps = ["/pub-x/a.md", "/pub0.md", "/pub/deep-x/b.md", "/pub/deep0.md"]
        written = await storage.write(entries=[Entry(path=Path(p), content="t") for p in traps], parents=True)
        assert written.success is True
        bob = _paths(await storage.tree(path=Path("/"), authority=BOB))
        assert {"/pub/deep-x/b.md", "/pub/deep0.md"} <= bob
        assert not bob & {"/pub-x", "/pub-x/a.md", "/pub0.md"}
        carol = _paths(await storage.tree(path=Path("/"), authority=CAROL))
        assert "/pub/deep/x.md" in carol
        assert not carol & {"/pub/deep-x", "/pub/deep-x/b.md", "/pub/deep0.md", "/pub/readme.md"}

    @needs("grant", "tree")
    async def test_tree_cuts_a_posture_hole_and_keeps_its_siblings(self, storage: GrantsBackend) -> None:
        await _world(storage)
        traps = [Entry(path=Path(p), content="t") for p in ("/eng-x/a.md", "/eng0.md")]
        assert (await storage.write(entries=traps, parents=True)).success is True
        assert (await storage.posture(path=Path("/"), posture="shared", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/eng"), posture="private", authority=SYSTEM)).success is True
        dave = _paths(await storage.tree(path=Path("/"), authority=DAVE))
        assert {"/eng-x/a.md", "/eng0.md", "/pub/readme.md", "/hr/other.md"} <= dave
        assert not dave & {"/eng", "/eng/spec.md", "/eng/secret/plan.md"}

    @needs("grant", "tree")
    async def test_tree_shows_an_owned_row_only_where_every_member_sees(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert "/hr/case.md" in _paths(await storage.tree(path=Path("/"), authority=ANN))
        pair = _paths(await storage.tree(path=Path("/"), authority=PAIR))
        assert "/pub/readme.md" in pair
        assert not pair & {"/hr/case.md", "/eng/spec.md"}

    @needs("grant", "glob")
    async def test_glob_never_names_a_hidden_row(self, storage: GrantsBackend) -> None:
        await _world(storage)
        paths = _paths(await storage.glob(patterns=("/**/*.md",), authority=BOB))
        assert paths == {"/pub/readme.md", "/pub/deep/x.md"}

    @needs("grant", "grep")
    async def test_grep_never_matches_inside_a_hidden_row(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.grep(pattern="lantern", allow_scan=True, output_mode="files", authority=BOB)
        assert result.success is True
        assert _paths(result) == {"/pub/readme.md"}

    # ------------------------------------------------------------------
    # The owner floor and the subject set
    # ------------------------------------------------------------------

    @needs("grant", "read")
    async def test_an_owner_reads_its_own_row_under_a_private_posture(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.read(path=Path("/hr/case.md"), authority=ANN)).success is True
        assert _kind(await storage.read(path=Path("/hr/case.md"), authority=BOB)) == VFSErrorKind.not_found

    @needs("grant", "read")
    async def test_a_subject_set_holds_only_what_every_member_holds(self, storage: GrantsBackend) -> None:
        # ann reaches /eng through her group and /hr/case.md as its owner;
        # bob reaches neither, so the pair reaches neither. Both read /pub.
        await _world(storage)
        assert (await storage.read(path=Path("/pub/readme.md"), authority=PAIR)).success is True
        assert _kind(await storage.read(path=Path("/eng/spec.md"), authority=PAIR)) == VFSErrorKind.not_found
        assert _kind(await storage.read(path=Path("/hr/case.md"), authority=PAIR)) == VFSErrorKind.not_found

    # ------------------------------------------------------------------
    # Posture — what everyone holds
    # ------------------------------------------------------------------

    @needs("grant", "read")
    async def test_anonymous_is_unauthenticated_on_a_private_mount(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.read(path=Path("/pub/readme.md"), authority=ANON)
        assert _kind(result) == VFSErrorKind.unauthenticated

    @needs("grant", "write", "mkedge", "glean", "sweep", "move", "copy", "restore")
    @pytest.mark.parametrize("verb", sorted(ANONYMOUS_CALLS))
    async def test_anonymous_is_unauthenticated_on_every_verb_of_a_private_mount(
        self, storage: GrantsBackend, verb: str
    ) -> None:
        await _world(storage)
        result = await ANONYMOUS_CALLS[verb](storage)
        assert _kind(result) == VFSErrorKind.unauthenticated, verb

    @needs("grant", "read", "write")
    async def test_a_shared_posture_lets_anyone_read_and_nobody_unnamed_write(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.posture(path=Path("/"), posture="shared", authority=SYSTEM)).success is True
        assert (await storage.read(path=Path("/hr/other.md"), authority=ANON)).success is True
        assert (await storage.read(path=Path("/hr/other.md"), authority=DAVE)).success is True
        write = await storage.write(entries=[Entry(path=Path("/hr/new.md"), content="x")], authority=ANON)
        assert _kind(write) == VFSErrorKind.unauthenticated
        named = await storage.write(entries=[Entry(path=Path("/hr/new.md"), content="x")], authority=DAVE)
        assert _kind(named) == VFSErrorKind.permission_denied

    @needs("grant", "read")
    async def test_a_deeper_posture_decides_beneath_it(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.posture(path=Path("/"), posture="open", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/hr"), posture="private", authority=SYSTEM)).success is True
        assert (await storage.read(path=Path("/eng/spec.md"), authority=DAVE)).success is True
        assert _kind(await storage.read(path=Path("/hr/other.md"), authority=DAVE)) == VFSErrorKind.not_found

    # ------------------------------------------------------------------
    # The write gate
    # ------------------------------------------------------------------

    @needs("grant", "write", "read")
    async def test_a_granted_writer_creates_and_owns(self, storage: GrantsBackend) -> None:
        await _world(storage)
        # Out of the group, ann still reads what she made, and nothing else there.
        result = await storage.write(entries=[Entry(path=Path("/eng/new.md"), content="x")], authority=ANN)
        assert result.success is True
        assert (await storage.remove_member(group="group:eng", member="ann", authority=SYSTEM)).success is True
        assert (await storage.read(path=Path("/eng/new.md"), authority=ANN)).success is True
        assert _kind(await storage.read(path=Path("/eng/spec.md"), authority=ANN)) == VFSErrorKind.not_found

    @needs("grant", "edit")
    async def test_a_visible_read_only_row_refuses_an_edit(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.edit(
            path=Path("/pub/readme.md"), edits=[EditOperation("readme", "README")], authority=BOB
        )
        assert _kind(result) == VFSErrorKind.permission_denied

    @needs("grant", "edit")
    async def test_a_hidden_row_refuses_an_edit_as_missing(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.edit(path=Path("/eng/spec.md"), edits=[EditOperation("spec", "SPEC")], authority=BOB)
        assert _kind(result) == VFSErrorKind.not_found

    @needs("grant", "write")
    async def test_a_write_under_a_road_directory_is_denied_before_lookup(self, storage: GrantsBackend) -> None:
        # carol sees /pub only as a road, so a new name there is denied
        # whether or not a row already holds it.
        await _world(storage)
        fresh = await storage.write(entries=[Entry(path=Path("/pub/new.md"), content="x")], authority=CAROL)
        taken = await storage.write(entries=[Entry(path=Path("/pub/readme.md"), content="x")], authority=CAROL)
        assert _kind(fresh) == _kind(taken) == VFSErrorKind.permission_denied

    @needs("grant", "write", "mkdir")
    async def test_no_verb_acts_on_a_road_directory_itself(self, storage: GrantsBackend) -> None:
        # Even a no-op mkdir would answer with the directory's version.
        await _world(storage)
        mkdir = await storage.mkdir(path=Path("/pub"), exist_ok=True, authority=CAROL)
        write = await storage.write(entries=[Entry(path=Path("/pub"), content="x")], authority=CAROL)
        assert _kind(mkdir) == _kind(write) == VFSErrorKind.permission_denied

    @needs("grant", "delete", "mkdir", "edit")
    async def test_a_partial_caller_is_refused_per_verb(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert _kind(await storage.delete(path=Path("/eng/spec.md"), authority=BOB)) == VFSErrorKind.not_found
        assert _kind(await storage.mkdir(path=Path("/eng/x"), authority=BOB)) == VFSErrorKind.not_found
        missing = await storage.edit(path=Path("/eng/nope.md"), edits=[EditOperation("a", "b")], authority=ANN)
        assert _kind(missing) == VFSErrorKind.not_found

    @needs("grant", "mkedge", "rmedge")
    async def test_an_edge_needs_write_at_its_source_and_read_at_its_target(self, storage: GrantsBackend) -> None:
        await _world(storage)
        visible = Edge(source=Path("/eng/spec.md"), target=Path("/pub/readme.md"), edge_type="ref")
        hidden = Edge(source=Path("/eng/spec.md"), target=Path("/hr/other.md"), edge_type="ref")
        read_only = Edge(source=Path("/pub/readme.md"), target=Path("/eng/spec.md"), edge_type="ref")
        assert (await storage.mkedge(edges=[visible], authority=ANN)).success is True
        assert _kind(await storage.mkedge(edges=[hidden], authority=ANN)) == VFSErrorKind.not_found
        assert _kind(await storage.mkedge(edges=[read_only], authority=BOB)) == VFSErrorKind.permission_denied
        assert _kind(await storage.rmedge(edges=[read_only], authority=BOB)) == VFSErrorKind.permission_denied
        assert (await storage.rmedge(edges=[visible], authority=ANN)).success is True

    @needs("grant", "write")
    async def test_a_write_under_a_hidden_directory_is_not_found(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.write(entries=[Entry(path=Path("/eng/new.md"), content="x")], authority=BOB)
        assert _kind(result) == VFSErrorKind.not_found

    @needs("grant", "write", "stat")
    async def test_parents_never_mint_through_a_hidden_ancestor(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.write(
            entries=[Entry(path=Path("/eng/secret/deeper/n.md"), content="x")], parents=True, authority=CAROL
        )
        assert result.success is False
        assert _kind(await storage.stat(path=Path("/eng/secret/deeper"), authority=SYSTEM)) == VFSErrorKind.not_found

    @needs("grant", "write", "stat")
    async def test_a_mixed_batch_fails_whole_and_writes_nothing(self, storage: GrantsBackend) -> None:
        await _world(storage)
        entries = [Entry(path=Path(f"/eng/batch/{n}.md"), content="x") for n in range(50)]
        entries.append(Entry(path=Path("/pub/intruder.md"), content="x"))
        result = await storage.write(entries=entries, parents=True, authority=ANN)
        assert result.success is False
        assert _kind(await storage.stat(path=Path("/eng/batch/0.md"), authority=SYSTEM)) == VFSErrorKind.not_found

    @needs("grant", "delete", "stat")
    async def test_a_subtree_mutation_checks_every_row_beneath(self, storage: GrantsBackend) -> None:
        # Everyone may write /open, except the private /open/closed beneath
        # it: deleting /open would destroy a row dave cannot write.
        await _world(storage)
        planted = await storage.write(
            entries=[Entry(path=Path("/open/closed/k.md"), content="x")], parents=True, authority=SYSTEM
        )
        assert planted.success is True
        assert (await storage.posture(path=Path("/open"), posture="open", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/open/closed"), posture="private", authority=SYSTEM)).success
        result = await storage.delete(path=Path("/open"), authority=DAVE)
        assert result.success is False
        assert (await storage.sweep(path=Path("/open"), authority=DAVE)).success is False
        assert (await storage.stat(path=Path("/open/closed/k.md"), authority=SYSTEM)).success is True

    @needs("grant", "delete", "stat")
    async def test_a_hole_with_no_rows_beneath_blocks_nothing(self, storage: GrantsBackend) -> None:
        # The subtree check reads rows, not prefixes: a private posture on
        # an empty path inside /open hides nothing, so the delete proceeds.
        await _world(storage)
        planted = await storage.write(
            entries=[Entry(path=Path("/open/k.md"), content="x")], parents=True, authority=SYSTEM
        )
        assert planted.success is True
        assert (await storage.posture(path=Path("/open"), posture="open", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/open/empty"), posture="private", authority=SYSTEM)).success
        assert (await storage.delete(path=Path("/open"), authority=DAVE)).success is True
        assert _kind(await storage.stat(path=Path("/open/k.md"), authority=SYSTEM)) == VFSErrorKind.not_found

    @needs("grant", "delete", "stat")
    async def test_a_subtree_check_reads_past_its_first_page(self, storage: GrantsBackend) -> None:
        # The unwritable row sorts after a full page of writable ones.
        await _world(storage)
        bulk = [Entry(path=Path(f"/open/a/{n:04}.md"), content="x") for n in range(1_001)]
        bulk.append(Entry(path=Path("/open/z/k.md"), content="x"))
        assert (await storage.write(entries=bulk, parents=True, authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/open"), posture="open", authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/open/z"), posture="private", authority=SYSTEM)).success is True
        assert _kind(await storage.delete(path=Path("/open"), authority=DAVE)) == VFSErrorKind.permission_denied
        assert (await storage.stat(path=Path("/open/a/0000.md"), authority=SYSTEM)).success is True

    @needs("grant", "move", "stat")
    async def test_a_move_needs_write_at_both_ends(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.move(
            operations=[ResolvedPair(Path("/eng/spec.md"), Path("/pub/spec.md"))], authority=ANN
        )
        assert result.success is False
        assert (await storage.stat(path=Path("/eng/spec.md"), authority=SYSTEM)).success is True

    @needs("grant", "delete", "restore", "read")
    async def test_an_owner_restores_its_own_trashed_row(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.delete(path=Path("/hr/case.md"), authority=ANN)).success is True
        assert (await storage.restore(path=Path("/hr/case.md"), authority=ANN)).success is True
        assert (await storage.read(path=Path("/hr/case.md"), authority=ANN)).success is True

    @needs("grant", "delete", "restore")
    async def test_a_trashed_row_the_caller_cannot_see_does_not_restore(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.delete(path=Path("/hr/other.md"), authority=SYSTEM)).success is True
        result = await storage.restore(path=Path("/hr/other.md"), authority=ANN)
        assert _kind(result) == VFSErrorKind.not_found

    @needs("grant", "delete", "restore")
    async def test_a_visible_trashed_row_the_caller_cannot_write_does_not_restore(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.posture(path=Path("/"), posture="shared", authority=SYSTEM)).success is True
        assert (await storage.delete(path=Path("/hr/other.md"), authority=SYSTEM)).success is True
        result = await storage.restore(path=Path("/hr/other.md"), authority=DAVE)
        assert _kind(result) == VFSErrorKind.permission_denied

    @needs("grant", "sweep", "stat")
    async def test_sweep_needs_write_on_the_swept_prefix(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.sweep(path=Path("/pub"), authority=BOB)).success is False
        assert (await storage.stat(path=Path("/pub/readme.md"), authority=SYSTEM)).success is True

    # ------------------------------------------------------------------
    # The grant verbs
    # ------------------------------------------------------------------

    @needs("grant", "read")
    async def test_a_widened_grant_is_seen_on_the_next_call(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert _kind(await storage.read(path=Path("/eng/spec.md"), authority=BOB)) == VFSErrorKind.not_found
        granted = await storage.grant(path=Path("/eng/spec.md"), principal="bob", level="read", authority=ANN)
        assert granted.success is True
        assert (await storage.read(path=Path("/eng/spec.md"), authority=BOB)).success is True
        revoked = await storage.revoke(path=Path("/eng/spec.md"), principal="bob", authority=ANN)
        assert revoked.success is True
        assert _kind(await storage.read(path=Path("/eng/spec.md"), authority=BOB)) == VFSErrorKind.not_found

    @needs("grant")
    async def test_nobody_grants_more_than_it_holds(self, storage: GrantsBackend) -> None:
        await _world(storage)
        seen = await storage.grant(path=Path("/pub"), principal="dave", level="read", authority=BOB)
        hidden = await storage.grant(path=Path("/eng"), principal="dave", level="read", authority=BOB)
        assert _kind(seen) == VFSErrorKind.permission_denied
        assert _kind(hidden) == VFSErrorKind.not_found

    @needs("grant")
    async def test_a_reserved_principal_cannot_be_granted(self, storage: GrantsBackend) -> None:
        await _world(storage)
        for principal in ("*", "system", "anon", " ", "x" * 256):
            result = await storage.grant(path=Path("/eng"), principal=principal, level="read", authority=SYSTEM)
            assert _kind(result) == VFSErrorKind.invalid, principal

    @needs("grant", "grants")
    async def test_grants_lists_the_rows_that_decide_a_path(self, storage: GrantsBackend) -> None:
        await _world(storage)
        full = await storage.grants(path=Path("/eng/spec.md"), authority=ANN)
        assert full.success is True
        rows = {(row["principal_id"], row["path_prefix"], row["level"]) for row in _granted(full)}
        assert rows == {("*", "/", "none"), ("group:eng", "/eng", "read_write")}
        assert {row["granted_by"] for row in _granted(full)} == {"system"}
        partial = await storage.grants(path=Path("/pub"), authority=BOB)
        assert {row["principal_id"] for row in _granted(partial)} == {"*", "bob"}

    @needs("grant", "revoke", "grants", "posture")
    async def test_every_grant_verb_is_gated_like_grant(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert _kind(await storage.revoke(path=Path("/eng"), principal="ann", authority=BOB)) == VFSErrorKind.not_found
        assert _kind(await storage.grants(path=Path("/eng"), authority=BOB)) == VFSErrorKind.not_found
        denied = await storage.posture(path=Path("/pub"), posture="open", authority=BOB)
        assert _kind(denied) == VFSErrorKind.permission_denied
        # ``none`` narrows only a posture row; storage refuses it on a principal's.
        level = await storage.grant(path=Path("/eng"), principal="bob", level="none", authority=SYSTEM)
        assert _kind(level) == VFSErrorKind.invalid

    @needs("grant", "revoke")
    async def test_revoking_a_missing_grant_is_a_warning(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.revoke(path=Path("/eng"), principal="dave", authority=SYSTEM)
        assert result.success is True
        assert [error.severity for error in result.errors] == [Severity.warning]

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    @needs("add_member")
    async def test_only_the_system_actor_changes_membership(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.add_member(group="group:eng", member="bob", authority=ANN)
        assert _kind(result) == VFSErrorKind.permission_denied

    @needs("add_member", "read")
    async def test_nested_groups_reach_their_grants(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.add_member(group="group:all", member="bob", authority=SYSTEM)).success
        assert (await storage.add_member(group="group:eng", member="group:all", authority=SYSTEM)).success
        assert (await storage.read(path=Path("/eng/spec.md"), authority=BOB)).success is True
        assert (await storage.remove_member(group="group:eng", member="group:all", authority=SYSTEM)).success
        assert _kind(await storage.read(path=Path("/eng/spec.md"), authority=BOB)) == VFSErrorKind.not_found

    @needs("add_member")
    async def test_a_membership_cycle_is_refused(self, storage: GrantsBackend) -> None:
        await _world(storage)
        assert (await storage.add_member(group="group:b", member="group:a", authority=SYSTEM)).success
        result = await storage.add_member(group="group:a", member="group:b", authority=SYSTEM)
        assert result.success is False

    @needs("add_member")
    async def test_nesting_past_the_depth_cap_is_refused(self, storage: GrantsBackend) -> None:
        await _world(storage)
        chain = [f"group:g{n}" for n in range(MAX_GROUP_DEPTH + 2)]
        outcomes = [
            await storage.add_member(group=outer, member=inner, authority=SYSTEM) for inner, outer in pairwise(chain)
        ]
        assert outcomes[0].success is True
        assert outcomes[-1].success is False
        assert _kind(outcomes[-1]) == VFSErrorKind.authority_budget

    @needs("remove_member")
    async def test_removing_a_membership(self, storage: GrantsBackend) -> None:
        await _world(storage)
        refused = await storage.remove_member(group="group:eng", member="ann", authority=ANN)
        assert _kind(refused) == VFSErrorKind.permission_denied
        missing = await storage.remove_member(group="group:eng", member="bob", authority=SYSTEM)
        assert missing.success is True
        assert [error.severity for error in missing.errors] == [Severity.warning]

    @needs("add_member")
    async def test_a_reserved_principal_cannot_be_a_member(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.add_member(group="group:eng", member="*", authority=SYSTEM)
        assert _kind(result) == VFSErrorKind.invalid

    @needs("add_member")
    async def test_a_group_id_must_carry_its_prefix(self, storage: GrantsBackend) -> None:
        await _world(storage)
        result = await storage.add_member(group="eng", member="bob", authority=SYSTEM)
        assert _kind(result) == VFSErrorKind.invalid

    # ------------------------------------------------------------------
    # Ranked search — hidden rows never move a visible score
    # ------------------------------------------------------------------

    @needs("grant", "glean")
    async def test_a_hidden_only_term_never_reaches_the_statistics_export(self, storage: GrantsBackend) -> None:
        await _world(storage)
        hidden = Entry(path=Path("/hr/secret.md"), content="quarantine lantern")
        assert (await storage.write(entries=[hidden], authority=SYSTEM)).success is True
        assert (await _reindexer(storage).reindex()).success is True
        result = await storage.glean(query="quarantine lantern", authority=BOB)
        assert result.success is True
        exported = (result.model_extra or {})["lexical_stats"]
        assert "quarantine" not in exported["terms"]
        assert exported["terms"]["lantern"]["df"] == 1
        whole = await storage.glean(query="quarantine lantern", authority=SYSTEM)
        assert "quarantine" in (whole.model_extra or {})["lexical_stats"]["terms"]

    @needs("grant", "glean")
    async def test_a_sibling_that_sorts_inside_a_grant_never_counts_in_the_statistics(
        self, storage: GrantsBackend
    ) -> None:
        # The visible document count is an aggregate no row check follows,
        # so a pushdown admitting "/pub-x" or "/pub0" would leak its size.
        await _world(storage)
        reindexer = _reindexer(storage)
        assert (await reindexer.reindex()).success is True
        before = _n_docs(await storage.glean(query="lantern", authority=BOB))
        outside = [Entry(path=Path(p), content="lantern") for p in ("/pub-x/a.md", "/pub0.md")]
        assert (await storage.write(entries=outside, parents=True, authority=SYSTEM)).success is True
        assert (await reindexer.reindex()).success is True
        assert _n_docs(await storage.glean(query="lantern", authority=BOB)) == before
        inside = Entry(path=Path("/pub/deep0.md"), content="lantern")
        assert (await storage.write(entries=[inside], authority=SYSTEM)).success is True
        assert (await reindexer.reindex()).success is True
        assert _n_docs(await storage.glean(query="lantern", authority=BOB)) == before + 1

    @needs("grant", "glean")
    async def test_a_hidden_partition_never_moves_a_visible_score(self, storage: GrantsBackend) -> None:
        # The planted-ladder attack: bob plants a probe word beside words of
        # known counts; if hidden rows counted in the statistics, hidden
        # mentions of the probe would move its score against the ladder.
        await _world(storage)
        reindexer = _reindexer(storage)
        assert (await storage.write(entries=_ladder(), parents=True, authority=SYSTEM)).success is True
        assert (await reindexer.reindex()).success is True
        query = " ".join((PROBE, *(f"zqx{k}vk" for k in LADDER)))
        bob_before = _scores(await storage.glean(query=query, limit=20, authority=BOB))
        whole_before = _scores(await storage.glean(query=query, limit=20, authority=SYSTEM))
        mentions = [Entry(path=Path(f"/hr/leak/{n}.md"), content=f"about {PROBE}") for n in range(3)]
        assert (await storage.write(entries=mentions, parents=True, authority=SYSTEM)).success is True
        assert (await reindexer.reindex()).success is True
        bob_after = _scores(await storage.glean(query=query, limit=20, authority=BOB))
        whole_after = _scores(await storage.glean(query=query, limit=20, authority=SYSTEM))
        assert bob_after == bob_before
        assert all(not path.startswith("/hr/") for path, _ in bob_after)
        # The control: a whole-mount caller counts the new rows, so its scores move.
        assert dict(whole_after)["/pub/bob/probe.md"] != dict(whole_before)["/pub/bob/probe.md"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _granted(result: Result) -> list[dict[str, object]]:
    """The ``grants=`` rows a grant verb answered with."""
    rows = (result.model_extra or {}).get("grants")
    assert isinstance(rows, list), result
    return rows


def _ladder() -> list[Entry]:
    """bob's plants: one probe file, and each ladder word in exactly *k* files."""
    plants = [Entry(path=Path("/pub/bob/probe.md"), content=f"plain words\n{PROBE}")]
    for k in LADDER:
        plants += [Entry(path=Path(f"/pub/bob/ladder{k}_{n}.md"), content=f"plain words\nzqx{k}vk") for n in range(k)]
    return plants


def _scores(result: Result) -> list[tuple[str, float | None]]:
    assert result.success is True, result.errors
    return [(str(o.path), o.score) for o in result.observations]


def _n_docs(result: Result) -> int:
    """The visible document count a partial caller's glean exported."""
    assert result.success is True, result.errors
    n_docs = (result.model_extra or {})["lexical_stats"]["n_docs"]
    assert isinstance(n_docs, int)
    return n_docs


def _reindexer(storage: GrantsBackend) -> SupportsReindex:
    if not isinstance(storage, SupportsReindex):
        pytest.skip("backend does not expose reindex")
    return storage
