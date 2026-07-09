"""Laws of the Result envelope: evidence in, verdict derived.

The algebra laws (L1-L5) pin ``|`` as a pure fold — associative,
idempotent over path-distinct rows, ``Result()`` identity, success a
homomorphism, rebase distributing over merge — and the wire round-trip
as value-preserving. The contract tests pin the kind vocabulary (retry
totality, prefix degradation, alias tombstones), severity semantics,
provenance stamping, overflow reconstruction, lenient parsing, boundary
rollup, and the zero-progress merge policy.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from vfs.models import Observation
from vfs.paths import MAX_PATH_LENGTH
from vfs.results import (
    KIND_CONTRACTS,
    Result,
    ResultError,
    RetryClass,
    Severity,
    VFSErrorKind,
    kind_family,
)
from vfs.results.envelope import _QUARANTINE_CLIP


def obs(path: str, **kwargs: object) -> Observation:
    return Observation.model_validate({"path": path, **kwargs})


def err(kind: VFSErrorKind | str = VFSErrorKind.timeout, message: str = "slow", **kwargs: object) -> ResultError:
    return ResultError.model_validate({"kind": kind, "message": message, **kwargs})


def err_multiset(errors: list[ResultError]) -> list[str]:
    """Order-insensitive value key — merge order may differ, facts may not."""
    return sorted(json.dumps(e.model_dump(mode="json"), sort_keys=True) for e in errors)


# A valid 1004-char local path; overflows once rebased under the 31-char mount.
DEEP_LOCAL = "/" + "/".join(["a" * 250] * 4)
LONG_MOUNT = "/" + "m" * 30


# ---------------------------------------------------------------------------
# Algebra laws — | is a pure fold; policy lives outside it
# ---------------------------------------------------------------------------


class TestAlgebraLaws:
    def test_l1_union_is_associative(self) -> None:
        a = Result(ops=("glob",), observations=[obs("/x.md", score=0.9)], errors=[err(message="a down")])
        b = Result(ops=("grep",), observations=[obs("/x.md", size_bytes=42), obs("/y.md")])
        c = Result(
            ops=("glob",), observations=[obs("/z.md")], errors=[err(kind=VFSErrorKind.not_found, message="gone")]
        )
        assert (a | b) | c == a | (b | c)

    def test_l2_union_is_idempotent_over_path_distinct_rows(self) -> None:
        a = Result(ops=("ls",), observations=[obs("/a.md"), obs("/b.md")], errors=[err()])
        assert a | a == a

    def test_l2_empty_result_is_the_identity(self) -> None:
        a = Result(ops=("grep",), observations=[obs("/a.md", score=0.5), obs("/a.md", score=0.1)], errors=[err()])
        assert Result() | a == a
        assert a | Result() == a

    def test_l3_success_is_a_homomorphism(self) -> None:
        ok = Result(observations=[obs("/a.md")])
        warned = Result(errors=[err(severity=Severity.warning)])
        failed = Result(errors=[err(kind=VFSErrorKind.unavailable, message="down")])
        for left, right in [(ok, warned), (ok, failed), (failed, warned), (failed, failed)]:
            assert (left | right).success == (left.success and right.success)

    def test_l4_rebase_distributes_over_merge(self) -> None:
        a = Result(ops=("glob",), observations=[obs("/x.md", score=0.9)], errors=[err(message="a down")])
        b = Result(ops=("glob",), observations=[obs("/x.md", size_bytes=42), obs("/y.md")])
        left = (a | b).with_mount("/m")
        right = a.with_mount("/m") | b.with_mount("/m")
        assert left.observations == right.observations
        assert left.success == right.success
        assert err_multiset(left.errors) == err_multiset(right.errors)

    def test_l4_rebase_distributes_including_overflow_rows(self) -> None:
        # The deep row rides both sides; its unaddressable warning must
        # collapse to one fact by value, not double as two.
        a = Result(observations=[obs(DEEP_LOCAL), obs("/ok.py")])
        b = Result(observations=[obs(DEEP_LOCAL)], errors=[err(message="b slow")])
        left = (a | b).with_mount(LONG_MOUNT)
        right = a.with_mount(LONG_MOUNT) | b.with_mount(LONG_MOUNT)
        assert left.observations == right.observations
        assert left.success == right.success
        assert err_multiset(left.errors) == err_multiset(right.errors)

    def test_l5_wire_round_trip_preserves_value(self) -> None:
        r = Result(
            ops=("grep",),
            observations=[obs("/a.md", score=0.9)],
            errors=[err(path="/a.md", source="/m", data={"retry_after_ms": 50})],
        )
        assert Result.from_payload(r.to_payload()) == r
        assert Result.from_payload(r.to_payload(exclude_none=False)) == r

    def test_l5_diamond_dedup_survives_the_wire(self) -> None:
        # (a|b)&b in-process and across one hop must agree — value
        # identity, not id() identity, is the dedup key.
        a = Result(ops=("ls",), errors=[err(kind=VFSErrorKind.not_found, message="a gone")])
        b = Result(ops=("ls",), errors=[err(message="b slow")])
        union = a | b
        in_process = (union & b).errors
        hopped = (Result.from_payload(union.to_payload()) & b).errors
        assert err_multiset(in_process) == err_multiset(hopped)
        assert len(hopped) == 2

    def test_identical_failures_from_two_mounts_stay_two_facts(self) -> None:
        # Equal kind/message, distinct source — provenance is what makes
        # equality-dedup lawful.
        dead_a = Result(errors=[err(message="down")]).with_mount("/a")
        dead_b = Result(errors=[err(message="down")]).with_mount("/b")
        assert len((dead_a | dead_b).errors) == 2


# ---------------------------------------------------------------------------
# Kind vocabulary — contract table, prefix dispatch, tombstones
# ---------------------------------------------------------------------------


class TestKindContracts:
    def test_contract_table_is_total_over_the_vocabulary(self) -> None:
        for kind in VFSErrorKind:
            contract = KIND_CONTRACTS[kind]
            assert isinstance(contract.retry_class, RetryClass)
            assert contract.hint
            assert contract.path_means

    def test_every_kind_is_its_own_family(self) -> None:
        for kind in VFSErrorKind:
            assert kind_family(kind) is kind

    def test_unknown_child_degrades_to_longest_known_prefix(self) -> None:
        assert kind_family("vfs.unavailable.dns") is VFSErrorKind.unavailable
        assert kind_family("vfs.unavailable.backend.tls") is VFSErrorKind.backend_unavailable
        assert err(kind="vfs.unavailable.dns").retry_class is RetryClass.transient

    def test_unknown_namespace_degrades_to_none_no_assumption(self) -> None:
        assert kind_family("x.acme.flaky") is None
        assert err(kind="x.acme.flaky").retry_class is None

    def test_retired_kind_string_parses_to_its_new_value(self) -> None:
        e = err(kind="vfs.backend_unavailable")
        assert e.kind is VFSErrorKind.backend_unavailable
        assert str(e.kind) == "vfs.unavailable.backend"
        assert kind_family("vfs.backend_unavailable") is VFSErrorKind.backend_unavailable


# ---------------------------------------------------------------------------
# Severity — unknown is never silently downgraded
# ---------------------------------------------------------------------------


class TestSeverity:
    def test_default_severity_is_error_and_fatal(self) -> None:
        e = err()
        assert e.severity is Severity.error
        assert e.is_fatal

    def test_warning_and_info_do_not_fail_the_envelope(self) -> None:
        r = Result(errors=[err(severity=Severity.warning), err(severity=Severity.info, message="skip")])
        assert r.success
        assert not r.failures
        assert len(r.warnings) == 1

    def test_unknown_severity_reads_as_error(self) -> None:
        e = err(severity="catastrophic")
        assert e.is_fatal
        assert not Result(errors=[e]).success

    def test_unknown_severity_round_trips_as_its_raw_string(self) -> None:
        e = err(severity="catastrophic")
        restored = ResultError.model_validate(e.model_dump(mode="json"))
        assert restored.severity == "catastrophic"
        assert restored == e


# ---------------------------------------------------------------------------
# Provenance — the rebase seam stamps source, structurally
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_with_mount_always_returns_a_copy(self) -> None:
        pathless = err()
        assert pathless.with_mount("/m") is not pathless
        assert pathless.with_mount("/m").source == "/m"

    def test_source_stamps_then_reroots_across_hops(self) -> None:
        e = err(path="/x").with_mount("/inner").with_mount("/outer")
        assert e.source == "/outer/inner"
        assert e.path == "/outer/inner/x"

    def test_root_mount_is_a_real_hop_for_provenance(self) -> None:
        assert err().with_mount("/").source == "/"
        r = Result(observations=[obs("/a.md")], errors=[err()]).with_mount("/")
        assert r.errors[0].source == "/"
        assert r.paths == ("/a.md",)

    def test_without_mount_inverts_with_mount(self) -> None:
        e = err(path="/x")
        assert e.with_mount("/m").without_mount("/m") == e
        r = Result(ops=("ls",), observations=[obs("/a.md")], errors=[err(path="/a.md")])
        assert r.with_mount("/m").without_mount("/m") == r

    def test_source_overflow_clamps_to_the_hop_mount(self) -> None:
        # The seam never raises; the nearest addressable locus wins.
        e = err(source=DEEP_LOCAL).with_mount(LONG_MOUNT)
        assert e.source == LONG_MOUNT


# ---------------------------------------------------------------------------
# Rebase overflow — loss on record, never failure, locus reconstructible
# ---------------------------------------------------------------------------


class TestRebaseOverflow:
    def test_overflow_row_becomes_unaddressable_warning_and_rows_survive(self) -> None:
        rebased = Result(ops=("glob",), observations=[obs(DEEP_LOCAL), obs("/ok.py")]).with_mount(LONG_MOUNT)
        assert rebased.success is True
        assert rebased.paths == (f"{LONG_MOUNT}/ok.py",)
        [warning] = rebased.errors
        assert warning.kind is VFSErrorKind.unaddressable
        assert warning.severity is Severity.warning
        assert warning.path is None
        assert warning.source == LONG_MOUNT
        assert str(MAX_PATH_LENGTH) in warning.message

    def test_row_at_exactly_the_limit_survives(self) -> None:
        mount = "/" + "m" * 19  # 20 + 1004 == 1024
        rebased = Result(observations=[obs(DEEP_LOCAL)]).with_mount(mount)
        assert rebased.errors == []
        assert len(rebased.paths[0]) == MAX_PATH_LENGTH

    def test_fit_then_overflow_records_the_entry_local_truth(self) -> None:
        # A path that fits early hops and overflows later must still
        # record the producing frame's path, not an already-rebased one.
        local = "/" + "/".join(["p" * 220] * 4)  # 884 chars
        m1, m2 = "/" + "a" * 100, "/" + "b" * 100
        assert len(m1) + len(local) <= MAX_PATH_LENGTH
        assert len(m2) + len(m1) + len(local) > MAX_PATH_LENGTH
        e = err(kind=VFSErrorKind.not_found, message="x", path=local).with_mount(m1).with_mount(m2)
        assert e.path is None
        record = (e.data or {})["vfs.overflow"]
        assert record["local_path"] == local
        assert str(e.source) + record["local_path"] == m2 + m1 + local

    def test_overflow_locus_reconstructs_after_three_hops(self) -> None:
        e = err(kind=VFSErrorKind.not_found, message="missing", path=DEEP_LOCAL)
        hopped = e.with_mount(LONG_MOUNT).with_mount("/b").with_mount("/c")
        assert hopped.path is None
        assert hopped.source == "/c/b" + LONG_MOUNT
        record = (hopped.data or {})["vfs.overflow"]
        assert str(hopped.source) + record["local_path"] == "/c/b" + LONG_MOUNT + DEEP_LOCAL

    def test_overflow_record_is_append_once(self) -> None:
        # The first hop's entry-local path is the truth; later hops must
        # re-root source, never clobber the record.
        e = err(path=DEEP_LOCAL, data={"vfs.overflow": {"local_path": "/already/recorded"}})
        rebased = e.with_mount(LONG_MOUNT)
        assert (rebased.data or {})["vfs.overflow"] == {"local_path": "/already/recorded"}

    def test_row_overflow_warning_source_rebases_on_later_hops(self) -> None:
        first = Result(observations=[obs(DEEP_LOCAL)]).with_mount(LONG_MOUNT)
        third = first.with_mount("/b").with_mount("/c")
        assert third.errors[0].source == "/c/b" + LONG_MOUNT
        assert third.success is True

    def test_rebase_is_pure(self) -> None:
        r = Result(observations=[obs(DEEP_LOCAL)])
        r.with_mount(LONG_MOUNT)
        assert r.paths == (DEEP_LOCAL,)
        assert r.errors == []


# ---------------------------------------------------------------------------
# Wire leniency — per-item quarantine, reconciliation, open fields
# ---------------------------------------------------------------------------


class TestWireLeniency:
    def test_corrupt_observation_quarantines_as_warning_and_siblings_survive(self) -> None:
        r = Result.from_payload(
            {
                "observations": [
                    {"path": "/good/row.txt", "kind": "file"},
                    {"path": "/bad/\x00row", "kind": "file"},
                ],
            }
        )
        assert r.paths == ("/good/row.txt",)
        assert r.success is True
        [quarantine] = r.errors
        assert quarantine.kind is VFSErrorKind.internal
        assert quarantine.severity is Severity.warning
        assert (quarantine.data or {})["vfs.quarantine"]["item"] == {"path": "/bad/\x00row", "kind": "file"}

    def test_corrupt_error_quarantines_at_error_severity(self) -> None:
        # An unreadable failure fact must not launder the envelope into
        # success.
        r = Result.from_payload({"errors": [{"message": "kindless"}]})
        assert r.success is False
        [quarantine] = r.errors
        assert quarantine.kind is VFSErrorKind.internal
        assert quarantine.is_fatal

    def test_strict_restores_raise_on_invalid(self) -> None:
        payload = {"observations": [{"path": "/bad/\x00row", "kind": "file"}]}
        with pytest.raises(ValidationError):
            Result.from_payload(payload, strict=True)

    def test_hopeless_payload_returns_fatal_internal_never_raises(self) -> None:
        for garbage in ("garbage", None, 42, ["not", "a", "mapping"]):
            r = Result.from_payload(garbage)
            assert r.success is False
            assert r.errors[0].kind is VFSErrorKind.internal

    def test_reconciliation_synthesizes_the_missing_failure(self) -> None:
        r = Result.from_payload({"success": False, "observations": [], "errors": []})
        assert r.success is False
        [synthesized] = r.errors
        assert synthesized.kind is VFSErrorKind.internal
        assert (synthesized.data or {})["vfs.claim"] == {"success": False}

    def test_reconciliation_skipped_when_a_fatal_error_survived(self) -> None:
        payload = {"success": False, "errors": [{"kind": "vfs.timeout", "message": "slow"}]}
        r = Result.from_payload(payload)
        assert r.success is False
        assert len(r.errors) == 1

    def test_claimed_success_is_ignored_and_rederived(self) -> None:
        payload = {"success": True, "errors": [{"kind": "vfs.timeout", "message": "slow"}]}
        assert Result.from_payload(payload).success is False

    def test_stored_success_is_unrepresentable_at_construction(self) -> None:
        # success= is no longer a field: the type checker rejects the
        # kwarg, and any dict form is stripped then re-derived.
        lying = Result.model_validate({"success": True, "errors": [err(kind=VFSErrorKind.not_found, message="gone")]})
        assert lying.success is False

    def test_smuggled_success_extra_never_reaches_the_wire(self) -> None:
        # model_copy/model_construct bypass validation; the wire dict
        # must still carry only the derived verdict.
        r = Result(errors=[err(kind=VFSErrorKind.not_found, message="gone")])
        for lying in (r.model_copy(update={"success": True}), Result.model_construct(errors=r.errors, success=True)):
            assert lying.success is False
            assert lying.to_payload()["success"] is False

    def test_oversized_quarantined_item_is_clipped(self) -> None:
        # Bound derives from the constant (+1 for the ellipsis) so the
        # clamp size can move without silently desyncing this pin.
        r = Result.from_payload({"observations": [{"path": "/bad/\x00row", "junk": "Q" * 5000}]})
        item = (r.errors[0].data or {})["vfs.quarantine"]["item"]
        assert isinstance(item, str)
        assert len(item) <= _QUARANTINE_CLIP + 1

    def test_malformed_envelope_field_salvages_validated_items(self) -> None:
        r = Result.from_payload(
            {
                "ops": "glob",
                "observations": [{"path": "/a.md"}, {"path": "/b.md"}],
                "errors": [{"kind": "vfs.timeout", "message": "slow"}],
            }
        )
        assert r.paths == ("/a.md", "/b.md")
        kinds = {str(e.kind) for e in r.errors}
        assert kinds == {"vfs.timeout", "vfs.internal"}
        assert r.success is False

    def test_novel_fields_survive_a_full_hop(self) -> None:
        payload = Result(ops=("read",), errors=[err()]).to_payload()
        payload["errors"][0]["trace_id"] = "abc"
        payload["peer_note"] = "from a newer peer"
        hopped = Result.from_payload(payload).to_payload()
        assert hopped["errors"][0]["trace_id"] == "abc"
        assert hopped["peer_note"] == "from a newer peer"

    def test_payload_success_is_the_derived_verdict(self) -> None:
        assert Result(errors=[err()]).to_payload()["success"] is False
        assert Result(errors=[err(severity=Severity.warning)]).to_payload()["success"] is True


# ---------------------------------------------------------------------------
# Boundary rollup — capped at the wire, never in the algebra
# ---------------------------------------------------------------------------


def outage(n: int) -> Result:
    merged = Result()
    for i in range(n):
        down = Result(errors=[err(kind=VFSErrorKind.backend_unavailable, message="down")])
        merged = merged | down.with_mount(f"/m{i}")
    return merged


class TestRollup:
    def test_rollup_groups_by_kind_and_severity(self) -> None:
        r = outage(5) | Result(errors=[err(severity=Severity.warning, message="slow")])
        payload = r.to_payload(max_errors=3)
        assert len(payload["errors"]) == 3  # outage head + rollup, warning group of one
        rollup = payload["errors"][1]
        assert rollup["data"]["vfs.rollup"]["count"] == 4
        assert len(rollup["data"]["vfs.rollup"]["sources"]) == 4

    def test_rollup_leaves_the_derived_verdict_invariant(self) -> None:
        r = outage(5)
        payload = r.to_payload(max_errors=2)
        assert payload["success"] == r.success
        assert Result.from_payload(payload).success == r.success

    def test_under_the_cap_nothing_rolls(self) -> None:
        r = outage(3)
        assert len(r.to_payload(max_errors=3)["errors"]) == 3

    def test_in_process_nothing_is_ever_dropped(self) -> None:
        assert len(outage(5).errors) == 5


# ---------------------------------------------------------------------------
# Merge policy — demotion only at the fan-out seam, zero-progress rule
# ---------------------------------------------------------------------------


class TestMergePolicy:
    def test_merge_is_the_plain_fold_no_demotion(self) -> None:
        live = Result(observations=[obs("/a.md")])
        dead = Result(errors=[err(kind=VFSErrorKind.backend_unavailable, message="down")])
        merged = Result.merge([live, dead], op="grep")
        assert merged.success is False
        assert merged.ops == ("grep",)

    def test_merge_branches_demotes_when_any_branch_progressed(self) -> None:
        live = Result(observations=[obs("/live/hit.txt")]).with_mount("/live")
        dead = Result(errors=[err(kind=VFSErrorKind.backend_unavailable, message="down")]).with_mount("/dead")
        merged = Result.merge_branches([live, dead], op="grep")
        assert merged.success is True
        assert merged.paths == ("/live/live/hit.txt",)
        [demoted] = merged.errors
        assert demoted.severity is Severity.warning
        assert demoted.kind is VFSErrorKind.backend_unavailable
        assert demoted.source == "/dead"
        assert demoted.retry_class is RetryClass.transient

    def test_merge_branches_stays_fatal_when_every_branch_failed(self) -> None:
        dead_a = Result(errors=[err(kind=VFSErrorKind.backend_unavailable, message="down")]).with_mount("/a")
        dead_b = Result(errors=[err(kind=VFSErrorKind.backend_unavailable, message="down")]).with_mount("/b")
        merged = Result.merge_branches([dead_a, dead_b], op="grep")
        assert merged.success is False
        assert all(e.is_fatal for e in merged.errors)

    def test_an_empty_successful_branch_counts_as_progress(self) -> None:
        empty = Result(ops=("grep",))
        dead = Result(errors=[err(kind=VFSErrorKind.backend_unavailable, message="down")])
        merged = Result.merge_branches([empty, dead], op="grep")
        assert merged.success is True
        assert merged.errors[0].severity is Severity.warning
