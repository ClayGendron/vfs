# 059 — Identity Model Decision (pointer)

- **Status:** landed 2026-07-14 as ADR
  `context/decisions/004-stable-node-identity.md`
- **Date:** 2026-07-14
- **Owner:** Clay Gendron
- **Kind:** decision record (no code)

This reserved slot from the stable-ID series (learnings 2026-07-08)
became an ADR rather than a story: ULID logical identity + integer
surrogate key, `parent_id` as the one structural pointer, path as
regenerable cache. See the ADR for the decision, options, and
consequences.

The schema deltas of reserved stories 060–063 are absorbed by story
072 (Stage-1 `rows.py` rewrite + Pass A); 064–066 (store namespace,
edge surfaces, vocab) remain future stories.
