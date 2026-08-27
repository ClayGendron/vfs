# 044. Read-Path Coherence Without Locks: the Advisory/Authoritative Two-Read Protocol

- **Status:** accepted 2026-08-18 — spec 107's decision set, written
  at the 107–116 mining pass (2026-08-19). Repairs ADR 042's
  emptiness-gate consequence (ADR 042 carries the amendment note);
  every statement shape and cost figure of ADR 042 stands.
- **Date:** 2026-08-18
- **Deciders:** Clay Gendron (the selecting constraint: no repair may
  hold a lock or make a writer wait, even milliseconds); the protocol
  shape chosen against the campaign's executed evidence.
- **Context source:** the 2026-08-18 glob/grep review campaign
  (`../research/2026-08-18-glob-grep-review-campaign.md`, finding 1 —
  the range's one critical defect, executed on live SQL Server and
  Oracle) and its decision pass. Implemented by spec 107; the
  remediation-landing review
  (`../research/2026-08-18-remediation-landing-review.md`) re-raced
  the protocol clean on both engines.

## Context

ADR 042's overlay-emptiness gate read its verdict in grep's preamble
and treated it as same-snapshot with the index-tier statements it
authorized skipping the scan for. That holds only under a
repeatable-read pin. On SQL Server's default READ COMMITTED, Oracle's
per-statement consistency, and the GENERIC floor, a rival write
committing a demotion (`encoded = False`) between the verdict and the
candidate fetch left the row excluded from the index side with the
scan tier that owns it never run — `success=True`, the row silently
missing. A seam-staged race lost 1 of 3 rows on SQL Server and Oracle;
a hook-free natural race lost a row in 7 of 12 rounds on SQL Server.
The pointer-only recheck cannot see it: a content write demotes the
flag but moves no epoch pointer.

## Options considered

- **Per-engine isolation pins** — SQL Server's lock-free SNAPSHOT
  needs a database-level option vfs cannot impose; its REPEATABLE READ
  fallback takes shared locks that block writers. Rejected by the
  constraint.
- **A writer-maintained overlay generation** on the meta row — turns
  one row into a hotspot every write transaction serializes on.
  Rejected by the constraint.
- **Fusing the EXISTS into the candidate fetch** — a single statement
  is not point-in-time consistent under locking READ COMMITTED.
  Rejected as unsound.
- **Disabling the gate on unpinned engines** — sound, but forfeits the
  skip and forks the dialects; strictly dominated by the choice below.
- **Read the authoritative verdict after the reads it vouches for** —
  chosen.

## Decision

1. **The preamble verdict is advisory; the verdict that authorizes
   skipping the scan tier is read after every index-tier statement it
   vouches for.** A non-empty preamble verdict routes the call onto
   the scan path unchanged. An empty one defers: after the ladder and
   candidate fetch the combined pointer + EXISTS statement is
   re-issued, and that read doubles as the epoch recheck. Empty again
   → skip; non-empty → a rival demotion landed mid-call, so the scan
   tier runs before assembly; pointer moved at either read →
   `StaleSnapshot`, the existing redrive.
2. **Soundness needs no isolation assumption.** The argument requires
   only that a statement never sees *less* than what was committed
   when it began — true on every engine class vfs serves, the GENERIC
   floor included. No dialect fork, no profile field.
3. **Cost neutrality on the common paths is a law, proven by a bench
   gate.** The skip path issues two combined reads where it issued one
   combined read plus one pointer recheck; the scan path is unchanged;
   the only new work is one scan-tier run when a demotion actually
   landed mid-call. Measured: write path −0.6 % (noise), zero-hit
   floor 41.6 → 42.0 ms, raced path 43.2 ms — the correctness price
   is ~1 ms.

## Consequences

- The read path's coherence story is now "no locks, no writer
  involvement, authority read last" — the posture any future
  staleness gate on this backend must meet.
- The false-empty class is structurally closed; the rescued-path
  epoch recheck is pinned by a counting spy (spec 113) because a
  `skip_verified` mutant survived the suite on engines whose race
  rival is a write.
- ADR 042's trash-stamping fork (delete setting `encoded = True`)
  stays open and untouched; it would shrink the overlay the advisory
  read routes to the scan path.
