# 160 — Cross-mount copy: the router does read-plus-write for files, and says so when it did

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo; revised 2026-10-08 after a review against `0760fe9` (the hook is `_route_two_path`; the read must project `data` and pick the body by `source`; no displacement; the metadata marker's premise was false; the result shape; the two groupings)
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (router: the two-path dispatch in `base.py`)
- **Depends on:** the two-path routing as built (`_route_pairs` coerces input, L2504; `_route_two_path` L2419–2477 groups per binding and fires the `cross_mount` EXDEV refusal at L2466–2472 before the source-binding gate at L2474), 152 slice A (`Entry(data=…)` derives `source="bytes"`, hash, size, sniffed mime and `render_status = "pending"`, `entry.py` L236–243; `Observation.data`, L443; a default `read` never fetches bytes and returns a bytes row's rendering as `content`, `reads.py` L100–117 and L525–539), 161 if it lands first (the copy's write would mint a version row like any write).
- **Research it stands on:** `../../../research/2026-10-08-smartowl-workspace-integration-issues.md` item 22.

## Intent

"Copy the course rubric into my files" is refused `cross_mount` today, even when both mounts are writable, because a copy that spans two storages cannot be one storage's atomic operation. That is the right refusal for `move` (the EXDEV rule: no silent half-move) and the wrong default for `copy` of a file, which is what every agent will try and which `cp` has done across filesystems forever. The agent's workaround is `read` then `write`, which works for text only; a binary body has no text to carry, and a naive read returns its rendering.

One line: `copy` of a file across mounts is a read on one side and a write on the other, done by the router, reported honestly.

## Decided semantics

1. **Files copy across mounts; directories do not.** For a `copy` whose source and destination resolve to different bindings, the router reads the source with the caller's authority and `columns={"kind", "source", "mime_type", "content", "data"}`, and builds the write `Entry` from `source`: `data=` for a bytes row, `content=` for a text row. The rendering of a bytes row is never the body; the destination re-renders (`render_status` starts `pending`, or inline under 159). The write goes through the destination's own gate with the same authority. A directory source refuses `cross_mount` as today; a recursive cross-mount copy is a batch the caller composes from `tree` (which returns `path` and `kind`) plus `copies=`, after `mkdir` of the destination directories.
2. **It is not atomic, and the result says so.** The returned result is the write's result relabelled `ops=("copy",)`: one observation per pair as the write minted it, `status="created"`. The read's observations are dropped. Each cross-mount observation is paired with an info record `ResultError(kind=cross_mount, severity=info, path=<dest>, data={"src": "/course/x", "dest": "/mine/x", "source": "bytes" | "text"})` so an audit reader can see it was two operations (precedent for named `data` on an info record: `indexing.py` L349–354). A read refusal (`not_found`, a visibility denial) is returned as the copy's error at the source path, and no write dispatches for that pair. A failed write after a successful read is the write's own classified error; nothing to roll back on the source.
3. **No displacement.** The router writes with `overwrite=False`, so an occupied destination refuses `exists` exactly as in-mount copy does (`topology.py` L590–593); the caller deletes first.
4. **`move` is unchanged.** EXDEV stands for move; an agent that wants a cross-mount move does `copy` then `delete`, and the two results say which half happened.
5. **Permissions compose.** The pair gates as two ops: `read` capability on the source binding; `write` capability and composed write permission at the destination rel. A `read` mount can be a source and never a destination. Validation stays up front: one bad pair, cross-mount or not, rejects the whole batch with nothing dispatched.
6. **Parity with in-mount copy on what travels.** Body and kind travel; `mime_type` travels as the declared type and the write sniffs it against the bytes; `ext` comes from the destination path; the owner is the writer and the posture is the destination's. Not carried: `external_id`, edges, and the render stamps. There is no description or custom-metadata column on the row, so nothing else exists to carry; the earlier marker on metadata is resolved.

## Scope

- A cross-mount branch in `_route_two_path` for `copy` only, taken where the EXDEV refusal fires today; the file-kind check.
- Cross-mount pairs group twice: by source binding for one batched `read` per source mount (`self.read(observations=…, columns=…)`, precedent `base.py` L1845), then by destination binding for one batched `write` per destination mount, chunked as writes already are. In-mount pairs in the same batch dispatch as today; all groups run under `_gather_settled` and merge.
- Honest profile, in the docstring, not as a limit: the in-mount copy pages bodies at `BLOB_PAGE_BYTES`; the router form holds every body of a batch in memory at once. The only body bound today is the destination engine's `ValueCap`, checked by the write, which rule 2 already covers.
- Tests: text and bytes bodies (the PDF case asserts `read(columns= {"data"})` at the destination returns equal bytes and `source == "bytes"`); read-only source; read-only destination; occupied destination; directory source refused; a batch spanning three destinations counts three `_dispatch_entry` write calls; `tests/base/test_dispatch.py` L169 (`test_two_path_cross_mount_rejected`) drops `copy` for files.
- On landing: remove the README's cross-mount Known-limits bullet (153).
- Out of scope: cross-mount `move`, edge copying across mounts (`mkedge` is already in-mount only).

## Acceptance criteria

- `copy(src="/course/rubric.md", dest="/mine/rubric.md")` with `/course` mounted `read` succeeds, and `read /mine/rubric.md` returns the rubric; the same for a PDF body, byte-equal at the destination.
- `copy(src="/mine/notes.md", dest="/course/notes.md")` refuses `read_only` at the destination; a copy onto an existing destination refuses `exists`.
- A directory source across mounts still refuses `cross_mount`; `move` across mounts still refuses `cross_mount`.
- `scripts/ci.sh 3.13` green.
