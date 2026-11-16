# The brief: the eight open kernel rulings, checked against the tree and the specs as they stand

The brief one researcher received on 2026-11-15, verbatim below the table. It serves roadmap story K1 in [the roadmap](../../../standards/roadmap.md): the kernel's public names and argument families are decided and written down once. The developer chose K1 as the next spec on 2026-11-15.

| File | What it is |
|---|---|
| `00-brief.md` | This brief. |
| `01-the-open-rulings-against-the-tree-and-the-specs.md` | The one study. |
| `experiments/adr-087-as-retired.md` | The retired record, as `git show 3667fec2^:context/decisions/087-the-kernel-is-the-gate-and-everything-under-it-and-every-front-is-a-facet.md` printed it. |

## The brief

You are the researcher for one study. The repository is vfs at `/Users/claygendron/Git/Repos/vfs`. Read `AGENTS.md` and `context/research/README.md` first; they bind you.

**The question.** A decision record, ADR 087 of 2026-10-24, set the kernel's shape in seventeen pins and left eight items for the developer to rule on. Decision records were retired from the tree on 2026-10-30 (commit `3667fec2`): decisions now live in the spec that carries them. Roadmap story K1 asks for those eight items ruled and written down, because roadmap stories K2 to K9 cannot freeze a public name until they are. The developer will rule on each item. Your study gives the developer, for each item, what is true today and what each choice costs, so each ruling is made on evidence and the spec that carries the rulings can be written from your file.

**The eight items**, from the record's "Pending Clay" list, which is in `experiments/adr-087-as-retired.md` beside this brief:

1. Pin 3: keep `delete` and `move` as the Python names, or rename to `remove` and `rename`. Roadmap decision D4, lean: keep.
2. Pin 12: a listing's resumption key as a field of `Result`, or a separate return. D6, lean: a field.
3. Pin 16: flat names with new arguments, or kernel groups as namespaces such as `vfs.query.grep`. D5, lean: flat.
4. Pin 17: when `move(replace=True)` lands on an occupant, the destination row's identity survives, or the source's. Lean: the destination's.
5. Pin 9: the 100 KB threshold above which the write-path hash runs on a worker thread, and whether an integrity failure is a kind of its own or a child of `unavailable`. D8, lean: the child kind `vfs.unavailable.integrity`, as spec 175 says.
6. Pin 10: the replay row's time to live (spec 177 leans 24 hours), and whether `idempotentHint` is withheld from a tool whose verb has one non-idempotent form. D11, lean: withhold.
7. Spec 174's fork: `overwrite=` leaves `write`, since `if_absent=True` is today's `overwrite=False`. D7, lean: yes.
8. Spec 180's fork: the hot window `PACK_HOT_ROWS` (lean 1) and the history verb's name (lean `versions`).

**What to find for each item.** Label every claim EXECUTED (a command ran and you report its output), READ (read in a file you cite by path and line, or by commit) or INFERRED (your reasoning).

- The live tree today: the signature, the constant or the error kind as it stands in `src/vfs`, by file and line. Verbs were renamed after the record was written (commits `280a983c`, `e90ec653`, and the two faces in `f9632d9c`), so read the code, never the record, for today's names.
- What each active spec says, and where two specs disagree. The specs that stand on the record are the numbered folders 167, 169, 171, 172 and 174 to 181 under `context/specifications/active/`. The roadmap says specs 167, 169 and 171 still write `overwrite=` where the record and spec 181 write `replace=`: count the occurrences, by file.
- What the earlier research already found, by memo and section: `context/research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md` and `context/research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`, with their studies folders. Cite them. Do not redo their prior-art work, and do not open the sibling reference clones: where the memos leave a gap on an item, say so in one sentence.
- What has changed since 2026-10-24 that bears on the item: a landed spec under `context/specifications/archive/`, a rename, a new public face, a new constitution or standards rule.
- What each choice costs, counted: the call sites, tests, docstrings, documentation pages and spec lines a rename or a removal would touch (EXECUTED, with the search you ran).
- Your lean, in one sentence with its reason, marked as a lean.

**Three further things.**

- A table of the record's seventeen pins: for each, whether the tree today agrees with it (built), has not built it, or contradicts it, with the file and line that shows it. The record is gone from the tree, so the K1 spec may have to carry the pins that still stand.
- Every place under `context/specifications/active/` and `context/standards/` that cites ADR 087 or another retired record for a kernel decision, counted by file, and whether the roadmap's "Architecture page 02" and its Open list still exist anywhere in the tree.
- Today's public surface: the verbs each of the two faces exposes, by name, with the count, and the error kinds, with the count.

**What you may and may not do.** Read anything in the repository. Run read-only commands: `git show`, `git log`, `git grep`, searches, and `uv run --no-sync python -c …` for introspection. Do not run pytest, Docker or any database: experiments are running on the four test engines right now and must not be disturbed. Do not change git state in any way: no checkout, restore, stash, commit, branch or worktree. Do not edit any file under `src/`, `tests/` or `context/` other than your one study file. Do not use the network.

**What to write.** One file, `01-the-open-rulings-against-the-tree-and-the-specs.md`, in this folder, written with the Write tool. Its shape: a title on line one; a first paragraph saying what was asked, against which commit (`git rev-parse HEAD`), and what was done; a line defining the three labels; one section per item in the order above; then the three further things; then a section "What this study did not reach"; then "One line". Every paragraph is one line of any length, with no hard wrapping. Links are relative Markdown links that resolve. The file holds no clarification marker, no to-be-decided note and no to-do note: where something is not known, say what would settle it. Write plainly: short sentences, one idea each.

**What to send back.** A short message: the path of the file, and for each of the eight items one line with today's state and your lean. Nothing else.
