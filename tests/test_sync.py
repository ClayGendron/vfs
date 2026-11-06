"""The synchronous face: every kernel and session verb as a plain call, one loop on one thread per facade."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import subprocess
import sys
import threading
import warnings
from pathlib import Path as FsPath
from typing import Any

import pytest
from jupyter_client.manager import KernelManager
from sqlalchemy import event

import vfs
import vfs.sync as sync_module
from tests.base.test_authority import ALICE, CALLS, seen
from tests.support.base_doubles import CannedStorage, RecorderStorage
from tests.support.server_schemas import server_schema
from vfs.base import AsyncVirtualFileSystem
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry, Match, Observation
from vfs.ops import ALL_OPS, MANAGEMENT_METHODS, Op
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.session import AsyncSession
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import FOREIGN_LOOP_WARNING, LOOP_THREAD_NAME, Session, VirtualFileSystem

REPO = FsPath(__file__).resolve().parents[1]

# A return or parameter annotation that names the async family maps to the sync one.
FAMILY = {"AsyncSession": "Session", "AsyncVirtualFileSystem": "VirtualFileSystem"}

SCRIPT = """\
from vfs import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

with VirtualFileSystem(storage=InMemoryStorage()) as fs:
    written = fs.write(path="/a.txt", content="x")
    read = fs.read("/a.txt")
print(written.success, read.success)
"""

CELLS = (
    "from vfs import VirtualFileSystem\n"
    "from vfs.storage.backends.memory import InMemoryStorage\n"
    "fs = VirtualFileSystem(storage=InMemoryStorage())",
    'print(fs.write(path="/a.txt", content="x").success)',
    'print(fs.read("/a.txt").success)',
    "fs.close()",
    "import threading\nprint(sorted(t.name for t in threading.enumerate()))",
)

NOTICE = FOREIGN_LOOP_WARNING.split("{op}")[1]
"""The part of the notice after the verb's name, what a cell's stderr shows."""

STATS = {"n_docs": 50, "avg_dl": 3.0, "terms": {"lease": {"df": 5, "idf": 0.0}}}


def _row(path: str, score: float, text: str) -> Observation:
    return Observation(path=Path(path), score=score, matches=[Match(start=1, end=1, content=text, score=score)])


def _mount(rows: list[Observation]) -> CannedStorage:
    return CannedStorage({"glean": Result(ops=("glean",), observations=rows, lexical_stats=STATS, legs={"m": 1})})


def _loop_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == LOOP_THREAD_NAME]


def _normalized(signature: inspect.Signature) -> tuple[list[tuple[str, Any, Any, Any]], Any]:
    params = [
        (name, p.kind, p.default, FAMILY.get(p.annotation, p.annotation)) for name, p in signature.parameters.items()
    ]
    return params, FAMILY.get(signature.return_annotation, signature.return_annotation)


def _assert_twins(original: Any, twin: Any) -> None:
    """The twin's parameters are the original's; its return names the sync family where the original named the async."""
    o_params, o_return = _normalized(inspect.signature(original))
    t_params, t_return = _normalized(inspect.signature(twin))
    assert t_params == o_params
    assert t_return == o_return


class HangingReadStorage(RecorderStorage):
    """A read that never answers: the in-flight call a close or an interrupt must cancel."""

    def __init__(self) -> None:
        super().__init__(name="hanging", description="Hanging read storage double")
        self.started = threading.Event()

    async def read(self, *, authority: Any = None, **kwargs: Any) -> Result:
        self.started.set()
        await asyncio.Event().wait()
        return Result(ops=("read",), observations=[])


class RespawningReadStorage(HangingReadStorage):
    """A read that, when cancelled, leaves a new task behind: the orphan only the runner's own sweep can end."""

    async def read(self, *, authority: Any = None, **kwargs: Any) -> Result:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            asyncio.get_running_loop().create_task(asyncio.Event().wait())
        return Result(ops=("read",), observations=[])


class CallbackStage:
    """A reranker that reaches for the sync handle from the loop thread, the deadlock the facade refuses."""

    def __init__(self) -> None:
        self.fs: VirtualFileSystem | None = None
        self.seen: list[Any] = []

    async def rerank(self, query: str, candidates: Any, *, limit: int) -> Any:
        assert self.fs is not None
        self.seen.append(self.fs.read("/low/l1"))
        try:
            self.fs.add_mount(RecorderStorage(), "/late")
        except RuntimeError as exc:
            self.seen.append(exc)
        return candidates


# ---------------------------------------------------------------------------
# The notebook and the script
# ---------------------------------------------------------------------------


def test_write_then_read_through_the_facade() -> None:
    with VirtualFileSystem(storage=InMemoryStorage()) as fs:
        written = fs.write(path="/a.txt", content="x")
        read = fs.read("/a.txt")
    assert written.success is True
    assert read.success is True
    assert read.one().content == "x"


def test_a_plain_interpreter_with_no_loop_writes_and_reads() -> None:
    """A script with no asyncio.run harness: the facade's own loop is the only one."""
    done = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=False, cwd=REPO)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "True True\n"


@pytest.mark.slow
def test_the_cells_run_in_a_real_ipykernel() -> None:
    """The kernel's loop is running on the main thread while each cell blocks on the facade."""
    assert not any("nest_asyncio" in cell for cell in CELLS)
    manager = KernelManager(kernel_name="python3")
    manager.start_kernel()
    client = manager.blocking_client()
    outputs: list[list[str]] = []
    try:
        client.start_channels()
        client.wait_for_ready(timeout=120)
        for cell in CELLS:
            lines: list[str] = []

            def hook(message: dict[str, Any], lines: list[str] = lines) -> None:
                if message["msg_type"] == "stream":
                    lines.append(message["content"]["text"])

            reply = client.execute_interactive(cell, output_hook=hook, timeout=120)
            assert reply["content"]["status"] == "ok", (cell, reply["content"], lines)
            outputs.append(lines)
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)
    assert "True" in "".join(outputs[1])
    assert "True" in "".join(outputs[2])
    assert LOOP_THREAD_NAME not in "".join(outputs[4])
    # The kernel's loop is foreign to the facade: the notice appears once across the cells, no more.
    assert "".join(line for lines in outputs for line in lines).count(NOTICE) == 1


async def test_close_works_from_inside_a_running_loop() -> None:
    """A notebook cell closes the facade while the kernel's loop runs on the same thread."""
    fs = VirtualFileSystem(storage=InMemoryStorage())
    assert fs.ls("/").success is True
    fs.close()
    assert fs.closed is True
    assert _loop_threads() == []


# ---------------------------------------------------------------------------
# Parity: the twins and the originals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ALL_OPS | MANAGEMENT_METHODS))
def test_every_router_coroutine_has_a_sync_twin(name: str) -> None:
    """A verb that joins the router without its twin fails here by name."""
    original = getattr(AsyncVirtualFileSystem, name)
    twin = getattr(VirtualFileSystem, name)
    assert inspect.iscoroutinefunction(original)
    assert not inspect.iscoroutinefunction(twin)
    _assert_twins(original, twin)


SESSION_COROUTINES = sorted(
    name for name, _ in inspect.getmembers(AsyncSession, inspect.iscoroutinefunction) if not name.startswith("_")
)


@pytest.mark.parametrize("name", SESSION_COROUTINES)
def test_every_session_coroutine_has_a_sync_twin(name: str) -> None:
    twin = getattr(Session, name)
    assert not inspect.iscoroutinefunction(twin)
    _assert_twins(getattr(AsyncSession, name), twin)


def test_the_constructors_and_the_context_managers_are_twins() -> None:
    assert len(SESSION_COROUTINES) == len(ALL_OPS) + 1
    _assert_twins(AsyncVirtualFileSystem.__init__, VirtualFileSystem.__init__)
    _assert_twins(AsyncSession.__init__, Session.__init__)
    _assert_twins(AsyncVirtualFileSystem.session, VirtualFileSystem.session)
    _assert_twins(AsyncVirtualFileSystem.mounts, VirtualFileSystem.mounts)
    _assert_twins(AsyncVirtualFileSystem.capabilities, VirtualFileSystem.capabilities)
    _assert_twins(AsyncSession.__aexit__, Session.__exit__)
    _assert_twins(AsyncSession.__aenter__, Session.__enter__)
    # The router has no async context manager; the facade's exists because it owns a thread.
    assert not hasattr(AsyncVirtualFileSystem, "__aenter__")
    assert callable(VirtualFileSystem.__enter__) and callable(VirtualFileSystem.__exit__)


# ---------------------------------------------------------------------------
# The deadlock guard
# ---------------------------------------------------------------------------


@pytest.mark.timeout(60, method="thread")
def test_a_verb_from_the_loop_thread_is_refused_not_hung() -> None:
    """Dropping the loop-thread check in `_result` makes this hang on its own loop; the timeout names it."""
    stage = CallbackStage()
    with VirtualFileSystem(rerankers=(stage,)) as fs:
        stage.fs = fs
        fs.add_mount(_mount([_row("/l1", 0.2, "lease lease"), _row("/l2", 0.1, "nothing")]), "/low")
        fs.add_mount(_mount([_row("/h1", 0.9, "unrelated"), _row("/h2", 0.8, "a lease")]), "/high")
        merged = fs.glean("lease")
    assert merged.success is True
    refusal = stage.seen[0]
    assert isinstance(refusal, Result)
    assert refusal.ops == ("read",)
    assert refusal.errors[0].kind is ErrorKind.invalid
    assert "loop thread" in refusal.errors[0].message


@pytest.mark.timeout(60, method="thread")
def test_a_management_call_from_the_loop_thread_raises() -> None:
    """Dropping `_refuse_loop_thread` from the management hop makes this hang; the timeout names it."""
    stage = CallbackStage()
    with VirtualFileSystem(rerankers=(stage,)) as fs:
        stage.fs = fs
        fs.add_mount(_mount([_row("/l1", 0.2, "lease")]), "/low")
        fs.add_mount(_mount([_row("/h1", 0.9, "lease")]), "/high")
        assert fs.glean("lease").success is True
        assert fs.mounts()[-1].path != "/late"
    raised = stage.seen[1]
    assert isinstance(raised, RuntimeError)
    assert "loop thread" in str(raised)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_close_stops_the_loop_thread_and_is_idempotent() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    assert fs.ls("/").success is True
    assert len(_loop_threads()) == 1
    assert fs.closed is False
    fs.close()
    assert fs.closed is True
    assert _loop_threads() == []
    assert fs.close() is None
    with VirtualFileSystem(storage=InMemoryStorage()) as other:
        assert len(_loop_threads()) == 1
    assert other.closed is True
    assert _loop_threads() == []


@pytest.mark.parametrize("op", sorted(ALL_OPS))
def test_a_verb_after_close_answers_the_closed_fact(op: Op) -> None:
    """The same fact the router mints after its own close, minted before any hop is attempted."""
    storage = RecorderStorage()
    fs = VirtualFileSystem(storage=storage)
    fs.close()
    result = getattr(fs, op)(**CALLS[op])
    assert result.ops == (op,)
    assert result.success is False
    assert [error.kind for error in result.errors] == [ErrorKind.backend_unavailable]
    assert result.errors[0].message.endswith("the filesystem is closed")
    assert storage.calls == []


def test_a_management_call_after_close_raises() -> None:
    fs = VirtualFileSystem(storage=RecorderStorage())
    fs.close()
    with pytest.raises(RuntimeError, match="closed"):
        fs.add_mount(RecorderStorage(), "/m")
    assert fs.mounts() == ()
    assert fs.capabilities() == frozenset()


@pytest.mark.timeout(60)
def test_close_cancels_the_calls_other_threads_are_waiting_on() -> None:
    """A pooled worker mid-call sees a cancellation; dropping the drain and the runner's sweep hangs the join."""
    storage = HangingReadStorage()
    fs = VirtualFileSystem(storage=storage)
    outcome: list[BaseException | Result] = []

    def worker() -> None:
        try:
            outcome.append(fs.read("/a.txt"))
        except BaseException as exc:  # the whole point is which exception arrives
            outcome.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert storage.started.wait(timeout=10)
    fs.close()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert _loop_threads() == []
    assert isinstance(outcome[0], concurrent.futures.CancelledError)


@pytest.mark.timeout(60)
def test_the_runner_sweeps_a_task_born_during_shutdown() -> None:
    """A task spawned as the drain cancels its parent outlives the drain; without the runner's sweep the join hangs."""
    storage = RespawningReadStorage()
    fs = VirtualFileSystem(storage=storage)
    outcome: list[BaseException | Result] = []

    def worker() -> None:
        try:
            outcome.append(fs.read("/a.txt"))
        except BaseException as exc:  # the whole point is which exception arrives
            outcome.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert storage.started.wait(timeout=10)
    fs.close()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert _loop_threads() == []
    assert isinstance(outcome[0], concurrent.futures.CancelledError)


def test_close_under_load_on_a_real_storage_returns_cleanly() -> None:
    """The pooled shutdown: in-flight calls are cancelled and gathered before the router closes; close raises nothing.

    Without the drain, the router's close disposes the engine's pool while a worker's call still draws on it,
    and the pool's own error escapes from `close()` in most trials.
    """
    for _ in range(5):
        fs = VirtualFileSystem(storage=InMemoryStorage())
        outcomes: list[Result | BaseException] = []
        served: list[int] = []
        warm = threading.Event()

        def worker(
            fs: VirtualFileSystem = fs,
            outcomes: list[Result | BaseException] = outcomes,
            served: list[int] = served,
            warm: threading.Event = warm,
        ) -> None:
            while True:
                try:
                    result = fs.ls("/")
                except concurrent.futures.CancelledError as exc:
                    outcomes.append(exc)
                    return
                if not result.success:
                    outcomes.append(result)
                    return
                served.append(1)
                if len(served) >= 40:
                    warm.set()

        workers = [threading.Thread(target=worker) for _ in range(4)]
        for thread in workers:
            thread.start()
        assert warm.wait(timeout=30)
        fs.close()
        for thread in workers:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in workers)
        assert len(outcomes) == 4
        for outcome in outcomes:
            if isinstance(outcome, Result):
                assert [error.kind for error in outcome.errors] == [ErrorKind.backend_unavailable]
            else:
                assert isinstance(outcome, concurrent.futures.CancelledError)
        assert _loop_threads() == []


def test_an_interrupt_in_the_waiting_thread_cancels_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Ctrl-C in the notebook must not leave the verb running on the loop behind the user's back."""
    storage = HangingReadStorage()
    futures: list[concurrent.futures.Future[Any]] = []
    real_wait = sync_module._wait

    def interrupted(future: concurrent.futures.Future[Any]) -> Any:
        if not futures:
            futures.append(future)
            raise KeyboardInterrupt
        return real_wait(future)

    monkeypatch.setattr(sync_module, "_wait", interrupted)
    with VirtualFileSystem(storage=storage) as fs:
        with pytest.raises(KeyboardInterrupt):
            fs.read("/a.txt")
        assert futures[0].cancelled()
        assert fs.ls("/").success is True


def test_one_thread_per_facade_not_per_call() -> None:
    with VirtualFileSystem(storage=InMemoryStorage()) as fs:
        [thread] = _loop_threads()
        for _ in range(100):
            assert fs.ls("/").success is True
        assert _loop_threads() == [thread]
    assert _loop_threads() == []


def test_the_management_twins_drive_the_mount_tree() -> None:
    """Each management method reaches the router through the hop and answers or raises as the router does."""
    with VirtualFileSystem(storage=InMemoryStorage()) as fs:
        child = InMemoryStorage(name="child")
        fs.add_mount(child, "/m")
        assert [info.path for info in fs.mounts()] == ["/", "/m"]
        assert fs.locate("/m/x.md")[:5] == ("/m/x.md", "/m", "child", "InMemoryStorage", "/x.md")
        split = fs.locate_edge("/a/x.md", "/m/y.md")
        assert split.same_storage is False
        assert (split.source.mount, split.target.mount) == ("/", "/m")
        fs.remount("/m", permissions="read")
        assert fs.write(path="/m/x.md", content="x").errors[0].kind is ErrorKind.read_only
        binding = fs.unbind("/m")
        assert binding.storage is child
        assert [info.path for info in fs.mounts()] == ["/"]
        fs.bind(child, "/m")
        assert [info.path for info in fs.mounts()] == ["/", "/m"]
        fs.remove_mount("/m")
        assert [info.path for info in fs.mounts()] == ["/"]
        with pytest.raises(ValueError, match="No mount"):
            fs.unbind("/m")


# ---------------------------------------------------------------------------
# Wrapping and the engines
# ---------------------------------------------------------------------------


def test_wrap_serves_a_router_touched_on_another_loop(tmp_path: FsPath) -> None:
    """The SQLite case ruling D27 allows: touched by one loop, then served and closed by the facade's."""
    router = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/wrapped.sqlite"))

    async def touch() -> Result:
        return await router.write(path="/a.txt", content="x")

    assert asyncio.run(touch()).success is True
    fs = VirtualFileSystem.wrap(router)
    assert fs.read("/a.txt").one().content == "x"
    fs.close()
    assert fs.closed is True
    assert _loop_threads() == []
    assert router.mounts() == ()


@pytest.mark.postgres
def test_the_facade_owns_its_asyncpg_loop_beside_the_main_threads_own() -> None:
    """asyncpg binds an engine to the loop that first touches it; the facade's loop is that loop."""
    with server_schema("VFS_TEST_POSTGRES_URL") as (url, schema):
        storage = DatabaseStorage(url=url, schema=schema, embedder=HashEmbeddingProvider())
        with VirtualFileSystem(storage=storage) as fs:
            assert fs.write(path="/a.txt", content="x").success is True

            async def sibling_read() -> str | None:
                rival = DatabaseStorage(url=url, schema=schema, embedder=HashEmbeddingProvider())
                try:
                    return (await rival.read(path=Path("/a.txt"))).one().content
                finally:
                    await rival.close()

            assert asyncio.run(sibling_read()) == "x"
            assert fs.read("/a.txt").one().content == "x"


@pytest.mark.slow
def test_a_ten_thousand_entry_write_costs_what_the_async_path_costs(tmp_path: FsPath) -> None:
    """The hop adds a thread switch per call and no statement; both lists include first touch."""
    entries = [Entry(path=Path(f"/d{i % 100}/f{i}.txt"), content=f"row {i}") for i in range(10_000)]
    sync_storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/sync.sqlite")
    async_storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/async.sqlite")
    counts = {"sync": 0, "async": 0}
    for side, storage in (("sync", sync_storage), ("async", async_storage)):

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(
            conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any, side: str = side
        ) -> None:
            counts[side] += 1

    with VirtualFileSystem(storage=sync_storage) as fs:
        assert fs.write(entries=entries, parents=True).success is True

    async def through_the_router() -> Result:
        router = AsyncVirtualFileSystem(storage=async_storage)
        try:
            return await router.write(entries=entries, parents=True)
        finally:
            await router.close()

    assert asyncio.run(through_the_router()).success is True
    assert counts["sync"] == counts["async"]
    assert counts["sync"] > 0


# ---------------------------------------------------------------------------
# The sync session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(ALL_OPS))
def test_a_sync_session_verb_is_the_facade_call_with_the_authority_filled_in(op: Op) -> None:
    direct_storage, session_storage = RecorderStorage(), RecorderStorage()
    with (
        VirtualFileSystem(storage=direct_storage) as direct,
        VirtualFileSystem(storage=session_storage) as routed,
    ):
        expected = getattr(direct, op)(**CALLS[op], authority=ALICE)
        with routed.session(ALICE) as s:
            assert isinstance(s, Session)
            assert s.authority == ALICE and s.closed is False
            result = getattr(s, op)(**CALLS[op])
    assert result == expected
    assert seen(session_storage) == seen(direct_storage)
    assert all(authority == ALICE for _op, authority in seen(session_storage))


@pytest.mark.parametrize("op", sorted(ALL_OPS))
def test_a_closed_sync_session_refuses_and_dispatches_nothing(op: Op) -> None:
    """One closed fact, held by the wrapped session and read through the twin."""
    storage = RecorderStorage()
    with VirtualFileSystem(storage=storage) as fs:
        with fs.session(ALICE) as s:
            pass
        assert s.closed is True
        assert s._session.closed is True
        result = getattr(s, op)(**CALLS[op])
    assert result.success is False
    assert result.errors[0].kind is ErrorKind.invalid
    assert "closed" in result.errors[0].message
    assert storage.calls == []

    async def the_async_refusal() -> Result:
        router = AsyncVirtualFileSystem(storage=RecorderStorage())
        closed = router.session(ALICE)
        await closed.close()
        return await getattr(closed, op)(**CALLS[op])

    assert result == asyncio.run(the_async_refusal())


def test_sync_closed_is_final() -> None:
    with VirtualFileSystem(storage=RecorderStorage()) as fs:
        s = fs.session(ALICE)
        s.close()
        s.close()
        with pytest.raises(ValueError, match="cannot reopen"), s:
            pass


# ---------------------------------------------------------------------------
# The tree around the facade
# ---------------------------------------------------------------------------


def test_the_management_allowlist_is_owned_by_ops() -> None:
    expected = {"add_mount", "remove_mount", "bind", "unbind", "remount", "close", "locate", "locate_edge"}
    assert frozenset(expected) == MANAGEMENT_METHODS
    assert "MANAGEMENT_METHODS = " not in (REPO / "tests" / "test_ops.py").read_text()


def test_the_facade_is_the_only_thread_hop_in_the_package() -> None:
    hits = sorted(
        str(path.relative_to(REPO))
        for path in (REPO / "src" / "vfs").rglob("*.py")
        if "run_coroutine_threadsafe" in path.read_text() or "threading.Thread(" in path.read_text()
    )
    assert hits == ["src/vfs/sync.py"]


def test_the_reference_page_is_in_the_nav() -> None:
    assert (REPO / "docs" / "reference" / "sync.md").exists()
    nav = (REPO / "mkdocs.yml").read_text()
    assert "- Kernel API (async): reference/api.md" in nav
    assert "- Synchronous face: reference/sync.md" in nav
    assert "- AsyncSession: reference/session.md" in nav


# ---------------------------------------------------------------------------
# The two faces named
# ---------------------------------------------------------------------------

OLD_NAMES = ("SyncVirtualFileSystem", "SyncSession")
TEXT = {".py", ".pyi", ".md", ".yml"}
HEADINGS = {
    "api.md": "# `AsyncVirtualFileSystem`: the kernel's API",
    "sync.md": "# `VirtualFileSystem` and `Session`: the synchronous face",
    "session.md": "# `AsyncSession`",
}


def _first_heading_and_paragraph(page: FsPath) -> tuple[str, str]:
    chunks = [chunk.strip() for chunk in page.read_text().split("\n\n") if chunk.strip()]
    index = next(i for i, chunk in enumerate(chunks) if chunk.startswith("# "))
    return chunks[index], chunks[index + 1]


def test_the_four_names_are_exported_and_the_old_ones_are_gone() -> None:
    assert {"VirtualFileSystem", "AsyncVirtualFileSystem", "Session", "AsyncSession"} <= set(vfs.__all__)
    assert vfs.VirtualFileSystem is VirtualFileSystem and vfs.Session is Session
    assert vfs.AsyncVirtualFileSystem is AsyncVirtualFileSystem and vfs.AsyncSession is AsyncSession
    roots = (REPO / "src" / "vfs", REPO / "docs", REPO / "context" / "standards")
    files = [REPO / "README.md", *(path for root in roots for path in root.rglob("*") if path.suffix in TEXT)]
    stale = sorted(str(path.relative_to(REPO)) for path in files if any(old in path.read_text() for old in OLD_NAMES))
    assert stale == []


def test_the_plain_name_is_the_synchronous_face() -> None:
    assert not inspect.iscoroutinefunction(VirtualFileSystem.read)
    assert inspect.iscoroutinefunction(AsyncVirtualFileSystem.read)
    assert sync_module.VirtualFileSystem is vfs.VirtualFileSystem
    assert vfs.base.AsyncVirtualFileSystem is vfs.AsyncVirtualFileSystem
    package = REPO / "src" / "vfs"
    assert (package / "base.py").exists() and (package / "sync.py").exists()
    assert not (package / "kernel.py").exists() and not (package / "facade.py").exists()


async def test_a_sync_verb_on_a_foreign_running_loop_warns_once_and_serves() -> None:
    """The test's own loop is the foreign one; the notice names the caller's file, then falls silent."""
    with VirtualFileSystem(storage=InMemoryStorage()) as fs, warnings.catch_warnings(record=True) as first:
        warnings.simplefilter("always")
        written = fs.write(path="/a.txt", content="x")
        assert written.success is True
        with warnings.catch_warnings(record=True) as rest:
            warnings.simplefilter("always")
            assert fs.read("/a.txt").success is True
            assert fs.session(ALICE).read("/a.txt").success is True
            fs.locate("/a.txt")
    assert [w.category for w in first] == [RuntimeWarning]
    assert "VirtualFileSystem.write" in str(first[0].message) and "AsyncVirtualFileSystem" in str(first[0].message)
    assert first[0].filename == __file__
    assert rest == []
    with VirtualFileSystem(storage=InMemoryStorage()) as other, warnings.catch_warnings(record=True) as again:
        warnings.simplefilter("always")
        assert other.session(ALICE).ls("/").success is True
    assert [w.category for w in again] == [RuntimeWarning]
    assert "VirtualFileSystem.ls" in str(again[0].message)
    assert again[0].filename == __file__


def test_no_warning_without_a_running_loop() -> None:
    def hundred_reads(fs: VirtualFileSystem) -> list[warnings.WarningMessage]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(100):
                assert fs.read("/a.txt").success is True
        return caught

    with VirtualFileSystem(storage=InMemoryStorage()) as fs:
        assert fs.write(path="/a.txt", content="x").success is True
        assert hundred_reads(fs) == []
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(hundred_reads, fs).result() == []


def test_the_own_loop_refusal_comes_before_the_warning() -> None:
    """A callback on the facade's own loop is refused as today and never reaches the notice."""
    stage = CallbackStage()
    with VirtualFileSystem(rerankers=(stage,)) as fs, warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stage.fs = fs
        fs.add_mount(_mount([_row("/l1", 0.2, "lease")]), "/low")
        fs.add_mount(_mount([_row("/h1", 0.9, "lease")]), "/high")
        assert fs.glean("lease").success is True
    refusal = stage.seen[0]
    assert isinstance(refusal, Result) and refusal.errors[0].kind is ErrorKind.invalid
    assert caught == []


async def test_close_inside_a_running_loop_emits_no_warning() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fs.close()
    assert fs.closed is True
    assert caught == []


def test_the_docs_name_the_two_faces() -> None:
    reference = REPO / "docs" / "reference"
    for name, heading in HEADINGS.items():
        found, paragraph = _first_heading_and_paragraph(reference / name)
        assert found == heading, name
        if name == "api.md":
            assert "AsyncVirtualFileSystem" in paragraph and "VirtualFileSystem" in paragraph
    sync_page = (reference / "sync.md").read_text()
    assert "VirtualFileSystem" in sync_page and "Session" in sync_page
    assert sync_page.count("RuntimeWarning") == 1
    assert "AsyncSession" in (reference / "session.md").read_text()
    readme = (REPO / "README.md").read_text()
    sync_fence = readme.index("VirtualFileSystem(")
    assert "await" not in readme[readme.rfind("```python", 0, sync_fence) : sync_fence]
    assert sync_fence < readme.index("AsyncVirtualFileSystem(")
