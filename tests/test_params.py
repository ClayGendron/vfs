"""Ingress type gates: the params table's drift guard, the per-verb garbage
matrix (invalid, parameter named, zero dispatch), and the precedence pins."""

from __future__ import annotations

import inspect
from typing import get_args

import pytest

from tests.support.base_doubles import RecorderFS, RecorderStorage
from vfs.base import AsyncVirtualFileSystem
from vfs.ops import ALL_OPS, RUNGS, TRAVERSE_DEPTH_DEFAULT, TRAVERSE_LIMIT_DEFAULT
from vfs.params import GRANTABLE, INT_CEILING, PARAMS, POSTURES, RULES, param_violation
from vfs.results import ErrorKind
from vfs.session import AsyncSession
from vfs.storage.grants import GRANTABLE_LEVELS, Posture
from vfs.sync import Session, VirtualFileSystem
from vfs.vid import ABSENT

# ----------------------------------------------------------------------
# drift — the table and the public surface may never diverge
# ----------------------------------------------------------------------


def test_table_covers_every_op() -> None:
    assert set(PARAMS) == ALL_OPS
    assert set(RULES) <= ALL_OPS


def test_every_verb_signature_matches_the_table() -> None:
    for op, specs in PARAMS.items():
        verb = getattr(AsyncVirtualFileSystem, op)
        sig_names = {name for name in inspect.signature(verb).parameters if name != "self"}
        table_names = {spec.name for spec in specs}
        assert sig_names == table_names, f"{op}: drift on {sig_names ^ table_names}"


def test_the_version_preconditions_are_gone_from_every_face_and_the_table() -> None:
    """A version alone names no file, so no face offers it as a precondition."""
    gone = {"if_version", "if_versions"}
    assert all(gone.isdisjoint(spec.name for spec in specs) for specs in PARAMS.values())
    for face in (AsyncVirtualFileSystem, VirtualFileSystem, AsyncSession, Session):
        for op in PARAMS:
            verb = getattr(face, op, None)
            if verb is not None:
                assert gone.isdisjoint(inspect.signature(verb).parameters), (face.__name__, op)
    assert {spec.name for spec in PARAMS["write"]} >= {"if_vid", "if_vids", "if_absent"}


def test_the_traverse_signature_defaults_equal_the_table_defaults() -> None:
    # The gate never substitutes a ParamSpec default; the verb's own
    # signature carries it, so the two must agree or the wire and the
    # in-process caller see different walks.
    signature = inspect.signature(AsyncVirtualFileSystem.traverse).parameters
    for spec in PARAMS["traverse"]:
        if spec.default is not None and spec.name in signature:
            assert signature[spec.name].default == spec.default, spec.name
    assert signature["depth"].default == 1 and signature["limit"].default == 128
    assert (TRAVERSE_DEPTH_DEFAULT, TRAVERSE_LIMIT_DEFAULT) == (1, 128)


def test_the_grant_choices_derive_from_the_ladder() -> None:
    # A posture takes every rung; a grant every rung but none.
    assert POSTURES == frozenset(get_args(Posture)) == frozenset(RUNGS)
    assert GRANTABLE == frozenset(GRANTABLE_LEVELS) == POSTURES - {"none"}
    assert {"open", "shared", "private"}.isdisjoint(POSTURES)
    assert param_violation("set_posture", {"path": "/", "posture": "private"}) is not None
    assert param_violation("set_posture", {"path": "/", "posture": "list"}) is None
    assert param_violation("grant", {"path": "/", "principal": "bob", "level": "none"}) is not None
    assert param_violation("grant", {"path": "/", "principal": "bob", "level": "contribute"}) is None


def test_every_int_channel_enforces_the_shared_ceiling() -> None:
    # The seam sweep: no int channel is unbounded above, so no value
    # the gate admits can overflow an FFI or SQL integer downstream.
    swept = 0
    for op, specs in PARAMS.items():
        for spec in specs:
            if spec.kind != "int":
                continue
            swept += 1
            assert spec.maximum == INT_CEILING, (op, spec.name)
            at_max = param_violation(op, {spec.name: INT_CEILING})
            assert at_max is None or spec.name not in at_max, (op, spec.name, at_max)
            over = param_violation(op, {spec.name: INT_CEILING + 1})
            assert over is not None and spec.name in over and str(INT_CEILING) in over
    assert swept == 11


def test_violation_messages_name_the_parameter() -> None:
    # The invalid KindContract's hint is "fix the flagged parameter" —
    # every type/domain refusal must say which one.
    assert param_violation("tree", {"max_depth": "2"}) == (
        "tree max_depth must be an integer >= 1 and <= 2147483647, got '2'"
    )
    assert param_violation("grep", {"case_mode": "bogus", "pattern": "x"}) == (
        "grep case_mode must be one of ['insensitive', 'sensitive', 'smart'], got 'bogus'"
    )
    assert param_violation("run", {"path": "/t", "arguments": 5}) == "run arguments must be a dict, got int"
    assert param_violation("write", {"path": "/f", "data": "x"}) == "write data must be bytes, got str"
    assert param_violation("write", {"path": "/f", "data": b"x"}) is None
    vid = "0123456789abcdef0123"
    must = "the 20 characters a result carries"
    assert param_violation("write", {"path": "/f", "content": "x", "if_vid": 7}) == (
        f"write if_vid must be a vid, {must}, got int"
    )
    assert param_violation("write", {"path": "/f", "content": "x", "if_vid": "x" * 40}) == (
        f"write if_vid must be a vid, {must}, got {'x' * 32!r}"
    )
    assert param_violation("write", {"path": "/f", "content": "x", "if_vid": vid.upper()}) == (
        f"write if_vid must be a vid, {must}, got {vid.upper()!r}"
    )
    assert param_violation("write", {"entries": [], "if_vids": {"/f": 0}}) == (
        f"write if_vids values must be vids, {must}, got int"
    )
    assert (
        param_violation("write", {"entries": [], "if_vids": {7: vid}}) == "write if_vids keys must be strings, got int"
    )
    assert param_violation("write", {"entries": [], "if_vids": ["/f"]}) == (
        "write if_vids must be a mapping of paths to vids, got list"
    )
    assert param_violation("write", {"entries": [], "if_vids": {"/f": vid, "/g": ABSENT}}) is None
    assert param_violation("write", {"path": "/f", "content": "x", "if_vid": ABSENT}) is None
    assert param_violation("write", {"entries": [], "if_vid": vid}) == (
        "write takes if_vid with path, and if_vids with entries"
    )
    assert param_violation("write", {"path": "/f", "content": "x", "if_vids": {"/f": vid}}) == (
        "write takes if_vid with path, and if_vids with entries"
    )
    absent = "write if_absent=True takes no if_vid or if_vids: an absent file has no vid"
    assert param_violation("write", {"path": "/f", "content": "x", "if_absent": True, "if_vid": vid}) == absent
    assert param_violation("write", {"entries": [], "if_absent": True, "if_vids": {"/f": vid}}) == absent
    assert param_violation("write", {"path": "/f", "content": "x", "if_absent": False, "if_vid": vid}) is None
    edit_forms = "edit takes if_vid with path, and if_vids with observations"
    assert param_violation("edit", {"path": "/f", "old": "a", "new": "b", "if_vid": vid}) is None
    assert param_violation("edit", {"observations": [], "edits": [], "if_vids": {"/f": ABSENT}}) is None
    assert param_violation("edit", {"observations": [], "edits": [], "if_vid": vid}) == edit_forms
    assert param_violation("edit", {"path": "/f", "old": "a", "new": "b", "if_vids": {"/f": vid}}) == edit_forms
    assert param_violation("edit", {"path": "/f", "old": "a", "new": "b", "if_vid": 3}) == (
        f"edit if_vid must be a vid, {must}, got int"
    )
    assert param_violation("write", {"path": "/f", "content": "x", "append": True, "if_vid": ABSENT}) == (
        "write takes append or if_absent, not both: an append to an absent path already creates it"
    )
    assert param_violation("write", {"entries": [], "append": True}) == (
        "write append=True takes one file: path with content or data"
    )
    assert param_violation("write", {"path": "/f", "content": "x", "append": True, "if_absent": True}) == (
        "write takes append or if_absent, not both: an append to an absent path already creates it"
    )
    # A flag that is left out is a flag that is off, as on a call that arrives without its defaults.
    assert param_violation("write", {"path": "/f", "content": "x", "append": True}) is None
    assert param_violation("write", {"path": "/f", "content": "x", "append": True, "if_vid": "0" * 20}) is None
    assert param_violation("write", {"path": "/f", "content": "x", "if_absent": True}) is None


# ----------------------------------------------------------------------
# the garbage matrix — wrong type, bounds, bogus enum, truthy non-bool
# ----------------------------------------------------------------------

GARBAGE = [
    ("read-columns", lambda fs: fs.read("/f.txt", columns=123)),
    ("read-non-str-column-item", lambda fs: fs.read("/f.txt", columns=frozenset({"path", 7}))),
    ("read-authority", lambda fs: fs.read("/f.txt", authority=123)),
    ("read-both-targets", lambda fs: fs.read("/f.txt", observations=[])),
    ("stat-both-targets", lambda fs: fs.stat("/f.txt", observations=[])),
    ("ls-both-targets", lambda fs: fs.ls("/f.txt", observations=[])),
    ("tree-bool-depth", lambda fs: fs.tree("/", max_depth=True)),
    ("tree-str-depth", lambda fs: fs.tree("/", max_depth="2")),
    ("tree-missing-path", lambda fs: fs.tree(None)),
    ("write-content-only", lambda fs: fs.write(content="x")),
    ("write-path-only", lambda fs: fs.write(path="/f.txt")),
    ("write-non-str-content", lambda fs: fs.write(path="/f.txt", content=7)),
    ("write-non-bytes-data", lambda fs: fs.write(path="/f.txt", data="x")),
    ("write-content-and-data", lambda fs: fs.write(path="/f.txt", content="x", data=b"y")),
    ("write-both-forms", lambda fs: fs.write(entries=[], path="/f.txt", content="x")),
    ("write-entries-and-data", lambda fs: fs.write(entries=[], data=b"y")),
    ("write-int-vid", lambda fs: fs.write(path="/f.txt", content="x", if_vid=7)),
    ("write-short-vid", lambda fs: fs.write(path="/f.txt", content="x", if_vid="0" * 19)),
    ("write-upper-vid", lambda fs: fs.write(path="/f.txt", content="x", if_vid="A" * 20)),
    ("write-vid-with-entries", lambda fs: fs.write(entries=[], if_vid="0" * 20)),
    ("write-vids-with-path", lambda fs: fs.write(path="/f.txt", content="x", if_vids={"/f.txt": "0" * 20})),
    ("write-vids-not-a-mapping", lambda fs: fs.write(entries=[], if_vids=[("/f.txt", "0" * 20)])),
    ("write-vids-non-str-key", lambda fs: fs.write(entries=[], if_vids={1: "0" * 20})),
    ("write-vids-not-a-vid", lambda fs: fs.write(entries=[], if_vids={"/f.txt": 1})),
    ("write-append-with-the-mark", lambda fs: fs.write(path="/f.txt", content="x", append=True, if_vid=ABSENT)),
    ("write-truthy-append", lambda fs: fs.write(path="/f.txt", content="x", append=1)),
    ("write-append-with-entries", lambda fs: fs.write(entries=[], append=True)),
    ("write-append-with-if-absent", lambda fs: fs.write(path="/f.txt", content="x", append=True, if_absent=True)),
    ("write-truthy-if-absent", lambda fs: fs.write(path="/f.txt", content="x", if_absent="yes")),
    ("write-absent-with-vid", lambda fs: fs.write(path="/f.txt", content="x", if_absent=True, if_vid="0" * 20)),
    ("write-absent-with-vids", lambda fs: fs.write(entries=[], if_absent=True, if_vids={"/f.txt": "0" * 20})),
    ("write-truthy-parents", lambda fs: fs.write(path="/f.txt", content="x", parents=1)),
    ("edit-int-vid", lambda fs: fs.edit("/f.txt", old="a", new="b", if_vid=7)),
    ("edit-vid-with-observations", lambda fs: fs.edit(observations=[], edits=[], if_vid="0" * 20)),
    ("edit-vids-with-path", lambda fs: fs.edit("/f.txt", old="a", new="b", if_vids={"/f.txt": "0" * 20})),
    ("edit-vids-not-a-vid", lambda fs: fs.edit(observations=[], edits=[], if_vids={"/f.txt": "x"})),
    ("edit-partial-pair", lambda fs: fs.edit("/f.txt", old="a")),
    ("edit-non-str-old", lambda fs: fs.edit("/f.txt", old=1, new="b")),
    ("edit-truthy-replace-all", lambda fs: fs.edit("/f.txt", old="a", new="b", replace_all="yes")),
    ("delete-truthy-cascade", lambda fs: fs.delete("/f.txt", cascade=1)),
    ("restore-both-forms", lambda fs: fs.restore("/f.txt", observations=[])),
    ("sweep-non-str-path", lambda fs: fs.sweep(123)),
    ("sweep-non-authority", lambda fs: fs.sweep("/.vfs/trash", authority=123)),
    ("mkdir-truthy-parents", lambda fs: fs.mkdir("/d", parents="yes")),
    ("mkdir-truthy-exist-ok", lambda fs: fs.mkdir("/d", exist_ok=1)),
    ("mkedge-non-str-type", lambda fs: fs.mkedge(source="/a.py", target="/b.py", edge_type=123)),
    ("move-missing-dest", lambda fs: fs.move(src="/a")),
    ("move-both-forms", lambda fs: fs.move(src="/a", dest="/b", moves=[])),
    ("copy-missing-src", lambda fs: fs.copy(dest="/b")),
    ("glob-non-str-pattern", lambda fs: fs.glob(123)),
    ("glob-str-paths", lambda fs: fs.glob("*", paths="/m")),
    ("glob-non-str-path-item", lambda fs: fs.glob("*", paths=("/m", 1))),
    ("glob-str-ext", lambda fs: fs.glob("*", ext="py")),
    ("glob-bool-cap", lambda fs: fs.glob("*", max_count=True)),
    ("glob-str-cap", lambda fs: fs.glob("*", max_count="5")),
    ("glob-zero-cap", lambda fs: fs.glob("*", max_count=0)),
    ("glob-columns", lambda fs: fs.glob("*", columns=123)),
    ("grep-bogus-case-mode", lambda fs: fs.grep("x", case_mode="bogus")),
    ("grep-bogus-output-mode", lambda fs: fs.grep("x", output_mode="bogus")),
    ("grep-negative-context", lambda fs: fs.grep("x", before_context=-1)),
    ("grep-str-context", lambda fs: fs.grep("x", after_context="2")),
    ("grep-zero-per-file-cap", lambda fs: fs.grep("x", max_count=0)),
    ("grep-truthy-flag", lambda fs: fs.grep("x", fixed_strings="yes")),
    ("grep-generator-paths", lambda fs: fs.grep("x", paths=(p for p in ()))),
    ("glob-null-ext", lambda fs: fs.glob("*", ext=None)),
    ("grep-null-context", lambda fs: fs.grep("x", before_context=None)),
    ("grep-null-case-mode", lambda fs: fs.grep("x", case_mode=None)),
    ("grep-null-paths", lambda fs: fs.grep("x", paths=None)),
    ("delete-null-cascade", lambda fs: fs.delete("/f.txt", cascade=None)),
    ("search-null-limit", lambda fs: fs.search("q", limit=None)),
    ("search-non-str-query", lambda fs: fs.search(123)),
    ("search-bool-limit", lambda fs: fs.search("q", limit=True)),
    ("traverse-bogus-method", lambda fs: fs.traverse("bogus", "/a.py")),
    ("traverse-zero-depth", lambda fs: fs.traverse("outbound", "/a.py", depth=0)),
    ("traverse-zero-limit", lambda fs: fs.traverse("outbound", "/a.py", limit=0)),
    ("traverse-retired-method", lambda fs: fs.traverse("ancestors", "/a.py")),
    ("traverse-minimal-off-meet", lambda fs: fs.traverse("outbound", "/a.py", minimal=True)),
    (
        "traverse-type-in-both-lists",
        lambda fs: fs.traverse("outbound", "/a.py", edge_types=("a",), edge_types_not=("a",)),
    ),
    ("traverse-bad-type-segment", lambda fs: fs.traverse("outbound", "/a.py", edge_types=("a/b",))),
    ("traverse-str-edge-types", lambda fs: fs.traverse("outbound", "/a.py", edge_types="imports")),
    ("traverse-truthy-minimal", lambda fs: fs.traverse("meet", "/a.py", minimal=1)),
    ("run-non-dict-arguments", lambda fs: fs.run("/t", arguments=123)),
]


@pytest.mark.parametrize(("label", "call"), GARBAGE, ids=[label for label, _ in GARBAGE])
async def test_garbage_classifies_invalid_with_zero_dispatch(label: str, call) -> None:
    fs = RecorderFS()
    result = await call(fs)
    assert result.success is False, label
    assert result.errors[0].kind is ErrorKind.invalid, label
    assert fs.calls == [], label


# ----------------------------------------------------------------------
# precedence — caller-input facts outrank router-state facts
# ----------------------------------------------------------------------


async def test_param_gate_beats_closed_table() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.close()
    result = await fs.tree("/", max_depth="2")  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is ErrorKind.invalid


async def test_param_gate_beats_busy() -> None:
    root = AsyncVirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/m/inner", parents=True)
    result = await root.delete("/m", cascade="x")  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is ErrorKind.invalid


# ----------------------------------------------------------------------
# positive controls — well-typed calls pass the gate untouched
# ----------------------------------------------------------------------


async def test_valid_grep_params_dispatch() -> None:
    fs = RecorderFS()
    result = await fs.grep("x", case_mode="smart", output_mode="count", before_context=2, max_count=3)
    assert result.success is True
    op, kwargs = fs.calls[0]
    assert op == "grep"
    assert kwargs["case_mode"] == "smart"


async def test_run_arguments_dict_passes_through() -> None:
    fs = RecorderFS()
    result = await fs.run("/tool", arguments={"a": 1})
    assert result.success is True
    op, kwargs = fs.calls[0]
    assert op == "run"
    assert kwargs["arguments"] == {"a": 1}
