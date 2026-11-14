# One page per public name holds from 22 names to 60; a page per method costs NumPy and Polars a hand-kept index of over 1,600 lines, and a reference kept on a separate site loses its links

I was asked, on 2026-11-14, how three projects divide their API reference into pages at scale, how each indexes it, how a per-object page is generated, whether the reference is a separate site, what a reader sees for a class with dozens of methods, what the approach costs, and how CPython and NumPy use a glossary from pages and from docstrings. The conclusion asked for is what page granularity suits a library with 22 public names today that may have 60 in two years. The time box was 30 minutes. I used about 12 of them; every part of the question was reached, and the closing section names the three things the clones could not settle.

## Sources

- Clone `numpy` at `d63a30827d` (2026-11-14), licence BSD-3-Clause. Documentation under `doc/`.
- Clone `polars` at `2d9938d` (2026-11-14), licence MIT. User guide under `docs/` with `zensical.toml` at the root; API reference under `py-polars/docs/`.
- Clone `cpython` at `b968417` (2026-11-14), licence Python Software Foundation License Version 2. A shallow clone, so its history was not read. Documentation under `Doc/`.
- https://numpy.org/doc/stable/objects.inv, read 2026-11-14. It reports NumPy 2.5; the clone is the development branch.
- https://numpy.org/doc/stable/reference/generated/numpy.ndarray.html, https://numpy.org/doc/stable/reference/generated/numpy.ndarray.sort.html and https://numpy.org/doc/stable/reference/arrays.ndarray.html, read 2026-11-14.
- https://docs.pola.rs/api/python/stable/objects.inv, read 2026-11-14.
- https://docs.pola.rs/api/python/stable/reference/dataframe/index.html, https://docs.pola.rs/api/python/stable/reference/expressions/index.html and https://docs.pola.rs/api/python/stable/reference/dataframe/api/polars.DataFrame.filter.html, read 2026-11-14.
- https://docs.pola.rs/user-guide/getting-started/, read 2026-11-14.
- The 143 distinct API reference addresses listed in the Polars clone's `docs/source/_build/API_REFERENCE_LINKS.yml`, each requested once on 2026-11-14 for its status only.
- https://docs.python.org/3/objects.inv, read 2026-11-14. It reports Python 3.15; the clone is the development branch.
- https://docs.python.org/3/library/pathlib.html and https://docs.python.org/3/library/stdtypes.html, read 2026-11-14.
- Sphinx 9.2.0 from the public package index, run once on a two-file probe project on 2026-11-14.
- Every command and the figure it printed is saved in [counts.txt](experiments/03-one-page-per-object-at-scale-and-an-api-reference-kept-apart/counts.txt), with the two scripts that decode an inventory, [inv.py](experiments/03-one-page-per-object-at-scale-and-an-api-reference-kept-apart/inv.py) and [kinds.py](experiments/03-one-page-per-object-at-scale-and-an-api-reference-kept-apart/kinds.py).

The labels: EXECUTED marks a command or fetch I ran whose output I report; READ marks something read in a file cited by path in a clone at the commit above, or in a page cited by address and date; INFERRED marks my own reasoning from the two.

## Terms used

A docstring is the text a Python object carries in the code to describe itself. Sphinx is the documentation tool all three projects build with. A toctree is the Sphinx directive that lists the child pages of a page, and so builds the navigation. Autosummary is the Sphinx extension that turns a list of names into a table of one-line summaries, and, when the list carries a `:toctree:` option, also writes one page per listed name from a template. A role is inline markup such as `:func:` or `:term:` that Sphinx resolves into a link at build time. An inventory (`objects.inv`) is the file a built Sphinx site publishes that maps every documented object to the page that holds it; counting its distinct pages counts the built site without building it. Granularity means how much one page holds: one member, one class, one module or one topic.

## NumPy: a page per object, generated, inside one build

How the reference is divided. READ: the reference source is 113 hand-written `.rst` files under `doc/source/reference/`. They hold prose and autosummary tables. EXECUTED: `doc/source` holds 238 autosummary directives in 46 files, and 220 of their 226 `:toctree:` options name the folder `generated`. Each listed name becomes its own page there. EXECUTED: the live inventory holds 2,671 distinct pages, 2,443 of them under `reference/` and 2,148 under `reference/generated/`. Of those 2,148 pages, 848 hold a method, 801 a function, 235 an attribute, 164 a data object, 51 a property, 35 a class, 7 an exception and 7 a module; 2,145 hold exactly one object. INFERRED: a method, an attribute or a property gets a page of its own, and those members are 1,134 of the 2,148 generated pages, 53 percent. The 113 files a person writes become about nineteen times as many pages.

Why per object. READ: no file in the clone states the reason. INFERRED: the unit follows the docstring format. Each NumPy docstring is a full document with parameters, notes, see-also links and worked examples, and `doc/source/conf.py` turns on plots for the examples (`numpydoc_use_plots = True`), so one object fills a page.

How the index is organised and who maintains it. READ: `doc/source/reference/index.rst` has three hand-written groups: Python API (module structure, array objects, universal functions, routines by topic, typing), C API, and other topics. READ: `doc/source/reference/routines.rst`, titled "Routines and objects by topic", lists 26 topic pages by hand. A comment in that file says the listing is "opinionated and incomplete" by design and that per-module listings and the search box cover the rest. READ: a topic page such as `routines.sort.rst` is hand-written headings (Sorting, Searching, Counting) over autosummary tables, and a person types each name into a table. READ: `tools/refguide_check.py` (665 lines) compares a submodule's `__all__` with the names the reference lists, and its own docstring says its output "does need to be checked manually". READ: a comment in `doc/source/reference/module_structure.rst` says there is no single page covering the main namespace because it is "hard to create without introducing duplicate references". INFERRED: the index is by topic, it is kept by hand, and nothing fails a build when a public name is missing from it.

How a per-object page is generated. READ: `doc/source/_templates/autosummary/` holds seven templates, 131 lines in all. `class.rst` extends Sphinx's stock class template and replaces its methods and attributes blocks with an autosummary that carries `:toctree:` but sits inside a comment, so the member pages are written and the list is not shown; the template's own comment calls this a hack. `method.rst`, `attribute.rst` and `member.rst` are 13 lines each: a title, the word that names the kind, and one directive that pulls the docstring. They are marked `:orphan:`, meaning Sphinx is told not to complain that no toctree lists them.

What a page holds. EXECUTED: the live page for `numpy.ndarray.sort` is 37,339 bytes with one signature; its article is about 9,900 bytes and the page carries 95 links. It holds the signature, the docstring sections and a source link.

Separate site or section. READ: one Sphinx build. `doc/source/index.rst` lists five top entries: User Guide, API reference, Building from source, Development, and release notes. The API reference is a top-level entry of the same site. EXECUTED: guide to reference, the 39 files under `doc/source/user/` carry 396 explicit object roles, and `conf.py` sets `default_role = "autolink"` so a bare backticked name also links. EXECUTED: reference to guide, the docstrings under `numpy/` carry 75 `:ref:` markers and the hand-written reference pages 165. INFERRED: because it is one build, every one of these links is resolved by the tool, and the build runs with warnings as errors (`SPHINXOPTS ?= -W` in `doc/Makefile`; `SPHINXOPTS="-W -n" spin docs` in `.circleci/config.yml`).

A class with dozens of methods. EXECUTED: `ndarray` has two pages. The generated page `reference/generated/numpy.ndarray.html` is 79,626 bytes: the class docstring, an attributes section, and one flat table of 53 methods, each row a link to that method's own page. The hand-written page `reference/arrays.ndarray.html` is 134,804 bytes: 644 source lines of prose with 121 table rows under 8 second-level and 9 third-level headings (array attributes, array conversion, shape manipulation, item selection, calculation, arithmetic, special methods). INFERRED: the grouping by topic that makes a 53-method class readable is written by hand on a second page, apart from the generated one.

What the project says it costs. READ: no file in the clone states a build time. READ: the visible costs are the seven templates, `doc/preprocess.py` and `doc/postprocess.py` (51 and 50 lines), the 665-line checker, and a `clean` target in `doc/Makefile` that must find and delete every `generated` folder.

## Polars: a page per object, generated, on a separate build

How the reference is divided. EXECUTED: `py-polars/docs/source` holds 101 hand-written `.rst` files and 120 autosummary directives, 119 of which write pages into `api/`. About 1,641 names are typed by hand into those tables. EXECUTED: the live inventory holds 1,545 pages, 1,541 under `reference/`: expressions 541, series 446, the shared `api` folder 206, dataframe 153, lazyframe 128, sql 26, catalog 15, datatype expressions 14. Of the 1,446 pages that hold a Python object, 1,167 hold a method and 1,382 hold exactly one object. INFERRED: 81 percent of the object pages are a single method.

How the index is organised and who maintains it. READ: `py-polars/docs/source/reference/index.rst` is a grid of cards, one per major class or area (DataFrame, LazyFrame, Series, Expressions, Functions, Data types, Input/output, Config, SQL, Exceptions, Testing). Inside a class the index is by topic: `reference/dataframe/` holds ten topic pages (aggregation, attributes, computation, descriptive, export, group by, modify and select, miscellaneous, plot, style), and `reference/expressions/` and `reference/series/` hold about twenty each. READ: the contributing guide, `docs/source/development/contributing/index.md`, says new additions "should be added manually to the API reference by adding an entry to the correct `.rst` file". INFERRED: by topic, by hand, with no check that a public method is listed.

How a per-object page is generated. READ: `py-polars/docs/_templates/autosummary/` holds six templates, 63 lines in all. `class.rst` uses the same commented-out autosummary device as NumPy to write member pages without showing the list. Four templates serve accessors, the namespaces such as `Series.str` that hang off a class. READ: `py-polars/docs/_templates/sidebar-nav-bs.html` (9 lines) overrides the theme's sidebar to show the navigation four levels deep.

Separate site or section. READ: two builds with two tools under one domain. The user guide is Markdown under `docs/source`, configured by `zensical.toml` and built by `zensical build` in `.github/workflows/docs-global.yml`. The API reference is Sphinx, built by `make html` in `.github/workflows/docs-python.yml` and deployed to `api/python/dev`, `api/python/stable` and `api/python/version/<major>`. The guide's deploy step excludes `api/python/` and `api/rust/` from its clean-up so the two do not overwrite each other. INFERRED: the reference is versioned on its own and the guide is not.

How the two link. READ: guide to reference, the guide's navigation has one entry, API, whose page `docs/source/api/reference.md` is 13 lines that link out to the two reference sites. READ: a guide page shows code through a macro, `code_block(path, snippet, [names])`, and each name in the third argument is looked up in a hand-kept table, `docs/source/_build/API_REFERENCE_LINKS.yml`, to print a link under the code. EXECUTED: the macro is called 335 times in the guide's 87 Markdown files; the table is 505 lines and holds 143 distinct Python reference addresses; 11 guide pages hold 20 more hard-coded addresses. EXECUTED: I requested each of the 143 addresses once. 140 answered 200 and 3 answered 404: the pages for `polars.dtype_of`, `polars.Expr.list` and `polars.LazyFrame.fetch`. READ: reference to guide, `py-polars/docs/source/conf.py` adds one external link, "User guide", to the top bar. EXECUTED: the docstrings under `py-polars/src/polars` hold 4 links to the guide. INFERRED: the two sites are joined by addresses a person types, the tool checks none of them, and about 2 percent were dead on the day.

A class with dozens of methods. READ: `reference/dataframe/index.rst` documents the class with all its members and a summary table (`:members:`, `:autosummary:`, and `:noindex:` so the anchors do not clash with the per-method pages). EXECUTED: the live DataFrame page is 1,508,248 bytes: a summary table of 159 rows, then 136 full signatures with their docstrings. The Expressions page is 1,695,019 bytes with 214 signatures. Each method also has its own page: `polars.DataFrame.filter.html` is 268,936 bytes, of which the article is about 16,500; the page carries 1,597 links, and 1,564 of them are sidebar entries. INFERRED: every DataFrame method is rendered twice, once inline on a page of one and a half megabytes and once alone, and on the page of its own about 94 percent of the bytes are navigation.

What the project says it costs. READ: no file states a build time. READ: `py-polars/docs/Makefile` runs Sphinx with `-j auto -W` and with `-j 1 -W` on macOS. READ: a comment in `docs-global.yml` says "zensical has no hooks", so the script that once ran as a build hook now runs as a separate workflow step. READ: the project has no glossary; the inventory holds no term.

## CPython: a page per module, written by hand, inside one build

How the reference is divided. EXECUTED: `Doc/library/` holds 329 `.rst` files and `Doc/builtins/` 7 more (built-in functions, constants, types and exceptions). 269 library files carry a `.. module::` directive; the other 60 are topic and index pages. The live inventory holds 328 pages under `library/`; 262 open with a module, and 245 hold two or more objects. EXECUTED: nothing is generated. `Doc/` holds no autodoc or autosummary directive, and `Doc/conf.py` does not load either extension. The library and built-in pages hold 10,060 object entries typed by hand: 3,638 methods, 2,209 functions, 1,396 attributes, 1,320 data entries, 1,043 classes, 320 exceptions and 134 others. INFERRED: about thirty objects a page.

Where one module is too big for a page, it is split by topic, not by object. EXECUTED: `asyncio` is 19 files, `email` 16, `tkinter` 10 and `xml` 9.

How the index is organised and who maintains it. READ: `Doc/library/index.rst` lists 34 topic pages by hand (text processing, binary data, data types, numeric, functional, file and directory access, and so on). Each topic page is a short paragraph and a toctree of its modules; `Doc/library/filesys.rst` lists nine. READ: Sphinx also generates an alphabetical module index and a general index, and the home page template `Doc/tools/templates/indexcontent.html` links both under "Indices, glossary, and search". INFERRED: the index a reader meets first is by topic and hand-kept; the alphabetical one is the tool's by-product.

Separate site or section. READ: one build. `Doc/contents.rst` lists 17 top entries, among them the tutorial, the language reference, built-ins, the library reference, how-to guides and the glossary. EXECUTED: guide to reference, the 47 files under `Doc/tutorial` and `Doc/howto` carry 1,492 object roles. Reference to guide, the library and built-in pages carry 263 `seealso` blocks. INFERRED: every link in both directions is a role the build resolves.

A class with dozens of methods. EXECUTED: `Doc/library/pathlib.rst` holds 58 method directives on one page. The live page is 271,233 bytes with 81 signatures under 8 second-level and 19 third-level headings that a person wrote: pure paths, concrete paths, querying file type and status, reading and writing files, reading directories, creating files and directories, copying and moving, permissions. EXECUTED: the largest page is the built-in types, `Doc/builtins/stdtypes.rst`, at 7,003 lines; live it is 815,874 bytes with 306 signatures. INFERRED: a class stays on its module's page and is made readable by topic headings in the page's own table of contents.

What the project says it costs. READ: no file in the clone states a cost. INFERRED: the cost is the 10,060 hand-typed entries, each a signature kept in step with the code by review alone. READ: the guard the project has is on links, not on signatures: `Doc/Makefile` sets `--fail-on-warning`, and `.github/workflows/reusable-docs.yml` builds with `--nitpicky`, the mode that reports every unresolved reference, and runs `Doc/tools/check-warnings.py` with `--fail-if-regression` and `--fail-if-improved` against a list of 22 excused files.

## The glossary in CPython and NumPy

Where it sits. READ: CPython's is `Doc/glossary.rst`, a top-level entry in `Doc/contents.rst` beside the tutorial and the library reference, and linked from the home page. READ: NumPy's is `doc/source/glossary.rst`, a top-level file that `doc/source/user/index.rst` lists in a hidden toctree captioned "Extras", so it travels with the user guide.

How an entry is written. READ: both use one Sphinx `.. glossary::` directive on one page. A term is a line indented three spaces and its definition is the indented block beneath. CPython's file opens with a comment asking writers to keep the alphabetical order. An entry is a paragraph or more, and it links onward with roles: to other terms, and to the module or function that implements the idea. EXECUTED: CPython defines 178 terms in 1,745 lines; NumPy defines 50 in 564. The live inventories agree with both counts.

How often pages link a term. EXECUTED: CPython's `.rst` pages hold 2,335 `:term:` markers in 262 files; 262 markers are inside the glossary itself and 2,073 are in other pages, 1,048 of them in the library and built-in reference. EXECUTED: NumPy's `.rst` pages hold 100 markers in 18 files; 26 are inside the glossary and 74 outside.

How often docstrings link a term. EXECUTED: CPython, none: no `:term:` marker in any `.py` file under `Lib/` or in the C sources under `Objects/`, `Modules/` and `Python/`. Its reference pages are not built from docstrings. EXECUTED: NumPy, 9 markers in 6 files, across all its Python sources. Four name a term NumPy's own glossary defines: `casting`, `row-major`, `column-major` and `array_like`. The other five (`generic type` three times, `sequences`, `python:path-like object`) name terms that glossary does not define. INFERRED: those five resolve against Python's glossary through intersphinx, the Sphinx extension that resolves a role against another project's inventory. The word `array_like` occurs 1,053 times in those sources and is linked once.

Whether a check fails the build on an unknown term. EXECUTED: Sphinx does it, not either project. A probe project with one known and one unknown term printed `WARNING: term not in glossary: 'gadget' [ref.term]`; the build exited 0 without `-W` and 1 with it. READ: both projects build with warnings as errors, CPython through `SPHINXERRORHANDLING = --fail-on-warning` in `Doc/Makefile` and NumPy through `SPHINXOPTS ?= -W`. Neither has a glossary check of its own. READ: CPython adds one glossary feature, `Doc/tools/extensions/glossary_search.py` (63 lines), which writes every definition to a JSON file so the search page can show a matching glossary entry above the other results.

## The three projects side by side

| | NumPy | Polars | CPython |
|---|---|---|---|
| Unit of a page | one object, a method included | one object, a method included | one module; a large module split by topic |
| Written or generated | generated from docstrings by autosummary | generated from docstrings by autosummary | written by hand |
| Hand-written reference files | 113 | 101 | 336 |
| Reference pages built | 2,443, of which 2,148 generated | 1,541 | 335 |
| Share of object pages that hold a member | 53 percent | 81 percent | none; about 30 objects a page |
| Primary index | by topic, 26 topic pages, by hand | by class, then by topic, by hand; about 1,641 names typed | by topic, 34 topic pages, by hand |
| Check that the index is complete | a script whose output is read by a person | none; a rule in the contributing guide | none needed; the page is the documentation |
| Templates and scripts for pages | 7 templates of 131 lines, 2 scripts, 1 checker of 665 lines | 6 templates of 63 lines, a sidebar override, a 188-line macro, a 505-line link table | none |
| Reference and guide | one build, one site | two builds, two tools, one domain | one build, one site |
| Guide to reference links | 396 roles, resolved at build | 335 macro calls through a hand-kept table; 3 of 143 addresses dead | 1,492 roles, resolved at build |
| Reference to guide links | 75 in docstrings, 165 in pages | one top-bar link, 4 in docstrings | 263 see-also blocks |
| A class with dozens of methods | a flat table of 53 on the generated page; topic groups on a second, hand-written page | a 1.5 MB page with 136 members inline, and a page per member | one page, 81 signatures under hand-written topic headings |
| Glossary | 50 terms; 74 links from pages; 4 from docstrings | none | 178 terms; 2,073 links from pages; 0 from docstrings |
| Stated cost | none stated | none stated | none stated |

## The pattern

Granularity follows how the page is made. INFERRED: the two projects that generate pages from docstrings give every object a page, methods included. The project that writes pages by hand gives a module a page. Nobody in this set generates a page per class with its members on it as the main unit, which is what the vfs site does today; Polars comes closest, and its class pages are the 1.5 MB ones.

A page per member multiplies the page count by ten to twenty. INFERRED: 113 source files become 2,148 generated pages at NumPy and 101 become 1,541 at Polars. More than half of those pages are a single method. The multiplication is paid in the sidebar too: a Polars method page is 94 percent navigation.

The index is by topic and a person keeps it, in all three. INFERRED: no project leads with an alphabetical or a by-module list. The alphabetical index exists only where the tool makes it for free. And where pages are generated, the hand-kept index is the long part: Polars types about 1,641 names into tables, and neither generating project fails a build when a public name is missing.

A class with dozens of methods is always given topic groups. INFERRED: NumPy writes them on a second page, Polars makes a folder of topic pages per class, CPython writes headings on the one page. A flat list of members in one order is nobody's final answer.

One build keeps its links; two builds lose them. INFERRED: NumPy and CPython link guide and reference with roles the build resolves and refuse a broken one. Polars links them with typed addresses, and 3 of 143 were dead when requested. The link back from reference to guide is where separation shows most: 4 docstring links at Polars.

A glossary is linked from prose pages, hardly ever from docstrings. INFERRED: 2,073 against 0 at CPython and 74 against 4 at NumPy. The term most used in NumPy's docstrings is linked once in 1,053 uses.

## One thing each project does that looks like a mistake

NumPy. INFERRED: `ndarray` has two entry pages. The generated one, where a cross-reference to `numpy.ndarray` lands, lists 53 methods in one flat table. The hand-written one, at another address, is the one that groups them by topic. A reader who arrives by link gets the weaker of the two.

Polars. INFERRED: the guide reaches the reference through a table of addresses kept by hand in a 505-line file, with nothing checking them, and 3 were dead. The second cost of the same separation is that each method page ships about 250,000 bytes of sidebar around 16,500 bytes of content.

CPython. INFERRED: the built-in types page is one page of 7,003 source lines and 815,874 bytes with 306 signatures. The project splits `asyncio` into 19 pages by topic and leaves this one whole.

## What each granularity costs a library of 22 names, and of 60

EXECUTED: the vfs package exports 22 names. A rough count of each class's own public names plus its model fields gives about 266 members, twelve a name; the two file-system classes hold 38 and 36, and seven classes hold none of their own. The figures for 60 names below assume the same ratio and are INFERRED.

| Granularity | Pages at 22 names | Pages at 60 names | What a person keeps by hand | What it needs built | Seen in |
|---|---|---|---|---|---|
| One page per member | about 290 | about 790 | every member typed under a topic: about 266 lines now, about 730 later | member templates, a device to write pages the navigation hides, a deep sidebar | NumPy, Polars |
| One page per public name | 22 | 60 | one line per name in a topic index | the list of names, which exists | the vfs site today |
| One page per name, with the error classes sharing a page | 17 | about 45 | the same index, and which names share | the list of names, with groups | CPython's exceptions page, 72 exceptions on one page |
| One page per topic or module | about 6 | 10 to 15 | the grouping pages themselves | nothing beyond hand-written pages that each pull several objects | CPython |

One page per member. INFERRED: this buys a short page for each of 266 members and costs an index of that many typed lines. It suits NumPy because one function's docstring fills a page with parameters, notes, examples and plots. The vfs docstrings are prose with no parameter sections, so a member's page would be a signature and a paragraph inside a full page of navigation. At 60 names it is about 790 pages where the whole site is expected to be about a hundred.

One page per topic. INFERRED: this gives the fewest pages and no generated navigation, and it is what a hand-written reference does. It costs the stable address per name. On the vfs site each glossary term links to the page of the class that defines it and the build hook admits a page only for an exported name; both rest on a name owning a page. A file-systems topic page would also hold both faces, 74 members, which is the size of CPython's `pathlib` page.

One page per public name. INFERRED: 22 pages now and 60 later are both inside what one sidebar section shows. The largest page holds 38 or 39 members. CPython's `pathlib` page holds 81 signatures and reads well because of its topic headings; Polars' DataFrame page holds 136 and is where a page stops being usable. The vfs pages are below the first of those and far below the second.

## What the vfs site should do

Keep one page per public name. Reason: it is the only granularity whose cost does not grow faster than the API. Evidence: a page per member is a nineteenfold and a fifteenfold multiplication at NumPy and Polars and would put about 790 pages on a site planned at about a hundred; a page per topic removes the per-name address the glossary links and the export check stand on. The largest vfs page, at 39 members, is under half of the 81 that CPython keeps on one page.

Put the error classes on one shared page. Reason: a page that holds only a class name and one line is navigation, not reference. Evidence: five exported error classes have no public member of their own and a sixth, `MountError`, has one; CPython documents 72 built-in exceptions on one page. Six pages become one, which takes the count from 22 to 17 now and keeps it near 45 at 60 names if the same share of names stays this small. The two other classes with no member of their own inherit a full set and keep their pages.

Write the API section's entry page by hand, as an index by topic, one line per name. Reason: it is the index all three projects lead with, and at this granularity it is 22 lines now and 60 later, not 1,641. Evidence: `routines.rst` at NumPy, the card grid at Polars, `library/index.rst` at CPython. Group by what the reader is doing (open a file system, act as a caller, read a result, handle an error, store data), not by module and not alphabetically. The two file-system faces sit on one row of that index and keep their own pages; NumPy does the same when `routines.sort.rst` lists `sort` and `ndarray.sort` in one table.

Make the build fail when an exported name has neither a page nor a stated reason to have none. Reason: both generating projects leave index completeness to a person, and that is the one check they lack. Evidence: NumPy's checker says its output must be read by hand, and Polars has only a sentence in its contributing guide. The vfs hook already refuses a page for a name that is not exported; the reverse check is the same comparison turned around, and at 22 to 60 names it costs nothing.

Give a class page topic groups before considering a split. Reason: every project gives a class with dozens of methods a grouping by topic, and none relies on one flat list. Evidence: the hand-written `ndarray` page, the ten DataFrame topic pages, the `pathlib` headings. The vfs classes are already laid out in the source by concern, so listing members in source order carries the grouping; a summary at the top of the page that shows those groups is what the reader needs. Which mkdocstrings option draws that summary is the subject of [the second study](02-how-material-sites-with-mkdocstrings-build-and-shape-api-pages.md).

If a class page ever passes about 80 members, split it by topic, not by member. Reason: that is the size of the largest one-page class in this set that still reads well, and the project that owns it splits by topic when it must. Evidence: `pathlib` at 81 signatures on one page; `asyncio` in 19 topic pages; Polars at 136 members inline and 1.5 MB.

Keep the API reference inside the same build as the rest of the site. Reason: a link between guide and reference is only as good as the tool that checks it. Evidence: 1,492 and 396 resolved roles at CPython and NumPy against a hand-kept table with 3 dead addresses in 143 at Polars, and a single top-bar link in the other direction. The vfs glossary links, the `:term:` check and the links from a glossary term to a class page all need both ends in one build.

Expect the glossary to be linked from the hand-written pages far more than from docstrings, and give those pages the same build-stopping check. Reason: that is where the links are in both projects. Evidence: 2,073 from pages and none from docstrings at CPython; 74 and 4 at NumPy. The vfs check on a docstring's `:term:` is stricter than either project's, which rely on Sphinx's general warning. The same refusal of an unknown term should cover a tutorial, a how-to guide and an explanation page, because most of the links will be written there.

The one-line version: one page per exported name, the error classes sharing one, a hand-written topic index that the build checks for completeness, all in one build with the guide.

## What this study could not settle

Build time. No clone states how long its documentation takes to build, and I did not build any of the three. Building NumPy's and Polars' reference locally and timing a clean build and a one-docstring rebuild would give the figure; the page counts above (2,148 and 1,541 generated pages) are the only cost measured here.

Why NumPy and Polars chose a page per member. Neither clone gives the reason in a file I read, and the CPython clone is shallow. Reading the commit that introduced `doc/source/_templates/autosummary/class.rst` in a full NumPy history, and the pull request that introduced the same template at Polars, would show what each was solving.

How large a vfs class page is when built. The 80-member threshold is taken from other projects' pages, whose docstrings are longer than the vfs ones. Building the vfs site and measuring the `AsyncVirtualFileSystem` page in bytes and in table-of-contents entries would place it against `pathlib`'s 271,233 bytes and 27 headings directly.
