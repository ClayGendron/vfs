# 020. Schema Format Version: Fixed at 1 Until First Release

- **Status:** accepted (2026-07-21, approved by Clay in session)
- **Date:** 2026-07-21
- **Deciders:** Clay Gendron
- **Decided by:** human (raised as a design question by the 077 code
  review; precedent commissioned and reviewed in-session)

## Context

`SCHEMA_FORMAT_VERSION` (currently 1) is stamped into the meta table at
provisioning and checked at adopt time; a mismatch classifies as
`schema_mismatch`. The 077 landing re-keyed every durable reference from
integer ids to ULID `entry_id` — an incompatible on-disk change — and
deliberately did not bump the constant, since no durable pre-077
databases exist. The review asked for the policy to be made explicit:
when does the number start moving, and what should the guard say?

The precedent (research memo
`2026-07-21-prior-art-design-review-notes.md`, §2): SQLite, Jackrabbit
Oak, and JuiceFS all treat their public format number as describing
*shipped* formats — SQLite's file formats 1–4 map 1:1 to released
versions; JuiceFS runs production at `MetaVersion = 1` today. Postgres
bumps on every incompatible development commit, but on a deliberately
*internal second counter* (`CATALOG_VERSION_NO`) kept beneath the
user-facing version. Every system refuses on mismatch — none silently
migrates — and the best guards are precise: found and expected values,
an actionable hint, directional messaging, and (Oak) a corrupt/impossible
stored value classified as corruption rather than as a version miss.

## Decision

1. **`SCHEMA_FORMAT_VERSION` stays 1 until the first release.**
   Pre-release incompatible schema changes do not bump it; a dev database
   that predates such a change is recreated, not versioned around. This
   is the SQLite/Oak/JuiceFS treatment of a public format number.
2. **From the first release on, every incompatible schema change bumps
   it by one.** "Incompatible" means an existing database would misread
   or miswrite under the new code — renames, re-keys, semantic changes to
   stored values. Additive, ignorable changes do not bump.
3. **The guard refuses; it never migrates silently.** On mismatch the
   error carries both versions and the remedy. When bumping begins, the
   guard grows two refinements from precedent: a corrupt or absent stored
   version classifies as corruption, not `schema_mismatch`; and the
   message is directional (store newer than code: upgrade the client;
   store older: migrate or recreate).
4. **If pre-release dev databases ever become a real hazard, add a
   second internal counter** (the Postgres `catversion` pattern) rather
   than moving the public number early. Not needed today.

## Consequences

- **Easier:** pre-release refactors stay cheap (no version churn, no
  migration theater for databases nobody holds); version 1 in the wild
  will mean exactly "the first released format".
- **Harder:** the release itself becomes a commitment point — the first
  post-release incompatible change must remember this record and bump;
  nothing mechanical enforces that yet.
- **Committed to:** the guard-refinement work in pin 3 lands with the
  first post-release bump, not before.
