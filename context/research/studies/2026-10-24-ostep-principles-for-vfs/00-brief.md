# Brief: what should vfs adopt from *Operating Systems: Three Easy Pieces*?

- **Date:** 2026-10-24
- **Asked by:** Clay Gendron. His words: "have opus agents take
  different sections of it and write up what principles, verbs, nouns,
  etc that vfs should adopt and build around."
- **Source:** Arpaci-Dusseau and Arpaci-Dusseau, *Operating Systems:
  Three Easy Pieces* (OSTEP), version 1.10, the PDF Clay downloaded on
  2026-10-23. Text extracted with `pdftotext -layout` and split by
  chapter into eight section files in the session scratchpad. The book
  is free to read and is cited here. **Never quote the book.** No
  sentences, no phrases in quotation marks, no copied tables or
  figures. Paraphrase every idea in your own words and cite the chapter
  and page it came from (Clay, 2026-10-24).
- **Why now:** yesterday's memo
  `context/research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  recommends splitting vfs into a kernel (the gate, the file
  operations, the query, history and rights operations) and facets over
  it (fronts and derived verbs). Before writing that ADR, Clay wants
  the textbook's principles laid against vfs.

## What vfs is today (read these before writing)

- `CLAUDE.md` (production posture, two audiences, the 10,000-row
  batch contract, never assume SQLite).
- `src/vfs/base.py` module docstring and the public method list
  (`VirtualFileSystem`: the router and the gate).
- `src/vfs/storage/protocol.py` (the storage seam, `Supports*`).
- `src/vfs/results/` (`Result`, `Observation`, `ErrorKind`).
- `context/README.md` (the pipeline) and the memo named above (§0,
  §4 especially; it is the design the study informs).
- Skim `context/decisions/` titles (`ls context/decisions`) so a
  principle the repo already decided is cited as such, not rediscovered.

## What each study must produce

One file, `context/research/studies/2026-10-24-ostep-principles-for-vfs/<NN>-<slug>.md`,
with these sections in this order:

1. **What the chapters say** (short; one paragraph per chapter; the
   crux of each chapter in the book's own framing).
2. **Principles vfs should adopt**, as a numbered list. Each item:
   the principle in one sentence; the chapter and page it comes from;
   whether vfs already follows it (cite the file, ADR or spec), half
   follows it, or does not; and the one concrete change to vfs it
   implies, if any.
3. **Nouns and verbs.** A table of the chapter's nouns (inode, fd,
   superblock, journal, cursor, lease, ...) and verbs (open, read,
   fsync, rename, ...), with vfs's name for the same thing today, or
   "none", and whether vfs should adopt the name, adopt the concept
   under its own name, or deliberately not have it, with a reason.
4. **What does not transfer**, and why (a row store in Postgres is not
   a disk; say where the analogy breaks).
5. **The one design lesson** for vfs in three sentences.

## Rules

- **No quotations from the book, anywhere in the study.** Say the idea
  in your own words and cite chapter and page.
- Label every claim **READ** (the book, with chapter and page; or a
  vfs file at HEAD `ac5c515`), **EXECUTED** (ran here with `uv run`),
  or **INFERRED**.
- Report what the book teaches and how it lands on vfs; do not write
  the ADR. Do not recommend for vfs as a whole; that is the synthesis.
- Never touch `src/`, `tests/`, `pyproject.toml`, any ADR or spec.
  No worktrees, no branches, no commits. `uv run` for any Python.
- Write for Clay: short sentences, one idea per sentence, define each
  term the first time, no dense paragraphs. Tables are good.
