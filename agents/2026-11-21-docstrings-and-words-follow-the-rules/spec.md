# Docstrings and words follow the rules

A draft, written on 2026-11-21. It is not reviewed, and nothing is built.

## The outcome wanted

Every public member under `src/vfs/` has a docstring that follows `documentation/maintainers/how-we-write-docstrings.md`, every term of art it uses is in the glossary, and no page, docstring, comment or test name uses a word the naming rules retired.

## The problem

### Docstrings

- **The docstrings of 16 source files break the rules.** About 265 of 311 break a rule in `how-we-write-docstrings.md`, and about 170 public members have none. The largest files are `rights.py`, `paths.py`, `backend.py`, `labels.py`, `ranking.py` and `sync.py`.
- **The words "router", "bind path", "bind point" and "bind site" remain** in those files, in `fanout.py` and in `pattern_matching/glob.py`.
- **"Storage backend" gives way to the term Storage.** Storage is a glossary term since 2026-11-20, with `StorageBackend` as its type. Eleven places in four pages under `documentation/` still say "storage backend" and link nothing, and nine docstrings under `src/vfs/` say it with no `:term:` marker. The example line in `how-we-document.md` is one of the eleven.
- **The example in `how-we-write-docstrings.md` names `overwrite`.** It shows the `write` docstring before and after a rewrite, and `write` takes `if_absent` in its place since pull request 22.
- **The docs export does not follow an alias of a type variable.** It tells a type variable by what the value is, and does not follow `T = U` or a renamed constructor.

### The glossary

- **Eight words used in docstrings have no glossary entry.** They are gate, capability, permission map, posture, authority, trash view, mount point and attempt. Attempt means one try of one call's transaction, as `documentation/maintainers/cancellation.md` and `attempts.py` use it.

### Pages, comments and names

- **`documentation/maintainers/mounts.md` is bullet points for the greater part.** 36 of its 48 lines are list items. `how-we-document.md` says a page is prose, with a list only for things that are a list.
- **Comment blocks in `dialects.py` and `engine.py` run past two lines.** The working agreement allows two.
- **A test name uses an old word.** `test_unmount_and_remount_pass_under_a_rule_beneath_the_site` keeps "remount", because documents under `context/` cite it by name.

## Decisions

1. **The 16 files are rewritten one module at a time,** largest first, each a commit that `scripts/docs.sh check` passes.
2. **A lint test refuses the retired words** in `src/vfs/` and `documentation/`, so they do not come back.
3. **The eight terms are added to `documentation/reference/glossary.json` and `glossary.md`,** and each first use in a docstring takes a `:term:` marker.
4. **The test is renamed `test_unmount_and_mount_again_pass_under_a_rule_beneath_the_site`,** and the documents under `context/` that cite it are changed with it.
5. **The docs export follows one level of alias.**
6. **The long comment blocks move into the docstrings of the functions they explain,** as the working agreement says.

## Tests

Decision 2's lint test is written first and seen failing on today's tree. The export gets a test with `T = U`.

## Scope

In: docstrings and comments under `src/vfs/`, the pages named above, the glossary and the docs export. Out: any change of behaviour.

## Not checked

- The counts of 265 and 170, which are from 2026-11-19 and were not counted again on `dev`.

## Choices to confirm

1. **Decision 4: rename the test and the citations?** Recommended: yes, since `context/` takes no new work but its citations may be corrected.

## One line

Every public docstring follows the rules and links its terms, and a lint test keeps the retired words out.
