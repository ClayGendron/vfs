"""The glean leg against real sqlite rows: scope rungs, the two rounds,
the overlay, records, the two-read protocol, ordering laws and the mask.

Direct backend tests — capability declaration is a router concern, so
these rows call ``storage.glean`` straight through the seam. The
overlay serves everything until ``reindex()`` runs; several rows run
in both worlds because the answer must not depend on which side served.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import true

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.models.lexical import encode_block
from vfs.paths import Path
from vfs.results import Result, Severity, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import glean as glean_module
from vfs.storage.backends.database.lexical import TermStatistics
from vfs.storage.backends.database.seams import installed

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


def _scores(result: Result) -> list[float]:
    scores = [o.score for o in result.observations]
    assert all(score is not None for score in scores)
    return [score for score in scores if score is not None]


class TestRefusals:
    async def test_a_query_with_no_term_classifies_invalid(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.glean(query="!!! ...")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        await storage.close()

    async def test_a_defective_glob_classifies_invalid(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.glean(query="tokens", globs=("a**b",))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        await storage.close()

    def test_the_wall_budget_must_be_positive(self, tmp_path: Any) -> None:
        with pytest.raises(ValueError, match="glean_wall_seconds"):
            DatabaseStorage(url=_url(tmp_path), glean_wall_seconds=0)


class TestRanking:
    async def test_entries_come_best_first_on_a_unit_scale(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.glean(query="tokens")
        assert result.success is True, result.errors
        assert _paths(result)[0] == "/notes.txt"  # three occurrences in a short body
        scores = _scores(result)
        assert scores[0] == 1.0 and scores == sorted(scores, reverse=True)
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert set(_paths(result)) == {"/notes.txt", "/src/lexer.py", "/src/parser.py", "/docs/tokens.md"}
        await storage.close()

    async def test_a_hit_carries_its_chunks_with_bounds_text_and_score(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        [row] = (await storage.glean(query="dispatches", limit=1)).observations
        assert str(row.path) == "/docs/routing.md"
        [match] = row.matches or []
        assert (match.start, match.end) == (1, 1)
        assert match.match is None and match.content is not None and "dispatches" in match.content
        assert match.score == row.score == 1.0
        assert {"path", "kind", "version", "score", "matches"} <= row.populated
        await storage.close()

    async def test_a_chunk_hit_carries_a_bolded_preview_inside_its_bounds(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        [row] = (await storage.glean(query="Tokens", limit=1, globs=("src/**",))).observations
        for match in row.matches or []:
            assert match.preview is not None and "**tokens**" in match.preview
            assert match.preview_start is not None and match.preview_end is not None
            assert match.start <= match.preview_start <= match.preview_end <= match.end
        await storage.close()

    async def test_a_query_term_absent_from_a_chunk_leaves_its_head_unbolded(self, tmp_path: Any) -> None:
        # Both terms are in the index but only one occurs in the chunk that answers.
        files = {"/a.md": "stream of tokens\n", "/b.md": "a request arrives\nand a stream flows\n"}
        storage = await _indexed(tmp_path, files)
        result = await storage.glean(query="tokens request")
        [b] = [o for o in result.observations if str(o.path) == "/b.md"]
        [match] = b.matches or []
        assert match.preview == "a **request** arrives\nand a stream flows"
        await storage.close()

    async def test_a_long_entry_carries_its_best_chunks_with_distinct_bounds(self, tmp_path: Any) -> None:
        sections = (f"## Section {i}\n\nlantern words in section {i}, plain prose sentence.\n\n" for i in range(120))
        storage = await _indexed(tmp_path, {"/doc/big.md": "".join(sections), "/doc/small.md": "no lantern here\n"})
        [row] = (await storage.glean(query="lantern", limit=1)).observations
        assert str(row.path) == "/doc/big.md"
        matches = row.matches or []
        assert len(matches) == glean_module.TOP_CHUNKS
        bounds = [(m.start, m.end) for m in matches]
        assert len(set(bounds)) == len(bounds) and bounds == sorted(bounds)
        assert matches[0].score == row.score == 1.0
        assert all(m.score is not None and 0.0 < m.score <= 1.0 for m in matches)
        await storage.close()

    async def test_the_limit_counts_entries_and_ties_break_by_path(self, tmp_path: Any) -> None:
        files = {"/b.txt": "same words here\n", "/a.txt": "same words here\n", "/c.txt": "same words here\n"}
        storage = await _indexed(tmp_path, files)
        result = await storage.glean(query="same words", limit=2)
        assert _paths(result) == ["/a.txt", "/b.txt"]
        assert [o.score for o in result.observations] == [1.0, 1.0]
        await storage.close()

    async def test_columns_narrow_the_mask_and_identity_stays(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        [row] = (await storage.glean(query="dispatches", limit=1, columns=frozenset({"path"}))).observations
        assert row.populated == {"path", "kind", "version", "score", "matches"}
        assert row.size_bytes is None
        await storage.close()

    async def test_term_statistics_ride_the_envelope(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.glean(query="tokens unknownword")
        export = result.lexical_stats  # ty: ignore[unresolved-attribute]
        assert export["n_docs"] == len(CORPUS) and export["avg_dl"] > 0
        assert set(export["terms"]) == {"tokens"} and export["terms"]["tokens"]["df"] == 4
        await storage.close()

    async def test_an_indexed_term_absent_from_the_corpus_answers_empty(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        result = await storage.glean(query="unknownword")
        assert result.success is True and result.observations == []
        await storage.close()


class TestScope:
    async def test_globs_take_the_narrow_rung(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = await _indexed(tmp_path)
        narrowed: list[int] = []
        real = glean_module._chunk_ids_for

        async def spying(session, tables, epoch, doc_ids, budget):
            narrowed.append(len(doc_ids))
            return await real(session, tables, epoch, doc_ids, budget)

        monkeypatch.setattr(glean_module, "_chunk_ids_for", spying)
        result = await storage.glean(query="tokens", globs=("src/**",))
        assert set(_paths(result)) == {"/src/lexer.py", "/src/parser.py"}
        assert narrowed == [4]  # the segment index nominated the src entries, the deep directory among them
        await storage.close()

    async def test_a_wide_scope_takes_the_probe_rung_and_answers_identically(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        narrow = await storage.glean(query="tokens", globs=("src/**",))
        monkeypatch.setattr(glean_module, "SCOPE_ID_BUDGET", 1)
        narrowed: list[int] = []
        monkeypatch.setattr(glean_module, "_chunk_ids_for", lambda *a: narrowed.append(1))
        wide = await storage.glean(query="tokens", globs=("src/**",))
        assert narrowed == []  # over the budget: no allow-list resolution
        assert _paths(wide) == _paths(narrow) and wide.errors == narrow.errors
        assert [o.score for o in wide.observations] == [o.score for o in narrow.observations]
        await storage.close()

    async def test_exclusions_and_ext_gate_every_row(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        assert set(_paths(await storage.glean(query="tokens", globs_not=("src/**",)))) == {
            "/notes.txt",
            "/docs/tokens.md",
        }
        assert _paths(await storage.glean(query="tokens", ext=("md",))) == ["/docs/tokens.md"]
        assert _paths(await storage.glean(query="tokens", ext_not=("py", "md"))) == ["/notes.txt"]
        await storage.close()

    async def test_a_glob_contradicting_the_ext_channel_answers_empty_in_both_worlds(self, tmp_path: Any) -> None:
        # Every gate derives ``py`` while the channel wants ``md``: the
        # scan has no live arm and the index side has no admitted row.
        storage = await _fresh(tmp_path)
        for _world in ("overlay", "indexed"):
            result = await storage.glean(query="tokens", globs=("*.py",), ext=("md",))
            assert result.success is True and result.observations == []
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_the_meta_subtree_is_hidden_unless_addressed(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, {"/a.txt": "tokens here\n"})
        assert (
            await storage.write(entries=[Entry(path=Path("/.vfs/hidden.txt"), content="tokens too\n")], parents=True)
        ).success
        assert (await storage.reindex()).success is True
        assert _paths(await storage.glean(query="tokens")) == ["/a.txt"]
        assert _paths(await storage.glean(query="tokens", globs=("/.vfs/**",))) == ["/.vfs/hidden.txt"]
        await storage.close()

    async def test_piped_rows_admit_their_own_paths(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        rows = (await storage.glean(query="tokens", globs=("docs/**", "notes.txt"))).observations
        piped = await storage.glean(query="tokens", observations=rows[:1])
        assert _paths(piped) == [str(rows[0].path)]
        await storage.close()

    async def test_the_same_scope_answers_identically_before_and_after_reindex(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        before = await storage.glean(query="tokens", globs=("src/**",))
        assert (await storage.reindex()).success is True
        after = await storage.glean(query="tokens", globs=("src/**",))
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
        reference = await storage.glean(query="common anchor", limit=5)
        assert _paths(reference)[0] == "/c/0130.txt"
        packed: list[int] = []
        real = glean_module._packed_arms

        def spying(arms, parameter_budget):
            statements = real(arms, parameter_budget)
            packed.append(sum(len(statement) for statement in statements))
            return statements

        monkeypatch.setattr(glean_module, "_packed_arms", spying)
        monkeypatch.setattr(glean_module, "HEAD_BLOCKS", 1)
        result = await storage.glean(query="common anchor", limit=5)
        assert packed == [1]  # one arm: the second block of ``common``
        assert [(str(o.path), o.score) for o in result.observations] == [
            (str(o.path), o.score) for o in reference.observations
        ]
        await storage.close()


class TestProbes:
    async def test_a_wide_rung_that_runs_short_deepens_then_records(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(glean_module, "FUSION_K", 1)
        monkeypatch.setattr(glean_module, "PROBE_DEEPEN", 1)
        result = await storage.glean(query="tokens", limit=10)
        assert result.success is True
        [record] = result.errors
        assert record.kind == VFSErrorKind.truncated and record.severity == Severity.warning
        assert record.data == {"window": 1, "found": 1}
        assert "scope probe budget" in record.message
        await storage.close()

    async def test_a_narrow_rung_with_a_full_window_records_it(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        monkeypatch.setattr(glean_module, "FUSION_K", 1)
        result = await storage.glean(query="tokens", limit=3, globs=("src/**",))
        [record] = result.errors
        assert "candidate window" in record.message and record.data == {"window": 1, "found": 1}
        await storage.close()

    def test_round_two_arms_pack_under_the_parameter_budget(self) -> None:
        arms = [(3, true()), (3, true()), (5, true()), (2, true())]
        packed = glean_module._packed_arms(arms, 6)
        assert [len(statement) for statement in packed] == [2, 1, 1]
        assert glean_module._packed_arms([], 6) == []


class TestOverlay:
    async def test_a_never_indexed_store_serves_from_live_text(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        result = await storage.glean(query="tokens")
        assert result.success is True, result.errors
        assert _paths(result)[0] == "/notes.txt"
        [match] = result.observations[0].matches or []
        assert (match.start, match.end, match.content) == (1, 1, None)
        # The overlay's preview is cut from the body it already scored — no chunk row, no second read.
        assert match.preview == "A stream of **tokens**, **tokens**, **tokens**."
        assert (match.preview_start, match.preview_end) == (1, 1)
        assert result.lexical_stats["n_docs"] == 0  # ty: ignore[unresolved-attribute]
        await storage.close()

    async def test_a_written_file_with_a_new_word_is_found_before_reindex(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="zebra tokens\n")])).success
        result = await storage.glean(query="zebra")
        assert _paths(result) == ["/fresh.txt"]
        # The overlay and the index share one scale: the fresh row ranks among indexed rows.
        mixed = await storage.glean(query="tokens")
        assert "/fresh.txt" in _paths(mixed) and mixed.observations[0].score == 1.0
        await storage.close()

    async def test_a_dirty_row_out_of_scope_leaves_the_overlay_empty(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/docs/fresh.md"), content="tokens late\n")])).success
        admitted_sizes: list[int] = []
        real = glean_module._overlay

        async def spying(session, tables, profile, budget, executor, admitted, terms, stats):
            admitted_sizes.append(len(admitted))
            return await real(session, tables, profile, budget, executor, admitted, terms, stats)

        monkeypatch.setattr(glean_module, "_overlay", spying)
        result = await storage.glean(query="tokens", globs=("src/**",))
        assert set(_paths(result)) == {"/src/lexer.py", "/src/parser.py"}
        assert admitted_sizes == [0]  # the scan ran and nominated nothing in scope
        await storage.close()

    async def test_the_overlay_budget_truncates_loudly(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = await _fresh(tmp_path)
        monkeypatch.setattr(glean_module, "OVERLAY_BUDGET", 2)
        result = await storage.glean(query="tokens")
        assert result.success is True
        [record] = result.errors
        assert record.kind == VFSErrorKind.truncated and record.data == {"scanned": 2, "budget": 2}
        await storage.close()

    async def test_a_rival_publish_between_the_reads_is_redriven(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        moves = {"n": 0}

        async def rival() -> None:
            if moves["n"] == 0:
                moves["n"] += 1
                assert (await storage.reindex()).success is True

        with installed("glean:after-pointer-read", rival):
            result = await storage.glean(query="tokens")
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
        real = glean_module.pointer_with_overlay
        calls = {"n": 0}

        async def blind_preamble(session, tables):
            calls["n"] += 1
            pointer, overlay_empty = await real(session, tables)
            return (pointer, True) if calls["n"] == 1 else (pointer, overlay_empty)

        real_epoch = glean_module.current_epoch
        epoch_calls = {"n": 0}

        async def counting_epoch(session, tables):
            epoch_calls["n"] += 1
            return await real_epoch(session, tables)

        monkeypatch.setattr(glean_module, "pointer_with_overlay", blind_preamble)
        monkeypatch.setattr(glean_module, "current_epoch", counting_epoch)
        result = await storage.glean(query="tokens")
        assert result.success is True, result.errors
        assert "/fresh.txt" in _paths(result)
        assert calls["n"] == 2  # advisory, then authoritative
        assert epoch_calls["n"] == 1  # a rescued verdict is never skip-verified
        await storage.close()

    async def test_a_pointer_that_never_settles_classifies_conflict(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage = await _indexed(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        real = glean_module.current_epoch
        calls = {"n": 0}

        async def always_moving(session, tables):
            calls["n"] += 1
            return ((await real(session, tables)) or 0) + calls["n"]

        monkeypatch.setattr(glean_module, "current_epoch", always_moving)
        result = await storage.glean(query="tokens")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.conflict and result.errors[0].retryable is True
        await storage.close()

    def test_overlay_blocks_take_decoded_bodies_and_local_statistics(self) -> None:
        assert glean_module._text(b"alpha beta") == glean_module._text("alpha beta") == "alpha beta"
        docs = [(1, "alpha beta"), (2, "beta beta gamma")]
        blocks, idfs, avg_dl = glean_module._overlay_blocks(
            docs, ["beta", "delta"], TermStatistics({}, 0, 0.0, 1.2, 0.75)
        )
        assert [block.term for block in blocks] == [0]  # delta occurs nowhere: no block
        assert blocks[0].doc_ids == encode_block([1, 2], [1, 2], [2, 3])[0]
        assert avg_dl == 2.5 and idfs[0] == pytest.approx(0.1823, abs=1e-3)
        assert idfs[1] > idfs[0]  # the rarer term (absent) takes the higher idf
        blocks, idfs, avg_dl = glean_module._overlay_blocks([], ["beta"], TermStatistics({}, 0, 0.0, 1.2, 0.75))
        assert blocks == [] and avg_dl == 0.0 and len(idfs) == 1

    async def test_an_overlay_hit_spans_its_whole_body_and_previews_the_best_window(self, tmp_path: Any) -> None:
        body = "".join(f"line {i} of prose\n" for i in range(1, 9)) + "the lantern line\nlast line\n"
        storage = await _fresh(tmp_path, {"/fresh.md": body})
        [row] = (await storage.glean(query="lantern")).observations
        [match] = row.matches or []
        assert (match.start, match.end, match.content) == (1, 10, None)
        assert match.preview is not None and match.preview.endswith("line 8 of prose\nthe **lantern** line")
        assert (match.preview_start, match.preview_end) == (6, 9)  # the earliest window holding the hit
        await storage.close()


class TestBudgets:
    async def test_an_expired_wall_budget_truncates_and_skips_the_overlay(self, tmp_path: Any) -> None:
        storage = await _indexed(tmp_path, glean_wall_seconds=1e-9)
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="tokens late\n")])).success
        result = await storage.glean(query="tokens")
        assert result.success is True
        assert any("wall-time budget" in e.message for e in result.errors)
        assert "/fresh.txt" not in _paths(result)
        await storage.close()

    async def test_traits_declare_the_lexical_leg_and_its_overlay(self, tmp_path: Any) -> None:
        storage = await _fresh(tmp_path)
        traits = storage.traits()
        assert traits["glean_signals"] == "lexical" and traits["glean_staleness"] == "overlay"
        await storage.close()
