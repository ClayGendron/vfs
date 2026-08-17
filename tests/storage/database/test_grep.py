"""The grep pipeline against real sqlite rows: gate, ladder, overlay, budgets.

Direct backend tests — capability declaration is a router concern, so
these rows call ``storage.grep`` straight through the seam. The scan
side serves everything until ``reindex()`` runs, which is itself the
overlay contract: the same call must answer identically before and
after an index build, so several rows run their assertions in both
worlds.
"""

from __future__ import annotations

from time import monotonic
from typing import Any

import pytest
from sqlalchemy import func, select, update

from tests.support.database_helpers import _url
from vfs.models import Entry
from vfs.paths import Path
from vfs.pattern_matching import compile_filter
from vfs.results import Result, Severity, VFSErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import grep as grep_module
from vfs.storage.backends.database.seams import installed


async def _fresh(tmp_path, files: dict[str, str]) -> DatabaseStorage:
    storage = DatabaseStorage(url=_url(tmp_path))
    for path, content in files.items():
        assert (await storage.write(entries=[Entry(path=Path(path), content=content)], parents=True)).success is True
    return storage


def _paths(result: Result) -> list[str]:
    return [str(o.path) for o in result.observations]


class TestRefusalGate:
    async def test_uncompilable_pattern_classifies_invalid(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "body"})
        result = await storage.grep(pattern="(")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        await storage.close()

    async def test_defective_glob_classifies_invalid(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "body"})
        channels: tuple[dict[str, Any], ...] = ({"globs": ("a**b",)}, {"globs_not": ("x/",)})
        for channel in channels:
            result = await storage.grep(pattern="body", **channel)
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.invalid
        await storage.close()

    async def test_gramless_pattern_refuses_naming_the_scan_tier(self, tmp_path) -> None:
        # "ab" folds to two bytes — no trigram exists, so the index
        # cannot narrow it; the refusal names its own override.
        storage = await _fresh(tmp_path, {"/a.txt": "ab here"})
        result = await storage.grep(pattern="ab")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unindexable_pattern
        assert "allow_scan=True" in result.errors[0].message
        await storage.close()

    async def test_allow_scan_runs_the_refused_pattern_on_the_scan_tier(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "ab here", "/b.txt": "nothing"})
        result = await storage.grep(pattern="ab", allow_scan=True)
        assert result.success is True
        assert _paths(result) == ["/a.txt"]
        await storage.close()

    async def test_invert_match_is_scan_shaped_without_allow_scan(self, tmp_path) -> None:
        # The refusal gate is pattern-shaped: invert wants the
        # non-matches, which no occurrence index narrows, so the scan
        # tier runs without the opt-out even for a gramless pattern.
        storage = await _fresh(tmp_path, {"/a.txt": "keep\nzz gone"})
        result = await storage.grep(pattern="zz", invert_match=True)
        assert result.success is True
        matches = result.observations[0].matches
        assert matches is not None
        assert [m.content for m in matches] == ["keep"]
        await storage.close()

    async def test_allow_scan_after_reindex_still_scans_everything(self, tmp_path) -> None:
        # The opt-out runs the whole scope on the scan tier — encoded
        # entries included — so it can never lose an indexed row.
        storage = await _fresh(tmp_path, {"/a.txt": "ab here"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="ab", allow_scan=True)
        assert _paths(result) == ["/a.txt"]
        await storage.close()


class TestOverlayPartition:
    async def test_reindexed_content_serves_from_the_index_side(self, tmp_path) -> None:
        # After reindex the entry is encoded, which the scan side's
        # NOT-encoded partition excludes — the row can only have come
        # through the posting ladder.
        storage = await _fresh(tmp_path, {"/a.py": "needle body", "/b.py": "other body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle")
        assert result.success is True
        assert _paths(result) == ["/a.py"]
        await storage.close()

    async def test_dirty_and_encoded_entries_union_without_double_serving(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/clean.txt": "needle one", "/dirty.txt": "needle two"})
        assert (await storage.reindex()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/dirty.txt"), content="needle three")])).success is True
        result = await storage.grep(pattern="needle")
        assert _paths(result) == ["/clean.txt", "/dirty.txt"]
        await storage.close()

    async def test_invert_match_scans_everything_after_reindex(self, tmp_path) -> None:
        # invert is scan-shaped by construction: encoded rows must still
        # be scanned, so dropping invert from scan_all loses this row.
        storage = await _fresh(tmp_path, {"/with.txt": "needle here", "/without.txt": "clean body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle", invert_match=True)
        assert result.success is True
        assert _paths(result) == ["/without.txt"]
        await storage.close()

    async def test_fixed_strings_serves_encoded_rows_after_reindex(self, tmp_path) -> None:
        # The literal plan must nominate encoded rows too — the regex
        # metachar is literal text, and the index side owns the row now.
        storage = await _fresh(tmp_path, {"/dot.txt": "call a.b here", "/x.txt": "call axb here"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="a.b", fixed_strings=True)
        assert _paths(result) == ["/dot.txt"]
        await storage.close()

    async def test_word_regexp_serves_encoded_rows_after_reindex(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/word.txt": "the needle word", "/sub.txt": "needles inside"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle", word_regexp=True)
        assert _paths(result) == ["/word.txt"]
        await storage.close()

    async def test_stale_postings_cannot_resurrect_overwritten_content(self, tmp_path) -> None:
        # The old grams still sit in the published epoch, but the write
        # reset the flags: the index side drops the entry at the encoded
        # gate and the scan side sees only the fresh body.
        storage = await _fresh(tmp_path, {"/a.txt": "old needle"})
        assert (await storage.reindex()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="fresh body")])).success is True
        gone = await storage.grep(pattern="needle")
        assert gone.success is True
        assert gone.observations == []
        fresh = await storage.grep(pattern="fresh")
        assert _paths(fresh) == ["/a.txt"]
        await storage.close()

    async def test_alternation_plans_grams_per_branch(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "alpha body", "/b.txt": "beta body", "/c.txt": "gamma body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="alpha|beta")
        assert _paths(result) == ["/a.txt", "/b.txt"]
        await storage.close()

    async def test_an_absent_gram_short_circuits_to_empty(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "steady body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="zzzqqq")
        assert result.success is True
        assert result.observations == []
        await storage.close()

    async def test_disjoint_literal_runs_intersect_to_empty(self, tmp_path) -> None:
        # Both grams are indexed but no chunk holds both: the ladder's
        # intersection empties mid-way and short-circuits.
        storage = await _fresh(tmp_path, {"/a.txt": "abc alone", "/b.txt": "xyz alone"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="abc.*xyz")
        assert result.success is True
        assert result.observations == []
        await storage.close()

    async def test_readers_see_old_or_new_epoch_never_a_mix(self, tmp_path) -> None:
        # Mid-rebuild — next epoch's posting rows committed, publish not
        # yet run — grep answers exactly as before the build started.
        storage = await _fresh(tmp_path, {"/a.txt": "alphaone body"})
        assert (await storage.reindex()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="betatwo body")])).success is True
        posting = storage._host.tables.posting_list
        mid_window: list[tuple[list[str], list[str], int]] = []

        async def observe() -> None:
            fresh = await storage.grep(pattern="betatwo")
            stale = await storage.grep(pattern="alphaone")
            async with storage._host.engine.connect() as conn:
                staged = await conn.execute(select(func.count()).select_from(posting).where(posting.c.epoch == 2))
            mid_window.append((_paths(fresh), _paths(stale), staged.scalar_one()))

        with installed("reindex:before-publish", observe):
            assert (await storage.reindex()).success is True
        fresh_paths, stale_paths, staged_rows = mid_window[0]
        assert fresh_paths == ["/a.txt"]  # the old world: served by the scan overlay
        assert stale_paths == []
        assert staged_rows > 0  # the new epoch already sits in the table, unqueried
        published = await storage.grep(pattern="betatwo")
        assert _paths(published) == ["/a.txt"]
        await storage.close()

    async def test_a_corrupt_posting_blob_classifies_internal(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "needle body"})
        assert (await storage.reindex()).success is True
        posting = storage._host.tables.posting_list
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(posting).values(postings=b"\x05\x01"))
        result = await storage.grep(pattern="needle")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.internal
        await storage.close()


class TestStructuralGates:
    async def test_globs_admit_and_exclude_on_both_sides(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/src/a.py": "needle py", "/docs/b.txt": "needle txt"})
        for _ in range(2):
            kept = await storage.grep(pattern="needle", globs=("*.py",))
            assert _paths(kept) == ["/src/a.py"]
            dropped = await storage.grep(pattern="needle", globs_not=("*.py",))
            assert _paths(dropped) == ["/docs/b.txt"]
            anchored = await storage.grep(pattern="needle", globs=("/docs/**",))
            assert _paths(anchored) == ["/docs/b.txt"]
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_ext_filters_read_the_path_derived_extension(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.py": "needle", "/b.txt": "needle"})
        for _ in range(2):
            kept = await storage.grep(pattern="needle", ext=("py",))
            assert _paths(kept) == ["/a.py"]
            dropped = await storage.grep(pattern="needle", ext_not=(".PY",))
            assert _paths(dropped) == ["/b.txt"]
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_contradictory_glob_and_ext_is_clean_empty(self, tmp_path) -> None:
        # The derived ext of "*.py" contradicts ext=("txt",): every arm
        # is provably empty and the scan never touches a row.
        storage = await _fresh(tmp_path, {"/a.py": "needle"})
        result = await storage.grep(pattern="needle", globs=("*.py",), ext=("txt",))
        assert result.success is True
        assert result.observations == []
        await storage.close()

    async def test_meta_rows_need_a_meta_literal_gate(self, tmp_path) -> None:
        # Both worlds: the scan side excludes meta at SQL, while the
        # index side (meta content is chunked too) excludes it at the
        # authoritative Python gate — a wildcard head never lifts it.
        storage = await _fresh(tmp_path, {"/real.txt": "needle", "/.vfs/state/s.txt": "needle"})
        for _ in range(2):
            assert _paths(await storage.grep(pattern="needle")) == ["/real.txt"]
            lifted = await storage.grep(pattern="needle", globs=("/.vfs/**",))
            assert _paths(lifted) == ["/.vfs/state/s.txt"]
            wildcard = await storage.grep(pattern="needle", globs=("/.v*/**",))
            assert wildcard.observations == []
            assert (await storage.reindex()).success is True
        await storage.close()


class TestGlobChannelScoping:
    async def test_a_composed_glob_confines_the_scan_to_its_subtree(self, tmp_path) -> None:
        # Scope arrives purely as pattern text: the router's composed
        # glob confines candidates exactly as the old root channel did.
        storage = await _fresh(tmp_path, {"/data/a.txt": "needle", "/other/b.txt": "needle"})
        result = await storage.grep(pattern="needle", globs=("/data/**",))
        assert _paths(result) == ["/data/a.txt"]
        await storage.close()


class TestScopedNomination:
    """The allow-list joins nomination: budgets count scoped candidates."""

    async def test_scoped_recall_survives_a_saturated_budget(self, tmp_path, monkeypatch) -> None:
        # The pre-fix defect: the budget was spent on out-of-scope
        # candidates (lower doc ids) and the glob then discarded them —
        # silent recall loss. The allow-list intersects before the cut,
        # so every in-scope row survives and nothing truncates.
        monkeypatch.setattr(grep_module, "CANDIDATE_BUDGET", 5)
        files = {f"/bulk/f{i:02}.txt": "needle body" for i in range(10)}
        files |= {f"/scoped/g{i}.txt": "needle body" for i in range(3)}
        storage = await _fresh(tmp_path, files)
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle", globs=("scoped/**",))
        assert _paths(result) == [f"/scoped/g{i}.txt" for i in range(3)]
        assert result.errors == []
        await storage.close()

    async def test_an_unbounded_glob_arm_falls_back_whole(self, tmp_path) -> None:
        # "*.txt" yields no segment term: pruning is void for the call
        # and the ext/name facts alone narrow the fetch — same results.
        storage = await _fresh(tmp_path, {"/a/one.txt": "needle", "/a/two.py": "needle"})
        for _ in range(2):
            result = await storage.grep(pattern="needle", globs=("*.txt",))
            assert _paths(result) == ["/a/one.txt"]
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_a_dead_scope_short_circuits_the_index_side(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/src/a.txt": "needle"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle", globs=("nosuchdir/**",))
        assert result.success is True
        assert result.observations == []
        await storage.close()

    async def test_name_and_ext_facts_keep_the_dotfile_rescue(self, tmp_path) -> None:
        # "/src/.py" has a NULL stored ext; the pushdown's dot-suffix
        # arm must admit it exactly as the authority does.
        storage = await _fresh(tmp_path, {"/src/.py": "needle", "/src/real.py": "needle", "/src/off.txt": "needle"})
        for _ in range(2):
            result = await storage.grep(pattern="needle", globs=("src/*.py",))
            assert _paths(result) == ["/src/.py", "/src/real.py"]
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_basename_literal_scope_pins_the_name_column(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/src/Makefile": "needle", "/src/other.mk": "needle"})
        for _ in range(2):
            result = await storage.grep(pattern="needle", globs=("src/**/Makefile",))
            assert _paths(result) == ["/src/Makefile"]
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_stem_prefix_scope_rides_a_sargable_like(self, tmp_path) -> None:
        # The literal head escapes its LIKE metacharacters: a stored
        # name with "_" in the prefix must not wildcard-match.
        storage = await _fresh(tmp_path, {"/t/test_a.py": "needle", "/t/testXa.py": "needle", "/t/b.py": "needle"})
        for _ in range(2):
            result = await storage.grep(pattern="needle", globs=("t/test_*.py",))
            assert _paths(result) == ["/t/test_a.py"]
            assert (await storage.reindex()).success is True
        await storage.close()

    async def test_a_rename_is_visible_to_the_next_scoped_grep(self, tmp_path) -> None:
        # Segment postings are live truth while gram postings are
        # epoch-scoped: a rename lands in scope with no reindex between.
        storage = await _fresh(tmp_path, {"/old/a.txt": "needle"})
        assert (await storage.reindex()).success is True
        assert (await storage.move(operations=[ResolvedPair(src=Path("/old"), dest=Path("/new"))])).success is True
        found = await storage.grep(pattern="needle", globs=("new/**",))
        assert _paths(found) == ["/new/a.txt"]
        gone = await storage.grep(pattern="needle", globs=("old/**",))
        assert gone.observations == []
        await storage.close()


class TestOutputModes:
    async def test_context_windows_clamp_to_the_file(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "one\ntwo\nneedle\nfour\nfive"})
        result = await storage.grep(pattern="needle", before_context=2, after_context=1)
        matches = result.observations[0].matches
        assert matches is not None
        [match] = matches
        assert (match.start, match.match, match.end) == (1, 3, 4)
        assert match.content == "one\ntwo\nneedle\nfour"
        await storage.close()

    async def test_word_regexp_wraps_the_compiled_pattern(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/whole.txt": "cat scratched", "/sub.txt": "concatenate"})
        result = await storage.grep(pattern="cat", word_regexp=True)
        assert _paths(result) == ["/whole.txt"]
        await storage.close()

    async def test_max_count_caps_lines_mode_matches(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "needle\nplain\nneedle\nneedle"})
        result = await storage.grep(pattern="needle", max_count=2)
        matches = result.observations[0].matches
        assert matches is not None
        assert [m.match for m in matches] == [1, 3]
        await storage.close()

    async def test_files_mode_carries_neither_content_nor_matches(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "needle"})
        result = await storage.grep(pattern="needle", output_mode="files", columns=frozenset({"content"}))
        row = result.observations[0]
        assert row.content is None
        assert row.matches is None
        await storage.close()

    async def test_count_mode_reports_the_capped_hit_count_on_score(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "needle\nneedle\nneedle"})
        full = await storage.grep(pattern="needle", output_mode="count")
        assert full.observations[0].score == 3.0
        capped = await storage.grep(pattern="needle", output_mode="count", max_count=2)
        assert capped.observations[0].score == 2.0
        await storage.close()

    async def test_requested_content_column_rides_lines_mode_rows(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "needle body"})
        plain = await storage.grep(pattern="needle")
        assert plain.observations[0].content is None
        projected = await storage.grep(pattern="needle", columns=frozenset({"content"}))
        assert projected.observations[0].content == "needle body"
        await storage.close()


class TestBudgets:
    async def test_candidate_budget_truncates_with_a_warning(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(grep_module, "CANDIDATE_BUDGET", 1)
        storage = await _fresh(tmp_path, {"/a.txt": "needle", "/b.txt": "needle"})
        result = await storage.grep(pattern="needle", allow_scan=True, globs=("*.txt",))
        assert result.success is True
        assert len(result.observations) == 1
        [warning] = result.errors
        assert warning.kind == VFSErrorKind.truncated
        assert warning.severity is Severity.warning
        assert "narrow the pattern" in warning.message
        await storage.close()

    async def test_candidate_budget_also_caps_the_index_side(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(grep_module, "CANDIDATE_BUDGET", 1)
        storage = await _fresh(tmp_path, {"/a.txt": "needle one", "/b.txt": "needle two"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle")
        assert result.success is True
        assert len(result.observations) == 1
        assert any(e.kind == VFSErrorKind.truncated for e in result.errors)
        await storage.close()

    async def test_wall_time_budget_truncates_between_stages(self, tmp_path) -> None:
        # The budget is a constructor knob (default WALL_TIME_BUDGET); a
        # vanishing one expires before the first stage and truncates all.
        storage = DatabaseStorage(url=_url(tmp_path), grep_wall_seconds=1e-9)
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle")], parents=True)).success
        result = await storage.grep(pattern="needle")
        assert result.success is True
        assert result.observations == []
        assert {e.kind for e in result.errors} == {VFSErrorKind.truncated}
        await storage.close()

    def test_a_non_positive_wall_budget_refuses_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="grep_wall_seconds"):
            DatabaseStorage(url=_url(tmp_path), grep_wall_seconds=0)

    async def test_posting_byte_budget_narrows_the_gram_choice_soundly(self, tmp_path, monkeypatch) -> None:
        # A budget too small for a second blob still intersects the
        # rarest gram alone — a superset the verifier then narrows.
        monkeypatch.setattr(grep_module, "POSTING_BYTE_BUDGET", 1)
        storage = await _fresh(tmp_path, {"/a.txt": "needle body", "/b.txt": "other body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="needle")
        assert _paths(result) == ["/a.txt"]
        assert result.errors == []
        await storage.close()

    async def test_every_or_branch_gets_its_exempt_rarest_blob(self, tmp_path, monkeypatch) -> None:
        # The first-gram exemption is per branch: an exhausted byte
        # budget must not silently drop a later branch's only blob.
        monkeypatch.setattr(grep_module, "POSTING_BYTE_BUDGET", 1)
        storage = await _fresh(tmp_path, {"/a.txt": "alpha_first body", "/b.txt": "omega_second body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="alpha_first|omega_second")
        assert _paths(result) == ["/a.txt", "/b.txt"]
        assert result.errors == []
        await storage.close()

    async def test_an_expired_deadline_stops_the_branch_union(self, tmp_path) -> None:
        # The deadline is consulted between OR branches: an expired
        # union fetches nothing more and the call truncates loudly.
        storage = DatabaseStorage(url=_url(tmp_path), grep_wall_seconds=1e-9)
        entries = [
            Entry(path=Path("/a.txt"), content="alpha_first"),
            Entry(path=Path("/b.txt"), content="omega_second"),
        ]
        assert (await storage.write(entries=entries, parents=True)).success is True
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="alpha_first|omega_second")
        assert result.success is True
        assert result.observations == []
        assert {e.kind for e in result.errors} == {VFSErrorKind.truncated}
        await storage.close()

    async def test_a_saturated_index_side_names_the_skipped_overlay(self, tmp_path, monkeypatch) -> None:
        # Index candidates alone fill the budget: the scan overlay is
        # never consulted, so the fresh dirty file is honestly absent
        # and the truncation record names the skipped overlay.
        monkeypatch.setattr(grep_module, "CANDIDATE_BUDGET", 2)
        storage = await _fresh(tmp_path, {"/a.txt": "needle one", "/b.txt": "needle two", "/c.txt": "needle three"})
        assert (await storage.reindex()).success is True
        assert (await storage.write(entries=[Entry(path=Path("/fresh.txt"), content="needle four")])).success is True
        result = await storage.grep(pattern="needle")
        assert result.success is True
        assert "/fresh.txt" not in _paths(result)
        [warning] = [e for e in result.errors if e.kind == VFSErrorKind.truncated]
        assert "overlay not consulted" in warning.message
        await storage.close()

    async def test_content_is_fetched_in_byte_budgeted_batches(self, tmp_path, monkeypatch) -> None:
        # Three ~30-byte bodies under a 64-byte budget: the fetch must
        # split, and no batch may exceed the budget (singletons exempt).
        monkeypatch.setattr(grep_module, "CONTENT_BYTE_BUDGET", 64)
        batches: list[list[str]] = []
        real = grep_module._content_for_entries

        async def recording(session, tables, membership_budget, entry_ids):
            batches.append(list(entry_ids))
            return await real(session, tables, membership_budget, entry_ids)

        monkeypatch.setattr(grep_module, "_content_for_entries", recording)
        files = {f"/f{i}.txt": f"needle padding padding {i:04d}" for i in range(3)}
        storage = await _fresh(tmp_path, files)
        result = await storage.grep(pattern="needle")
        assert len(result.observations) == 3
        assert len(batches) > 1
        assert all(len(batch) < 3 for batch in batches)
        await storage.close()

    async def test_an_expired_deadline_fetches_no_content_at_all(self, tmp_path, monkeypatch) -> None:
        # The deadline is consulted before each fetch batch: an expired
        # call must stop cold, never materialize one more body.
        fetches: list[object] = []
        real = grep_module._content_for_entries

        async def counting(session, tables, membership_budget, entry_ids):
            fetches.append(entry_ids)
            return await real(session, tables, membership_budget, entry_ids)

        monkeypatch.setattr(grep_module, "_content_for_entries", counting)
        storage = DatabaseStorage(url=_url(tmp_path), grep_wall_seconds=1e-9)
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="needle")], parents=True)).success
        result = await storage.grep(pattern="needle")
        assert result.observations == []
        assert fetches == []
        await storage.close()

    async def test_count_mode_verdicts_carry_no_body(self, tmp_path) -> None:
        # files/count retain only the verdict: even an explicit content
        # projection must not ship bodies the mode cannot report.
        storage = await _fresh(tmp_path, {"/a.txt": "needle\nneedle"})
        result = await storage.grep(pattern="needle", output_mode="count", columns=frozenset({"content"}))
        assert result.observations[0].score == 2.0
        assert result.observations[0].content is None
        await storage.close()


class TestEpochLadder:
    async def test_a_moved_pointer_redrives_the_call_once(self, tmp_path, monkeypatch) -> None:
        # The re-read sees the pointer move on attempt one; the redrive
        # re-reads everything from current state and serves correctly.
        storage = await _fresh(tmp_path, {"/a.txt": "needle body"})
        assert (await storage.reindex()).success is True
        real = grep_module.current_epoch
        calls = {"n": 0}

        async def moved_once(session, tables):
            calls["n"] += 1
            current = await real(session, tables)
            if calls["n"] == 2:  # the first attempt's post-ladder re-read
                return (current or 0) + 1
            return current

        monkeypatch.setattr(grep_module, "current_epoch", moved_once)
        result = await storage.grep(pattern="needle")
        assert result.success is True
        assert _paths(result) == ["/a.txt"]
        assert calls["n"] == 4  # two pointer reads per attempt: exactly one redrive
        await storage.close()

    async def test_a_pointer_that_never_settles_classifies_conflict(self, tmp_path, monkeypatch) -> None:
        # Bounded retries, then loud: the exhausted redrive leaves as a
        # retryable conflict, never a silent empty success.
        storage = await _fresh(tmp_path, {"/a.txt": "needle body"})
        assert (await storage.reindex()).success is True
        real = grep_module.current_epoch
        calls = {"n": 0}

        async def always_moving(session, tables):
            calls["n"] += 1
            return ((await real(session, tables)) or 0) + calls["n"]

        monkeypatch.setattr(grep_module, "current_epoch", always_moving)
        result = await storage.grep(pattern="needle")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.conflict
        assert result.errors[0].retryable is True
        await storage.close()

    async def test_scan_only_calls_never_touch_the_pointer(self, tmp_path, monkeypatch) -> None:
        # scan_all reads no epoch-dependent partition: neither the
        # initial pointer read nor the re-read should ever run.
        storage = await _fresh(tmp_path, {"/a.txt": "needle body"})
        calls = {"n": 0}
        real = grep_module.current_epoch

        async def counting(session, tables):
            calls["n"] += 1
            return await real(session, tables)

        monkeypatch.setattr(grep_module, "current_epoch", counting)
        result = await storage.grep(pattern="needle", invert_match=True)
        assert result.success is True
        assert result.observations == []
        assert calls["n"] == 0
        await storage.close()


class TestSnapshotState:
    async def test_grep_before_any_reindex_serves_from_the_scan_side(self, tmp_path) -> None:
        # No published epoch: the index side is empty by construction
        # and the NOT-encoded partition owns the whole store.
        storage = await _fresh(tmp_path, {"/a.txt": "needle"})
        meta = storage._host.tables.meta
        async with storage._host.engine.connect() as conn:
            assert (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one() is None
        result = await storage.grep(pattern="needle")
        assert _paths(result) == ["/a.txt"]
        await storage.close()

    async def test_smart_case_judges_the_raw_pattern(self, tmp_path) -> None:
        storage = await _fresh(tmp_path, {"/a.txt": "Hello World"})
        insensitive = await storage.grep(pattern="hello", case_mode="smart")
        assert _paths(insensitive) == ["/a.txt"]
        sensitive = await storage.grep(pattern="Hello", case_mode="smart")
        assert _paths(sensitive) == ["/a.txt"]
        miss = await storage.grep(pattern="HELLO", case_mode="smart")
        assert miss.observations == []
        await storage.close()

    async def test_folded_planning_survives_case_sensitive_verification(self, tmp_path) -> None:
        # The index stream is folded; the verifier is not. A sensitive
        # search for the exact case must come back through the ladder.
        storage = await _fresh(tmp_path, {"/a.txt": "Needle body", "/b.txt": "needle body"})
        assert (await storage.reindex()).success is True
        result = await storage.grep(pattern="Needle")
        assert _paths(result) == ["/a.txt"]
        await storage.close()


class TestScanMergeBounds:
    async def test_an_expired_deadline_stops_the_arm_chunk_loop(self, tmp_path) -> None:
        # The loop consults the deadline before each chunk: an expired
        # scan issues no statements and nominates nothing.
        storage = await _fresh(tmp_path, {"/a.txt": "needle one", "/b.txt": "needle two"})
        host = storage._host
        gates = [compile_filter("*.txt", ())]
        async with host.session_factory() as session:
            nominated, overflow = await grep_module._entries_for_scan(
                session,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                gates,
                frozenset(),
                everything=True,
                fetched=frozenset({"path"}),
                limit=10,
                deadline=-1.0,
            )
        assert nominated == []
        assert overflow is False
        await storage.close()

    async def test_the_merge_prunes_to_the_lowest_paths_across_chunks(self, tmp_path, monkeypatch) -> None:
        # Two arm chunks each return limit+1 rows: the merge must hold
        # only the lowest limit+1 paths, and truncate with overflow.
        monkeypatch.setattr(grep_module, "arm_budget", lambda profile, parameter_budget, arm_binds: 1)
        files = dict.fromkeys(("/a1.txt", "/a2.txt", "/b1.log", "/b2.log"), "needle body")
        storage = await _fresh(tmp_path, files)
        host = storage._host
        gates = [compile_filter("*.txt", ()), compile_filter("*.log", ())]
        async with host.session_factory() as session:
            nominated, overflow = await grep_module._entries_for_scan(
                session,
                host.tables,
                host.profile,
                host.parameter_budget,
                host.membership_budget,
                gates,
                frozenset(),
                everything=True,
                fetched=frozenset({"path"}),
                limit=1,
                deadline=monotonic() + 60,
            )
        assert [m["path"] for m in nominated] == ["/a1.txt"]
        assert overflow is True
        await storage.close()
