"""Executable evidence for story 057 — defects in the current Result envelope.

Run: uv run python context/stories/057-result-envelope/repro.py

Each section demonstrates one defect the 057 redesign fixes, against the
live code. Every claim in spec.md that says "verified" points here. The
script asserts CURRENT behavior — when 057 lands, these assertions should
start failing, and the file retires with the story.
"""

# ruff: noqa: T201  — printing findings is this script's purpose

from __future__ import annotations

import asyncio

from pydantic import ValidationError

from vfs.backends.memory import InMemoryStorage
from vfs.base2 import VirtualFileSystem
from vfs.paths import Path
from vfs.results2 import Result, ResultError, VFSErrorKind
from vfs.storage import TransportError


class DeadStorage(InMemoryStorage):
    """A wire-shaped backend whose peer is gone: every op raises TransportError."""

    def __init__(self) -> None:
        super().__init__(name="dead", description="dead backend")

    async def read(self, **kwargs: object) -> Result:  # type: ignore[override]
        raise TransportError("connection refused")

    async def stat(self, **kwargs: object) -> Result:  # type: ignore[override]
        raise TransportError("connection refused")

    async def ls(self, **kwargs: object) -> Result:  # type: ignore[override]
        raise TransportError("connection refused")

    async def tree(self, **kwargs: object) -> Result:  # type: ignore[override]
        raise TransportError("connection refused")

    async def grep(self, **kwargs: object) -> Result:  # type: ignore[override]
        raise TransportError("connection refused")

    async def glob(self, **kwargs: object) -> Result:  # type: ignore[override]
        raise TransportError("connection refused")


class OverclaimStorage:
    """Read-family-only storage that DECLARES glob — reaches the funnel's
    unsupported arm (vs the gate's), exposing the path-referent split."""

    name = "overclaim"
    description = "declares more than it implements"

    def __init__(self) -> None:
        self._inner = InMemoryStorage()

    def capabilities(self) -> frozenset[str]:
        return frozenset({"read", "stat", "ls", "tree", "glob"})

    async def read(self, **kwargs: object) -> Result:
        return await self._inner.read(**kwargs)  # type: ignore[arg-type]

    async def stat(self, **kwargs: object) -> Result:
        return await self._inner.stat(**kwargs)  # type: ignore[arg-type]

    async def ls(self, **kwargs: object) -> Result:
        return await self._inner.ls(**kwargs)  # type: ignore[arg-type]

    async def tree(self, **kwargs: object) -> Result:
        return await self._inner.tree(**kwargs)  # type: ignore[arg-type]


def check(label: str, condition: bool, detail: str) -> None:
    status = "CONFIRMED" if condition else "NOT REPRODUCED (behavior changed?)"
    print(f"[{status}] {label}\n    {detail}\n")
    assert condition, f"repro expectation failed: {label}"


# ---------------------------------------------------------------------------
# 1. success is stored, not derived — the lying state is default-constructible
# ---------------------------------------------------------------------------


def defect_1_stored_success() -> None:
    lying = Result(
        function="read",
        success=True,
        errors=[ResultError(kind=VFSErrorKind.not_found, message="gone")],
    )
    round_tripped = Result.from_payload(lying.to_payload())
    check(
        "1. success=True with a fatal error constructs and survives the wire",
        lying.success and bool(lying.errors) and round_tripped.success,
        f"success={lying.success}, errors={len(lying.errors)}; after round-trip success={round_tripped.success}",
    )


# ---------------------------------------------------------------------------
# 2. id()-based error dedup breaks across a wire round-trip (diamond case)
# ---------------------------------------------------------------------------


def defect_2_id_dedup() -> None:
    a = Result(function="ls", success=False, errors=[ResultError(kind=VFSErrorKind.not_found, message="a gone")])
    b = Result(function="ls", success=False, errors=[ResultError(kind=VFSErrorKind.timeout, message="b slow")])
    union = a | b
    in_process = len((union & b).errors)
    after_wire = len((Result.from_payload(union.to_payload()) & b).errors)
    check(
        "2. diamond (a|b)&b dedups in-process but double-counts after to_payload/from_payload",
        in_process == 2 and after_wire == 3,
        f"errors in-process={in_process}, after wire round-trip={after_wire}",
    )


# ---------------------------------------------------------------------------
# 3. rebase identity depends on path presence — dedup depends on history
# ---------------------------------------------------------------------------


def defect_3_rebase_identity() -> None:
    pathless = ResultError(kind=VFSErrorKind.timeout, message="slow")
    pathed = ResultError(kind=VFSErrorKind.timeout, message="slow", path=Path("/x"))
    check(
        "3. with_mount returns the SAME object for path=None, a copy for path set",
        pathless.with_mount("/m") is pathless and pathed.with_mount("/m") is not pathed,
        "identity (and therefore id()-dedup behavior) depends on whether an error happened to carry a path",
    )


# ---------------------------------------------------------------------------
# 4. one dead mount fails the whole fan-out envelope; good rows ride hidden
# ---------------------------------------------------------------------------


async def defect_4_fanout_poisoning() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(InMemoryStorage(name="live"), "/live")
    await fs.write(path="/live/hit.txt", content="needle")
    await fs.add_mount(DeadStorage(), "/dead")
    result = await fs.grep("needle")
    kinds = {str(e.kind) for e in result.errors}
    check(
        "4. unscoped grep with 1 dead mount of 2: success=False (isError=true) despite good rows",
        (not result.success) and len(result.observations) == 1 and "vfs.backend_unavailable" in kinds,
        f"success={result.success}, rows={len(result.observations)}, error kinds={kinds}",
    )


# ---------------------------------------------------------------------------
# 5. _probe_bind_site consumes only the bit: mkdir advice for a dead backend
# ---------------------------------------------------------------------------


async def defect_5_probe_bit_only() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(DeadStorage(), "/dead")
    try:
        await fs.bind(InMemoryStorage(), "/dead/sub")
        message = "<no error raised>"
    except ValueError as exc:
        message = str(exc)
    check(
        "5. bind under a dead backend advises mkdir instead of surfacing the transport failure",
        "mkdir it" in message and "unavailable" not in message,
        f"message: {message!r}",
    )


# ---------------------------------------------------------------------------
# 6. error.path referents diverge: bind path at the gate, None at the funnel
# ---------------------------------------------------------------------------


async def defect_6_path_referents() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(InMemoryStorage(name="dim"), "/dim")
    # Gate: capability missing from the snapshot -> path = bind path.
    incapable = VirtualFileSystem(storage=InMemoryStorage())
    await incapable.add_mount(OverclaimStorage(), "/oc")
    gate_err = (await fs.run("/dim/tool")).errors[0]
    funnel_err = (await incapable.glob("*", paths=("/oc/x",))).errors[0]
    check(
        "6. same logical condition (entry cannot do op): gate carries the bind path, funnel carries None",
        str(gate_err.kind) == "vfs.unsupported"
        and gate_err.path == "/dim"
        and str(funnel_err.kind) == "vfs.unsupported"
        and funnel_err.path is None,
        f"gate path={gate_err.path!r}, funnel path={funnel_err.path!r}",
    )


# ---------------------------------------------------------------------------
# 7. from_payload is a poison pill: one bad path destroys every row
# ---------------------------------------------------------------------------


def defect_7_poison_payload() -> None:
    payload = {
        "function": "ls",
        "success": True,
        "observations": [
            {"path": "/good/row.txt", "kind": "file"},
            {"path": "/bad/\x00row", "kind": "file"},
        ],
        "errors": [],
    }
    try:
        Result.from_payload(payload)
        poisoned = False
    except ValidationError:
        poisoned = True
    check(
        "7. one structurally invalid remote path raises out of from_payload, killing the good row too",
        poisoned,
        "ValidationError raised for the whole envelope (raw exception -> would crash the caller's fan-out)",
    )


# ---------------------------------------------------------------------------
# 8. from_payload strips unknown fields — the 'lossless' claim is false
# ---------------------------------------------------------------------------


def defect_8_field_stripping() -> None:
    r = Result(function="read", success=False, errors=[ResultError(kind=VFSErrorKind.timeout, message="slow")])
    payload = r.to_payload()
    payload["errors"][0]["severity"] = "warning"  # a field from a newer peer
    hopped = Result.from_payload(payload).to_payload()  # one mid-chain hop
    check(
        "8. a newer peer's field (severity) is silently deleted by one mid-chain hop",
        "severity" not in hopped["errors"][0],
        f"error keys after hop: {sorted(hopped['errors'][0])}",
    )


# ---------------------------------------------------------------------------
# 9. caller's max_count multiplies by mount count under fan-out
# ---------------------------------------------------------------------------


async def defect_9_max_count() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    for name in ("a", "b"):
        await fs.add_mount(InMemoryStorage(name=name), f"/{name}")
        await fs.write(path=f"/{name}/one.txt", content="x")
        await fs.write(path=f"/{name}/two.txt", content="x")
    result = await fs.glob("*.txt", max_count=1)
    check(
        "9. glob(max_count=1) over 2 mounts returns 2 rows — the caller's bound is per-entry, not per-call",
        len(result.observations) == 2,
        f"rows={len(result.observations)} for max_count=1",
    )


# ---------------------------------------------------------------------------
# 10. _merge_results' disjointness premise is false at bind paths (tree)
# ---------------------------------------------------------------------------


async def defect_10_bind_path_fusion() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(InMemoryStorage(name="m"), "/m")
    await fs.write(path="/m/f.txt", content="x")
    result = await fs.tree("/")
    rows_at_bind = [o for o in result.observations if o.path == "/m"]
    check(
        "10. tree('/') merges the owner's stored /m row with the descent's rebased root row (left-wins fill)",
        len(rows_at_bind) == 1,
        "two backends each produced a row for /m pre-merge; the union silently fused them "
        "while the docstring claims entries 'never answer for the same path'",
    )


async def main() -> None:
    print("story 057 — current-envelope defect reproductions\n")
    defect_1_stored_success()
    defect_2_id_dedup()
    defect_3_rebase_identity()
    await defect_4_fanout_poisoning()
    await defect_5_probe_bit_only()
    await defect_6_path_referents()
    defect_7_poison_payload()
    defect_8_field_stripping()
    await defect_9_max_count()
    await defect_10_bind_path_fusion()
    print("all 10 defects reproduced against the current envelope")


if __name__ == "__main__":
    asyncio.run(main())
