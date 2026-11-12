"""The search leg against real sqlite rows: scope rungs, the two rounds,
the overlay, records, the two-read protocol, ordering laws and the mask.

Direct backend tests — capability declaration is a router concern, so
these rows call ``storage.search`` straight through the seam. The
overlay serves everything until ``reindex()`` runs; several rows run
in both worlds because the answer must not depend on which side served.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event, select, true
from sqlalchemy.dialects import mssql, sqlite

from tests.support.database_helpers import _url
from tests.support.oracles.lexical import pure_overlay_postings, pure_score_blocks
from tests.support.statements import is_statistics_statement
from vfs import deadline as deadline_module
from vfs.deadline import WALL_TIME_BUDGET, WALL_TIME_CAUSE
from vfs.embedding import HashEmbeddingProvider
from vfs.models import Entry
from vfs.models.lexical import OverlayPostings, encode_block
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.pattern_matching import glob as glob_module
from vfs.results import ErrorKind, Result, Severity
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database import scope as scope_module
from vfs.storage.backends.database import search as search_module
from vfs.storage.backends.database.dialects import MSSQL, SQLITE
from vfs.storage.backends.database.lexical import TermStatistics
from vfs.storage.backends.database.seams import installed

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# The overlay's three SQL legs as SQLite spells them: the body fetch (the
# preview fetch takes the same shape), the surrogate-id fetch and the
# path-ordered nominee fetch.
_BODY_FETCH = re.compile(r"\bFROM vfs_content\b")
_SURROGATE_FETCH = re.compile(r"^SELECT vfs_entries\.entry_id, vfs_entries\.id\s+FROM vfs_entries\b")
_NOMINEE_FETCH = re.compile(r"\bFROM vfs_entries\b.*\bORDER BY vfs_entries\.path\b", re.S)

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
    assert (await storage.reindex()).success is True
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
        real = search_module._chunk_ids_for

        async def spying(session, tables, epoch, doc_ids, profile, budget):
            narrowed.append(len(doc_ids))
            return await real(session, tables, epoch, doc_ids, profile, budget)

        monkeypatch.setattr(search_module, "_chunk_ids_for", spying)
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
        monkeypatch.setattr(search_module, "_chunk_ids_for", lambda *a: narrowed.append(1))
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
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_the_meta_subtree_is_hidden_unless_addressed(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, {"/a.txt": "tokens here\n"})
        assert (
            await storage.write(entries=[Entry(path=Path("/.vfs/hidden.txt"), content="tokens too\n")], parents=True)
        ).success
        assert (await storage.reindex()).success is True
        assert _paths(await storage.search(query="tokens")) == ["/a.txt"]
        assert _paths(await storage.search(query="tokens", globs=("/.vfs/**",))) == ["/.vfs/hidden.txt"]
        await storage.close()

    async def test_piped_rows_admit_their_own_paths(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        rows = (await storage.search(query="tokens", globs=("docs/**", "notes.txt"))).observations
        piped = await storage.search(query="tokens", observations=rows[:1])
        assert _paths(piped) == [str(rows[0].path)]
        await storage.close()

    async def test_the_same_scope_answers_identically_before_and_after_reindex(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        before = await storage.search(query="tokens", globs=("src/**",))
        assert (await storage.reindex()).success is True
        after = await storage.search(query="tokens", globs=("src/**",))
        assert _paths(before) == _paths(after) == ["/src/lexer.py", "/src/parser.py"]
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
        real = search_module.tail_block_statements

        def spying(postings, epoch, asked, *rest):
            wanted.append({term: list(nos) for term, nos in asked.items()})
            return real(postings, epoch, asked, *rest)

        monkeypatch.setattr(search_module, "tail_block_statements", spying)
        monkeypatch.setattr(search_module, "HEAD_BLOCKS", 1)
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
        async with storage._host.engine.begin() as conn:
            await conn.exec_driver_sql("ANALYZE")
            stat_rows = (await conn.exec_driver_sql("SELECT count(*) FROM sqlite_stat1")).scalar_one()
        assert stat_rows > 0
        selected: list[list[int]] = []
        scored: list[list[int]] = []
        real_select, real_score = search_module.select_blocks, search_module.score_blocks

        def recording_select(*args: Any, **kwargs: Any) -> Any:
            chosen = real_select(*args, **kwargs)
            selected.extend([no for no in competing if no >= search_module.HEAD_BLOCKS] for competing in chosen)
            return chosen

        def counting_score(blocks: Any, *args: Any, **kwargs: Any) -> Any:
            scored.append([block.term for block in blocks])
            return real_score(blocks, *args, **kwargs)

        monkeypatch.setattr(search_module, "select_blocks", recording_select)
        monkeypatch.setattr(search_module, "score_blocks", counting_score)
        monkeypatch.setattr(search_module, "HEAD_BLOCKS", 1)
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
        packed = search_module._packed_arms(arms, 6)
        assert [len(statement) for statement in packed] == [2, 1, 1]
        assert search_module._packed_arms([], 6) == []

    def test_the_tail_fetch_takes_the_tuple_form_where_declared(self) -> None:
        postings = build_vfs_tables().lex_postings
        wanted = {"the": [8, 9, 10], "is": [8, 9, 10, 11]}

        def compiled(profile: Any, dialect: Any, parameter_budget: int) -> list[tuple[str, int]]:
            statements = search_module.tail_block_statements(postings, 1, wanted, profile, parameter_budget, 4)
            rendered = [s.compile(dialect=dialect, compile_kwargs={"render_postcompile": True}) for s in statements]
            return [(str(c), len(c.params)) for c in rendered]

        tuple_form = compiled(SQLITE, sqlite.dialect(), 8)
        assert [(binds - 1) // 2 for _, binds in tuple_form] == [2, 2, 2, 1]
        assert all("IN (VALUES" in text and " OR " not in text for text, _ in tuple_form)
        arms = compiled(MSSQL, mssql.dialect(), 8)
        assert [binds for _, binds in arms] == [5, 6]
        assert all(" OR " not in text and "VALUES" not in text for text, _ in arms)
        [(packed, binds)] = compiled(MSSQL, mssql.dialect(), 16)
        assert binds == 11 and " OR " in packed and "VALUES" not in packed


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

    async def test_a_written_file_with_a_new_word_is_found_before_reindex(self, tmp_path: Any) -> None:
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
                assert (await storage.reindex()).success is True

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
            pointer, overlay_empty = await real(session, tables)
            return (pointer, True) if calls["n"] == 1 else (pointer, overlay_empty)

        real_epoch = search_module.current_epoch
        epoch_calls = {"n": 0}

        async def counting_epoch(session, tables):
            epoch_calls["n"] += 1
            return await real_epoch(session, tables)

        monkeypatch.setattr(search_module, "pointer_with_overlay", blind_preamble)
        monkeypatch.setattr(search_module, "current_epoch", counting_epoch)
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
        real = search_module.current_epoch
        calls = {"n": 0}

        async def always_moving(session, tables):
            calls["n"] += 1
            return ((await real(session, tables)) or 0) + calls["n"]

        monkeypatch.setattr(search_module, "current_epoch", always_moving)
        result = await storage.search(query="tokens")
        assert result.success is False
        assert result.errors[0].kind == ErrorKind.conflict and result.errors[0].retryable is True
        await storage.close()

    def test_overlay_blocks_take_counted_postings_and_local_statistics(self) -> None:
        """Guards: a block encoded in arrival order (path order) rather than doc-id order,
        or the local statistics counted over anything but the bodies the kernel reached."""
        assert search_module._text(b"alpha beta") == search_module._text("alpha beta") == "alpha beta"
        # Two bodies, "alpha beta" (id 1) and "beta beta gamma" (id 2), counted in reverse path order.
        counted = search_module._OverlayCount([[(2, 2, 3), (1, 1, 2)], []], 2, 5)
        blocks, idfs, avg_dl = search_module._overlay_blocks(
            counted, ["beta", "delta"], TermStatistics({}, 0, 0.0, 1.2, 0.75)
        )
        assert [block.term for block in blocks] == [0]  # delta occurs nowhere: no block
        assert blocks[0].doc_ids == encode_block([1, 2], [1, 2], [2, 3])[0]
        assert avg_dl == 2.5 and idfs[0] == pytest.approx(0.1823, abs=1e-3)
        assert idfs[1] > idfs[0]  # the rarer term (absent) takes the higher idf
        nothing = search_module._OverlayCount([[]], 0, 0)
        blocks, idfs, avg_dl = search_module._overlay_blocks(nothing, ["beta"], TermStatistics({}, 0, 0.0, 1.2, 0.75))
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
