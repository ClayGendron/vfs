"""A table-driven reference evaluator for the vfs shell's execution policy.

Reference only, never shipped. It models the rule the S6 report argues for:
there is no separate "command policy"; a command resolves to a program, the
program resolves to the verbs it will call, and every verb is judged by the
gate vfs already has, in the router's pinned order:

    resolve program  ->  capability  ->  grammar  ->  permission  ->  budgets

The permission step reads the caller's rung on each touched prefix against the
one verb-to-rung table (mirrors ``VERB_RUNGS`` in ``src/vfs/ops.py``). The
program runs AS the caller: it holds exactly the caller's rungs, never more.

Run:  uv run python context/research/studies/2026-10-15-agent-shell/experiments/s6/policy_eval.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal, NamedTuple

# ---------------------------------------------------------------------------
# The ladder and the verb table (mirrors src/vfs/ops.py, ADR 080)
# ---------------------------------------------------------------------------

Rung = Literal["none", "list", "read", "add", "contribute", "read_write"]
RUNGS: Final[tuple[Rung, ...]] = ("none", "list", "read", "add", "contribute", "read_write")
RANK: Final[dict[Rung, int]] = {r: i for i, r in enumerate(RUNGS)}


class Needs(NamedTuple):
    primary: Rung
    create: Rung | None = None
    traverse: Rung | None = None


VERB_RUNGS: Final[dict[str, Needs]] = {
    "read": Needs("read"),
    "stat": Needs("list"),
    "ls": Needs("list"),
    "tree": Needs("list"),
    "glob": Needs("list"),
    "grep": Needs("read"),
    "glean": Needs("read"),
    "graph": Needs("read", traverse="list"),
    "write": Needs("contribute", create="add"),
    "edit": Needs("contribute"),
    "mkdir": Needs("contribute", create="add"),
    "delete": Needs("read_write"),
    "restore": Needs("read_write"),
    "move": Needs("read_write", create="add"),
    "copy": Needs("read_write", create="add", traverse="read"),
    "mkedge": Needs("contribute", traverse="list"),
    "rmedge": Needs("contribute", traverse="list"),
    "grant": Needs("read_write"),
    "revoke": Needs("read_write"),
    "grants": Needs("read"),
    # The S6 recommendation: run reads the program row, so its rung is read.
    "run": Needs("read"),
}

MUTATING: Final[frozenset[str]] = frozenset(
    {"write", "edit", "delete", "restore", "mkdir", "mkedge", "rmedge", "move", "copy"}
)
READ_FAMILY: Final[frozenset[str]] = frozenset({"read", "stat", "ls", "tree", "glob", "grep", "glean", "graph"})
DEVELOPER_OPS: Final[frozenset[str]] = frozenset({"sweep", "posture", "add_member", "remove_member"})

META_ROOT: Final = "/.vfs"
BIN_DIR: Final = "/.agents/bin"

# ---------------------------------------------------------------------------
# Budgets — the pre-flight set (names mirror grep.py's discipline)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Budgets:
    """Pre-flight: shape caps a parsed command can violate before any verb runs.

    Runtime budgets (fuel, wall time, memory, stdout bytes) are not judged
    here: they trip while the program runs and classify ``timeout`` or
    ``budget_exhausted``; a capped-but-served result carries ``truncated``
    as a warning, exactly as grep does.
    """

    stage_budget: int = 64  # pipeline stages per command line
    argv_byte_budget: int = 128 * 1024  # bytes of argv after expansion
    fanout_budget: int = 10_000  # paths one stage may address in one call (the batch contract)
    stdout_byte_budget: int = 4 * 1024 * 1024  # bytes a stage may hand to the next or to the caller
    wall_time_budget: float = 10.0  # seconds per command line (grep's WALL_TIME_BUDGET)
    fuel_budget: int = 2_000_000_000  # wasm instructions per program (an epoch-free determinism knob)
    memory_byte_budget: int = 256 * 1024 * 1024  # wasm linear memory per program
    verb_call_budget: int = 10_000  # verb dispatches per program run (counts operations, not time)


# ---------------------------------------------------------------------------
# The inputs
# ---------------------------------------------------------------------------


class Need(NamedTuple):
    """One verb the program will call, on one path, with the facts the gate needs."""

    verb: str
    path: str
    create: bool = False  # the path is a fresh name the verb mints
    traverse: bool = False  # the verb only reads this path (a copy's source, a walk node)
    owned: bool = False  # the caller's own row (the owner floor rides)
    capability: str | None = None  # a non-fs capability the program wants (e.g. "net")


@dataclass(frozen=True)
class Command:
    line: str
    program: str
    argv: tuple[str, ...]
    needs: tuple[Need, ...] = ()
    stages: int = 1
    fanout: int = 1
    stdout_bytes: int = 0
    runtime: Literal["returns", "loops_forever", "over_fuel"] = "returns"


@dataclass(frozen=True)
class Caller:
    name: str
    rungs: dict[str, Rung]  # prefix -> rung the caller holds there (grants + posture, merged)
    anonymous: bool = False

    def rung_at(self, path: str) -> Rung:
        best: Rung = "none"
        best_len = -1
        for prefix, rung in self.rungs.items():
            if (path == prefix or path.startswith(prefix.rstrip("/") + "/") or prefix == "/") and len(prefix) > best_len:
                best, best_len = rung, len(prefix)
        return best


@dataclass(frozen=True)
class Host:
    """Mount-table facts: what each mount declares minus its deny_ops; the host's program mask."""

    caps: dict[str, frozenset[str]]  # mount prefix -> effective caps (declared - deny_ops)
    read_only: frozenset[str] = frozenset()  # mount prefixes carrying permissions="read"
    deny_programs: frozenset[str] = frozenset()  # the proposed deny_ops extension to program names
    bin: dict[str, str] = field(default_factory=dict)  # program name -> row path under BIN_DIR
    builtins: frozenset[str] = frozenset()  # the kernel's own words (the vfs verbs as commands)
    kernel_capabilities: frozenset[str] = frozenset({"fs"})  # what the kernel can hand a program

    def mount_of(self, path: str) -> str:
        best = "/"
        for prefix in self.caps:
            if prefix != "/" and (path == prefix or path.startswith(prefix + "/")) and len(prefix) > len(best):
                best = prefix
        return best


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    allowed: bool
    kind: str | None = None  # the classified ErrorKind value, vfs.* vocabulary
    detail: str = ""
    warnings: list[str] = field(default_factory=list)
    runtime: str = ""  # what the runtime budgets would do once the program runs

    def __str__(self) -> str:
        head = "ALLOW" if self.allowed else f"DENY  {self.kind}"
        parts = [head]
        if self.detail:
            parts.append(self.detail)
        for w in self.warnings:
            parts.append(f"[warning: {w}]")
        if self.runtime:
            parts.append(f"[runtime: {self.runtime}]")
        return " — ".join(parts)


def _deny(kind: str, detail: str) -> Verdict:
    return Verdict(False, kind, detail)


# ---------------------------------------------------------------------------
# The evaluator: resolve → capability → grammar → permission → budgets
# ---------------------------------------------------------------------------


def evaluate(cmd: Command, caller: Caller, host: Host, budgets: Budgets = Budgets()) -> Verdict:
    # 1. Resolve the program. A developer-plane word is not in the shell's
    #    vocabulary at all: it is unrecognized, never "denied".
    if cmd.program in DEVELOPER_OPS:
        return _deny("vfs.unrecognized", f"{cmd.program!r} is a developer-plane verb; the shell has no such word")
    if cmd.program in host.deny_programs:
        return _deny("vfs.unsupported", f"program {cmd.program!r} is masked by the host (deny_ops on programs)")
    if cmd.program in host.builtins:
        pass
    elif cmd.program in host.bin:
        # run's own gate: the caller must READ the program row (run's rung is read).
        row = host.bin[cmd.program]
        held = caller.rung_at(row)
        if RANK[held] < RANK["read"]:
            if held == "none":
                return _deny("vfs.not_found", f"{row} is not visible to {caller.name}")
            return _deny("vfs.permission_denied", f"run needs read on {row}; {caller.name} holds {held}")
    else:
        return _deny("vfs.unrecognized", f"no builtin or installed program named {cmd.program!r}")

    # 2. Capability: every verb the program will call must be declared by the
    #    mount it touches (declared caps minus deny_ops); a non-fs capability
    #    must be one the kernel can hand out at all.
    for need in cmd.needs:
        if need.capability is not None and need.capability not in host.kernel_capabilities:
            return _deny("vfs.unsupported", f"{cmd.program!r} wants capability {need.capability!r}; the kernel has none")
        mount = host.mount_of(need.path)
        if need.verb not in host.caps.get(mount, frozenset()):
            return _deny("vfs.unsupported", f"operation {need.verb!r} is not declared by the storage mounted at {mount}")

    # 3. Grammar: a mutation may not address the reserved metadata tree.
    for need in cmd.needs:
        if need.verb in MUTATING and (need.path == META_ROOT or need.path.startswith(META_ROOT + "/")):
            return _deny("vfs.invalid", f"{need.verb} may not address the reserved tree {need.path}")
        if need.verb in MUTATING and host.mount_of(need.path) in host.read_only:
            return _deny("vfs.read_only", f"the mount at {host.mount_of(need.path)} is read-only")

    # 4. Permission: each verb against the caller's rung on the touched path,
    #    read from the one table; the owner floor rides for a named caller.
    for need in cmd.needs:
        needs = VERB_RUNGS[need.verb]
        if need.create and needs.create is not None:
            wanted: Rung = needs.create
        elif need.traverse and needs.traverse is not None:
            wanted = needs.traverse
        else:
            wanted = needs.primary
        held = caller.rung_at(need.path)
        if need.owned and not caller.anonymous and need.verb in MUTATING and RANK[held] >= RANK["add"]:
            continue  # the owner floor: a named caller alters and trashes its own rows
        if RANK[held] >= RANK[wanted]:
            continue
        if held == "none":
            if caller.anonymous:
                return _deny("vfs.unauthenticated", f"{need.path} is {held!r} to everyone; a named authority is needed")
            if need.verb in READ_FAMILY and need.verb != "read":
                continue  # a listing never reveals a hidden row: it simply is not in the answer
            return _deny("vfs.not_found", f"{need.path} is not visible to {caller.name}")
        return _deny("vfs.permission_denied", f"{need.verb} needs {wanted} on {need.path}; {caller.name} holds {held}")

    # 5. Budgets. Shape caps refuse before anything runs; the fan-out cap
    #    chunks and serves (the batch contract); the rest trip at runtime.
    verdict = Verdict(True)
    if cmd.stages > budgets.stage_budget:
        return _deny("vfs.invalid", f"{cmd.stages} stages exceed the stage budget of {budgets.stage_budget}")
    argv_bytes = sum(len(a.encode()) for a in cmd.argv)
    if argv_bytes > budgets.argv_byte_budget:
        return _deny("vfs.invalid", f"argv is {argv_bytes} bytes; the budget is {budgets.argv_byte_budget}")
    if cmd.fanout > budgets.fanout_budget:
        verdict.warnings.append(
            f"vfs.budget_exhausted.truncated: {cmd.fanout} paths exceed the fan-out budget of "
            f"{budgets.fanout_budget}; the first {budgets.fanout_budget} are served, refine the scope"
        )
    if cmd.stdout_bytes > budgets.stdout_byte_budget:
        verdict.warnings.append(
            f"vfs.budget_exhausted.truncated: stdout would be {cmd.stdout_bytes} bytes; cut at "
            f"{budgets.stdout_byte_budget}, rows served are whole"
        )
    if cmd.runtime == "loops_forever":
        verdict.runtime = f"vfs.timeout after {budgets.wall_time_budget}s (epoch deadline); rows already emitted are kept"
    elif cmd.runtime == "over_fuel":
        verdict.runtime = f"vfs.budget_exhausted after {budgets.fuel_budget} instructions (fuel trap); not retryable as-is"
    return verdict


# ---------------------------------------------------------------------------
# The twenty-odd cases
# ---------------------------------------------------------------------------

BUILTINS: Final = frozenset({"ls", "cat", "rm", "tee", "cp", "mv", "grep", "wc", "echo", "mkdir", "glob", "stat"})
FULL: Final = frozenset(VERB_RUNGS) - {"run"} | {"run"}

HOST = Host(
    caps={
        "/": FULL,
        "/archive": FULL - MUTATING,  # a mount whose deny_ops masked every mutation
        "/vendor": FULL,  # permissions="read": the map, not deny_ops, refuses writes
    },
    read_only=frozenset({"/vendor"}),
    deny_programs=frozenset(),
    bin={"jq": f"{BIN_DIR}/jq.wasm", "loop": f"{BIN_DIR}/loop.wasm", "curl": f"{BIN_DIR}/curl.wasm"},
    builtins=BUILTINS,
)
HOST_NO_RM = Host(**{**HOST.__dict__, "deny_programs": frozenset({"rm"})})

ALICE = Caller("alice", {"/": "read", "/notes": "read_write", "/drafts": "add", BIN_DIR: "read", "/secret": "none"})
BOB = Caller("bob", {"/": "list", "/notes": "contribute", BIN_DIR: "list", "/wiki": "add"})
INSTALLER = Caller("installer", {"/": "read", BIN_DIR: "add"})
NOBODY = Caller("anon", {"/": "none", "/scratch": "add"}, anonymous=True)

CASES: Final[list[tuple[str, Command, Caller, Host]]] = [
    ("1  list at list", Command("ls /notes", "ls", ("ls", "/notes"), (Need("ls", "/notes"),)), BOB, HOST),
    ("2  cat at list", Command("cat /x.md", "cat", ("cat", "/x.md"), (Need("read", "/x.md"),)), BOB, HOST),
    ("3  cat at read", Command("cat /x.md", "cat", ("cat", "/x.md"), (Need("read", "/x.md"),)), ALICE, HOST),
    (
        "4  rm -rf at read_write (trash, reversible)",
        Command("rm -rf /notes", "rm", ("rm", "-rf", "/notes"), (Need("delete", "/notes"),), fanout=4_000),
        ALICE,
        HOST,
    ),
    (
        "5  rm -rf at contribute, not own",
        Command("rm -rf /notes", "rm", ("rm", "-rf", "/notes"), (Need("delete", "/notes"),)),
        BOB,
        HOST,
    ),
    (
        "6  rm own row at add (owner floor)",
        Command("rm /wiki/mine.md", "rm", ("rm", "/wiki/mine.md"), (Need("delete", "/wiki/mine.md", owned=True),)),
        BOB,
        HOST,
    ),
    (
        "7  cat 10k files (batch contract) — bytes over the stdout budget",
        Command(
            "cat /corpus/**/*.md",
            "cat",
            ("cat", "/corpus/**/*.md"),
            (Need("read", "/corpus"),),
            fanout=10_000,
            stdout_bytes=200 * 1024 * 1024,
        ),
        ALICE,
        HOST,
    ),
    (
        "8  cat 25k files — over the fan-out budget",
        Command("cat /corpus/**", "cat", ("cat", "/corpus/**"), (Need("read", "/corpus"),), fanout=25_000),
        ALICE,
        HOST,
    ),
    ("9  a program that loops forever", Command("loop", "loop", ("loop",), (), runtime="loops_forever"), ALICE, HOST),
    ("10 a program that burns fuel", Command("loop --hot", "loop", ("loop", "--hot"), (), runtime="over_fuel"), ALICE, HOST),
    (
        "11 install into bin at add (fresh name)",
        Command(
            "tee /.agents/bin/yq.wasm",
            "tee",
            ("tee", f"{BIN_DIR}/yq.wasm"),
            (Need("write", f"{BIN_DIR}/yq.wasm", create=True),),
        ),
        INSTALLER,
        HOST,
    ),
    (
        "12 install into bin at list",
        Command("tee /.agents/bin/yq.wasm", "tee", ("tee", f"{BIN_DIR}/yq.wasm"), (Need("write", f"{BIN_DIR}/yq.wasm", create=True),)),
        BOB,
        HOST,
    ),
    (
        "13 overwrite another's program at add",
        Command("tee /.agents/bin/jq.wasm", "tee", ("tee", f"{BIN_DIR}/jq.wasm"), (Need("write", f"{BIN_DIR}/jq.wasm"),)),
        INSTALLER,
        HOST,
    ),
    ("14 sweep (developer plane)", Command("sweep /notes", "sweep", ("sweep", "/notes"), (Need("delete", "/notes"),)), ALICE, HOST),
    ("15 posture (developer plane)", Command("posture / none", "posture", ("posture", "/", "none"), ()), ALICE, HOST),
    ("16 git (no such program)", Command("git status", "git", ("git", "status"), ()), ALICE, HOST),
    (
        "17 jq at read on bin and on the data",
        Command("jq . /data.json", "jq", ("jq", ".", "/data.json"), (Need("read", "/data.json"),)),
        ALICE,
        HOST,
    ),
    ("18 jq at list on bin (can name, not read)", Command("jq . /notes/d.json", "jq", ("jq", ".", "/notes/d.json"), (Need("read", "/notes/d.json"),)), BOB, HOST),
    (
        "19 curl wants the network",
        Command("curl https://example.com", "curl", ("curl", "https://example.com"), (Need("read", "/", capability="net"),)),
        ALICE,
        HOST,
    ),
    (
        "20 pipeline grep | wc",
        Command("grep foo /notes | wc -l", "grep", ("grep", "foo", "/notes"), (Need("grep", "/notes"),), stages=2),
        ALICE,
        HOST,
    ),
    (
        "21 write into a deny_ops-masked mount",
        Command("echo hi > /archive/x", "tee", ("tee", "/archive/x"), (Need("write", "/archive/x", create=True),)),
        ALICE,
        HOST,
    ),
    (
        "22 write into a permissions='read' mount",
        Command("echo hi > /vendor/x", "tee", ("tee", "/vendor/x"), (Need("write", "/vendor/x", create=True),)),
        ALICE,
        HOST,
    ),
    ("23 rm when the host masks rm", Command("rm /notes/x", "rm", ("rm", "/notes/x"), (Need("delete", "/notes/x"),)), ALICE, HOST_NO_RM),
    (
        "24 read the trash view",
        Command("cat /.vfs/trash/notes/x", "cat", ("cat", "/.vfs/trash/notes/x"), (Need("read", "/.vfs/trash/notes/x"),)),
        ALICE,
        HOST,
    ),
    (
        "25 write into the trash view",
        Command("tee /.vfs/trash/notes/x", "tee", ("tee", "/.vfs/trash/notes/x"), (Need("write", "/.vfs/trash/notes/x"),)),
        ALICE,
        HOST,
    ),
    ("26 anonymous cat under a none posture", Command("cat /secret.md", "cat", ("cat", "/secret.md"), (Need("read", "/secret.md"),)), NOBODY, HOST),
    (
        "27 anonymous write under an add posture",
        Command("tee /scratch/n.md", "tee", ("tee", "/scratch/n.md"), (Need("write", "/scratch/n.md", create=True),)),
        NOBODY,
        HOST,
    ),
    (
        "28 cp: read on the source, add at the target",
        Command("cp /x.md /drafts/x.md", "cp", ("cp", "/x.md", "/drafts/x.md"), (Need("copy", "/x.md", traverse=True), Need("copy", "/drafts/x.md", create=True))),
        ALICE,
        HOST,
    ),
    (
        "29 mv: read_write on the source",
        Command("mv /x.md /drafts/x.md", "mv", ("mv", "/x.md", "/drafts/x.md"), (Need("move", "/x.md"), Need("move", "/drafts/x.md", create=True))),
        ALICE,
        HOST,
    ),
    (
        "30 a program writing into bin as a caller holding read on bin (no more than its caller)",
        Command("jq --install /.agents/bin/evil.wasm", "jq", ("jq", "--install"), (Need("write", f"{BIN_DIR}/evil.wasm", create=True),)),
        ALICE,
        Host(**{**HOST.__dict__}),
    ),
    ("31 a hidden path in a glob (never revealed)", Command("glob /secret/**", "glob", ("glob", "/secret/**"), (Need("glob", "/secret"),)), ALICE, HOST),
    ("32 cat a hidden path", Command("cat /secret/k.md", "cat", ("cat", "/secret/k.md"), (Need("read", "/secret/k.md"),)), ALICE, HOST),
    ("33 a 200-stage pipeline", Command("a | b | ... (200 stages)", "cat", ("cat",), (), stages=200), ALICE, HOST),
]


def main() -> None:
    width = max(len(name) for name, *_ in CASES)
    print(f"{'case':<{width}}  caller     verdict")
    print("-" * (width + 60))
    for name, cmd, caller, host in CASES:
        print(f"{name:<{width}}  {caller.name:<9}  {evaluate(cmd, caller, host)}")


if __name__ == "__main__":
    main()
