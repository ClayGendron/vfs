"""Ingress type gates: the params table's drift guard, the per-verb garbage
matrix (invalid, parameter named, zero dispatch), and the precedence pins."""

from __future__ import annotations

import inspect

import pytest

from tests.support.base_doubles import RecorderFS, RecorderStorage
from vfs.base import VirtualFileSystem
from vfs.ops import ALL_OPS
from vfs.params import INT_CEILING, PARAMS, RULES, param_violation
from vfs.results import VFSErrorKind

# ----------------------------------------------------------------------
# drift — the table and the public surface may never diverge
# ----------------------------------------------------------------------


def test_table_covers_every_op() -> None:
    assert set(PARAMS) == ALL_OPS
    assert set(RULES) <= ALL_OPS


def test_every_verb_signature_matches_the_table() -> None:
    for op, specs in PARAMS.items():
        verb = getattr(VirtualFileSystem, op)
        sig_names = {name for name in inspect.signature(verb).parameters if name != "self"}
        table_names = {spec.name for spec in specs}
        assert sig_names == table_names, f"{op}: drift on {sig_names ^ table_names}"


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
    assert swept == 7


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


# ----------------------------------------------------------------------
# the garbage matrix — wrong type, bounds, bogus enum, truthy non-bool
# ----------------------------------------------------------------------

GARBAGE = [
    ("read-columns", lambda fs: fs.read("/f.txt", columns=123)),
    ("read-non-str-column-item", lambda fs: fs.read("/f.txt", columns=frozenset({"path", 7}))),
    ("read-user-id", lambda fs: fs.read("/f.txt", user_id=123)),
    ("read-both-targets", lambda fs: fs.read("/f.txt", observations=[])),
    ("stat-both-targets", lambda fs: fs.stat("/f.txt", observations=[])),
    ("ls-both-targets", lambda fs: fs.ls("/f.txt", observations=[])),
    ("tree-bool-depth", lambda fs: fs.tree("/", max_depth=True)),
    ("tree-str-depth", lambda fs: fs.tree("/", max_depth="2")),
    ("tree-missing-path", lambda fs: fs.tree(None)),
    ("write-content-only", lambda fs: fs.write(content="x")),
    ("write-path-only", lambda fs: fs.write(path="/f.txt")),
    ("write-non-str-content", lambda fs: fs.write(path="/f.txt", content=7)),
    ("write-both-forms", lambda fs: fs.write(entries=[], path="/f.txt", content="x")),
    ("write-truthy-overwrite", lambda fs: fs.write(path="/f.txt", content="x", overwrite="yes")),
    ("write-truthy-parents", lambda fs: fs.write(path="/f.txt", content="x", parents=1)),
    ("edit-partial-pair", lambda fs: fs.edit("/f.txt", old="a")),
    ("edit-non-str-old", lambda fs: fs.edit("/f.txt", old=1, new="b")),
    ("edit-truthy-replace-all", lambda fs: fs.edit("/f.txt", old="a", new="b", replace_all="yes")),
    ("delete-truthy-cascade", lambda fs: fs.delete("/f.txt", cascade=1)),
    ("restore-both-forms", lambda fs: fs.restore("/f.txt", observations=[])),
    ("sweep-non-str-path", lambda fs: fs.sweep(123)),
    ("sweep-non-str-user", lambda fs: fs.sweep("/.vfs/trash", user_id=123)),
    ("mkdir-truthy-parents", lambda fs: fs.mkdir("/d", parents="yes")),
    ("mkdir-truthy-exist-ok", lambda fs: fs.mkdir("/d", exist_ok=1)),
    ("mkedge-non-str-type", lambda fs: fs.mkedge("/a.py", "/b.py", 123)),
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
    ("glean-null-limit", lambda fs: fs.glean("q", limit=None)),
    ("glean-non-str-query", lambda fs: fs.glean(123)),
    ("glean-bool-limit", lambda fs: fs.glean("q", limit=True)),
    ("graph-bogus-method", lambda fs: fs.graph("bogus", "/a.py")),
    ("graph-zero-depth", lambda fs: fs.graph("ancestors", "/a.py", depth=0)),
    ("run-non-dict-arguments", lambda fs: fs.run("/t", arguments=123)),
]


@pytest.mark.parametrize(("label", "call"), GARBAGE, ids=[label for label, _ in GARBAGE])
async def test_garbage_classifies_invalid_with_zero_dispatch(label: str, call) -> None:
    fs = RecorderFS()
    result = await call(fs)
    assert result.success is False, label
    assert result.errors[0].kind is VFSErrorKind.invalid, label
    assert fs.calls == [], label


# ----------------------------------------------------------------------
# precedence — caller-input facts outrank router-state facts
# ----------------------------------------------------------------------


async def test_param_gate_beats_closed_table() -> None:
    fs = VirtualFileSystem()
    await fs.close()
    result = await fs.tree("/", max_depth="2")  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_param_gate_beats_busy() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderStorage(), "/m/inner", parents=True)
    result = await root.delete("/m", cascade="x")  # ty: ignore[invalid-argument-type]
    assert result.errors[0].kind is VFSErrorKind.invalid


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
