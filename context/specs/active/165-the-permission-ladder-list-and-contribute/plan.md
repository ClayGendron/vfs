# 165 — plan

## Approach

Bottom-up, three slices, each leaving the tree green. The pre-build
review (`04-spec-165-review-before-build.md`) set the order of slice A
and the shape of three legs in slice B; its three probe scripts become
the first tests of slice B.

1. **Slice A, the words and the table.** `grants.py` first (the
   `Literal`, the ranks, `POSTURE_LEVELS` removed), then every raw
   label and posture word in the test-support files and the one docs
   fence, then `params.py` derivations, then `ops.py` with `Needs` and
   `VERB_RUNGS` and its drift test, then the format bump. At the end of
   A the gates still carry literals but every literal has a table
   entry to move to, and the tree is green because the support
   constants moved with the ranks.
2. **Slice B, the storage half.** `Resolution` as a mapping that
   aliases pieces; `Visibility` with two compiles, `admits` returning a
   rung, `tombstones` taking a rung; the gate's three legs comparing
   rungs (the read leg, the occupied-creation leg, the road for `list`
   slots); the anonymous check moved into the gate and the view with
   the posture rows as its source; the listing verbs projecting bare
   at `< read`; `read` refusing; `grep` and `glean` at the `read` view;
   `rmedge`'s per-row target record; the trash view's bare tombstone.
3. **Slice C, tests, docs, amendments.** The road baseline as a pin,
   the three matrices, the search-verb tests, the anonymous shapes, the
   aliasing tests, the oracle and contract updates, the docs, the ADR
   status lines.

## Trade-offs taken

- **Two compiles in the view, not a per-span level inside `Rights`.**
  The range algebra stays flat; the cost is one more compile, whose
  pieces alias when unused.
- **Aliasing shares pieces, not objects.** A `Rights` admits by its
  own level; the review showed an aliased object hides every row a
  posture labels `list`.
- **The road stays a per-call derivation.** Compiling it would make
  the rights cache depend on ordinary writes.
- **Re-provision, not repair.** Every format bump before this one
  refused old mounts at first touch; a relabel door would be a
  whole-corpus transaction with no caller today.
- **`contribute` means edit-any, `add` means own-only.** The word's
  precedent (SharePoint, Drive) is edit-any; the sticky directory is
  `add`.
- **Close the `rmedge` leak here**, in `rmedge_rows`' own per-row
  shape, so a hidden and an absent target are indistinguishable at
  the row and at the batch.
- **The anonymous check moves to the target.** `_resolution` sees no
  path; only the gate and the view do.

## Risks

- `Visibility.admits` changing type touches twenty-one call sites; a
  missed comparison silently widens. Mitigation: a parity test that
  every listing verb's bare rows equal the oracle's `list` set, and
  the grep pin that no gate passes a level literal.
- The anonymous check per target adds one chunked posture-row read per
  gate call where today there is one root read; bounded, but measure
  the statement count in the scale pins.
- Spec 164 waits on this; its text "every row passing `admits`"
  becomes a rung comparison, a wording change only.
