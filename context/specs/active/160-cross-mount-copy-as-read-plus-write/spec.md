# 160 — Cross-mount copy: the router does read-plus-write for files, and says so when it did

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** feature (router: the two-path dispatch in `base.py`)
- **Depends on:** the two-path routing as built (`_route_pairs`, the
  `cross_mount` EXDEV refusal), 152 slice A (`Entry.data`, `write(data=…)`),
  161 if it lands first (the copy's write would mint a version row like
  any write).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  item 22.

## Intent

"Copy the course rubric into my files" is refused `cross_mount` today,
even when both mounts are writable, because a copy that spans two
storages cannot be one storage's atomic operation. That is the right
refusal for `move` (the EXDEV rule: no silent half-move) and the wrong
default for `copy` of a file, which is what every agent will try and
which `cp` has done across filesystems forever. The agent's workaround
is `read` then `write`, which works for text only; a binary body has
no text to carry.

One line: `copy` of a file across mounts is a read on one side and a
write on the other, done by the router, reported honestly.

## Decided semantics

1. **Files copy across mounts; directories do not.** For a `copy`
   whose source and destination resolve to different bindings, the
   router reads the source entry (`content` or `data`, whichever the
   source is) with the caller's authority, and writes it at the
   destination with the same authority through the destination's own
   gate. A directory source refuses `cross_mount` as today; a recursive
   cross-mount copy is a batch the caller composes from `tree` plus
   `copies=`.
2. **It is not atomic, and the result says so.** The observation
   carries an info record `copied across mounts: read /course/x,
   wrote /mine/x` so an audit reader can see it was two operations.
   A failed write after a successful read is the write's own
   classified error; nothing to roll back on the source.
3. **`move` is unchanged.** EXDEV stands for move; an agent that wants
   a cross-mount move does `copy` then `delete`, and the two results
   say which half happened.
4. **Permissions compose.** The read is gated by the source mount's
   map and the write by the destination's; a `read` mount can be a
   source and never a destination.

## Scope

- A cross-mount branch in `_route_pairs` for `copy` only; file-kind
  check; the read-then-write with both results merged into one.
- Batch `copies=` groups cross-mount pairs per destination binding so
  a 10,000-pair batch issues bounded writes (one write batch per
  destination mount, chunked as writes already are).
- Tests: text and bytes bodies; read-only source; directory source
  refused; a batch spanning three destinations counts three write
  dispatches.
- Out of scope: cross-mount `move`, edge copying across mounts
  (`mkedge` is already in-mount only), metadata beyond body and kind.
  `[NEEDS CLARIFICATION: do custom metadata and the entry's
  description travel with a cross-mount copy? In-mount copy today
  copies the row; leaning yes for parity.]`

## Acceptance criteria

- `copy(src="/course/rubric.md", dest="/mine/rubric.md")` with
  `/course` mounted `read` succeeds, and `read /mine/rubric.md`
  returns the rubric; the same for a PDF body.
- `copy(src="/mine/notes.md", dest="/course/notes.md")` refuses
  `read_only` at the destination.
- A directory source across mounts still refuses `cross_mount`;
  `move` across mounts still refuses `cross_mount`.
- `scripts/ci.sh 3.13` green.
