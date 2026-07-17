# 038 — Results

- **Date:** 2026-07-04
- **Status:** implemented; full `tests/` suite green (986 passed)

## Contract fix

`repro.py` case 1 (rebase overflow) no longer raises: `root.glob("**/*")`
returns `success=False` with the overflow row classified as a
`vfs.invalid` error carrying `{mount, local_path}` in `data`. Sibling rows
in the same child result survive. Covered by
`tests/test_base.py::test_fanout_rebase_overflow_classifies_instead_of_raising`
and `tests/test_results.py::TestRebaseOverflow`.

An existing `ResultError` whose own `path` would overflow rebases to
`path=None` with `{mount, local_path}` merged into `data` (decided during
implementation — the spec's text only kept message/`data` intact, which
could silently lose the location when `data` was empty).

## Microbenchmark (not a CI gate)

Same machine and shape as `repro.py` (`/mnt/data` mount, 33-char local
path), 200k iterations, branded inputs:

| primitive               | before (full gate) | after (brand by proof) |
| ----------------------- | ------------------ | ---------------------- |
| `Path.with_mount`       | ~7.0–7.2 µs/row    | ~0.49 µs/row (~15×)    |
| `Path.without_mount`    | ~7 µs/row (same gate) | ~0.51 µs/row        |
| raw `Path._brand` concat (floor) | ~0.15–0.19 µs/row | —              |

Per 10k-row merge the outbound rebase drops from ~70 ms to ~5 ms. The
remaining gap to the raw-concat floor is the idempotent `Path(mount)`
re-gate plus method-call overhead — acceptable; the mount is gated once
per `Result.with_mount` call, so per-row cost inside the router seam is
lower still.

## Also landed

`vfs/rows.py` entry-table columns now derive from the named constants:
path-shaped columns (`path`, `parent_dir`, `parent_file`, `source_path`,
`target_path`, `original_path`) use `MAX_PATH_LENGTH`; segment-shaped
columns (`name`, `edge_type`, `mime_type`) use `MAX_SEGMENT_LENGTH`.
`external_id`, `created_by`, and `owner_id` keep literal sizes — their
widths are not derived from path policy.
