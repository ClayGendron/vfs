# Study: Spike: a statically linked CPython for WebAssembly with numpy compiled in, run over vfs

## Verdict

Landed. The spike was executed on 2026-10-16 and every deliverable it names is in the tree: the report `context/research/studies/2026-10-15-agent-shell/13-wasi-python-spike.md` (274 lines) and the experiments folder `experiments/s12/` (cross, fixtures, outputs, scripts, shim; 66 output files). All four counted acceptance criteria are recorded as met. The spec is research, changes nothing under `src/`, and has no unit left to build; it is archived with its landing notes, as roadmap story R7 criterion 1 already requires. Its forward-looking product (the yearly in-repo build plan) was overtaken on 2026-10-23 by the external `wasi-python` 0.1.0 runner, which is spec 172's and story T5a's concern, not this spec's.

## Against the tree

- EXECUTED: `ls context/research/studies/2026-10-15-agent-shell/` lists `13-wasi-python-spike.md`; `ls .../experiments/s12` lists `cross fixtures outputs scripts shim`; `ls .../s12/outputs | wc -l` gives 66.
- READ: the report's go/no-go table, `13-wasi-python-spike.md:14-24`, answers questions 1 to 7: GO on 1, 2, 3, 4 and 7; 5 estimated with the deciding fact named (C++ exceptions for matplotlib, a Fortran toolchain for scipy); 6 measured.
- READ: acceptance, `13-wasi-python-spike.md:26`: criteria 1 to 4 each marked met, with output files cited (`outputs/08_import_numpy.json` and others).
- READ: the deliverables list, `spec.md` Deliverables section, asks for a questions section and a plain-language verdict; both are present at `13-wasi-python-spike.md:249` and the "Verdict, in plain words" section after it.
- READ: the spec's own landing notes (`spec.md`, Landing notes) state nothing under `src/`, `crates/`, `tests/` or `pyproject.toml` was touched. EXECUTED: `ls src/vfs` shows no `shell/` package; `grep -n wasi pyproject.toml` finds nothing. INFERRED: consistent with a spike that writes only research.
- READ: `context/research/2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md:11` and `:30`: the external `wasi-python` 0.1.0 ships its own runner, mount protocol and tool protocol, which replace the spike's research shim and the `vfs.ping` door as the production path; everything in spec 172 about build, host, door and install is stale, while the spike's documented semantics (int32 default integer, no threads, no network) still hold.
- READ: the same memo `:20` records that wasi-python 0.1.0 also imports scipy, scikit-learn, statsmodels and matplotlib, which overtakes the spike's estimates for question 5 as a planning input. INFERRED: the estimates remain true as facts about a self-built static CPython; they no longer decide anything.
- EXECUTED: `git log --oneline -1` reports `09dad59` in this checkout, not the `0ed462f` named in the task; no file this study rests on is affected by the difference so far as read.

## Where the roadmap places it

- READ: `context/standards/roadmap.md:106` and `:897` count 173 among the four specs "built but not archived" (165, 162, 152 A/B, 173).
- READ: `roadmap.md:962-965`, story R7 (context-pipeline true-up, gate b), criterion 1: "Specs 165, 162, 152 ..., 173 move to `specifications/archive/` with landing notes". This is the row that places it: an archive action at gate b, not a build.
- READ: `roadmap.md:727`, story T5a (the Python guest over wasi-python, gate b) cites "spike 173" as one of the two proofs of the mechanism; the other is the 2026-10-23 memo. T5a's acceptance numbers (21 verbs for the pandas job) come from that memo, not from the spike.
- READ: `roadmap.md:1095`, D23 Decided 2026-10-28: Python and JavaScript guests both in 0.1.0, gate b, behind `vfs-py[python]` and `vfs-py[javascript]`.
- READ: `roadmap.md:1033`, cut-list item 8: the numpy/pandas bundle may move to 0.1.x with a stdlib-only guest first; INFERRED: this touches T5a, not this spike.

## Units proposed

None. The spec is landed research; it is archived, not converted. Its live successor work is story T5a (spec 172, to be rewritten from the 2026-10-23 memo) and story T5b with D49, which have their own studies.

## Open choices, each verified

The spec holds no `[NEEDS CLARIFICATION]` marker. Its open choices are the three questions in "Questions the spike answers"; the report's eight follow-on leans (`13-wasi-python-spike.md:249-258`) belong to the report and to spec 172, and are listed here only so the conversion of spec 172 finds them.

1. Choice: is the first annual build numpy and pandas only, matplotlib and scipy later? Lean (report Q2): numpy and pandas first. Verification: already-ruled. D23 Decided 2026-10-28 (`roadmap.md:1095`) puts the Python guest in 0.1.0 and T5a (`roadmap.md:727`) names numpy and pandas; the package set is now wasi-python's, which already imports matplotlib and scipy (memo `2026-10-23-...:20`), so no in-repo annual build exists to stage.
2. Choice: is the artifact small enough to download at install time, and what cold start does an agent see? Answer recorded (report Q3, Q4: 8.4 to 20 MB xz; 3 to 5 ms from a snapshot). Verification: already-ruled. D23 places the guest behind the optional extra `vfs-py[python]` (`roadmap.md:53`, `:1095`), and the artifact rides in the wasi-python wheel (memo `:114`, pin 4), so the in-repo download question no longer arises.
3. Choice: is the wasm speed penalty acceptable? Lean (report Q5): 1.3 to 2.3 times native is acceptable for a sandboxed read-compute-write loop. Verification: already-ruled. D23 Decided 2026-10-28 commits to the guest in 0.1.0 on this evidence; `roadmap.md:53` states the guests are for numpy and pandas shapes, not for control flow.
4. Report Q1 (3.14 + SDK 24 or 3.15 + SDK 33; lean 3.15 + SDK 33): already-ruled; the memo `:114` records pin 2 resolved as 3.15 with SDK 33, the line wasi-python 0.1.0 ships (memo `:139`).
5. Report Q6 (document the int32 default integer or patch numpy; lean document): holds for spec 172, precedent Pyodide's documentation (report `:257`) and the memo `:30` confirming the semantics on wasi-python; carried to the spec 172 study, not decided here.
6. Report Q7 (staged-buffer cache for the zip row) and Q8 (recipe files in this repo; lean this repo): already-ruled as moot; the memo `:114` moves the host and artifact set to wasi-python's runner and wheel, so neither the shim nor in-repo recipes exist to place.

## What is stale

- Status line names "ADR 086's pins" and four leans marked pending a ruling; the decision records were retired 2026-10-30 (commit `3667fec2`, READ `roadmap.md:106`), and the pins that matter are restated against wasi-python in memo `2026-10-23-...:114`.
- "Depends on" and "Research it stands on" cite ADR 086 as provisional; there is no ADR any more (`roadmap.md:106`).
- Landing notes say "spec 172 rewritten as the WASI Python runtime in four slices"; spec 172 is itself stale and awaits a rewrite on wasi-python (READ memo `:30`; `roadmap.md:725` "spec 172 rewritten, ADR 086 amended" as T5a's work).
- Rules place reference clones under `~/Git/Repos/`; AGENTS.md "Reference repos for research" now places them as sibling directories of the checkout (READ AGENTS.md).
- Report Q7 names "the spec 167 shim"; the production host is wasi-python's runner, not a vfs shim (memo `:11`).
- The pipeline plan (step 8, a yearly CI build of the interpreter in this repo) is overtaken by the published `wasi-python` wheel (memo `:11`, `:114`).
- The `vfs.ping` verb door through `Linker.define_func` is replaced by wasi-python's tool protocol, `from host import tools` (memo `:11`, `:114` pin 7).
- Question 5's estimates (matplotlib needs SDK 33; scipy months away) are overtaken: wasi-python 0.1.0 imports both (memo `:20`).

## Notes for the conversion

- No nine-section spec is written for 173. The action is R7 criterion 1: move the folder to `context/specifications/archive/` with its landing notes; the Status line's pending leans are corrected to "Decided 2026-10-28 (D23)" and "overtaken by the 2026-10-23 wasi-python memo" first.
- Facts worth keeping for the T5a spec: numpy's default integer is int32 on wasm32; no threads; no network; a snapshot cold start of 3 to 5 ms; kernels 1.3 to 2.3 times native (report table, `13-wasi-python-spike.md:21-22`). The memo confirms the first three on wasi-python.
- Roadmap decisions this spec cannot be built without: none; it is built. D23 is the ruling that closed its questions.
