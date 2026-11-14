# None of eight Diátaxis sources puts the API reference beside Reference: it sits inside Reference, or it is all of Reference under another name, and what else Reference holds is grouped by kind of thing

I was asked, as Researcher 01 of [the brief](00-brief.md) on 2026-11-14, where the API reference sits on documentation sites that follow Diátaxis (the framework that sorts documentation into tutorials, how-to guides, reference and explanation), what else their reference sections hold, how the API pages are made, how the other three kinds of page link into them, and how a glossary is kept and linked. The time box was 30 minutes. I used about 11 minutes of it, from 15:05 to 15:16 EST by the clock, and read all eight sources named in my question. Nothing was skipped. No site was built: every figure is a count over source files or a fetch of a live page.

## Sources

- `diataxis-documentation-framework`, commit 957c09c 2026-08-06, CC BY-SA 4.0, studied only. Read `source/reference.rst`, `source/reference-explanation.rst`, `source/how-to-use-diataxis.rst`, `source/index.rst`, and the deleted `complex-hierarchies.rst` from history at `c953482^`.
- `django`, commit f24f38c 2026-11-13, BSD-3-Clause. Read `docs/contents.txt`, `docs/index.txt`, `docs/ref/index.txt`, `docs/glossary.txt`, `docs/intro/whatsnext.txt`, `docs/conf.py`, `.readthedocs.yml`.
- `pytest`, commit fc9a7ef 2026-11-11, MIT. Read `doc/en/index.rst`, `doc/en/contents.rst`, `doc/en/reference/index.rst`, `doc/en/reference/reference.rst`, `doc/en/conf.py`, `scripts/update-plugin-list.py`.
- `hypothesis`, commit 9ab0be6 2026-11-06, MPL-2.0, studied only. Read `hypothesis/docs/index.rst`, `hypothesis/docs/reference/index.rst` and its four pages, `hypothesis/docs/glossary.rst`, `hypothesis/docs/prolog.rst`, `hypothesis/docs/conf.py`, `tooling/src/hypothesistooling/release.py`.
- `numpy`, commit d63a30827d 2026-11-14, BSD-3-Clause. Read `doc/source/index.rst`, `doc/source/reference/index.rst`, `doc/source/user/index.rst`, `doc/source/glossary.rst`, `doc/source/conf.py`, `doc/source/dev/howto-docs.rst`, `doc/neps/nep-0044-restructuring-numpy-docs.rst`, `doc/Makefile`.
- `toga`, commit c2e9a35 2026-11-13, BSD-3-Clause. Read `docs/config.yml`, `docs/mkdocs.en.yml`, `docs/en/SUMMARY.md`, `docs/en/reference/index.md`, `docs/en/reference/api/index.md`, `docs/en/reference/api/widgets/button.md`, `docs/en/reference/api/application/app.md`, `docs/main.py`, `docs/en/reference/data/apis_by_platform.yaml`.
- `sphinx-docs-starter-pack`, commit 47c1ca7 2026-10-16, GPL-3.0, studied only. Read `docs/index.rst`, the six `docs/*/index.rst` files, `docs/conf.py`, `CHANGELOG.md`, `CONTRIBUTING.md`.
- `lxd`, commit f051822 2026-11-13, AGPL-3.0, studied only. Read `doc/index.rst`, `doc/reference/index.md`, `doc/restapi_landing.md`, `doc/rest-api.md`, `doc/api.md`, `doc/reference/manpages.md`, `doc/conf.py`, `Makefile`.
- Live pages, all read 2026-11-14: https://diataxis.fr/reference/ ; https://diataxis.fr/complex-hierarchies/ (HTTP 404) ; https://docs.djangoproject.com/en/dev/ref/ ; https://docs.pytest.org/en/latest/reference/index.html ; https://hypothesis.readthedocs.io/en/latest/reference/index.html ; https://numpy.org/doc/stable/ ; https://toga.beeware.org/en/latest/reference/ ; https://canonical.com/lxd/docs/latest/reference/ (the redirect target of documentation.ubuntu.com/lxd/latest/reference/) ; https://documentation.ubuntu.com/sphinx-stack/latest/ (the redirect target of canonical-starter-pack.readthedocs-hosted.com).
- Every command and the figure it printed is saved in [experiments/01-where-the-api-reference-sits-on-sites-that-follow-diataxis/counts.txt](experiments/01-where-the-api-reference-sits-on-sites-that-follow-diataxis/counts.txt).

Labels: EXECUTED marks a command or fetch I ran whose output I report; READ marks something read in a file cited by path at the commit above, or in a page cited by URL and read 2026-11-14; INFERRED marks my own reasoning from the two.

## What the framework's text says about reference

READ, `source/reference.rst` lines 12 to 14: the purpose of reference is "to describe, as succinctly as possible, and in an orderly way", and reference is "led by the product it describes", where tutorials and how-to guides are led by what the user needs.

READ, lines 20 to 21: for software, "reference guides describe the software itself - APIs, classes, functions and so on - and how to use them." The framework names the API as the first example of reference content. It does not set the API apart from reference anywhere in the page.

READ, lines 45 to 49: generated reference is endorsed and bounded in two sentences. API documentation "can be generated automatically by the software it describes, which is a powerful way of ensuring that it remains faithfully accurate to the code", and a sidebar warns that generated reference is not all the documentation a project needs.

READ, lines 82 to 94, the section "Respect the structure of the machinery": "the structure of the documentation should mirror the structure of the product". The text adds that this does not mean forcing an unnatural structure; the logical arrangement of the code should help the reader make sense of the documentation. The style sidebar at lines 63 to 67 repeats it: reference is "structured according to the structure of the machinery itself".

READ, lines 69 to 79 and 97 to 100: reference describes and does not instruct or explain, and where instruction is wanted the page should "link to how-to guides, explanation and introductory tutorials". Reference should follow standard patterns, because it "is useful when it is consistent". Examples of usage are welcome because they illustrate without instructing.

READ, line 111: the content the framework lists for reference is "commands, options, operations, features, flags, limitations, error messages". READ, `source/reference-explanation.rst` line 29: lists of classes, methods or attributes and tables of information "will generally turn out to belong in reference".

EXECUTED: `git log --diff-filter=D -- complex-hierarchies.rst` shows that the page "Diátaxis in complex hierarchies" was deleted in commit c953482 on 2026-08-03, 272 lines, in a commit titled for translation machinery. `grep -rn -i -E 'landing page|hierarch|seven' source/*.rst` prints nothing, so its content did not move to another page. EXECUTED: the live URL https://diataxis.fr/complex-hierarchies/ returned HTTP 404 on 2026-11-14.

READ, `complex-hierarchies.rst` at `c953482^`: the deleted page held the only site outline the framework ever published. Under a "Reference" landing page it listed three children: "Command-line tool", "Available endpoints" and "API". The API was one child of Reference among other kinds of interface. The same page said a list in a table of contents becomes hard to read past about seven items unless it has a mechanical order such as alphabetical, that a landing page (the page a section opens on) should read as an overview with headings and a line of introduction per group, and that Diátaxis "does not mean that there must be simply four divisions of documentation in the hierarchy".

READ, `source/how-to-use-diataxis.rst` lines 25 to 42: the current text tells authors not to spend effort getting the top structure right first, and not to create empty sections for the four types.

INFERRED: the framework's text places the API inside reference, both in its definition and in its one published outline. It says how reference should be ordered (by the structure of the product) and says nothing on page size, on one page per object, or on a glossary. A glossary is a list of things consulted while working, so by the test at `source/reference-explanation.rst` line 29 it is reference.

## Django

READ, `docs/contents.txt`: the top-level order is intro, topics, howto, faq, ref, misc, glossary, releases, internals. The reference section is `docs/ref/` and its index page is titled "API Reference" (`docs/ref/index.txt` line 2). READ, `docs/index.txt`: the front page names the same section differently, "Reference guides contain technical reference for APIs and other aspects of Django's machinery". The API is not a separate entry. The section called API Reference is the whole reference.

READ, `docs/ref/index.txt`: beside Python classes the section holds the command line (`django-admin.txt`, 2,257 lines), settings (`settings.txt`, 4,205 lines), exceptions, the system check framework with its message identifiers (`checks.txt`), databases, logging, the template language and its built-in tags, and Unicode handling. EXECUTED: the index lists 30 entries in the alphabetical order of their file names, and six of them are folders (class-based-views 12 files, contrib 53, files 4, forms 8, models 14, templates 4). Grouping is by domain of the framework (models, forms, templates), not by kind of thing: the command line and settings are two entries in the same flat list as the model API.

EXECUTED: `grep` finds 0 autodoc directives under `docs/` (autodoc is the Sphinx extension that pulls a docstring into a page), and `docs/conf.py` does not load it. The API is written by hand with Sphinx object directives: 679 `class`, 670 `method`, 138 `function`, 944 `attribute`, 216 `setting`, 50 `exception` under `docs/ref/`. EXECUTED: 509 more `class`, `method`, `function` and `attribute` directives sit outside `ref/`, in topics, howto and intro, so some objects are defined in guide pages.

EXECUTED: `docs/ref/` holds 120 files of 680 in all (400 of the 680 are release notes). 97 of the 120 hold at least one Python object directive, about four in five. The 23 without one include the settings page, the databases page, the template language pages and section indexes.

EXECUTED: the guides link into the reference with Sphinx roles (a role is inline markup such as `:class:` that becomes a link to the object's entry). Counts of object roles including Django's own `:setting:` and `:djadmin:`: intro 152 in 14 files, topics 2,537 in 68 files, howto 487 in 38 files. Page links into `/ref/` are few by comparison: 6, 54 and 5. The reference links back out with 147 page links to topics, howto and intro.

READ, `docs/glossary.txt`: the glossary is a top-level page beside the reference section, not inside it. It is one Sphinx `glossary` directive holding 12 terms. An entry is one or two sentences and most end with a "See" link to a topic guide, not to the API. EXECUTED: the documentation holds 73 `:term:` markers and the Django source holds 0. Only 4 of the 73, outside the glossary page itself, name one of the glossary page's 12 terms. The rest point at four small glossaries declared inside topic and internals pages ("language code" 7 times, "feature release" 5) or at Python's own glossary.

READ, `docs/intro/whatsnext.txt` lines 66 to 71, the reason Django gives for keeping object detail out of guides: covering every class and function in the guides "would be overwhelming when you're trying to learn", so the details "are kept in the reference".

## pytest

READ, `doc/en/index.rst` and the live sidebar: the top entries are Get Started, How-to guides, Reference guides, Explanation, Examples, then "About the project". The API sits inside "Reference guides" as its first page, titled "API Reference" (`doc/en/reference/reference.rst`). It is not a separate top entry.

READ, `doc/en/reference/index.rst`: Reference guides holds five pages: API Reference, Fixtures reference, Configuration, Exit codes and the Pytest Plugin List. The changelog, the deprecations page and the backwards-compatibility policy sit outside, under "About the project" and "Further topics".

EXECUTED: the API Reference is one page of 3,859 lines. Its top sections are grouped by kind of thing: Constants, Functions, Marks, Fixtures, Hooks, Collection tree objects, Objects, Global Variables, Environment Variables, Exceptions, Warnings, Configuration Options, Command-line Flags. The command line (92 `option` directives), the configuration file keys (56 `confval`) and the environment variables (14 `envvar`) are sections of the page named API Reference.

EXECUTED: the page is a mix of generated and hand-written entries: 81 `autofunction`, 63 `autoclass`, 2 `autoexception` and 2 `autoattribute` directives pull docstrings; hooks, fixtures, options and configuration keys are written by hand. READ, `scripts/update-plugin-list.py` line 214: the plugin list page (17,688 lines) is written by a script.

EXECUTED: five reference pages; one is the API. By lines the API page is 3,859 of the 4,643 lines of the four hand-kept pages, 83%.

EXECUTED: guides link in with roles: 292 in the 24 how-to files, 42 in the 8 explanation files, 42 in the examples. pytest has no glossary: no `glossary` directive, 0 `:term:` markers in `doc/en` and 0 in `src`.

## Hypothesis

READ, `hypothesis/docs/index.rst` and the live sidebar: the top entries are Quickstart, Tutorial, How-to guides, Explanations, API Reference, Stateful tests, Extras, Glossary, Changelog, then a second group "About Hypothesis". The fourth Diátaxis slot is named "API Reference" and lives in the folder `reference/`. There is no other reference entry.

READ, `hypothesis/docs/reference/index.rst`: the section is "split into four pages", each with a stated scope. "API Reference" holds "Non-strategy Hypothesis objects, classes, and functions". "Strategies Reference" holds the strategies. "Integrations Reference" holds "Features with a defined interface, but no code API": the ghostwriter, the observability data format, the pytest plugin, the command line. "Hypothesis internals" holds internal APIs for tool builders. That third page is the project's own statement of why some reference is kept apart from the Python API: it has an interface and no code object to document.

EXECUTED: the four pages are generated in place by autodoc inside hand-ordered topical headings: 74 `autofunction`, 39 `autoclass`, 10 `automodule`, 8 `autodata`, 7 `automethod`, and one hand-written `data` directive. The headings are topics (Settings, Database, Stateful tests, Numeric, Strings, Collections), not modules and not the alphabet. Page sizes are 529, 280, 308 and 49 lines of source.

EXECUTED: four reference pages, all under the API Reference entry; three are the Python API and one is the non-code interfaces.

READ, `hypothesis/docs/conf.py` line 290 and `hypothesis/docs/prolog.rst`: links into the API are made through substitutions (a substitution is a short name between bars, such as `|@given|`, that Sphinx replaces with a role). `prolog.rst` defines 209 of them and is prepended to every page and every docstring. EXECUTED: uses in the guides: tutorial 143 in 9 files, how-to 40 in 6 files, explanation 33 in 3 files.

READ, `hypothesis/docs/glossary.rst`: the glossary is a top-level page, outside the reference folder. It holds 5 terms under two headings, "User glossary" ("Terms that are part of our public API") and "Developer glossary". An entry is a definition, often with a code example, and links to API objects through the same substitutions. EXECUTED: 11 of the substitutions wrap a `:term:` role. They are used 23 times in documentation pages (3 of those inside the glossary page itself) and 34 times in the source docstrings. The docstrings link to the glossary more often than the pages do. READ, `hypothesis/docs/conf.py` line 29 and `tooling/src/hypothesistooling/release.py` lines 141 to 146: the build runs with `nitpicky = True` and `--fail-on-warning`.

## NumPy

READ, `doc/source/index.rst` lines 7 to 15: the top entries are User Guide, API reference, Building from source, Development, Release notes. EXECUTED: the live top bar at https://numpy.org/doc/stable/ shows the same five and adds two links the clone's table of contents does not hold, Learn and NEPs. NumPy does not use the four Diátaxis names in its navigation. READ, `doc/source/dev/howto-docs.rst` lines 74 to 82: it does adopt the four types for writing, crediting the framework by name. READ, `doc/neps/nep-0044-restructuring-numpy-docs.rst` line 194: the plan lists "Reference Guide (API Reference)" as one item, so the project treats the two names as the same thing.

READ, `doc/source/reference/index.rst`: the entry called API reference opens on a page titled "NumPy reference" with three headings: "Python API" (module structure, array objects, universal functions, routines by topic, typing), "C API", and "Other topics" (array API standard, SIMD, thread safety, global state, security, testing, SWIG). There is no command-line or settings reference; release notes are a separate top entry.

EXECUTED: the API is generated. `doc/source/reference/` holds 113 source files (72 at its top level, 24 under random, 13 under c-api, 4 under simd). They hold 233 `autosummary` directives in 44 files listing 1,674 entries (autosummary is the Sphinx extension that turns a list of names into a table and, when asked, a generated page per name), from the templates in `doc/source/_templates/autosummary/`. The index pages that list the names are written by hand, by topic. The built page count is Researcher 03's subject.

EXECUTED: the user guide links into the API with 397 object roles in 39 files, plus 93 bare back-tick names resolved by `default_role = "autolink"` (`doc/source/conf.py` line 159).

READ, `doc/source/user/index.rst` line 51: the glossary is `doc/source/glossary.rst`, attached only through a hidden "Extras" table of contents under the user guide. EXECUTED: the live front page has no link to it. It holds about 50 terms in one `glossary` directive; entries run from one sentence to several paragraphs with examples and link to reference pages. EXECUTED: 100 `:term:` markers in the documentation source (26 inside the glossary itself, 20 in the user guide, 21 in the reference) and 9 in the Python source.

## Toga

READ, `docs/config.yml`: Toga is built with Material for MkDocs with `navigation.tabs`, literate-nav and mkdocstrings, the same tool family as the vfs site. READ, `docs/en/SUMMARY.md`: the tabs are Tutorials, How-to guides, Topic guides, Reference, About Toga. Inside Reference there are two entries: "API reference" and "Supported platforms". EXECUTED: the live Reference page lists the same two. The API is inside Reference, as a named sub-section.

READ, `docs/en/SUMMARY.md`: the API reference is grouped by domain in seven hand-named groups: Application components, Widgets, Container widgets, Style, Data representation, Resources, Hardware. Two groups fix their order by hand (Application components for its first four pages, Data representation for all twelve) and the rest fall to the alphabet through a wildcard. Release history sits outside Reference, under About Toga. There is no command line, no settings page and no glossary.

EXECUTED: 68 files under `docs/en/reference/` of 121 pages in all; 56 are API (82%), 11 are platforms. One page covers one component. READ, `docs/en/reference/api/widgets/button.md`: a page is written by hand and holds a generated block. EXECUTED: 55 pages have a "## Reference" heading that holds the `:::` lines (185 lines in all), 53 have a "## Usage" heading with prose and code above it, 28 have "## Notes". READ, `docs/en/reference/api/index.md` and `docs/main.py` lines 26 to 36 and 119 to 128: the API landing page is a table per group, rendered by a macro from one data file, `docs/en/reference/data/apis_by_platform.yaml`, which holds each component's name, one-line description and platform support.

EXECUTED: guides link into the API by object name through autorefs (the MkDocs plugin that resolves `[toga.App][]` to wherever that object is documented): tutorial 12, how-to 30, topics 34. They hold 0 links by file path into `reference/`. EXECUTED: the redirect table in `docs/config.yml` holds 39 entries for reference pages that moved between folders.

## Canonical's starter pack

READ, `docs/index.rst`: the template's navigation is tutorials, how-to, reference, explanation, then a second group holding release-notes and contribute. Release notes are outside Reference in the template. EXECUTED: `docs/reference/index.rst` is 4 lines, a label and the title "Reference". The template says nothing about what Reference holds or where an API goes.

READ, `CONTRIBUTING.md` lines 150 and 279: the project names Diátaxis as the structure for new pages. READ, `docs/conf.py`: autodoc is not among the default extensions; a comment only notes that module pages generated by autodoc could be left out of the sitemap. READ, `CHANGELOG.md` line 146: guidelines "for pulling in docstrings using Sphinx `autodoc`" were introduced, but that guidance is not in this clone at this commit. EXECUTED: the pack's own documentation now redirects to https://documentation.ubuntu.com/sphinx-stack/latest/, whose front page lists the four sections and does not mention API documentation.

INFERRED: the template fixes the four sections and leaves the inside of Reference to each product. LXD, below, shows what a Canonical product then does.

## LXD

READ, `doc/index.rst` line 261: "This documentation uses the Diátaxis documentation structure", and the reference guides "include configuration options, API references, and other technical details". EXECUTED: the live top entries are Tutorial, How-to guides, Explanation, Reference.

READ, `doc/reference/index.md`: the Reference landing page has seven headed groups, each with one sentence of introduction: General information (requirements, architectures, guest compatibility, man pages for the command line), Releases (release notes, deprecation notices), Images, Configuration options, Production setup, API and integrations, Internal implementation details. The REST API is one entry in the sixth group, with the sentence "LXD exposes a REST API for managing all resources". Grouping is by kind of thing. LXD is the only project of the eight that puts release notes inside Reference.

READ, `doc/restapi_landing.md`: the REST API entry opens its own landing page with five pages under it: an overview, the specification, the extensions list, the events stream and the instance-side API. READ, `doc/api.md` and `Makefile` lines 329 to 334: the specification page is a Swagger UI viewer over `doc/rest-api.yaml` (22,076 lines), generated from annotations in the Go source by `make update-api`. READ, `doc/conf.py` lines 390 to 407 and `Makefile` line 82: the man pages are generated at build time by running the client, and the configuration options come from `doc/metadata.txt` (8,310 lines), generated from comments in the Go source. The overview and landing pages are hand-written.

EXECUTED: 231 documentation files; 85 under `doc/reference/`, of which 27 are release notes; 42 more pages sit at the `doc/` root, among them every REST API page. The API is six pages, under a tenth of the reference.

EXECUTED: guides link into the generated reference by name: 590 uses of the `{config:option}` role (116 in how-to guides, 23 in explanation, 6 in the tutorial) against 986 option entries, and 156 links with the `swagger:` scheme to REST endpoints. LXD has no glossary and 0 `:term:` markers.

## The eight side by side

| Source | Name of the reference entry | Where the API is | What else reference holds | How reference is grouped | API pages made by | Reference pages and API share | Glossary |
|---|---|---|---|---|---|---|---|
| Diátaxis text | Reference | inside: named first in the definition; a child of Reference in the deleted outline | command-line tool, endpoints; commands, options, flags, limitations, error messages | by the structure of the product | either; generation endorsed for accuracy | not applicable | not mentioned |
| Django | "API Reference" (front page says "Reference guides") | it is the section; not kept apart | command line, settings, exceptions, check messages, databases, template language | by domain, flat list of 30 in file-name order | hand, 0 autodoc | 120 files; 97 hold an object directive | top-level page, 12 terms, 4 inbound links to them |
| pytest | "Reference guides" | inside, first of five pages | fixtures, configuration, exit codes, plugin list | by kind of thing, on the page and across pages | mixed: 148 auto directives, the rest hand | 5 pages; API is 1 page and 83% of hand-kept lines | none |
| Hypothesis | "API Reference" | it is the section, split in four | integrations with no code API, internals | by kind of thing across pages, by topic within | autodoc inside hand-ordered headings | 4 pages; 3 are Python API | top-level page, 5 terms, 23 links from pages and 34 from docstrings |
| NumPy | "API reference" (page title "NumPy reference") | it is the entry; Python API, C API and other topics are its three headings | C API, SIMD, thread safety, security, testing | by language, then by topic | autosummary, 1,674 listed entries, hand-kept topic indexes | 113 source files; 17 are C API or SIMD | page hidden under the user guide, about 50 terms, 100 markers, 9 in source |
| Toga | "Reference" | inside, the sub-section "API reference" | supported platforms | by domain, seven groups | hand-written page with a generated block, mkdocstrings | 68 pages; 56 API (82%) | none |
| Canonical starter pack | "Reference" | not stated; the page is a bare title | nothing stated; release notes sit outside | not stated | not stated | 1 empty page | none |
| LXD | "Reference" | inside, in the group "API and integrations" | man pages, release notes, images, configuration options, metrics, internals | by kind of thing, seven groups with an introduction each | generated: Swagger from Go annotations; hand-written overview | 85 files plus root pages; API is 6 pages | none |

## The pattern

INFERRED from the table: in none of the eight is the API reference a top-level entry beside a Reference entry. There are two shapes. In the first, the entry is called Reference and the API is one named part of it: pytest, Toga, LXD, and the framework's own deleted outline. In the second, the entry is called API Reference and it is the only reference there is: Django, Hypothesis, NumPy. The second shape is not a separation. It is the same slot under a narrower name.

INFERRED: the narrower name stops fitting as soon as the product has an interface that is not Python objects. Django's "API Reference" holds 6,462 lines of command-line and settings reference. pytest files its command-line flags and configuration keys as sections of a page called "API Reference". Hypothesis had to write "Features with a defined interface, but no code API" to explain a page inside "API Reference". The three sites named Reference (pytest's section, Toga, LXD) need no such explanation.

INFERRED: the reasons given for any separation are about the reader's task, never about how the page was made. Django keeps object detail out of the guides because it "would be overwhelming when you're trying to learn". Hypothesis splits a page off for interfaces with no code object. LXD introduces its API group with what the API is for. No project says that generated pages belong apart because they are generated, and pytest, Hypothesis and Toga all mix generated blocks with hand-written text on one page.

INFERRED: what else reference holds is the same short list everywhere it exists: the command line, configuration or settings, errors and exit codes, file and data formats, supported platforms. Release notes sit outside Reference in six of the seven sources that have them or template them (Django, pytest, Hypothesis, NumPy, Toga, the starter pack); LXD alone puts them inside.

INFERRED: the sites whose reference is named Reference group it by kind of thing first (pytest's page sections, LXD's seven groups, Toga's API beside platforms), and then group the API by domain or topic (Toga's seven groups, Hypothesis's headings, NumPy's routines by topic). Nobody orders the API index by module or by the alphabet on purpose. Django's index is alphabetical by file name only, and reads as unordered on the live page.

INFERRED: guides link to the API by object name, not by page. Every site uses a mechanism that resolves a name to wherever the object is documented: Sphinx roles (Django 3,176, pytest 376, NumPy 397), substitutions (Hypothesis 216), autorefs (Toga 76), a custom option role (LXD 590). Toga's guides hold 0 path links into the reference, and its redirect table of 39 moved reference pages shows why that matters: pages move, names do not.

INFERRED: a glossary is the weakest part of every site that has one. Three of the eight have one, and all three keep it outside the reference section. Django's 12 terms receive 4 links. NumPy's is hidden from the front page. Only Hypothesis links it steadily, 57 times for 5 terms, and it does so from docstrings through a shared substitution. READ: all three build with warnings treated as errors: Django through `fail_on_warning: true` in `.readthedocs.yml` line 13, NumPy through `SPHINXOPTS ?= -W` in `doc/Makefile` line 14, Hypothesis through `--fail-on-warning`. INFERRED: Sphinx warns when a `:term:` names a term no glossary defines, so in all three an unknown term stops the build. The guard is the general warning gate, not a glossary check any of them wrote. I did not run a build to see it fail.

## One thing in each that looks like a mistake

- INFERRED, Diátaxis text: it deleted the only page that showed where an API, a command line and a landing page go, in a commit about translation, and the live URL is now a 404. The current text tells a reader what reference is and no longer shows how a reference section is laid out.
- INFERRED, Django: the section is titled "API Reference" on its own page and "Reference guides" on the front page, and its 30-entry index is ordered by file name, so "System check framework" follows "Applications" and the command line hides under the letter d. The index is four times the seven-item limit the framework's deleted page gave.
- INFERRED, pytest: one page of 3,859 lines called "API Reference" carries the command-line flags, the configuration keys and the environment variables, while a separate page called "Configuration" also exists. A reader looking for a configuration key has two places to look.
- INFERRED, Hypothesis: the section and its first page are both called "API Reference", and "Stateful tests" and "Extras" sit as top-level entries outside the four types.
- INFERRED, NumPy: the glossary, about 50 terms and 100 links, is attached only through a hidden table of contents and is not linked from the front page or the reference index.
- INFERRED, Toga: every API page has a "Usage" section of instruction-like prose above the generated block, which the framework's text advises linking to instead of including. The configuration needs `resolve_closest` because every page repeats the same headings, and the comment on `members_order: alphabetical` in `docs/config.yml` line 156 says the opposite of the setting.
- INFERRED, starter pack: `docs/reference/index.rst` is a bare title, so the template that many product sites start from gives no model for the section that most needs a standard pattern.
- INFERRED, LXD: release notes, 27 of the 85 files under `doc/reference/`, sit inside Reference, and the REST API pages sit at the `doc/` root while their landing page is listed from `doc/reference/`. An explanation page (`/explanation/instance_config`) is listed in the Reference configuration group.

## What the vfs site should do

1. Keep the API inside the Reference tab, as a named sub-section. Reason: the framework defines reference by the API, and a separate tab would split one kind of content across two entries. Evidence: 0 of 8 sources put the API beside Reference; the framework's definition (`source/reference.rst` lines 20 to 21) and its deleted outline both place it inside; Toga, on the same Material for MkDocs and mkdocstrings tools with tabs, uses Reference then "API reference".

2. Keep the tab's name "Reference" and call the sub-section "Python API". Reason: vfs has a command line, settings, error kinds and a storage protocol, and "API Reference" as the name of the whole would misfile all four. Evidence: Django, pytest and Hypothesis each file non-Python interfaces under a heading that says API, and Hypothesis had to explain it in a sentence.

3. Group Reference by kind of interface, one sidebar group each, with a landing page that gives each group one sentence. The groups the brief already names are Python API, Command line, Settings, Errors, Access levels, Storage protocol and Glossary. That is seven. Reason: a reader who consults reference arrives knowing which interface they are using, and the framework asks that the documentation mirror the structure of the product. Evidence: LXD's seven introduced groups; pytest's five pages by kind; the framework's outline (command-line tool, endpoints, API) and its seven-item limit for a list; Django's flat list of 30 as the counter-example.

4. Order the Python API group by domain in a hand-kept list, not by the alphabet and not by module. The list the build hook already holds is the right place for that order, with a group name per run of names. Reason: 22 names today and 60 later are too many for one flat list, and an alphabetical list puts `AsyncVirtualFileSystem` first and `VirtualFileSystem` last. Evidence: Toga's seven hand-named groups over 56 pages with a wildcard for the rest; Hypothesis's topical headings over generated entries; NumPy's hand-kept topic indexes over 1,674 generated entries; Django's file-name order as the counter-example.

5. Generate the API landing page from the same list that creates the pages, one row per name with its one-line summary. Reason: a landing page kept by hand drifts from the pages. Evidence: Toga renders its API index tables from one data file by a macro (`docs/main.py` lines 119 to 128); the framework's deleted page asks that a landing page read as an overview, not a bare list.

6. Keep generated API pages free of instruction, and link out to how-to guides and explanation instead. Reason: the framework's text says reference describes and links to the rest. Evidence: `source/reference.rst` lines 69 to 71; Toga's 53 "Usage" sections show the alternative and what it costs (duplicate headings on every page, and how-to content that no how-to index lists). Examples inside docstrings are within the rule (`source/reference.rst` lines 97 to 100).

7. Link from tutorials, how-to guides and explanation to API objects by name through autorefs, never by file path. Reason: the page an object lives on will change as the reference grows from five pages to a hundred, and a name survives that. Evidence: every site studied links by name (3,176 roles in Django's guides, 76 autorefs in Toga's with 0 path links); Toga's table of 39 redirects for moved reference pages.

8. Keep the Glossary inside the Reference tab, as its last group, and keep the build stop on an unknown term. Reason: a glossary is a list consulted while working, which is the framework's test for reference, and the sites that park it elsewhere barely link to it. Evidence: Django's 12 terms draw 4 links; NumPy's glossary is unreachable from the front page; Hypothesis, the only site that links terms from docstrings, gets 34 docstring links and 23 page links for 5 terms. The vfs `:term:` marker in docstrings is the Hypothesis practice. The vfs build stop on an unknown term gives the guarantee the three Sphinx sites get from building with warnings as errors, which MkDocs does not give by default.

9. Keep release notes and project history outside Reference. Reason: they are read once per release, not consulted while working. Evidence: six of the seven sources that have or template release notes keep them outside; in LXD, the exception, they are 27 of 85 reference files.

The one-line version: the API is reference, so it stays in the Reference tab under the name "Python API", beside the command line, settings, errors, access levels, the storage protocol and the glossary, each its own group, ordered by kind of interface and linked to by object name.

## What this study did not settle, and what would settle it

- Whether Canonical's current guidance on docstring-generated pages places them in Reference. The clone holds only the changelog line; the guidance lives in the `sphinx-stack` documentation, which was not cloned. Reading the how-to pages under https://documentation.ubuntu.com/sphinx-stack/latest/how-to/ would settle it.
- How many built pages NumPy's 1,674 autosummary entries become, and what one looks like. That is the subject of Researcher 03's file, [03-one-page-per-object-at-scale-and-an-api-reference-kept-apart.md](03-one-page-per-object-at-scale-and-an-api-reference-kept-apart.md).
- Whether readers reach an API page faster from a top-level tab than from a group inside Reference. No source studied measures it. A site search log or a first-click test on the built vfs site with both layouts would settle it; nothing public does.
- Whether an undefined glossary term does stop the Django, NumPy and Hypothesis builds as inferred from their warning settings. Running each project's documentation build in a scratch copy with one undefined `:term:` inserted would settle it.
