"""The search leg against real sqlite rows: scope rungs, the two rounds,
the overlay, records, the two-read protocol, ordering laws and the mask.

Direct backend tests — capability declaration is a router concern, so
these rows call ``storage.search`` straight through the seam. The
overlay serves everything until ``rebuild()`` runs; several rows run
in both worlds because the answer must not depend on which side served.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event, func, select, true
from sqlalchemy.dialects import sqlite

from tests.support.database_helpers import _url, writer_engine
from tests.support.oracles.lexical import pure_overlay_postings, pure_score_blocks
from tests.support.oracles.postings import decode_postings, decode_varints
from tests.support.partial_callers import BOB, SYSTEM, partial_store
from tests.support.statements import is_statistics_statement
from vfs import deadline as deadline_module
from vfs.deadline import WALL_TIME_BUDGET, WALL_TIME_CAUSE
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.models.lexical import OverlayPostings, encode_block, term_weight
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.pattern_matching import ScopeChannel
from vfs.pattern_matching import glob as glob_module
from vfs.results import ErrorKind, Result, Severity
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database import indexing as indexing_module
from vfs.storage.backends.database import lexical as lexical_module
from vfs.storage.backends.database import maintenance as maintenance_module
from vfs.storage.backends.database import scope as scope_module
from vfs.storage.backends.database import search as search_module
from vfs.storage.backends.database.dialects import SQLITE, membership_budget
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.lexical import TermStatistics
from vfs.storage.backends.database.reads import AdmittedScope
from vfs.storage.backends.database.rights import (
    Clause,
    Resolution,
    RightsCache,
    Visibility,
    resolve_authority,
    visibility_clauses,
)
from vfs.storage.backends.database.seams import installed
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import GrantRow

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from vfs.authority import Authority

# The overlay's three SQL legs as SQLite spells them: the body fetch (the
# preview fetch takes the same shape), the surrogate-id fetch and the
# path-ordered nominee fetch.
# A profile with no row constructors in IN, so the tail fetch takes its OR arms over SQLite's compiler.
NO_TUPLES = replace(SQLITE, tuple_in=False)

_BODY_FETCH = re.compile(r"\bFROM vfs_content\b")
_SURROGATE_FETCH = re.compile(r"^SELECT vfs_entries\.entry_id, vfs_entries\.id\s+FROM vfs_entries\b")
_NOMINEE_FETCH = re.compile(r"\bFROM vfs_entries\b.*\bORDER BY vfs_entries\.path\b", re.S)
# The text read of the answer's chunks: the one statement of a lexical search that reads the chunk table.
_CHUNK_FETCH = re.compile(r"\bFROM vfs_chunks\b")
# Any statement that reads the content table, whichever side of a join it stands on.
_CONTENT_READ = re.compile(r"\bvfs_content\b")

CORPUS = {
    "/src/parser.py": "def parse_tokens(stream):\n    return tokens_from(stream)\n",
    "/src/lexer.py": "def lex(stream):\n    tokens = split(stream)\n    return tokens\n",
    "/src/deep/router.py": "def route(request):\n    return dispatch(request)\n",
    "/docs/tokens.md": "Tokens are produced by the lexer and consumed by the parser.\n",
    "/docs/routing.md": "Routing dispatches a request to the mount that owns its path.\n",
    "/notes.txt": "A stream of tokens, tokens, tokens.\n",
}


async def _fresh(tmp_path: Any, files: dict[str, str] | None = None, **kwargs: Any) -> DatabaseStorage:
    storage = DatabaseStorage(url=_url(tmp_path), **kwargs)
    entries = [Entry(path=Path(path), content=body) for path, body in (files or CORPUS).items()]
    assert (await storage.write(entries=entries, parents=True)).success is True
    return storage


async def _indexed(tmp_path: Any, files: dict[str, str] | None = None, **kwargs: Any) -> DatabaseStorage:
    storage = await _fresh(tmp_path, files, **kwargs)
    assert (await storage.rebuild()).success is True
    return storage


def _paths(result: Result) -> list[str]:
    return [str(o.path) for o in result.observations]


class _JudgedSet:
    """A native set wrapped to record each hop's thread, or to report every hop unfinished."""

    def __init__(self, inner: Any, spy: _SetSpy) -> None:
        self._inner = inner
        self._spy = spy

    def judge(self, rows: Sequence[tuple[str, str]], *, budget: float | None) -> tuple[list[int | None], bool]:
        self._spy.threads.append(threading.current_thread().name)
        verdicts, completed = self._inner.judge(rows, budget=budget)
        return verdicts, completed and not self._spy.unfinished


class _SetSpy:
    """Stands in for the pattern layer's ``glob_set``: counts builds, wraps each set."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, unfinished: bool = False) -> None:
        self._real = glob_module.glob_set
        self.builds = 0
        self.threads: list[str] = []
        self.unfinished = unfinished
        monkeypatch.setattr(glob_module, "glob_set", self)

    def __call__(self, programs: Any, groups: Any, *, budget: float | None) -> Any:
        self.builds += 1
        built = self._real(programs, groups, budget=budget)
        return None if built is None else _JudgedSet(built, self)


def _walls(result: Result) -> list[Any]:
    return [error for error in result.errors if WALL_TIME_CAUSE in error.message]


def _scores(result: Result) -> list[float]:
    scores = [o.score for o in result.observations]
    assert all(score is not None for score in scores)
    return [score for score in scores if score is not None]


def _ranked(result: Result) -> list[tuple[str, float | None]]:
    return [(str(o.path), o.score) for o in result.observations]


@contextmanager
def _recorded(storage: DatabaseStorage) -> Iterator[list[str]]:
    """Every statement the store issues inside the block, the planner-statistics step's left out."""
    recorded: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if not is_statistics_statement(statement):
            recorded.append(statement)

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _overlay_legs(statements: Sequence[str]) -> tuple[int, int, int]:
    """``(body fetches, surrogate fetches, nominee fetches)`` among *statements*; a preview fetch is a body fetch."""
    bodies = sum(1 for sql in statements if _BODY_FETCH.search(sql))
    surrogates = sum(1 for sql in statements if _SURROGATE_FETCH.search(sql))
    nominees = sum(1 for sql in statements if _NOMINEE_FETCH.search(sql))
    return bodies, surrogates, nominees


async def _entry_ids(storage: DatabaseStorage, paths: Sequence[str]) -> set[Any]:
    entry = storage._host.tables.entry
    stmt = select(entry.c.entry_id).where(entry.c.path.in_(list(paths)))
    async with storage._host.session_factory() as session:
        return set((await session.execute(stmt)).scalars().all())


def _seen(result: Result) -> tuple[Any, ...]:
    """What a caller observes: paths, order and scores, every error whole, and the search envelope's two exports."""
    extra = result.model_extra or {}
    observed = [(str(o.path), o.score) for o in result.observations]
    errors = [(e.kind, e.severity, e.data, e.message) for e in result.errors]
    return observed, errors, extra.get("lexical_stats"), extra.get("legs")


async def _twenty_folders(tmp_path: Any, readable: Sequence[str], hidden: Sequence[str]) -> DatabaseStorage:
    """bob reads twenty folders ``/f00`` to ``/f19``, indexed, then *readable* and *hidden* written as dirty files."""
    storage = DatabaseStorage(url=_url(tmp_path))
    folders = [f"/f{n:02}" for n in range(20)]
    docs = [Entry(path=Path(f"{folder}/doc.md"), content="plain words\n") for folder in folders]
    assert (await storage.write(entries=docs, parents=True, authority=SYSTEM)).success is True
    assert (await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    for folder in folders:
        granted = await storage.grant(path=Path(folder), principal="bob", level="read", authority=SYSTEM)
        assert granted.success is True, granted.errors
    assert (await storage.rebuild()).success is True
    dirty = [Entry(path=Path(path), content="lantern hidden\n") for path in hidden]
    dirty += [Entry(path=Path(path), content="lantern readable\n") for path in readable]
    assert (await storage.write(entries=dirty, parents=True, authority=SYSTEM)).success is True
    return storage


async def _read_clauses(storage: DatabaseStorage, authority: Authority, parameter_budget: int) -> list[Clause]:
    """*authority*'s compiled read clauses on the store's entries table at *parameter_budget*."""
    host = storage._host
    async with host.session_factory() as session:
        resolved = await resolve_authority(
            session, host.tables, host.profile, host.membership_budget, authority, RightsCache()
        )
    assert isinstance(resolved, Resolution), resolved
    return visibility_clauses(host.tables.entry, resolved.at("read"), host.profile, parameter_budget) or []


async def test_the_backend_answers_search_with_its_own_op_name(tmp_path: Any) -> None:
    # Mutant: leave the answer or the refusal on the old op name.
    storage = await _fresh(tmp_path)
    answer = await storage.search(query="tokens")
    refusal = await storage.search(query="tokens", globs=("a**b",))
    no_term = await storage.search(query="!!!")
    assert answer.success is True and refusal.errors[0].kind == ErrorKind.invalid
    assert answer.ops == refusal.ops == no_term.ops == ("search",)
    await storage.close()


def test_the_wall_budget_is_spelled_search(tmp_path: Any) -> None:
    # Mutant: accept the old keyword as an alias beside the new one.
    with pytest.raises(TypeError, match="glean_wall_seconds"):
        DatabaseStorage(url=_url(tmp_path), glean_wall_seconds=1.0)  # ty: ignore[unknown-argument]
    with pytest.raises(ValueError, match="search_wall_seconds"):
        DatabaseStorage(url=_url(tmp_path), search_wall_seconds=0)


class TestRefusals:
    async def test_a_query_with_no_term_classifies_invalid(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.search(query="!!! ...")
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.invalid
        await storage.close()

    async def test_a_defective_glob_classifies_invalid(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.search(query="tokens", globs=("a**b",))
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.invalid
        await storage.close()

    def test_the_wall_budget_must_be_positive(self, tmp_path: Any) -> None:
        with pytest.raises(ValueError, match="search_wall_seconds"):
            DatabaseStorage(url=_url(tmp_path), search_wall_seconds=0)


class TestRanking:
    async def test_entries_come_best_first_on_a_unit_scale(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert _paths(result)[0] == "/notes.txt"  # three occurrences in a short body
        scores = _scores(result)
        assert scores[0] == 1.0 and scores == sorted(scores, reverse=True)
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert set(_paths(result)) == {"/notes.txt", "/src/lexer.py", "/src/parser.py", "/docs/tokens.md"}
        await storage.close()

    async def test_a_hit_carries_its_chunks_with_bounds_text_and_score(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        [row] = (await storage.search(query="dispatches", limit=1)).observations
        assert str(row.path) == "/docs/routing.md"
        [match] = row.matches or []
        assert (match.start, match.end) == (1, 1)
        assert match.match is None and match.content is not None and "dispatches" in match.content
        assert match.score == row.score == 1.0
        assert {"path", "kind", "version", "score", "matches"} <= row.populated
        await storage.close()

    async def test_a_chunk_hit_carries_a_bolded_preview_inside_its_bounds(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        [row] = (await storage.search(query="Tokens", limit=1, globs=("src/**",))).observations
        for match in row.matches or []:
            assert match.preview is not None and "**tokens**" in match.preview
            assert match.preview_start is not None and match.preview_end is not None
            assert match.start <= match.preview_start <= match.preview_end <= match.end
        await storage.close()

    async def test_a_query_term_absent_from_a_chunk_leaves_its_head_unbolded(self, tmp_path: Any) -> None:
        # Both terms are in the index but only one occurs in the chunk that answers.
        files = {"/a.md": "stream of tokens\n", "/b.md": "a request arrives\nand a stream flows\n"}
        storage = await _indexed(tmp_path, files)
        result = await storage.search(query="tokens request")
        [b] = [o for o in result.observations if str(o.path) == "/b.md"]
        [match] = b.matches or []
        assert match.preview == "a **request** arrives\nand a stream flows"
        await storage.close()

    async def test_a_long_entry_carries_its_best_chunks_with_distinct_bounds(self, tmp_path: Any) -> None:
        sections = (f"## Section {i}\n\nlantern words in section {i}, plain prose sentence.\n\n" for i in range(120))
        storage = await _indexed(tmp_path, {"/doc/big.md": "".join(sections), "/doc/small.md": "no lantern here\n"})
        [row] = (await storage.search(query="lantern", limit=1)).observations
        assert str(row.path) == "/doc/big.md"
        matches = row.matches or []
        assert len(matches) == search_module.TOP_CHUNKS
        bounds = [(m.start, m.end) for m in matches]
        assert len(set(bounds)) == len(bounds) and bounds == sorted(bounds)
        assert matches[0].score == row.score == 1.0
        assert all(m.score is not None and 0.0 < m.score <= 1.0 for m in matches)
        await storage.close()

    async def test_the_limit_counts_entries_and_ties_break_by_path(self, tmp_path: Any) -> None:
        files = {"/b.txt": "same words here\n", "/a.txt": "same words here\n", "/c.txt": "same words here\n"}
        storage = await _indexed(tmp_path, files)
        result = await storage.search(query="same words", limit=2)
        assert _paths(result) == ["/a.txt", "/b.txt"]
        assert [o.score for o in result.observations] == [1.0, 1.0]
        await storage.close()

    async def test_columns_narrow_the_mask_and_identity_stays(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        [row] = (await storage.search(query="dispatches", limit=1, columns=frozenset({"path"}))).observations
        assert row.populated == {"path", "kind", "version", "score", "matches"}
        assert row.size_bytes is None
        await storage.close()

    async def test_term_statistics_ride_the_envelope(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.search(query="tokens unknownword")
        export = result.lexical_stats  # ty: ignore[unresolved-attribute]
        assert export["n_docs"] == len(CORPUS) and export["avg_dl"] > 0
        assert set(export["terms"]) == {"tokens"} and export["terms"]["tokens"]["df"] == 4
        await storage.close()

    async def test_an_indexed_term_absent_from_the_corpus_answers_empty(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.search(query="unknownword")
        assert result.success is True and result.observations == []
        await storage.close()


class TestScope:
    async def test_globs_take_the_narrow_rung(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = await _indexed(tmp_path)
        narrowed: list[int] = []
        real = search_module.chunk_ids_for

        async def spying(session, tables, epoch, doc_ids, profile, budget):
            narrowed.append(len(doc_ids))
            return await real(session, tables, epoch, doc_ids, profile, budget)

        monkeypatch.setattr(search_module, "chunk_ids_for", spying)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert set(_paths(result)) == {"/src/lexer.py", "/src/parser.py"}
        assert narrowed == [4]  # the segment index nominated the src entries, the deep directory among them
        await storage.close()

    async def test_a_wide_scope_takes_the_probe_rung_and_answers_identically(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        narrow = await storage.search(query="tokens", globs=("src/**",))
        monkeypatch.setattr(search_module, "SCOPE_ID_BUDGET", 1)
        narrowed: list[int] = []
        monkeypatch.setattr(search_module, "chunk_ids_for", lambda *a: narrowed.append(1))
        wide = await storage.search(query="tokens", globs=("src/**",))
        assert narrowed == []  # over the budget: no allow-list resolution
        assert _paths(wide) == _paths(narrow) and wide.errors == narrow.errors
        assert [o.score for o in wide.observations] == [o.score for o in narrow.observations]
        await storage.close()

    async def test_exclusions_and_ext_gate_every_row(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        assert set(_paths(await storage.search(query="tokens", globs_not=("src/**",)))) == {
            "/notes.txt",
            "/docs/tokens.md",
        }
        assert _paths(await storage.search(query="tokens", ext=("md",))) == ["/docs/tokens.md"]
        assert _paths(await storage.search(query="tokens", ext_not=("py", "md"))) == ["/notes.txt"]
        await storage.close()

    async def test_a_glob_contradicting_the_ext_channel_answers_empty_in_both_worlds(self, tmp_path: Any) -> None:
        # Every gate derives ``py`` while the channel wants ``md``: the
        # scan has no live arm and the index side has no admitted row.
        storage = await _fresh(tmp_path)
        for _world in ("overlay", "indexed"):
            result = await storage.search(query="tokens", globs=("*.py",), ext=("md",))
            assert result.success is True and result.observations == []
            assert (await storage.rebuild()).success is True
        await storage.close()

    async def test_the_meta_subtree_is_hidden_unless_addressed(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, {"/a.txt": "tokens here\n"})
        assert (
            await storage.write(entries=[Entry(path=Path("/.vfs/hidden.txt"), content="tokens too\n")], parents=True)
        ).success
        assert (await storage.rebuild()).success is True
        assert _paths(await storage.search(query="tokens")) == ["/a.txt"]
        assert _paths(await storage.search(query="tokens", globs=("/.vfs/**",))) == ["/.vfs/hidden.txt"]
        await storage.close()

    async def test_piped_rows_admit_their_own_paths(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        rows = (await storage.search(query="tokens", globs=("docs/**", "notes.txt"))).observations
        piped = await storage.search(query="tokens", observations=rows[:1])
        assert _paths(piped) == [str(rows[0].path)]
        await storage.close()

    async def test_the_same_scope_answers_identically_before_and_after_rebuild(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        before = await storage.search(query="tokens", globs=("src/**",))
        assert (await storage.rebuild()).success is True
        after = await storage.search(query="tokens", globs=("src/**",))
        assert _paths(before) == _paths(after) == ["/src/lexer.py", "/src/parser.py"]
        await storage.close()

    @pytest.mark.parametrize(
        ("arms", "composed", "pattern_arms"), [(20, 200, 200), (21, None, 0)], ids=["10-20", "10-21"]
    )
    async def test_the_prefilter_plan_switches_on_the_product(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, arms: int, composed: int | None, pattern_arms: int
    ) -> None:
        """Guards: search choosing its prefilter apart from the one answer
        ``AdmittedScope.composed`` gives every verb, the overlay's fetch left
        without the composed arms (so a scope beside an entry-wide glob loses
        every unindexed row beneath its roots), or either plan losing a scoped
        row before or after the index is built."""
        files = {"/d00/x.e00": "tokens here\n", "/d00/x.zz": "tokens there\n", "/e/x.e00": "tokens elsewhere\n"}
        storage = await _fresh(tmp_path, files)
        answers: list[int | None] = []
        real = AdmittedScope.composed

        def spied(self: AdmittedScope, *, trashed: bool) -> tuple[str, ...] | None:
            answer = real(self, trashed=trashed)
            answers.append(None if answer is None else len(answer))
            return answer

        built: list[Any] = []
        real_arm = scope_module.pattern_arm

        def counted(*args: Any, **kwargs: Any) -> Any:
            built.append(args)
            return real_arm(*args, **kwargs)

        monkeypatch.setattr(AdmittedScope, "composed", spied)
        monkeypatch.setattr(scope_module, "pattern_arm", counted)
        scope = ScopeChannel(
            roots=tuple(Path(f"/d{i:02}") for i in range(10)), arms=tuple(f"*.e{i:02}" for i in range(arms))
        )
        # Never rebuilt yet: the overlay serves the call and builds the scan side's prefilter.
        assert _paths(await storage.search(query="tokens", scope=scope)) == ["/d00/x.e00"]
        assert len(built) == pattern_arms
        beside = await storage.search(query="tokens", globs=("/d00",), scope=scope)
        assert _paths(beside) == ["/d00/x.e00"]
        assert (await storage.rebuild()).success is True
        assert _paths(await storage.search(query="tokens", scope=scope)) == ["/d00/x.e00"]
        assert answers == [composed, composed, composed]
        await storage.close()


class TestRounds:
    async def test_a_term_past_the_head_blocks_is_fetched_by_key_in_round_two(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 140 docs share ``common`` (two blocks); the anchor sits in the
        # second block, so a one-block head cannot answer without round two.
        files = {f"/c/{i:04}.txt": f"common word number {i}\n" + ("anchor\n" if i == 130 else "") for i in range(140)}
        storage = await _indexed(tmp_path, files)
        reference = await storage.search(query="common anchor", limit=5)
        assert _paths(reference)[0] == "/c/0130.txt"
        wanted: list[dict[str, list[int]]] = []
        real = lexical_module.tail_block_statements

        def spying(postings, asked, *rest):
            wanted.append({term: list(nos) for (_epoch, term), nos in asked.items()})
            return real(postings, asked, *rest)

        monkeypatch.setattr(lexical_module, "tail_block_statements", spying)
        monkeypatch.setattr(lexical_module, "HEAD_BLOCKS", 1)
        result = await storage.search(query="common anchor", limit=5)
        assert wanted == [{"common": [1]}]  # one term wanting one block: the second block of ``common``
        assert [(str(o.path), o.score) for o in result.observations] == [
            (str(o.path), o.score) for o in reference.observations
        ]
        await storage.close()

    async def test_the_tail_fetch_returns_every_terms_blocks_under_statistics(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two terms of 300 documents (three blocks each), the anchor in each
        # term's last block, the later-sorting term asked first.
        files = {f"/z/{i:04}.txt": f"zeta word {i}\n" + ("anchor\n" if i == 290 else "") for i in range(300)}
        files |= {f"/a/{i:04}.txt": f"alpha word {i}\n" + ("anchor\n" if i == 290 else "") for i in range(300)}
        storage = await _indexed(tmp_path, files)
        async with writer_engine(storage._host.engine).begin() as conn:
            await conn.exec_driver_sql("ANALYZE")
            stat_rows = (await conn.exec_driver_sql("SELECT count(*) FROM sqlite_stat1")).scalar_one()
        assert stat_rows > 0
        selected: list[list[int]] = []
        scored: list[list[int]] = []
        real_select, real_score = lexical_module.select_blocks, lexical_module.score_blocks

        def recording_select(*args: Any, **kwargs: Any) -> Any:
            chosen = real_select(*args, **kwargs)
            selected.extend([no for no in competing if no >= lexical_module.HEAD_BLOCKS] for competing in chosen)
            return chosen

        def counting_score(blocks: Any, *args: Any, **kwargs: Any) -> Any:
            scored.append([block.term for block in blocks])
            return real_score(blocks, *args, **kwargs)

        monkeypatch.setattr(lexical_module, "select_blocks", recording_select)
        monkeypatch.setattr(lexical_module, "score_blocks", counting_score)
        monkeypatch.setattr(lexical_module, "HEAD_BLOCKS", 1)
        result = await storage.search(query="zeta alpha anchor", limit=5)
        assert result.success is True
        assert [len(tail) for tail in selected] == [2, 2]
        head, full = scored[0], scored[1]
        beyond_head = Counter(full)
        beyond_head.subtract(Counter(head))
        fetched = sum(beyond_head.values())
        assert sum(map(len, selected)) - fetched == 0  # every wanted block was scored
        assert beyond_head == Counter({0: 2, 1: 2})
        await storage.close()


class TestProbes:
    async def test_a_wide_rung_that_runs_short_deepens_then_records(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(search_module, "FUSION_K", 1)
        monkeypatch.setattr(search_module, "PROBE_DEEPEN", 1)
        result = await storage.search(query="tokens", limit=10)
        assert result.success is True
        [record] = [e for e in result.errors if e.severity == Severity.warning]
        assert record.kind == ErrorKind.truncated and record.severity == Severity.warning
        assert record.data == {"window": 1, "found": 1}
        assert "scope probe budget" in record.message
        await storage.close()

    async def test_a_narrow_rung_with_a_full_window_records_it(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(search_module, "FUSION_K", 1)
        result = await storage.search(query="tokens", limit=3, globs=("src/**",))
        [record] = [e for e in result.errors if e.severity == Severity.warning]
        assert "candidate window" in record.message and record.data == {"window": 1, "found": 1}
        await storage.close()

    def test_round_two_arms_pack_under_the_parameter_budget(self) -> None:
        arms = [(3, true()), (3, true()), (5, true()), (2, true())]
        packed = lexical_module._packed_arms(arms, 6)
        assert [len(statement) for statement in packed] == [2, 1, 1]
        assert lexical_module._packed_arms([], 6) == []

    def test_the_tail_fetch_takes_the_tuple_form_where_declared(self) -> None:
        postings = build_vfs_tables().lex_postings
        wanted = {(1, "the"): [8, 9, 10], (1, "is"): [8, 9, 10, 11]}

        def compiled(profile: Any, dialect: Any, budget: int) -> list[tuple[str, int]]:
            statements = lexical_module.tail_block_statements(postings, wanted, profile, budget)
            rendered = [s.compile(dialect=dialect, compile_kwargs={"render_postcompile": True}) for s in statements]
            return [(str(c), len(c.params)) for c in rendered]

        # Each slot's block is one (epoch, term, block_no) triple, three binds, a third of the budget a statement.
        tuple_form = compiled(SQLITE, sqlite.dialect(), 7)
        assert [binds // 3 for _, binds in tuple_form] == [2, 2, 2, 1]
        assert all("IN (VALUES" in text and " OR " not in text for text, _ in tuple_form)
        # The arms pack under the membership budget, which nets the reserve, never the whole parameter budget.
        arms = compiled(NO_TUPLES, sqlite.dialect(), 8)
        assert [binds for _, binds in arms] == [5, 6]
        assert all(" OR " not in text and "VALUES" not in text for text, _ in arms)
        [(packed, binds)] = compiled(NO_TUPLES, sqlite.dialect(), 16)
        assert binds == 11 and " OR " in packed and "VALUES" not in packed

    def test_the_tail_fetch_keeps_the_reserve_under_a_tight_budget(self) -> None:
        """Guards: the ``OR`` arms packed to the whole parameter budget, leaving the driver's reserve no room."""
        postings = build_vfs_tables().lex_postings
        wanted = {(epoch, term): list(range(40)) for epoch in range(1, 97) for term in ("heron", "kestrel")}
        budget = membership_budget(NO_TUPLES, 2_099)
        statements = lexical_module.tail_block_statements(postings, wanted, NO_TUPLES, budget)
        compile_kwargs = {"render_postcompile": True}
        binds = [len(s.compile(dialect=sqlite.dialect(), compile_kwargs=compile_kwargs).params) for s in statements]
        assert sum(binds) == 96 * 2 * 42 and all(count <= budget for count in binds), (budget, binds)


class TestOverlay:
    async def test_a_never_indexed_store_serves_from_live_text(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert _paths(result)[0] == "/notes.txt"
        [match] = result.observations[0].matches or []
        assert (match.start, match.end, match.content) == (1, 1, None)
        # The overlay's preview is cut from the live body, read once more for the entries that answer — no chunk row.
        assert match.preview == "A stream of **tokens**, **tokens**, **tokens**."
        assert (match.preview_start, match.preview_end) == (1, 1)
        assert result.lexical_stats["n_docs"] == 0  # ty: ignore[unresolved-attribute]
        await storage.close()

    async def test_a_written_file_with_a_new_word_is_found_before_rebuild(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="zebra tokens\n")])).success
        result = await storage.search(query="zebra")
        assert _paths(result) == ["/fresh.txt"]
        # The overlay and the index share one scale: the fresh row ranks among indexed rows.
        mixed = await storage.search(query="tokens")
        assert "/fresh.txt" in _paths(mixed) and mixed.observations[0].score == 1.0
        await storage.close()

    async def test_a_dirty_row_out_of_scope_leaves_the_overlay_empty(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/docs/fresh.md"), content="tokens late\n")])).success
        admitted_sizes: list[int] = []
        real = search_module._overlay

        async def spying(session, tables, profile, budget, executor, admitted, terms, stats, deadline):
            admitted_sizes.append(len(admitted))
            return await real(session, tables, profile, budget, executor, admitted, terms, stats, deadline)

        monkeypatch.setattr(search_module, "_overlay", spying)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert set(_paths(result)) == {"/src/lexer.py", "/src/parser.py"}
        assert admitted_sizes == [0]  # the scan ran and nominated nothing in scope
        await storage.close()

    def test_the_overlay_reads_the_shared_scan_tier_budget(self) -> None:
        """Guards: either verb cutting the dirty rows at a count of its own, or holding a budget name of its own
        for the scan tier beside the shared one."""
        assert scope_module.SCAN_TIER_BUDGET == 25_000
        assert search_module.SCAN_TIER_BUDGET == grep_module.SCAN_TIER_BUDGET == scope_module.SCAN_TIER_BUDGET
        shared = {"SCAN_TIER_BUDGET", "CONTENT_BYTE_BUDGET", "WALL_TIME_BUDGET"}
        search_budgets = {name for name in vars(search_module) if name.endswith("_BUDGET")}
        grep_budgets = {name for name in vars(grep_module) if name.endswith("_BUDGET")}
        assert search_budgets == shared | {"SCOPE_ID_BUDGET"}
        assert grep_budgets == shared | {"POSTING_BYTE_BUDGET"}

    async def test_the_overlay_budget_truncates_loudly(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = await _fresh(tmp_path)
        monkeypatch.setattr(search_module, "SCAN_TIER_BUDGET", 2)
        result = await storage.search(query="tokens")
        assert result.success is True
        [record] = [e for e in result.errors if e.severity == Severity.warning]
        assert record.kind == ErrorKind.truncated and record.data == {"scanned": 2, "budget": 2}
        await storage.close()

    async def test_two_stores_that_differ_only_in_hidden_dirty_rows_answer_alike(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the scan tier cut before the caller's view, so dirty rows it cannot read take the cut's places
        and move its record; the mutant is the packed group left out of the scan-tier statement."""
        monkeypatch.setattr(search_module, "SCAN_TIER_BUDGET", 2)
        alone, beside = await partial_store(0), await partial_store(5)
        try:
            answers = [await store.search(query="lantern", authority=BOB) for store in (alone, beside)]
        finally:
            await alone.close()
            await beside.close()
        assert answers[0].success is True, answers[0].errors
        assert {"/pub/fresh0.md", "/pub/fresh1.md"} <= set(_paths(answers[0]))
        assert _seen(answers[1]) == _seen(answers[0])

    async def test_a_widened_clause_never_serves_a_hidden_dirty_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards: the view's check dropped from the scan tier's rows, so a pushdown that admits too much is
        trusted; the clause is widened to admit every row, and the authority must still hold."""
        storage = await partial_store(5)
        monkeypatch.setattr(Visibility, "clauses", lambda _self, entry=None: [Clause(true(), 0)])
        try:
            result = await storage.search(query="lantern", authority=BOB)
        finally:
            await storage.close()
        assert result.success is True, result.errors
        assert sorted(_paths(result)) == ["/pub/fresh0.md", "/pub/fresh1.md", "/pub/indexed.md"]

    async def test_a_fanned_view_keeps_every_readable_dirty_row(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: hidden dirty rows ahead of a caller whose rights fan into several packed groups; the mutants are
        the packed group left out of the statement, and the group loop stopping after its first group."""
        readable = [f"/f{n:02}/r.md" for n in range(3)]
        storage = await _twenty_folders(tmp_path, readable, [f"/a{n}/h.md" for n in range(5)])
        monkeypatch.setattr(search_module, "SCAN_TIER_BUDGET", 3)
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda _self: 56))
        with _recorded(storage) as statements:
            result = await storage.search(query="lantern", authority=BOB)
        assert result.success is True, result.errors
        assert sorted(_paths(result)) == readable
        assert [e.data for e in result.errors if e.kind == ErrorKind.truncated] == []
        # At 56 binds the depth half of the packing cap (936) is wider than the bind half.
        groups = scope_module._packed(await _read_clauses(storage, BOB, 56), 56 // 2)
        assert len(groups) > 1
        assert sum("unlikely(" in statement for statement in statements) == len(groups)
        await storage.close()

    async def test_a_fanned_views_merge_keeps_the_window_that_reports_its_overflow(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the merge across a fanned caller's packed groups pruned to the lowest ``limit`` paths, not
        ``limit + 1``, so readable rows past the cut vanish and no truncation record says so.

        Each readable dirty file sits under a folder another group admits, so
        no one statement overflows and only the merged window can.
        """
        readable = ["/f00/r.md", "/f06/r.md", "/f12/r.md", "/f18/r.md"]
        storage = await _twenty_folders(tmp_path, readable, [])
        monkeypatch.setattr(search_module, "SCAN_TIER_BUDGET", 2)
        monkeypatch.setattr(grep_module, "SCAN_TIER_BUDGET", 2)
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda _self: 56))
        searched = await storage.search(query="lantern", authority=BOB)
        grepped = await storage.grep(pattern="lantern", authority=BOB)
        await storage.close()
        assert sorted(_paths(searched)) == readable[:2]
        assert [e.data for e in searched.errors if e.kind == ErrorKind.truncated] == [{"scanned": 2, "budget": 2}]
        assert _paths(grepped) == readable[:2]
        truncated = [e.data for e in grepped.errors if e.kind == ErrorKind.truncated]
        assert truncated == [{"scanned": 2, "index": 0, "budget": 2}]

    async def test_the_kernel_overlay_scores_as_the_oracle_does(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the kernel counting a term, a length or a body differently from tokenize-and-count,
        or the batched postings scoring differently from one pass over every body."""
        indexed = {
            "/idx/a.txt": "tokens of the parser stream\n",
            "/idx/b.txt": "a lexer stream\n",
            "/idx/c.txt": "tokens tokens everywhere\n",
        }
        storage = await _indexed(tmp_path, indexed)
        bodies = [f"{'tokens ' * (i % 4)}stream number {i} {'parser ' * (i % 3)}\n" for i in range(12)]
        dirty = [Entry(path=Path(f"/dirty/{i:02}.txt"), content=body) for i, body in enumerate(bodies)]
        assert (await storage.write(entries=dirty, parents=True)).success is True
        kernel = await storage.search(query="tokens parser stream", limit=20)
        assert kernel.success is True and len(kernel.observations) == 15

        def counted(docs: Any, terms: Any, *, budget: float | None) -> OverlayPostings:
            return pure_overlay_postings(docs, terms)

        monkeypatch.setattr(search_module, "overlay_postings", counted)
        monkeypatch.setattr(search_module, "score_blocks", pure_score_blocks)
        monkeypatch.setattr(lexical_module, "score_blocks", pure_score_blocks)
        oracle = await storage.search(query="tokens parser stream", limit=20)
        assert _ranked(kernel) == _ranked(oracle)
        await storage.close()

    async def test_the_overlay_fetches_bodies_in_byte_batches(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: every admitted body fetched in one statement whatever the byte budget,
        or a batch's surrogate ids fetched for the whole overlay at once."""
        files = {f"/d/{i}.txt": f"tokens body number {i}\n" for i in range(5)}
        storage = await _fresh(tmp_path, files)
        with _recorded(storage) as whole:
            reference = await storage.search(query="tokens")
        assert len(reference.observations) == 5
        # One nominee fetch, one surrogate fetch, one body fetch, plus the preview fetch.
        assert _overlay_legs(whole) == (2, 1, 1)
        monkeypatch.setattr(search_module, "CONTENT_BYTE_BUDGET", len(files["/d/0.txt"].encode()))
        with _recorded(storage) as batched:
            result = await storage.search(query="tokens")
        # One body and one surrogate fetch per batch of one, plus the preview; the nominee fetch stays one.
        assert _overlay_legs(batched) == (6, 5, 1)
        assert _ranked(result) == _ranked(reference)
        await storage.close()

    async def test_overlay_previews_come_from_one_bounded_fetch_of_the_answer(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the overlay keeping bodies past its batch, or the preview fetch reading
        every scored body instead of the entries in the answer."""
        files = {
            "/d/a.txt": "tokens tokens tokens\n",
            "/d/b.txt": "tokens tokens filler\n",
            "/d/c.txt": "tokens filler filler\n",
            "/d/d.txt": "nothing here\n",
            "/d/e.txt": "other words\n",
        }
        storage = await _fresh(tmp_path, files)
        returned: list[Any] = []
        real_overlay = search_module._overlay

        async def spying_overlay(*args: Any) -> Any:
            outcome = await real_overlay(*args)
            returned.append(outcome)
            return outcome

        fetched: list[list[Any]] = []
        real_fetch = search_module.content_for_entries

        async def spying_fetch(session, tables, profile, membership_budget, entry_ids):
            fetched.append(list(entry_ids))
            return await real_fetch(session, tables, profile, membership_budget, entry_ids)

        monkeypatch.setattr(search_module, "_overlay", spying_overlay)
        monkeypatch.setattr(search_module, "content_for_entries", spying_fetch)
        result = await storage.search(query="tokens", limit=2)
        assert _paths(result) == ["/d/a.txt", "/d/b.txt"]
        [(hits, completed)] = returned
        assert completed is True and set(hits) == await _entry_ids(storage, ["/d/a.txt", "/d/b.txt", "/d/c.txt"])
        assert all(isinstance(hit, search_module._Hit) for hit in hits.values())
        counted, previewed = fetched
        assert len(counted) == 5
        assert set(previewed) == await _entry_ids(storage, ["/d/a.txt", "/d/b.txt"])
        await storage.close()

    async def test_no_preview_fetch_when_the_overlay_does_not_answer(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a preview fetch issued for an answer that holds no overlay entry."""
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="nothing here\n")])).success
        fetched: list[list[Any]] = []
        real_fetch = search_module.content_for_entries

        async def spying_fetch(session, tables, profile, membership_budget, entry_ids):
            fetched.append(list(entry_ids))
            return await real_fetch(session, tables, profile, membership_budget, entry_ids)

        monkeypatch.setattr(search_module, "content_for_entries", spying_fetch)
        result = await storage.search(query="tokens")
        assert set(_paths(result)) == {"/notes.txt", "/src/lexer.py", "/src/parser.py", "/docs/tokens.md"}
        assert [len(ids) for ids in fetched] == [1]  # the dirty row was counted; nothing was previewed
        await storage.close()

    async def test_an_overlay_entry_purged_before_the_preview_read_is_absent(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a body missing from the preview read raising out of the call instead of leaving its
        entry absent, as grep leaves a body that did not come back."""
        files = {
            "/d/a.txt": "tokens tokens tokens\n",
            "/d/b.txt": "tokens tokens filler\n",
            "/d/c.txt": "tokens filler filler\n",
        }
        storage = await _fresh(tmp_path, files)
        real_fetch = search_module.content_for_entries
        calls = {"n": 0}

        async def purged_before_the_preview(session, tables, profile, membership_budget, entry_ids):
            calls["n"] += 1
            bodies = await real_fetch(session, tables, profile, membership_budget, entry_ids)
            if calls["n"] == 2:  # the preview read: the best entry's body is gone
                bodies.pop(next(iter(entry_ids)))
            return bodies

        monkeypatch.setattr(search_module, "content_for_entries", purged_before_the_preview)
        result = await storage.search(query="tokens", limit=2)
        assert result.success is True, result.errors
        assert calls["n"] == 2
        assert _paths(result) == ["/d/b.txt"]
        await storage.close()

    async def test_a_rival_publish_between_the_reads_is_redriven(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        moves = {"n": 0}

        async def rival() -> None:
            if moves["n"] == 0:
                moves["n"] += 1
                assert (await storage.rebuild()).success is True

        with installed("search:after-pointer-read", rival):
            result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert "/fresh.txt" in _paths(result) and moves["n"] == 1
        await storage.close()

    async def test_an_empty_overlay_verdict_is_reverified_after_the_fetch(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The race shape: the advisory read misses a fresh row the
        # authoritative read sees, and the overlay serves it mid-call.
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        real = search_module.pointer_with_overlay
        calls = {"n": 0}

        async def blind_preamble(session, tables):
            calls["n"] += 1
            snapshot = await real(session, tables)
            return snapshot._replace(overlay_empty=True) if calls["n"] == 1 else snapshot

        real_epoch = search_module.current_generation
        epoch_calls = {"n": 0}

        async def counting_epoch(session, tables):
            epoch_calls["n"] += 1
            return await real_epoch(session, tables)

        monkeypatch.setattr(search_module, "pointer_with_overlay", blind_preamble)
        monkeypatch.setattr(search_module, "current_generation", counting_epoch)
        result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert "/fresh.txt" in _paths(result)
        assert calls["n"] == 2  # advisory, then authoritative
        assert epoch_calls["n"] == 1  # a rescued verdict is never skip-verified
        await storage.close()

    async def test_a_pointer_that_never_settles_classifies_conflict(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)  # the classification is pinned, not the backoff
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        real = search_module.current_generation
        calls = {"n": 0}

        async def always_moving(session, tables):
            calls["n"] += 1
            return (await real(session, tables)) + calls["n"]

        monkeypatch.setattr(search_module, "current_generation", always_moving)
        result = await storage.search(query="tokens")
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.conflict and result.errors[0].retryable is True
        assert result.errors[0].message.endswith("the index generation moved mid-search"), result.errors[0].message
        await storage.close()

    def test_overlay_blocks_take_counted_postings_and_local_statistics(self) -> None:
        """Guards: a block encoded in arrival order (path order) rather than doc-id order,
        or the local statistics counted over anything but the bodies the kernel reached."""
        assert search_module._text(b"alpha beta") == search_module._text("alpha beta") == "alpha beta"
        # Two bodies, "alpha beta" (id 1) and "beta beta gamma" (id 2), counted in reverse path order.
        counted = search_module._OverlayCount([[(2, 2, 3), (1, 1, 2)], []], 2, 5)
        blocks, idfs, avg_dl = search_module._overlay_blocks(
            counted, ["beta", "delta"], TermStatistics({}, 0, 0.0, 1.2, 0.75, {})
        )
        assert [block.term for block in blocks] == [0]  # delta occurs nowhere: no block
        assert blocks[0].doc_ids == encode_block([1, 2], [1, 2], [2, 3])[0]
        assert avg_dl == 2.5 and idfs[0] == pytest.approx(0.1823, abs=1e-3)
        assert idfs[1] > idfs[0]  # the rarer term (absent) takes the higher idf
        nothing = search_module._OverlayCount([[]], 0, 0)
        stats = TermStatistics({}, 0, 0.0, 1.2, 0.75, {})
        blocks, idfs, avg_dl = search_module._overlay_blocks(nothing, ["beta"], stats)
        assert blocks == [] and avg_dl == 0.0 and len(idfs) == 1

    async def test_an_overlay_hit_spans_its_whole_body_and_previews_the_best_window(self, tmp_path: Any) -> None:
        body = "".join(f"line {i} of prose\n" for i in range(1, 9)) + "the lantern line\nlast line\n"
        storage = await _fresh(tmp_path, {"/fresh.md": body})
        [row] = (await storage.search(query="lantern")).observations
        [match] = row.matches or []
        assert (match.start, match.end, match.content) == (1, 10, None)
        assert match.preview is not None and match.preview.endswith("line 8 of prose\nthe **lantern** line")
        assert (match.preview_start, match.preview_end) == (6, 9)  # the earliest window holding the hit
        await storage.close()


class TestBudgets:
    async def test_an_expired_wall_budget_truncates_and_skips_the_overlay(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, search_wall_seconds=1e-9)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        result = await storage.search(query="tokens")
        assert result.success is True
        assert any("wall-time budget" in e.message for e in result.errors)
        assert "/fresh.txt" not in _paths(result)
        await storage.close()

    async def test_search_gates_judge_on_the_process_pool(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards: the gates built once per hop, or judged off the process pool."""
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/src/fresh.py"), content="tokens late\n")])).success
        spy = _SetSpy(monkeypatch)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert "/src/fresh.py" in _paths(result) and "/src/lexer.py" in _paths(result)
        assert spy.builds == 1 and len(spy.threads) >= 2
        assert all(name.startswith("vfs-offload") for name in spy.threads), spy.threads
        await storage.close()

    async def test_an_unfinished_gate_judgement_truncates_once(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: an unfinished judgement recorded once per hop, or not at all."""
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/src/fresh.py"), content="tokens late\n")])).success
        spy = _SetSpy(monkeypatch, unfinished=True)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert len(spy.threads) >= 2
        [wall] = _walls(result)
        assert (wall.kind, wall.severity) == (ErrorKind.truncated, Severity.warning)
        await storage.close()

    async def test_an_expired_wall_and_an_unfinished_judgement_record_once(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the wall's two sites each appending their own record."""
        storage = await _indexed(tmp_path, search_wall_seconds=1e-9)
        _SetSpy(monkeypatch, unfinished=True)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert result.success is True
        assert len(_walls(result)) == 1
        await storage.close()

    async def test_an_unfinished_chunk_entry_judgement_records_the_wall(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the chunk entries' completion flag ignored: a fully indexed call makes no overlay hop."""
        storage = await _indexed(tmp_path)
        spy = _SetSpy(monkeypatch, unfinished=True)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert spy.threads and "/src/lexer.py" in _paths(result)
        assert len(_walls(result)) == 1
        await storage.close()

    async def test_an_unfinished_overlay_judgement_records_the_wall(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the overlay's completion flag ignored: a never-indexed store judges only there."""
        storage = await _fresh(tmp_path)
        spy = _SetSpy(monkeypatch, unfinished=True)
        result = await storage.search(query="tokens", globs=("src/**",))
        assert len(spy.threads) == 1 and "/src/lexer.py" in _paths(result)
        assert len(_walls(result)) == 1
        await storage.close()

    @pytest.mark.parametrize("scope", [{"globs": ("src/**",)}, {"globs_not": ("*.md",)}], ids=["allow", "wide"])
    async def test_an_unfinished_vector_judgement_records_the_wall(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, scope: dict[str, Any]
    ) -> None:
        """Guards: the vector leg's completion flag ignored, on its allow-list branch or its probe loop,
        or its record dropped: terms the index never saw leave the vector leg the only one judging."""
        storage = await _indexed(tmp_path, embedder=HashEmbeddingProvider())
        spy = _SetSpy(monkeypatch, unfinished=True)
        result = await storage.search(query="zebra quantum", **scope)
        assert spy.threads and _paths(result)
        assert len(_walls(result)) == 1
        await storage.close()

    async def test_a_wall_inside_the_overlay_hop_records_once_and_keeps_what_was_reached(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the kernel's completion flag ignored, a stopped batch's postings dropped,
        or the wall recorded once per batch instead of once per call."""
        storage = await _indexed(tmp_path)
        dirty = [
            Entry(path=Path("/dirty/a.txt"), content="tokens early\n"),
            Entry(path=Path("/dirty/b.txt"), content="tokens later\n"),
        ]
        assert (await storage.write(entries=dirty, parents=True)).success is True
        real = search_module.overlay_postings
        budgets: list[float | None] = []

        def stopping(docs: Any, terms: Any, *, budget: float | None) -> OverlayPostings:
            budgets.append(budget)
            counted = real(docs[:1], terms, budget=budget)
            return OverlayPostings(counted.postings, 1, counted.total_dl, False)

        monkeypatch.setattr(search_module, "overlay_postings", stopping)
        result = await storage.search(query="tokens")
        assert result.success is True
        # The hop's budget is the wall's remainder cut at worker start, never unbounded.
        [budget] = budgets
        assert budget is not None and 0.0 <= budget <= WALL_TIME_BUDGET
        [wall] = _walls(result)
        assert (wall.kind, wall.severity, wall.data) == (ErrorKind.truncated, Severity.warning, None)
        indexed = {"/notes.txt", "/src/lexer.py", "/src/parser.py", "/docs/tokens.md"}
        assert set(_paths(result)) == indexed | {"/dirty/a.txt"}
        await storage.close()

    async def test_a_wall_between_overlay_batches_records_once_and_keeps_the_batches_counted(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the deadline unread between batches, so an expired call keeps fetching bodies,
        or the batches counted before the wall dropped from the answer."""
        files = {f"/d/{i}.txt": f"tokens body number {i}\n" for i in range(5)}
        storage = await _fresh(tmp_path, files)
        monkeypatch.setattr(search_module, "CONTENT_BYTE_BUDGET", len(files["/d/0.txt"].encode()))
        real_clock, real_kernel = deadline_module.monotonic, search_module.overlay_postings
        skew = {"seconds": 0.0}

        def skewed_clock() -> float:
            return real_clock() + skew["seconds"]

        def counting_kernel(docs: Any, terms: Any, *, budget: float | None) -> OverlayPostings:
            skew["seconds"] = 1e6  # the wall passes, as search reads it, once the first batch is counted
            return real_kernel(docs, terms, budget=budget)

        monkeypatch.setattr(deadline_module, "monotonic", skewed_clock)
        monkeypatch.setattr(search_module, "overlay_postings", counting_kernel)
        with _recorded(storage) as statements:
            result = await storage.search(query="tokens")
        assert result.success is True
        assert len(_walls(result)) == 1
        assert _paths(result) == ["/d/0.txt"]  # the first batch's body, the only one fetched
        # The first batch's surrogate and body fetch, the preview fetch, the nominee fetch: no second batch ran.
        assert _overlay_legs(statements) == (2, 1, 1)
        await storage.close()

    async def test_traits_declare_the_lexical_leg_and_its_overlay(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        traits = storage.traits()
        assert traits["search_signals"] == "lexical" and traits["search_staleness"] == "overlay"
        await storage.close()


# A partial caller's store: bob reads ``/d`` alone, and the file a whole caller ranks first is under ``/h``.
PARTIAL = {
    "/d/a.txt": "tokens once\n",
    "/d/b.txt": "tokens tokens and more words here\n",
    "/h/c.txt": "tokens tokens tokens\n",
}


async def _partial_store(tmp_path: Any = None) -> DatabaseStorage:
    """The partial caller's store, in memory or, for a node that commits a rival mid-call, on a file."""
    storage = InMemoryStorage() if tmp_path is None else DatabaseStorage(url=_url(tmp_path))
    entries = [Entry(path=Path(path), content=body) for path, body in PARTIAL.items()]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    assert (await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    assert (await storage.grant(path=Path("/d"), principal="bob", level="read", authority=SYSTEM)).success is True
    assert (await storage.rebuild()).success is True
    return storage


def _read_committed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model an engine whose read statements each see the latest commit, as one at READ COMMITTED does.

    A read op's connection is told to issue no ``BEGIN``, so SQLite takes
    no snapshot for the call and a rival committed at a seam is seen by
    the statements after it. Writers keep their transaction.
    """
    real = backend_module.op_execution_options

    def unpinned(profile: Any, *, writer: bool) -> dict[str, str | bool]:
        options = real(profile, writer=writer)
        return options if writer else {**options, "vfs_no_begin": True}

    monkeypatch.setattr(backend_module, "op_execution_options", unpinned)


def _bump_the_chunk_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A chunk-generation bump as a release makes it: the next run re-splits every entry into fresh chunk ids."""
    real = indexing_module.chunk_generation
    monkeypatch.setattr(indexing_module, "chunk_generation", lambda: real() + "-bumped")


def _text_reads(monkeypatch: pytest.MonkeyPatch, *, lose: str = "never") -> list[int | None]:
    """The chunk double: the real text read, the smallest chunk id it returned removed from the result.

    *lose* is ``never`` (a spy), ``first`` (the first call only) or
    ``every``. The list gains one item per text read: the id removed, or
    ``None``.
    """
    real = search_module._chunk_texts
    reads: list[int | None] = []

    async def losing(session, tables, chunk_ids, profile, membership_budget):
        texts = await real(session, tables, chunk_ids, profile, membership_budget)
        removed = min(texts) if lose == "every" or (lose == "first" and not reads) else None
        reads.append(removed)
        return {chunk_id: row for chunk_id, row in texts.items() if chunk_id != removed}

    monkeypatch.setattr(search_module, "_chunk_texts", losing)
    return reads


def _body_reads(monkeypatch: pytest.MonkeyPatch, *, lose: str = "never") -> list[int]:
    """The body double: the real live-body read, its result emptied on the ``first`` call or on ``every`` call.

    With *lose* ``never`` it is a spy. The list gains one item per call:
    how many entries the read was asked for.
    """
    real = search_module._resplit_bodies
    reads: list[int] = []

    async def losing(session, tables, profile, membership_budget, entry_ids, view):
        bodies = await real(session, tables, profile, membership_budget, entry_ids, view)
        reads.append(len(entry_ids))
        return {} if lose == "every" or (lose == "first" and len(reads) == 1) else bodies

    monkeypatch.setattr(search_module, "_resplit_bodies", losing)
    return reads


async def _chunk_owner(storage: DatabaseStorage, chunk_id: int | None) -> str:
    """The path of the entry that owns chunk *chunk_id*."""
    entry, chunks = storage._host.tables.entry, storage._host.tables.chunks
    owner = select(entry.c.path).join(chunks, chunks.c.entry_id == entry.c.entry_id).where(chunks.c.id == chunk_id)
    async with storage._host.session_factory() as session:
        return (await session.execute(owner)).scalar_one()


def _matches(result: Result) -> dict[str, Any]:
    return {str(o.path): o.matches for o in result.observations}


def _kinds(result: Result) -> list[Any]:
    return [error.kind for error in result.errors]


class TestVanishedChunks:
    """A chunk row a chunk pass or a sweep removed under a search: its entry answers from its live body, or the
    call runs again; it never raises."""

    async def test_search_after_a_chunk_generation_bump_answers_as_before(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a bump's run leaving the published epoch naming chunk rows it deleted, with a
        search that then raises for the first of them."""
        storage = await _indexed(tmp_path)
        settled = await storage.search(query="tokens")
        assert settled.success is True and len(settled.observations) == 4
        _bump_the_chunk_generation(monkeypatch)
        assert (await storage.rebuild()).success is True
        bumped = await storage.search(query="tokens")
        assert bumped.success is True, bumped.errors
        assert _ranked(bumped) == _ranked(settled)
        await storage.close()

    async def test_a_search_during_a_generation_bump_ranks_from_the_published_epoch(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a re-split entry dropped from the answer or redriven until the call gives up,
        where its unchanged body answers it in one bounded read."""
        storage = await _indexed(tmp_path)
        with _recorded(storage) as undisturbed:
            settled = await storage.search(query="tokens")
        reads = _text_reads(monkeypatch)
        _bump_the_chunk_generation(monkeypatch)
        during: list[tuple[Result, int]] = []

        async def observe() -> None:
            with _recorded(storage) as statements:
                result = await storage.search(query="tokens")
            during.append((result, len(statements)))

        with installed("rebuild:before-publish", observe):
            assert (await storage.rebuild()).success is True
        [(result, issued)] = during
        assert result.success is True, result.errors
        assert _ranked(result) == _ranked(settled) and result.errors == settled.errors
        for row in result.observations:
            [match] = row.matches or []
            assert (match.start, match.content) == (1, None)
        assert reads == [None]  # one text read: nothing was redriven
        assert (len(undisturbed), issued) == (9, 10)  # one bounded body read more than the settled search
        await storage.close()

    async def test_grep_and_search_stay_whole_through_a_generation_bump(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a re-split entry sent to the scan tier for the length of the build, where both
        verbs answer the first rows in path order and a truncation record."""
        files = {f"/d/f{i:02}.txt": f"plain words in file number {i}\n" for i in range(21)}
        files["/d/f18.txt"] = "a lantern hangs by the door\n"
        files["/d/f19.txt"] = "the lantern, the lantern\n"
        storage = await _indexed(tmp_path, files)
        monkeypatch.setattr(search_module, "SCAN_TIER_BUDGET", 5)
        monkeypatch.setattr(grep_module, "SCAN_TIER_BUDGET", 5)
        searched = await storage.search(query="lantern")
        grepped = await storage.grep(pattern="lantern")
        assert set(_paths(searched)) == set(_paths(grepped)) == {"/d/f18.txt", "/d/f19.txt"}
        assert ErrorKind.truncated not in _kinds(searched) and ErrorKind.truncated not in _kinds(grepped)
        _bump_the_chunk_generation(monkeypatch)
        during: list[tuple[Result, Result]] = []

        async def observe() -> None:
            during.append((await storage.search(query="lantern"), await storage.grep(pattern="lantern")))

        with installed("rebuild:before-publish", observe):
            assert (await storage.rebuild()).success is True
        [(search_during, grep_during)] = during
        assert (_ranked(search_during), search_during.errors) == (_ranked(searched), searched.errors)
        assert (_paths(grep_during), grep_during.errors) == (_paths(grepped), grepped.errors)
        await storage.close()

    async def test_a_chunk_gone_before_its_text_read_answers_from_the_live_body(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: a ranked chunk the text read did not return raising out of the call, redriving
        it, or dropping its entry; and a body read issued when no chunk is gone."""
        storage = await _indexed(tmp_path)
        with _recorded(storage) as undisturbed:
            settled = await storage.search(query="tokens")
        assert sum(1 for sql in undisturbed if _CHUNK_FETCH.search(sql)) == 1
        assert not [sql for sql in undisturbed if _CONTENT_READ.search(sql)]
        reads = _text_reads(monkeypatch, lose="first")
        with _recorded(storage) as disturbed:
            result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert _ranked(result) == _ranked(settled) and result.errors == settled.errors
        [removed] = reads
        assert await _chunk_owner(storage, removed) == "/notes.txt"
        assert (len(undisturbed), len(disturbed)) == (9, 10)
        assert sum(1 for sql in disturbed if _CONTENT_READ.search(sql)) == 1
        before, after = _matches(settled), _matches(result)
        [whole] = after.pop("/notes.txt")
        [chunk] = before.pop("/notes.txt")
        assert (whole.start, whole.end, whole.content, whole.score) == (1, 1, None, chunk.score)
        assert whole.preview == "A stream of **tokens**, **tokens**, **tokens**."
        assert after == before  # every other entry still answers from its chunk rows
        await storage.close()

    async def test_a_chunk_gone_with_its_body_redrives_once(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the redrive deleted, so an entry purged with its chunks reaches the assembly
        with chunk ids no row holds; or a redrive that leaves a record on a whole answer."""
        storage = await _indexed(tmp_path)
        with _recorded(storage) as undisturbed:
            settled = await storage.search(query="tokens")
        reads = _text_reads(monkeypatch, lose="first")
        asked = _body_reads(monkeypatch, lose="first")
        with _recorded(storage) as redriven:
            result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert _ranked(result) == _ranked(settled) and _matches(result) == _matches(settled)
        assert len(reads) == 2 and asked == [1, 0]
        assert (len(undisturbed), len(redriven)) == (9, 19)  # both attempts whole, and the one body read
        assert not {ErrorKind.conflict, ErrorKind.truncated} & set(_kinds(result))
        await storage.close()

    async def test_a_chunk_and_body_that_never_come_back_classify_conflict(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: an exhausted redrive raising out of the call, classified as anything but the
        retryable conflict a pointer that never settles gets, or naming the row it lost."""
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)  # the classification is pinned, not the backoff
        reads = _text_reads(monkeypatch, lose="every")
        _body_reads(monkeypatch, lose="every")
        result = await storage.search(query="tokens")
        assert result.success is False and result.observations == []
        [error] = result.errors
        assert (error.kind, error.retryable, error.path) == (ErrorKind.conflict, True, None)
        lost = "search kept losing to concurrent changes: an entry the answer carries is gone since it was ranked"
        assert error.message.endswith(lost)
        assert len(reads) == 4
        await storage.close()

    async def test_one_body_gone_among_several_redrives_the_call(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the redrive taken only when no live body came back at all, so one purged entry
        among several re-split ones reaches the assembly with chunk ids no row holds."""
        storage = await _indexed(tmp_path)
        settled = await storage.search(query="tokens")
        reads = _text_reads(monkeypatch)
        _bump_the_chunk_generation(monkeypatch)
        real = search_module._resplit_bodies
        asked: list[tuple[int, int]] = []

        async def losing_one(session, tables, profile, membership_budget, entry_ids, view):
            bodies = await real(session, tables, profile, membership_budget, entry_ids, view)
            if not asked:  # the first attempt: one of the re-split entries is purged as well
                del bodies[entry_ids[0]]
            asked.append((len(entry_ids), len(bodies)))
            return bodies

        monkeypatch.setattr(search_module, "_resplit_bodies", losing_one)
        during: list[Result] = []

        async def observe() -> None:
            during.append(await storage.search(query="tokens"))

        with installed("rebuild:before-publish", observe):
            assert (await storage.rebuild()).success is True
        [result] = during
        assert result.success is True, result.errors
        assert _ranked(result) == _ranked(settled)
        assert asked == [(4, 3), (4, 4)] and len(reads) == 2  # every hit re-split; one lost body ran the call again
        await storage.close()

    async def test_a_partial_callers_live_body_answer_keeps_its_view(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards: the live-body answer reaching past the caller's view, or changing what a
        partial caller is answered when one of its chunks is gone."""
        storage = await _partial_store()
        assert _paths(await storage.search(query="tokens"))[0] == "/h/c.txt"  # a whole caller's best hit
        undisturbed = await storage.search(query="tokens", authority=BOB)
        assert _paths(undisturbed) == ["/d/a.txt", "/d/b.txt"]
        reads = _text_reads(monkeypatch, lose="first")
        real = search_module._resplit_bodies
        views: list[Any] = []

        async def spying(session, tables, profile, membership_budget, entry_ids, view):
            views.append(view)
            return await real(session, tables, profile, membership_budget, entry_ids, view)

        monkeypatch.setattr(search_module, "_resplit_bodies", spying)
        result = await storage.search(query="tokens", authority=BOB)
        assert result.success is True, result.errors
        assert _ranked(result) == _ranked(undisturbed)
        assert not [path for path in _paths(result) if path.startswith("/h")]
        assert len(reads) == 1 and reads[0] is not None
        # The body read was handed bob's own view at the rung search reads at, never a wider one.
        [view] = views
        row = {"path": "/d/a.txt", "owner_id": None, "everyone_level": 0}
        assert view is not None and view.need == "read"
        assert view.holds(row, view.need) and not view.holds({**row, "path": "/h/c.txt"}, view.need)
        await storage.close()

    async def test_the_live_body_read_keeps_only_rows_the_view_holds(self) -> None:
        """Guards: the view test dropped from the live-body read, so it returns a body the call's
        resolution does not admit where the row sits."""
        storage = await _partial_store()
        host = storage._host
        by_path = {path: entry_id for path in PARTIAL for entry_id in await _entry_ids(storage, [path])}
        asked = [by_path["/d/a.txt"], by_path["/h/c.txt"]]
        resolution = Resolution.compile(
            {"bob": frozenset()}, [GrantRow("bob", "/d", "read")], owner_floor=True, pending=()
        )
        view = Visibility(resolution, "read", host.tables, SQLITE, 900, 2_099)
        # A second view that may name ``/h`` and not read it: the read judges at the view's rung, ``read``.
        naming = Resolution.compile(
            {"bob": frozenset()},
            [GrantRow("bob", "/d", "read"), GrantRow("bob", "/h", "list")],
            owner_floor=True,
            pending=(),
        )
        named = Visibility(naming, "read", host.tables, SQLITE, 900, 2_099)
        read, context = search_module._resplit_bodies, (host.tables, host.profile, host.membership_budget)
        async with host.session_factory() as session:
            held = await read(session, *context, asked, view)
            at_the_rung = await read(session, *context, asked, named)
            every = await read(session, *context, asked, None)
            nothing = await read(session, *context, [], view)
        assert held == at_the_rung == {by_path["/d/a.txt"]: "tokens once\n"}
        assert every == {by_path["/d/a.txt"]: "tokens once\n", by_path["/h/c.txt"]: "tokens tokens tokens\n"}
        assert nothing == {}
        await storage.close()

    async def test_the_live_body_read_pages_by_the_membership_budget(self) -> None:
        """Guards: the live-body read issued as one statement however many entries it is asked for."""
        storage = await _partial_store()
        host = storage._host
        asked = sorted(await _entry_ids(storage, list(PARTIAL)))
        async with host.session_factory() as session:
            with _recorded(storage) as paged:
                bodies = await search_module._resplit_bodies(session, host.tables, host.profile, 2, asked, None)
        assert sorted(bodies.values()) == sorted(PARTIAL.values())
        assert sum(1 for sql in paged if _CONTENT_READ.search(sql)) == 2  # three entries, two to a statement
        await storage.close()

    async def test_an_entry_with_one_chunk_gone_answers_whole(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: an entry counted gone only when all its chunks are, so one that kept some reaches
        the assembly with a chunk id no row holds; or its whole match scored by a chunk other than its best."""
        sections = [f"## Section {i}\n\nlantern words in section {i}, plain prose sentence.\n\n" for i in range(120)]
        storage = await _indexed(tmp_path, {"/doc/big.md": "".join(sections), "/doc/small.md": "no lantern here\n"})
        [settled] = (await storage.search(query="lantern", limit=1)).observations
        chunks = settled.matches or []
        assert len(chunks) == search_module.TOP_CHUNKS and chunks[-1].score != chunks[0].score == settled.score
        reads = _text_reads(monkeypatch, lose="first")
        [row] = (await storage.search(query="lantern", limit=1)).observations
        assert (str(row.path), row.score) == ("/doc/big.md", settled.score)
        [whole] = row.matches or []
        assert (whole.start, whole.end, whole.content) == (1, "".join(sections).count("\n"), None)
        assert whole.score == row.score  # the best chunk's score, on the entry's scale
        assert len(reads) == 1 and reads[0] is not None
        await storage.close()

    async def test_a_sweep_committed_at_the_seam_is_hidden_by_the_read_snapshot(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the window before the text read left without its seam, or the seam awaited
        after the read, so no rival can be committed between the ranking and the read."""
        storage = await _indexed(tmp_path)
        settled = await storage.search(query="tokens")
        reads = _text_reads(monkeypatch)
        fired: list[tuple[int, bool]] = []

        async def rival() -> None:
            swept = await storage.sweep(path=Path("/notes.txt"))
            fired.append((len(reads), swept.success))

        with installed("search:before-chunk-texts", rival):
            raced = await storage.search(query="tokens")
        assert fired == [(0, True)]  # once, before the text read, and the purge committed
        # SQLite's read snapshot was taken at the call's first read: the purge is not seen by it.
        assert raced.success is True and len(reads) == 1
        assert (_ranked(raced), _matches(raced)) == (_ranked(settled), _matches(settled))
        assert "/notes.txt" not in _paths(await storage.search(query="tokens"))
        await storage.close()

    async def test_the_live_body_read_is_asked_for_the_answer_alone(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the gone entries drawn from every ranked entry and not from the answer's, so a
        search with more hits than its limit reads the whole body of each hit it does not answer."""
        storage = await _indexed(tmp_path)
        assert len((await storage.search(query="tokens")).observations) == 4  # four hits, and two are asked for
        asked = _body_reads(monkeypatch)
        with _recorded(storage) as undisturbed:
            answer = await storage.search(query="tokens", limit=2)
        assert len(answer.observations) == 2 and asked == [0]
        assert not [sql for sql in undisturbed if _CONTENT_READ.search(sql)]
        reads = _text_reads(monkeypatch, lose="first")
        with _recorded(storage) as disturbed:
            again = await storage.search(query="tokens", limit=2)
        assert _ranked(again) == _ranked(answer) and len(reads) == 1
        assert asked == [0, 1]  # the answered entry whose chunk is gone, never a hit beyond the limit
        assert sum(1 for sql in disturbed if _CONTENT_READ.search(sql)) == 1
        await storage.close()

    async def test_the_live_body_read_leaves_out_an_entry_that_holds_no_text(self, tmp_path: Any) -> None:
        """Guards: an empty body returned as a body, or a body that is not there (a bytes write
        leaves no text row) decoded, where each must be absent so the caller redrives."""
        storage = await _fresh(tmp_path)
        emptied = Entry(path=Path("/notes.txt"), content="")
        binary = Entry(path=Path("/docs/tokens.md"), data=b"\x89PNG\r\n\x00\xff\xfe")
        assert (await storage.write(entries=[emptied, binary])).success is True
        host = storage._host
        asked = sorted(await _entry_ids(storage, ["/notes.txt", "/docs/tokens.md", "/src/lexer.py"]))
        [kept] = await _entry_ids(storage, ["/src/lexer.py"])
        async with host.session_factory() as session:
            read = search_module._resplit_bodies
            bodies = await read(session, host.tables, host.profile, host.membership_budget, asked, None)
        assert bodies == {kept: CORPUS["/src/lexer.py"]}
        await storage.close()

    @pytest.mark.parametrize("emptied", ["empty", "bytes"])
    async def test_an_entry_emptied_of_text_before_its_body_read_redrives(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, emptied: str
    ) -> None:
        """Guards: an entry left with no text inside the call's window answered from that body,
        an empty preview under its old score, or raising, where the call must run again."""
        storage = await _indexed(tmp_path)
        _read_committed(monkeypatch)
        reads = _text_reads(monkeypatch)
        path = Path("/notes.txt")
        body = Entry(path=path, content="") if emptied == "empty" else Entry(path=path, data=b"\x89PNG\r\n\x00\xff\xfe")
        committed: list[bool] = []

        async def rival() -> None:
            if not committed:  # once: the second attempt meets the state this left
                written = await storage.write(entries=[body])
                committed.append(written.success and (await storage.rebuild()).success)

        with installed("search:before-chunk-texts", rival):
            raced = await storage.search(query="tokens")
        assert committed == [True]
        assert raced.success is True, raced.errors
        assert len(reads) == 2 and "/notes.txt" not in _paths(raced)
        settled = await storage.search(query="tokens")
        assert (_ranked(raced), _matches(raced)) == (_ranked(settled), _matches(settled))
        await storage.close()

    async def test_an_entry_moved_out_of_the_view_before_its_body_read_redrives(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards: the live-body read handed no view, so a partial caller is answered the new body
        of an entry that left its view after it was ranked."""
        storage = await _partial_store(tmp_path)
        assert set(_paths(await storage.search(query="tokens", authority=BOB))) == {"/d/a.txt", "/d/b.txt"}
        _read_committed(monkeypatch)
        reads = _text_reads(monkeypatch)
        committed: list[bool] = []

        async def rival() -> None:
            if not committed:
                pair = ResolvedPair(src=Path("/d/a.txt"), dest=Path("/h/a.txt"))
                moved = await storage.move(operations=[pair], authority=SYSTEM)
                rewritten = [Entry(path=Path("/h/a.txt"), content="tokens moved\n")]
                written = await storage.write(entries=rewritten, authority=SYSTEM)
                committed.append(moved.success and written.success and (await storage.rebuild()).success)

        with installed("search:before-chunk-texts", rival):
            raced = await storage.search(query="tokens", authority=BOB)
        assert committed == [True]
        assert raced.success is True, raced.errors
        assert _paths(raced) == ["/d/b.txt"] and len(reads) == 2  # the moved entry ran the call again and left
        assert not [m for o in raced.observations for m in o.matches or [] if "moved" in (m.preview or "")]
        await storage.close()


async def _refreshed(storage: DatabaseStorage, files: dict[str, str]) -> None:
    entries = [Entry(path=Path(path), content=body) for path, body in files.items()]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    assert (await storage.refresh()).success is True


async def _live_docs(storage: DatabaseStorage) -> list[Any]:
    """Every ``vfs_lex_docs`` row of the live set, with its entry's path."""
    tables = storage._host.tables
    docs, entry = tables.lex_docs, tables.entry
    async with storage._host.session_factory() as session:
        pointer = (await session.execute(select(tables.index_state.c.current_gram_epoch))).scalar_one()
        live = await indexing_module.live_set(session, tables, pointer)
        stmt = select(docs.c.epoch, docs.c.chunk_id, docs.c.dl, entry.c.path).join(
            entry, entry.c.entry_id == docs.c.entry_id
        )
        return [row for row in (await session.execute(stmt)).all() if row.epoch in live]


async def _live_blocks(storage: DatabaseStorage) -> list[Any]:
    tables = storage._host.tables
    async with storage._host.session_factory() as session:
        pointer = (await session.execute(select(tables.index_state.c.current_gram_epoch))).scalar_one()
        live = await indexing_module.live_set(session, tables, pointer)
        rows = (await session.execute(select(tables.lex_postings))).all()
    return [row for row in rows if row.epoch in live]


async def _live_partial_store(tmp_path: Any, *, hidden: bool) -> DatabaseStorage:
    """bob reads ``/d``; a base and two deltas, the second store with hidden ``/h`` files in the base and a delta."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    storage = await _partial_store(tmp_path)
    if hidden:
        await _refreshed(storage, {"/h/base.txt": "tokens kestrel tokens tokens\n"})
        assert (await storage.rebuild()).success is True
    hidden_delta = {"/h/y.txt": "kestrel kestrel"} if hidden else {}
    await _refreshed(storage, {"/d/x.txt": "kestrel tokens words\n", **hidden_delta})
    await _refreshed(storage, {"/d/z.txt": "kestrel only here\n"})
    return storage


class TestLiveSet:
    async def test_a_re_split_entry_ranks_from_its_new_chunks(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        old = {row.chunk_id for row in await _live_docs(storage) if row.path == "/notes.txt"}
        await _refreshed(storage, {"/notes.txt": "A river of tokens, tokens and more tokens.\n"})
        result = await storage.search(query="tokens")
        assert result.success is True, result.errors
        assert _paths(result)[0] == "/notes.txt"
        live = await _live_docs(storage)
        assert not {row.chunk_id for row in live} & old
        assert {row.epoch for row in live if row.path == "/notes.txt"} == {max(row.epoch for row in live)}
        await storage.close()

    async def test_a_moved_generation_redrives_search_once(self, tmp_path: Any, monkeypatch) -> None:
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        real, pointers = search_module.current_generation, []
        index_state = storage._host.tables.index_state

        async def one_ahead(session, tables):
            pointers.append((await session.execute(select(index_state.c.current_gram_epoch))).scalar_one())
            generation = await real(session, tables)
            return generation + 1 if len(pointers) == 1 else generation

        monkeypatch.setattr(search_module, "current_generation", one_ahead)
        attempts: list[int] = []

        async def counted() -> None:
            attempts.append(len(attempts))

        with installed("search:after-pointer-read", counted):
            result = await storage.search(query="tokens")
        assert "/fresh.txt" in _paths(result)
        assert (len(attempts), pointers) == (2, [1, 1])
        await storage.close()

    async def test_a_generation_moved_at_the_empty_overlay_recheck_redrives_search(
        self, tmp_path: Any, monkeypatch
    ) -> None:
        # A quiet store skips the scan tier on its second combined read: a publish there redrives the call once.
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(storage._host, "_retry_base_delay", 0.0)
        real, calls = search_module.pointer_with_overlay, []

        async def moved_at_recheck(session, tables):
            calls.append(len(calls))
            snapshot = await real(session, tables)
            return snapshot._replace(generation=snapshot.generation + 1) if len(calls) == 2 else snapshot

        monkeypatch.setattr(search_module, "pointer_with_overlay", moved_at_recheck)
        result = await storage.search(query="tokens")
        assert result.success is True and _paths(result)[0] == "/notes.txt", result.errors
        assert len(calls) == 4  # two combined reads an attempt: exactly one redrive
        await storage.close()

    async def test_the_view_and_scope_paths_read_the_live_set(self, tmp_path: Any) -> None:
        storage = await _partial_store(tmp_path)
        await _refreshed(storage, {"/d/fresh.txt": "kestrel tokens\n"})
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            assert (await conn.execute(select(entry.c.encoded).where(entry.c.path == "/d/fresh.txt"))).scalar_one()
        viewed = await storage.search(query="kestrel", authority=BOB)
        scoped = await storage.search(query="kestrel", globs=("/d/**",))
        for result in (viewed, scoped):
            assert result.success is True and _paths(result) == ["/d/fresh.txt"], result.errors
            assert result.legs["lexical"]["hits"] == 1  # ty: ignore[unresolved-attribute]
        await storage.close()

    async def test_the_export_reports_the_live_set(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        await _refreshed(storage, {"/q1.txt": "quokka one\n", "/q2.txt": "quokka two\n"})
        await _refreshed(storage, {"/q3.txt": "quokka three\n"})
        stats = storage._host.tables.lex_stats
        async with storage._host.engine.connect() as conn:
            corpus = {row.epoch: row for row in await conn.execute(select(stats))}
        result = await storage.search(query="quokka")
        export = result.lexical_stats  # ty: ignore[unresolved-attribute]
        assert export["terms"]["quokka"]["df"] == 3
        assert export["n_docs"] == sum(row.n_docs for row in corpus.values())
        assert export["avg_dl"] == corpus[min(corpus)].avg_dl
        await storage.close()

    async def test_a_kept_chunk_id_is_posted_once(self, tmp_path: Any) -> None:
        files = {"/a.txt": "apricot body\n", "/b.txt": "bilberry body\n", "/c.txt": "cloudberry body\n"}
        storage = await _indexed(tmp_path, files)
        words = ("apricot", "bilberry", "cloudberry")
        scores = {word: (await storage.search(query=word)).observations[0].score for word in words}
        tables = storage._host.tables
        lex = (tables.posting_list, tables.lex_docs, tables.lex_postings, tables.lex_df)
        async with storage._host.engine.connect() as conn:
            counts = {t.name: (await conn.execute(select(func.count()).select_from(t))).scalar_one() for t in lex}
        await _refreshed(storage, {"/a.txt": "apricot body\n"})
        assert (await storage.delete(path=Path("/b.txt"))).success is True
        assert (await storage.restore(path=Path("/b.txt"))).success is True
        assert (await storage.delete(path=Path("/c.txt"))).success is True
        await _refreshed(storage, {"/c.txt": "cloudberry body\n"})
        entry = storage._host.tables.entry
        async with storage._host.engine.connect() as conn:
            assert all((await conn.execute(select(entry.c.encoded).where(entry.c.path.in_(files)))).scalars())
            after = {t.name: (await conn.execute(select(func.count()).select_from(t))).scalar_one() for t in lex}
        assert after == counts
        segments: dict[int, set[int]] = {}
        for row in await _live_blocks(storage):
            for chunk_id in decode_postings(bytes(row.doc_ids)):
                segments.setdefault(chunk_id, set()).add(row.epoch)
        assert segments and all(len(epochs) == 1 for epochs in segments.values())
        for word, score in scores.items():
            assert (await storage.search(query=word)).observations[0].score == score
        await storage.close()

    @pytest.mark.parametrize("budget", [None, 2], ids=["whole", "one-epoch-a-statement"])
    async def test_a_partial_caller_scores_and_exports_the_visible_live_set(
        self, tmp_path: Any, monkeypatch, budget: int | None
    ) -> None:
        storage = await _live_partial_store(tmp_path, hidden=True)
        if budget is not None:  # every live-set read then merges one statement per segment
            monkeypatch.setattr(EngineHost, "membership_budget", property(lambda self: budget))
        lexicons: list[Any] = []
        caps: list[tuple[int, int]] = []
        real_lexicon, real_extension = lexical_module.visible_lexicon, lexical_module.extension

        async def captured(*args: Any) -> Any:
            lexicons.append(await real_lexicon(*args))
            return lexicons[-1]

        class Capped:
            def __getattr__(self, name: str) -> Any:
                return getattr(real_extension(), name)

            def candidate_ids(self, groups: Any, allow: Any, cap: int) -> Any:
                found = real_extension().candidate_ids(groups, allow, cap)
                if allow is None:
                    caps.append((cap, len(found[0])))
                return found

        monkeypatch.setattr(search_module, "visible_lexicon", captured)
        monkeypatch.setattr(lexical_module, "extension", Capped)
        result = await storage.search(query="kestrel tokens", authority=BOB)
        assert result.success is True, result.errors
        [lexicon] = lexicons
        visible = [row for row in await _live_docs(storage) if row.path.startswith("/d/")]
        n_v, avg_v = len(visible), sum(row.dl for row in visible) / len(visible)
        assert (lexicon.stats.n_docs, lexicon.stats.avg_dl) == (n_v, avg_v)
        assert sorted(lexicon.visible) == sorted(row.chunk_id for row in visible)
        export = result.lexical_stats  # ty: ignore[unresolved-attribute]
        assert (export["n_docs"], export["avg_dl"]) == (n_v, avg_v)
        visible_ids = {row.chunk_id for row in visible}
        for term, summary in lexicon.stats.terms.items():
            blocks = [row for row in await _live_blocks(storage) if row.term == term]
            holding = {cid for row in blocks for cid in decode_postings(bytes(row.doc_ids)) if cid in visible_ids}
            assert summary.df == len(holding) == export["terms"][term]["df"], term
        for block in lexicon.blocks:
            ids = decode_postings(block.doc_ids)
            weights = [
                term_weight(tf, dl, avg_v, lexicon.idfs[block.term])
                for tf, dl in zip(decode_varints(block.tfs), decode_varints(block.dls), strict=True)
            ]
            assert len(ids) == len(weights) and block.bound >= max(weights) - 1e-12
        assert caps and all(cap >= union for cap, union in caps)
        oracle = pure_score_blocks(lexicon.blocks, lexicon.idfs, avg_v, 10, candidates=lexicon.visible)
        owner = {row.chunk_id: row.path for row in visible}
        expected = list(dict.fromkeys(owner[chunk_id] for chunk_id, _score in oracle))
        assert _paths(result) == expected
        await storage.close()

    async def test_many_segments_issue_bounded_statements(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards: the live set's epoch slice put back at ``budget - 1``, so a long live set leaves one term a probe."""
        storage = InMemoryStorage()
        base = [Entry(path=Path("/s/base.txt"), content="kestrel base\n")]
        assert (await storage.write(entries=base, parents=True)).success
        assert (await storage.rebuild()).success is True
        for n in range(39):
            await _refreshed(storage, {f"/s/d{n:02}.txt": f"kestrel delta {n} words\n"})
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            pointer = await indexing_module.current_epoch(session, tables)
            assert len(await indexing_module.live_set(session, tables, pointer)) == 40
        monkeypatch.setattr(EngineHost, "membership_budget", property(lambda _self: 16))
        query = " ".join(["kestrel", *(f"term{n:02}" for n in range(19))])
        with _recorded(storage) as statements:
            found = await storage.search(query=query)
        assert found.success is True and found.observations, found.errors
        probes = [sql for sql in statements if "FROM vfs_lex_df" in sql and "vfs_lex_df.epoch IN" in sql]
        assert len(probes) == 15, len(probes)
        await storage.close()

    async def test_a_zero_mean_length_never_fails_a_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Guards: the scorer's zero-mean guard deleted, so a delta on a base with no text divides by its mean.

        The refusal that keeps a refresh off such a base is patched away, so the pass publishes the delta.
        """

        async def no_refusal(*_args: Any, **_kwargs: Any) -> None:
            return None

        storage = InMemoryStorage()
        assert (await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
        assert (await storage.grant(path=Path("/d"), principal="bob", level="read", authority=SYSTEM)).success
        assert (await storage.rebuild()).success is True
        monkeypatch.setattr(maintenance_module, "refresh_refusal", no_refusal)
        await _refreshed(storage, {"/d/a.txt": "kestrel tokens here\n", "/h/b.txt": "kestrel hidden\n"})
        assert (await storage.write(entries=[Entry(path=Path("/d/fresh.txt"), content="kestrel fresh\n")])).success
        everyone, bob = ["/d/a.txt", "/d/fresh.txt", "/h/b.txt"], ["/d/a.txt", "/d/fresh.txt"]
        for authority, paths in ((SYSTEM, everyone), (BOB, bob)):
            found = await storage.search(query="kestrel tokens", authority=authority)
            assert found.success is True and sorted(_paths(found)) == paths, found.errors
            assert all(o.score is not None and math.isfinite(o.score) for o in found.observations)
        await storage.close()

    async def test_a_hidden_document_moves_no_number_a_partial_caller_sees(self, tmp_path: Any) -> None:
        alone = await _live_partial_store(tmp_path / "alone", hidden=False)
        beside = await _live_partial_store(tmp_path / "beside", hidden=True)
        seen = [_seen(await store.search(query="kestrel tokens", authority=BOB)) for store in (alone, beside)]
        assert seen[0] == seen[1]
        assert seen[0][0], seen[0]
        for store in (alone, beside):
            await store.close()
