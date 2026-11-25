# Study 03: the experiments the lint memo named, run on SQLite and four server engines

The lint memo's last section named five things it did not settle and an experiment for four of them, and the lint spec's eighth decision waited on them. This study ran them on 2026-11-25, with four more probes the first results called for. It was answered against vfs at `20a3075` (`git rev-parse HEAD` when the first probe ran; the head moved to `5b20fd4` during the day by commits that touch no file under `src/` or `tests/`). Nine scratch probes, `p09` to `p17`, were run as `uv run --no-sync python <script>` with the repository root and the experiments folder on `PYTHONPATH`, on the in-memory store and on four server engines, each in a container of its own on this machine: Postgres 17.12 with pgvector, MariaDB 11.8.9, SQL Server 2025 (17.0.5065.9) and Oracle 23ai Free (23.26.4.0.0). SQLite is 3.53.1. Every probe and its output is in [experiments/](experiments/), except `p09_plans_on_engines.py` and its `p09_<engine>.out` outputs, which were not saved to the repository: the run stopped at a usage limit before copying them, so the p09 figures are as that run recorded them and cannot be re-run from here. No pytest ran. The machine is x86_64 Linux with four cores and Python 3.13.18, and several probes always ran at once on it, so every clock below is a fact about a busy machine and nothing more.

EXECUTED means a command ran here and the claim reports its output. READ means read in a file cited by path and line. INFERRED means the researcher's reasoning from the two.

## 1. The answer in one paragraph

The checks hold on every engine, and the statements the earlier study wrote for them do not. Written once in SQLAlchemy Core and compiled for each engine at 100,000 files, the sixteen statements of [study 02](02-what-vfs-could-check-and-what-each-check-costs.md) found every planted damage on all five engines, but the plans of two to six of them on each engine hold a whole read of a table or an index, and an anti-join with a limit reads every row past its key when the store is clean (EXECUTED, section 2). One reshaped statement cures both: a page of at most a thousand rows of one table, each row judged by seeks, returning a key and one small integer a rule (section 3). How it probes matters as much as its shape: a left join is read whole by Oracle, a correlated `EXISTS` is hashed by Postgres and merged over whole indexes by SQL Server, and a correlated scalar subquery of one row was answered with a seek by every engine it ran on (section 4). Beside sixteen writers, three posture changes, a sweep and a mover, the structure flags reported nothing false on any engine; the label check reported hundreds to thousands of false rows that a second read did not withdraw, and reading it under the posture stamp and the relabel marks brought it to none (section 5). On SQL Server with snapshot reads off the walk was a deadlock victim; with them on it was not. At a million rows with one in a thousand torn, the findings are a thousand rows that cost six statements to keep and are stale as soon as a row is mended (section 6). In this repository's own `context/` tree, 97 unresolved references in 100 are code spans shaped like a path (section 7).

## 2. The first study's statements on five engines

EXECUTED, `p09_plans_on_engines.py`, outputs `p09_<engine>.out`. One store a engine, seeded through the storage verbs: 100,000 text files in 4,000 folders, 400 Markdown pages each linking two others, 2,000 files overwritten once, one folder at posture `none`, 50 grants, a full `rebuild`, then one folder and five pages deleted. Every engine held the same rows: 104,407 entries, 100,400 bodies, 2,000 version rows, 100,400 chunks, 105,206 edges, 308,404 segment postings. Each engine's statistics were refreshed, and each statement's plan was read with the engine's own tool: `EXPLAIN QUERY PLAN` on SQLite, `EXPLAIN (ANALYZE)` on Postgres, `EXPLAIN` on MariaDB, `SET SHOWPLAN_TEXT ON` on SQL Server, `EXPLAIN PLAN` and `DBMS_XPLAN` on Oracle. "whole" means the plan holds a read of a whole table or a whole index, by the word each engine prints for it.

| Statement | SQLite | Postgres | MariaDB | SQL Server | Oracle |
|---|---|---|---|---|---|
| structure, whole mount, by id | seeks | seeks | seeks | seeks | seeks |
| structure, one directory's children | seeks | seeks | seeks | seeks | seeks |
| structure, one subtree, by path | seeks | seeks | seeks | seeks | seeks |
| bytes, text bodies by id | seeks | seeks | seeks | seeks | seeks |
| body with no entry | whole | whole | whole | whole | whole |
| version with no entry | whole | seeks | whole | whole | whole |
| chunk with no entry | seeks | whole | whole | whole | seeks |
| edge with a missing end | seeks | seeks | whole | seeks | whole |
| grant on a path with no row | seeks | whole | seeks | seeks | seeks |
| version rows at or above the entry's version | seeks | seeks | whole | whole | whole |
| marked indexed, no chunk rows | seeks | seeks | whole | seeks | seeks |
| file nothing links to, one subtree | seeks | seeks | seeks | seeks | seeks |
| link to a tombstoned row, one subtree | seeks | seeks | seeks | seeks | seeks |
| two files with one hash, one subtree | seeks | seeks | seeks | seeks | seeks |
| two files with one hash, whole mount | seeks | seeks | seeks | seeks | whole |
| label in one posture region | seeks | seeks | seeks | seeks | seeks |

Counted down the columns: two on SQLite, three on Postgres, six on MariaDB, four on SQL Server, five on Oracle. What each whole read is, read off the plans. Postgres answers a body or a chunk with no entry with a parallel hash anti-join over a sequential scan of both tables, and scans the 52-row grant table. MariaDB materialises the entry table's identity index for a body, a chunk, an edge and an index mark, and scans the version table for the version rule. Oracle hash-joins against a fast full scan of the entry index for an edge and a version, and reads the entry table whole for the version rule. SQL Server scans an index for each of its four. SQLite's two, and the first of several on the other engines, are the page's own table walked in key order from its start, because the first page of a walk by entry id was planned with no lower bound.

The structure join, which the earlier study recommended, seeks on all five. The anti-joins do not, and they have a second fault no plan shows. Each is `WHERE NOT EXISTS (…) ORDER BY key LIMIT n`: on a clean store nothing passes the filter, so the statement reads every row past its key looking for a thousand that do not exist (INFERRED from the statement; EXECUTED in that every such first page returned no rows).

EXECUTED, the same probe's sections P3 to P5. The whole-mount structure walk is 105 statements for 104,406 rows on every engine, and flags nothing on the clean store. `labels_for` over a page of 1,000 paths is two statements, three on Oracle, whose 1,000-element budget cuts the page's ancestor paths into two reads. After one damage a rule was planted with direct SQL, every engine returned the same counts: one row with a parent that names nothing, one whose parent is a file, three torn paths (the two planted, one by letter case alone, and the row whose parent is a file), 25 live rows under the one deleted folder, two rows with no parent-child edge (the two with a wrong parent), and one each of a body, a version, a chunk and an edge with no entry, a grant on a path with no row, a version rule, an index mark and a wrong label.

The Oracle leg's first run stopped at P4 on a scratch statement that tested a boolean column with `IS 1`, which Oracle refuses (ORA-00908); it was respelled `= true` and the leg run again. The SQL Server leg's first run printed no plan lines, because `SHOWPLAN_TEXT` answers in two result sets and the probe read one; the probe was changed to read both through the driver's cursor and the leg run again. The outputs kept are the second runs.

## 3. The reshaped statement: a flag page

EXECUTED, `flagpages.py` and `p11_flag_pages.py`, outputs `p11_flag_pages_<engine>.out`, on a store seeded the same way. A flag page is two selects. The inner one is the page: at most `limit` rows of one table past a key, in key order. The outer one returns, for each of those rows, the key and one integer a rule, zero or one, each computed by a seek. So a statement visits a bounded number of rows whatever it finds, and a clean page costs the same as a damaged one. Two forms were run: `rows`, one slim row for each row visited, and `count`, one row a page holding the rows visited, the last key and a sum a flag.

The entry page carries nine structure flags in one statement: a row that is not the root and has no parent, a parent that names nothing, a parent that is not a directory, a torn path, a live row under a deleted parent, no parent-child edge, a file with a size and no body row, version rows at or above the row's version, and a row marked indexed with no chunk row. With the reference flags asked it carries three more: no link names the file, another file holds the same hash, and a link from the file names a deleted row.

EXECUTED, section Q3 and Q4 of each output. Every walk is one statement a page on every engine: 105 statements for the 104,407 entry rows, 101 for the bodies, 101 for the chunks, 106 for the edges, 3 for the versions, 1 for the grants. One folder's 25 children with every flag is one statement, and so is a subtree of 155 rows. After the same damage was planted, with one body row also deleted, every engine's entry walk raised the same flags, in both forms where both ran: 1 dangling, 1 under a file, 3 torn, 25 live under a deleted parent, 2 with no edge, 1 with no body, 1 version rule, 1 index mark; and the dependent walks raised 1 body, 1 version, 1 chunk and 1 edge with no entry and 1 grant on a path with no row.

Three things the engines said that the statement must respect.

- **The count form does not compile on SQL Server.** `SUM(CASE WHEN EXISTS (…) …)` is refused: "Cannot perform an aggregate function on an expression containing an aggregate or a subquery" (error 130). The rows form ran there. On the other four the count form returns one row a page where the rows form returns a thousand, and at a million rows on Postgres it took about four fifths of the rows form's time (section 6).
- **An empty string is not a key on Oracle.** The directory page started its key at `''`. On four engines it returned the folder's 25 rows; on Oracle it returned none, because an empty string is null there and `name > NULL` is never true. A walk's first page must carry no bound at all.
- **A reference flag for "nothing links to this file" fires on almost everything.** On this store it raised 99,975 of 104,407 rows on every engine: every text file, and of the 400 Markdown pages only the five whose two linkers were among the pages deleted. On a corpus that is not a wiki the rule says nothing unless it is kept to the files the link extractor reads.

The plans of this first spelling, read at the whole-mount page of 1,000 rows: SQLite and MariaDB seek throughout; Postgres hashes the body and chunk probes over a sequential scan and hash-joins the edge table; Oracle reads the entry table whole for the parent join and fast-full-scans the entry index on every dependent page; SQL Server merges over ordered scans of whole indexes. That is section 4's subject.

## 4. How a flag probes: a join, an `EXISTS`, or a one-row scalar subquery

EXECUTED, `p14_probe_shapes.py`, `p16_owner_pages.py` and `p17_version_walk_key.py`, at 100,000 files for the first two and 20,000 for the third. Three spellings of "does a row exist in the other table for this row" were put side by side on the same store: a left join on a unique key, a correlated `EXISTS` inside the flag's `CASE`, and a correlated scalar subquery that selects one row and is compared to null.

The entry page, whole mount, 1,000 rows:

| Engine | `EXISTS` in the flag, parent and edge joined | scalar subquery a probe, parent joined |
|---|---|---|
| SQLite | seeks | seeks |
| Postgres | hashed subplans over a sequential scan of the body table and the chunk table, a hash join over the edge table | seeks; the one sequential scan in the plan is of the blob table, which held no row and was never executed |
| MariaDB | seeks | seeks |
| Oracle | the entry table read whole | seeks |
| SQL Server | MSSQL_ENTRY_EXISTS | MSSQL_ENTRY_SCALAR |

The dependent pages, each row seeking the entry that owns it:

| Engine | left join to the entry table | scalar subquery |
|---|---|---|
| SQLite | seeks | seeks |
| Postgres | seeks, except the 52-row grant table, scanned | the same |
| MariaDB | MARIADB_OWNER_JOIN | MARIADB_OWNER_SCALAR |
| Oracle | a fast full scan of the entry table's identity index on the body, blob, chunk, edge and version pages | seeks on the body, blob, chunk, edge and grant pages |
| SQL Server | MSSQL_OWNER_JOIN | MSSQL_OWNER_SCALAR |

On Postgres the walk was also counted in buffer visits, the engine's own count of pages touched: 1,403,423 for the 104,407 entry rows in the `EXISTS` shape and 1,642,608 in the scalar shape, 13 and 16 a row. So at this size Postgres's choice to hash is not a mistake by its own measure; it is a read of a whole table a page all the same, and the scalar shape never makes one. On Oracle the difference is plain on the clock: the dependent walks took 5.9 to 12.4 seconds in the join shape and 0.8 to 1.3 in the scalar shape, on this machine.

The version table has a two-column key, and a page keyed by both columns joined by `OR` is a trap. EXECUTED, `p16` and `p17`: Postgres runs it as an index-only scan with the key condition as a filter, not as the scan's start, and Oracle as a full scan of the index, so each page reads the index from its beginning. VERSION_KEY_RESULT

INFERRED. No profile field is needed if one spelling seeks everywhere, and the scalar subquery is that spelling on the four engines whose plans were read in both shapes. A planner can still turn, as each of these did between spellings, so a plan node an engine is what holds it.

## 5. The walks beside writers

EXECUTED, `p12_walk_beside_writers.py`, outputs `p12_<engine>_<run>.out`. The workload is the contention node of [the label memo](../../2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window.md)'s experiment, rebuilt as a script: sixteen handles each write 50 new files beneath `/p`, half as the system actor and half as a granted caller; one handle changes the posture at `/p` three times, each with its relabel; one sweeps a deleted tree of 200 files. The run named `moves` adds a handle that moves a folder of 200 files back and forth ten times and one that deletes and restores a folder of 100 files ten times. Beside them one more handle walked the whole mount again and again, 100 rows a page, each page its own transaction, and read every flagged row a second time in a fresh transaction. The store was never damaged, so every finding either read reports is false.

| Engine and run | Calls and outcomes | Structure rows visited | Structure flags, first read and second | Label rows wrong, first read and second | Label rows wrong under the guard |
|---|---|---|---|---|---|
| Postgres, base | 804: 780 success, 24 retryable conflict | 11,085 | 0 and 0 | 5,794 and 5,794 | 0 |
| Postgres, moves | 834: 809 success, 25 retryable conflict | 10,452 | 0 and 0 | 1,194 and 1,194 | 0 |
| MariaDB, base | 804: 789 success, 15 retryable conflict | 8,830 | 0 and 0 | 4,808 and 4,709 | 0 |
| MariaDB, moves | 834: 799 success, 35 retryable conflict | 19,233 | 0 and 0 | 8,821 and 8,821 | 0 |
| Oracle, base | 804: all success | 7,378 | 0 and 0 | 299 and 200 | 0 |
| Oracle, moves | 834: all success | 19,607 | 0 and 0 | 8,666 and 8,556 | 0 |
| SQL Server, snapshot reads off, base | 804: all success | 17,923 | 0 and 0 | 521 and 437 | 0 |
| SQL Server, snapshot reads off, moves | the walk died: deadlock victim | | | | |
| SQL Server, snapshot reads on, base | 804: 801 success, 3 retryable conflict | 16,723 | 0 and 0 | 12,520 and 12,520 | 0 |
| SQL Server, snapshot reads on, moves | 834: 832 success, 2 retryable conflict | 22,717 | 0 and 0 | 17,371 and 17,371 | 0 |

One walk after each run settled found nothing on either read, so every count above is a false finding and none is damage.

**The structure flags.** Zero on every engine, on the first read. Each row is judged against its parent and its edge inside one statement, and on every engine that answers a statement from one snapshot there is no moment at which the statement sees half of a write. The second read withdrew nothing because there was nothing to withdraw.

**The label.** It compares a stored label with the posture rows, which is two statements, and a posture change is in force from its commit while its relabel reaches the rows afterwards. Read naively, 299 to 17,371 rows a run looked wrong, and the second read withdrew between none and a third of them, because the relabel was still running or had left its mark for the next call. The guard is an order of reads inside one transaction: the everyone stamp, the relabel marks, the page, the posture rows, the stamp again. A row counts as wrong only if the stamp did not move across the page and the row lies beneath no mark read at the start. Under it the count was zero on every engine, on the first read. Both facts are ones vfs keeps already: a posture write moves the stamp and plants its mark in one transaction (READ, `src/vfs/storage/backends/database/labels.py:239-260` and `:303`).

**SQL Server.** The base and moves runs were made in `master`, where `READ_COMMITTED_SNAPSHOT` is off and cannot be turned on, and again in a database made for the purpose with it on (`is_read_committed_snapshot_on` read back as 0 and 1). With it off, the moves run ended when the walker's plain `SELECT` was chosen as the victim of a deadlock: error 1205, "Transaction was deadlocked on lock resources with another process and has been chosen as the deadlock victim". With it on, both runs finished, every call was a success or a retryable conflict, and no flag was raised. The kept output of the failed run is cut to its error; the traceback above it was 59 KB.

## 6. One finding in a thousand rows, at a million rows: kept or paged

EXECUTED, `p13_findings_kept_or_paged.py` on Postgres, output `p13_findings_kept_or_paged.out`. The tables were made by vfs's own first touch and one file was written through the verbs; 1,000 folders of 1,000 files were then cloned from that file's row with direct SQL, with bodies and parent-child edges, to 1,001,003 entry rows. One file in each folder had its name rewritten, so 1,000 rows are torn.

| Measure | Count |
|---|---|
| The entry walk, rows form | 1,002 statements, 1,001,003 rows visited and returned, 1,000 pages holding a flag, 15,004,825 buffer visits |
| The entry walk, count form | 1,002 statements, 1,002 rows returned, 16,618,123 buffer visits |
| The second read of the 1,000 flagged rows | 1 statement at 1,000 keys a statement; 1,000 findings confirmed |
| Keeping them: one run's write | 1,000 rows of nine columns; 222 rows a statement under a 2,000-bind budget; 6 statements; 286,720 bytes of table and indexes |
| Keeping them: the next day's run | 6 statements, one delete and five inserts; 1,000 rows held |
| One folder asked afterwards, from the rows | 1 statement, 1,000 rows visited, 1 flag |
| The same folder, from the kept table | 1 statement, 1 row |
| After 100 of the torn rows were mended | the store holds 900; a fresh walk flags 900 pages; the kept table still lists 1,000 |

The run was made twice. In the first, the walk measured 12,132,115 and 11,746,759 buffer visits and took 41 and 33 seconds; in the second, with four other probes running, 15,004,825 and 16,618,123 and 83 and 68 seconds. Either way it is 12 to 17 buffer visits a row at a million rows, the figure section 4 measured at a hundred thousand, so a row costs the same in a store ten times the size. The first run's scratch table declared its path column as a plain string, and the range read of one folder returned no row under Postgres's default collation, which does not order by bytes; the column was redeclared with vfs's own bytewise type and the run made again. The first run's output is kept beside the second, cut where it was copied.

INFERRED. Cost does not choose between the two. A thousand rows and six statements a day is nothing, and at the reference deployment's eleven million rows it is eleven thousand rows. What chooses is what a kept row is: a write made by a verb that is ruled to change nothing, a claim that goes stale when a row is mended, and a row that names a path and must be judged against each reader's rights again when it is read.

## 7. References that name no file, in this repository's own context tree

EXECUTED, `p10_links_to_nothing.py`, output `p10_links_to_nothing.out`. vfs's own extractor (`vfs.models.links`) was run over the 1,021 Markdown documents git tracks under `context/`, 3,478 tracked files in all. Two mounts were measured: one holding `context/` alone, as a wiki would be mounted, and one holding the whole repository, so that a link into `src/` can resolve.

| Mount | References found | Resolved | Distinct edges | Unresolved | Of those, code spans shaped like a path | Of those, Markdown links or images | Rows a kept reference would add |
|---|---|---|---|---|---|---|---|
| `context/` alone | 46,232 | 3,671 | 2,758 | 42,561 | 41,479 | 1,082 | 24,750 |
| the whole repository | 46,232 | 15,009 | 9,152 | 31,223 | 30,255 | 968 | 18,270 |

The first mount was also written into an in-memory store and rebuilt. The store's own record reads `{'leg': 'links', 'sources': 1021, 'edges': 2252, 'unresolved': 43144}`, and the store holds 2,252 `links` edges. The probe's count is 506 edges higher and 583 unresolved lower because it resolved a reference against a directory as well as a file, and the store's resolver does not.

INFERRED. A row for every reference that names nothing would be about nine times the edges the extractor mints, 24 a document, and 97 in 100 of them would be a file name in backticks such as `backend.py`, which is not a page anyone wants written. The signal a "wanted page" rule needs is in the thousand unresolved links, and the extractor does not tell the two apart in what it returns: the probe told them apart by looking for the destination inside a link in the referring line.

## 8. Four small facts the spec leans on

EXECUTED, `p15_the_rest.py`, at 20,000 files on all five engines, outputs `p15_the_rest_<engine>.out`.

- **The whole mount walked by path is the walk by id.** 24 statements for 23,208 rows by id and 24 for 23,207 by path, on every engine; the path walk leaves the root out, which has no parent to judge. So a walk can be keyed by path for every caller.
- **Bytes bodies.** A page of 1,000 files left-joined to the blob table by its key fetched 1,000 bodies with none missing on every engine, and the blob rows' own walk is 3 statements for 2,000 rows.
- **A relabel mark with no posture row** is found by the two reads vfs already has, `inflight_marks` and `posture_rows`: two statements on every engine, one stray mark found.
- **A grant on a path with no row succeeds** on every engine. So a grant that names no row is a state the verbs make, not damage.
- **A file whose version sits below its own version rows** refuses every overwrite with the driver's own text on every engine (a duplicate key on the version table), and is not locked otherwise: a move of it succeeds, an overwrite after the move succeeds, a delete succeeds, and a fresh write at the first path succeeds twice. Each verb that raises the version without minting a version row moves it one step clear.

At this size, 20,000 rows, Postgres, Oracle and SQL Server each read small tables whole in the first spelling of the page, as section 4 found at 100,000.

## 9. What was changed between runs

The scripts in `experiments/` are their last versions. Four changes were made after some outputs were written, none to a statement those outputs measured: the boolean test and the two-result-set read of section 2; the plan reader came to spell an entry id as each engine's own literal, by the helper `tests/support/plan_store.py` already has, so that a page past the first could be planned; and a wait was added for the in-memory store's own statistics pass, which shares its one connection. `p14` was first written with the count form alone, died on SQL Server for the reason in section 3, and was given the rows form too and run again there.

## What this study did not reach

- **The reference scale.** The plans were read at 100,000 files and one walk at a million rows on Postgres. Whether Oracle and SQL Server keep the seek plans at a million rows and at eleven million was not run. The experiment is `p13`'s seed, which is Postgres SQL, ported to those two engines, and `p14` read on it.
- **A caller's narrowed page.** Every probe ran as the system actor, so no page was narrowed by `Visibility.narrow` and no reference probe carried a view's predicate. Their plans, and the count of clauses a real caller's rights compile to, were not measured. The experiment is `p14` with a view built by `grant_worlds.random_world`.
- **The byte layer at size.** Bodies here were tens of bytes. The fetch of a 32 MiB group, the hashing on the worker pool and the memory held were not run. The experiment is `p01`'s walk over a store with megabyte bodies on a server engine, counting bytes fetched a call.
- **SQL Server's deadlock in a database with snapshot reads on, at length.** Two runs finished clean; two runs are not a proof. The experiment is the `moves` run repeated fifty times in that database.
- **The posting tables, renderings, embeddings, signals and memberships**, which the earlier study also did not reach.
- **Version rows' bodies.** No version body was hashed.

## One line

Every check finds its damage on all five engines, but only as a bounded page whose flags are one-row scalar probes; the structure flags are true beside writers and the label is true only under the posture stamp and the relabel marks; keeping findings costs nothing and buys a stale list; and a row for every reference to nothing would be nine parts noise.
