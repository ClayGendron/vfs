# 070. Directories on the Road to a Visible Row Show as Bare Names

- **Status:** accepted 2026-09-28 (Clay, ruling on spec 058's open
  question Q1: "if there is a clear precedent we should follow it";
  the memo found the precedent split on this one point, and Clay took
  the recommendation). Refines ADR 065 rule 1 for directories.
- **Date:** 2026-09-28
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-28). Drafted by Claude from the
  memo `../research/2026-09-28-traverse-visibility-unix-plan9.md` and
  its executed study `../research/studies/2026-09-28-traverse-visibility/`.

## Context

ADR 065 made hidden rows absent: a row the caller may not read is not
found, never refused. Spec 058 applied that to directories too. So a
caller holding `read` on `/projects/alpha` and nothing else saw an
empty root: `ls /` showed nothing, and `ls /projects` answered
not-found.

Agents discover a mount by `ls /` and `tree /`. An empty root sends
them nowhere. Two special cases also fell out of the strict rule:
`tree /` returned rows whose parents it had not shown, and
`mkdir -p` over a hidden parent had no clean answer.

The memo studied Unix (V6, V7, Linux, FreeBSD), Plan 9 (the kernel,
lib9p, fossil, cwfs, kfs, exportfs), NFSv4, Windows, SharePoint,
Google Drive, S3 and mirage, with executed repros on macOS and Linux.
It found three clear precedents and one split:

- **Clear:** traverse, list and read are three separate rights, in
  every system studied.
- **Clear:** the check comes before the lookup. The kernel decides
  "may you go here?" before "is it here?", so a refusal never depends
  on whether the name exists.
- **Clear:** reaching a deep path needs no right on its ancestors.
- **Split:** whether a caller may *list* the ancestors of its grant.
  The operating systems and S3 leave it to an administrator; the
  sharing products (SharePoint, mirage) grant it automatically.

## Options considered

- **(a) Strict: ancestors stay hidden.** Safe, and what spec 058 said.
  Gives agents an empty root and keeps the `tree` and `mkdir -p`
  special cases.
- **(b) Traverse visibility from grant prefixes.** Shows every
  ancestor of every grant. Leaks: a grant on a path with no rows
  beneath it would reveal the ancestors' names, which are otherwise
  unknowable.
- **(b′) Traverse visibility from rows that exist.** Shows an
  ancestor only when a row the caller can see lies beneath it. The
  names shown are exactly the prefixes of paths the caller's own
  results already print, so it leaks nothing (a) does not.

## Decision

We chose **(b′)**.

1. **A directory is *on the road* when it is hidden and a row the
   caller can see lies beneath it.** The road is computed from rows
   that exist, never from grant prefixes alone: from the arm roots
   that exist, plus, for owned rows, a bounded byte-range probe
   beneath each candidate directory.
2. **A road directory shows as a bare name.** It appears in `ls`,
   `glob` and `tree` with path and kind only: no version, times, size,
   owner or child count. `stat` answers the same two fields. `read`
   answers what any directory answers (`wrong_kind`).
3. **Listing a road directory shows only its visible and road
   children.** Listings are trimmed, never refused (ADR 065's hiding
   family: access-based enumeration, `exportfs -P`, mirage).
4. **Every write beneath a road directory is `permission_denied`,
   decided on the directory before the target name is looked up.** An
   existing name and a fresh one answer alike, so the refusal reveals
   nothing about what the directory holds.
5. **A hidden directory with nothing visible beneath it stays absent**
   (ADR 065 rule 1): not found, exactly as a missing path.

## Consequences

- `ls /` and `tree /` show an agent the way to everything it can read.
- `tree` no longer returns orphans: each visible row's parents are on
  the road.
- The read verbs pay one extra step for hidden directories among
  their candidates: the road check. It is bounded by the candidate
  batch and chunked like every other membership list.
- Switching back to (a) later needs no security review: the two
  options carry the same information. Only what `ls`, `stat`, `tree`
  and `glob` show would change.
