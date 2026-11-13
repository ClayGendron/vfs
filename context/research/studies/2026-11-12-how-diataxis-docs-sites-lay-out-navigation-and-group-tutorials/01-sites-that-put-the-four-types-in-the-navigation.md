# Single-product sites that follow Diátaxis put the four types at the top of the navigation, usually under the Diátaxis words, and put the product's domains one level down inside each type and on the landing page; the one multi-product site turned it around and now leads with products

I was asked which documentation sites that say they follow Diátaxis put its four types into their navigation, how literally, under which names, and what a product with several components does. I worked on 2026-11-12 in a 30-minute time box and used about 30 minutes. I studied thirteen sites: diataxis.fr, Django, four Canonical sites and the Canonical Sphinx starter pack, pytest, NumPy with NEP 44, LangChain then and now, Cloudflare Workers, Wagtail, and three Python libraries found by search: Hypothesis, Briefcase (BeeWare) and minterpy. Hypothesis does not name Diátaxis anywhere I read, so it counts as a site with the shape but no stated adoption. Briefcase and minterpy name Diátaxis in their contributor pages. I read navigation from source files where a public repository holds them and from the live page otherwise; each section says which. The short outlines I saved are in [experiments/01-sites-that-put-the-four-types-in-the-navigation/navigation-outlines.txt](experiments/01-sites-that-put-the-four-types-in-the-navigation/navigation-outlines.txt).

## Sources

All read on 2026-11-12.

- https://diataxis.fr/ (live page) and https://raw.githubusercontent.com/evildmp/diataxis-documentation-framework/main/source/index.rst (navigation source); https://github.com/evildmp/diataxis-documentation-framework/tree/main/source (file listing)
- https://diataxis.fr/how-to-use-diataxis/, https://diataxis.fr/application/, https://diataxis.fr/start-here/
- https://diataxis.fr/complex-hierarchies/ and https://www.diataxis.fr/complex-hierarchies/ (both returned 404)
- https://docs.djangoproject.com/en/5.2/, https://docs.djangoproject.com/en/dev/, https://docs.djangoproject.com/en/5.2/intro/, https://docs.djangoproject.com/en/5.2/howto/, https://docs.djangoproject.com/en/5.2/topics/, https://docs.djangoproject.com/en/5.2/ref/
- https://raw.githubusercontent.com/django/django/main/docs/index.txt and https://raw.githubusercontent.com/django/django/main/docs/contents.txt
- https://github.com/canonical/sphinx-docs-starter-pack, https://raw.githubusercontent.com/canonical/sphinx-docs-starter-pack/main/docs/index.rst, https://raw.githubusercontent.com/canonical/sphinx-docs-starter-pack/main/docs/how-to/index.rst
- https://ubuntu.com/server/docs/ (redirect target of https://documentation.ubuntu.com/server/), https://raw.githubusercontent.com/canonical/ubuntu-server-documentation/main/docs/index.md, .../docs/how-to/index.md, .../docs/tutorial/index.md
- https://canonical.com/juju/docs/juju-cli/latest/ (redirect target of https://documentation.ubuntu.com/juju/latest/)
- https://canonical.com/lxd/docs/latest/ (redirect target of https://documentation.ubuntu.com/lxd/latest/)
- https://canonical.com/maas/docs
- https://docs.pytest.org/en/stable/
- https://numpy.org/doc/stable/, https://numpy.org/doc/stable/user/index.html, https://numpy.org/numpy-tutorials/, https://numpy.org/neps/nep-0044-restructuring-numpy-docs.html
- https://docs.langchain.com/ and https://raw.githubusercontent.com/langchain-ai/docs/main/src/docs.json (today's navigation source)
- https://raw.githubusercontent.com/langchain-ai/langchain/v0.3/docs/sidebars.js and .../v0.3/docs/docusaurus.config.js (the earlier navigation); https://python.langchain.com/docs/introduction/ (now a 308 redirect)
- https://developers.cloudflare.com/workers/ (page and raw HTML header), https://developers.cloudflare.com/workers/llms.txt, https://developers.cloudflare.com/workers/tutorials/, https://api.github.com/repos/cloudflare/cloudflare-docs/contents/src/content/docs/workers
- https://docs.wagtail.org/en/stable/, https://raw.githubusercontent.com/wagtail/wagtail/main/docs/index.rst, https://docs.wagtail.org/en/stable/contributing/documentation_modes.html
- https://hypothesis.readthedocs.io/en/latest/, https://raw.githubusercontent.com/HypothesisWorks/hypothesis/master/hypothesis/docs/index.rst, .../hypothesis/docs/changelog.rst
- https://briefcase.beeware.org/en/stable/, https://raw.githubusercontent.com/beeware/briefcase/main/docs/en/SUMMARY.md, .../docs/config.yml, .../docs/en/tutorial/index.md, https://beeware.org/contributing/guide/what/write-docs/
- https://minterpy-project.github.io/minterpy/stable/ and https://minterpy-project.github.io/minterpy/stable/contributors/contrib-docs/docs-design.html
- Page counts: https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1 for canonical/ubuntu-server-documentation, pytest-dev/pytest, django/django, minterpy-project/minterpy, numpy/numpy, numpy/numpy-tutorials, wagtail/wagtail, canonical/lxd and HypothesisWorks/hypothesis

EXECUTED means a command or fetch I ran whose output I report; READ means something read in a page or file cited above by URL on 2026-11-12; INFERRED means my own reasoning from the two.

## How the counts were taken

EXECUTED: page counts marked "files" come from the GitHub git-trees API. I counted documentation source files (.md, .rst, .txt, .mdx, .ipynb) under each top-level docs folder. A count includes each section's index page, so the number of real pages is the count minus one. Counts marked "entries" are items read from a live sidebar or index page. Counts marked "estimated" are neither, and say so.

## The sites, one by one

### diataxis.fr, the framework's own site

READ: the navigation source is five toctrees in `source/index.rst`. A hidden Home. Then "Start here". Then a practical group: Applying Diátaxis, Tutorials, How-to guides, Reference, Explanation, The compass, Workflow. Then a theory group: Understanding Diátaxis, Foundations, The map, Quality, Tutorials and how-to guides, Reference and explanation. Then a hidden tail: Colophon, Translation, News. It has no horizontal bar of its own beyond the theme's header.

INFERRED: the four type names appear in its sidebar because they are the subject of the site, not because the site is organised by type. Every page on diataxis.fr is explanation or how-to about writing docs. It is not an example of a four-part documentation site.

READ: what the site says a documentation site should look like is little. The landing page says documentation should be organised around the four needs, and gives no layout. The "Start here" page gives one structural rule, that reference should mirror the structure of the thing it describes. The workflow page argues against building the structure top-down and against creating empty sections for the four types first: structure should emerge as content improves, from the inside. Nothing I read on these pages addresses landing pages, multiple components or multiple audiences.

EXECUTED: the page on complex hierarchies, which search engines still list at `/complex-hierarchies/`, returns 404 on both the bare and the www domain, and no such file is in `source/`. A search snippet still describes it: the second axis (topic areas or user types) crossing the four types, loosening the structure where needed, and the test being whether forms stay unmixed. INFERRED: the site has dropped that page; its guidance on a second dimension is no longer on the live site.

Mistake: a page that the wider web still cites now 404s with no redirect.

### Django, where the four-part split began

READ: Django's top bar belongs to the project website (Overview, Download, Documentation, News, Code, Issues, Community, Foundation, Donate), with a documentation sub-bar for Getting Help, language and version. The documentation itself has no horizontal section bar.

READ: the master toctree in `docs/contents.txt` is type first: `intro`, `topics`, `howto`, `faq`, `ref`, `misc`, `glossary`, `releases`, `internals`. The four types are renamed: tutorials live in "intro" and are shown as "First steps" and "Getting started"; explanation is "Topic guides"; reference is "Reference guides" (the index page is titled "API Reference"); how-to keeps the Diátaxis words, "How-to guides".

READ: the landing page is not type first. It is a domain index: The model layer, The view layer, The template layer, and so on, each row linking to topic, reference and how-to pages side by side. In the development version the domain headings were reworked (Other core functionality, User-facing features, Developer-facing features, Resources and interfaces, Quality and dependability) and "How the documentation is organized", which names the four types, moved from third place to last. No notice on the page announces the change.

EXECUTED counts (files): intro 14, topics 68, howto 38, ref 120. READ (entries): the how-to index lists 23 guides in five domain groups, the last called "Other guides"; topics list 26 top-level entries; reference lists 30.

READ: tutorials are one numbered path, Parts 1 to 8, then two "Follow-on tutorials" (called "Advanced tutorials" in 5.2): how to write reusable apps, and writing a first contribution. The "intro" section landing page is a plain ordered list from overview and install through the eight parts to "What to read next". The how-to landing page is a list grouped by domain.

Mistake: a page titled "How to write reusable apps" is filed as a tutorial, and the how-to index ends in a catch-all "Other guides" of five unrelated items.

### Canonical: the starter pack, Ubuntu Server, Juju, LXD and MAAS

READ: the Sphinx starter pack's `docs/index.rst` ships the default layout. One hidden toctree holds `tutorials`, `how-to`, `reference`, `explanation`, in that order. A second holds `release-notes` and `contribute`. The how-to index is an empty skeleton. The landing body has an overview, a paragraph on how the docs are organised, and "Project and community".

READ, Ubuntu Server (source `docs/index.md`, live at ubuntu.com/server/docs/ after a 301 redirect): the sidebar is Tutorial, How-to guides, Reference, Explanation, then Contributing. There is no horizontal section bar. Inside each type the second level is the product's domains: how-to has 13 domain groups (Server installation, Security, Networking, Managing software, Data and storage, Mail services, Web services, Graphics, Virtualisation, Containers, High availability, Observability, Debugging), and explanation repeats most of the same names. The landing page has an "In this documentation" section that lists the domains (Getting started, Networking, Security, Managing your system, Data and storage, ...) with links that reach into several types, then "How this documentation is organized", then "Project and community".

EXECUTED counts (files), Ubuntu Server: tutorial 7, how-to 153, explanation 79, reference 10. READ: the tutorial index has five tutorials under two headings, "Getting started" (one: basic installation) and "Next steps" (four).

READ, Juju (live, after a 301 from documentation.ubuntu.com): sidebar Tutorial, How-to guides, Reference, Explanation, then "For contributors" (which holds its own How-to guides and Reference), then Release notes. Related products (Charmcraft, Ops, Pebble, the Terraform provider and others) are separate sites linked from "Related links", not sections of this one. The landing page has "In this documentation" grouped by task, then "How this documentation is organised", then "Project and community".

READ, LXD (live, after a 301): sidebar LXD (home), Tutorial, How-to guides, Explanation, Reference. How-to is grouped by domain (Getting started, Server and client, Instances, Images, Projects, Storage, Networking, Clustering, Production setup, ...). Release notes and the REST API sit inside Reference. The landing page shows domain cards (Start here, System containers and virtual machines, Clusters, Storage and networks, Access LXD, Quality, Lifecycle and administration). EXECUTED counts (files): tutorial 1, howto 87, explanation 15, reference 86, and 46 pages at the docs root.

READ, MAAS (live): sidebar Home, Tutorial, How-to guides (27 entries, the first "Get started"), Reference (API, CLI, configuration), Explanation (18 entries). The landing page shows a four-quadrant grid, one cell per type.

INFERRED: Canonical is the most literal adopter. The four types are the top level, named with the Diátaxis words, singular "Tutorial" on most product sites. A multi-component product is split into separate sites, one per component, and each site is type first. The domain axis appears twice: as the second level inside each type, and as the landing page's "In this documentation" list.

Mistakes: Juju nests a second set of types (How-to guides, Reference) under "For contributors". MAAS puts "Get started" inside How-to guides while Tutorial sits above it, so a newcomer sees two starting points. LXD's sidebar orders Explanation before Reference while its own landing text orders them the other way.

### pytest

READ (live sidebar): Get Started, How-to guides (23 entries), Reference guides (5), Explanation (7), Examples and customization tricks (8), About the project, Useful links. No horizontal section bar. The landing page shows a short example, a feature list, and a "Documentation" block that links the four areas with one line each.

EXECUTED counts (files): how-to 24, reference 6, explanation 8, example 10, plus a single getting-started page at the root.

INFERRED: three types keep the Diátaxis words; the tutorial is renamed "Get Started" and is one page. The site does not name Diátaxis on the landing page. "Examples and customization tricks" is a fifth, untyped section.

Mistake: the untyped Examples section sits beside the four types at the same level, so a reader looking for a recipe has two places to look.

### NumPy and NEP 44

READ (live): NumPy has a horizontal top bar: User Guide, API reference, Building from source, Development, Release notes, Learn (an external site of tutorials), NEPs (external). Version switcher and GitHub link sit at the right. The landing page shows four cards: Getting started, User guide, API reference, Contributor's guide.

READ: inside the User Guide the sidebar groups are Getting started (4), Fundamentals and usage (fundamentals, NumPy for MATLAB users, a link to the tutorials site, how-tos), Advanced usage and interoperability (5), and Extras (4). How-tos are one entry, not a section.

READ: NEP 44, accepted in 2020, splits the docs by audience first (users; developers and contributors; meta information) and lists the four types as parts of the users' side: tutorials, how-tos, reference, explanations. EXECUTED counts (files): user 39, reference 114; the separate tutorials repository holds 12 notebooks.

INFERRED: NumPy put audience on the top bar and folded three of the four types into one "User Guide". Only reference has its own top-level entry. The NEP's type list did not become the navigation.

Mistake: how-to guides, which the NEP asked for as a section, are a single entry two levels down inside the User Guide.

### LangChain and LangGraph, then and now

READ: in the v0.3 documentation (Docusaurus, `docs/sidebars.js` on the v0.3 branch) the sidebar was Introduction, Tutorials, How-to guides, Conceptual guide, then Ecosystem, Versions, and integrations. The top bar held Integrations, API Reference, More, and the version. That was a literal four-type layout with explanation renamed "Conceptual guide" and reference moved to the top bar.

EXECUTED: `python.langchain.com/docs/introduction` now returns a 308 redirect to docs.langchain.com. READ: today's site is built with Mintlify, and its `docs.json` navigation is product first. Two product groups: "Agent development lifecycle" (Home, Build, Test, Deploy, Monitor) and "Products and setup" (LangSmith setup, LLM Gateway, No-code agents, Engine, Deep Agents Code). Under Build a language dropdown (Python, TypeScript) leads to tabs by component: Overview, Managed Deep Agents, Deep Agents, LangChain, LangGraph, OpenWiki, Integrations, Learn, Reference, Contribute.

EXECUTED counts (entries in `docs.json`, Python side): LangChain tab 60, LangGraph 36, Deep Agents 39, Learn 27, Reference 16. Inside the LangChain tab the groups are by feature: Get started, Core components, Middleware, Frontend, Advanced usage, Agent development, Production.

READ: the four types survive in one place. The "Learn" tab holds a "Tutorials" group of 14, grouped by component (Deep Agents 4, LangChain 4, Multi-agent 4, LangGraph 2), and a "Conceptual overviews" group of 8. "How-to guides" no longer exists as a label; that content now lives inside each component tab.

INFERRED: when LangChain grew from one library into several products it moved from type first to product first and kept a type-first "Learn" tab as a collector for tutorials and concepts.

Mistake: the tutorial groups mix component names with a pattern name ("Multi-agent"), so one axis is not used consistently.

### Cloudflare Workers

READ (live HTML header): the top bar is cross-product: Docs Directory, API, SDKs, Changelog, search, log in. The product, Workers, owns the sidebar. EXECUTED: the Workers `llms.txt` lists 474 pages in 26 sections, starting Overview, Getting started (4), Examples (49), Tutorials (20), then feature areas such as Configuration (24), Runtime APIs (92), Framework guides (31), Testing (41), Wrangler (40), and ending Glossary, Reference (5). INFERRED: this order matches the sidebar, since `llms.txt` is generated from the same tree; I did not read the sidebar itself.

READ: the tutorials page is a table with Name, Last Updated and Difficulty columns: 52 rows, Beginner 34, Intermediate 17, Advanced 1. The landing page offers two ways to start (deploy a template or use the CLI), then use cases and integrations by product.

INFERRED: Cloudflare is product first, then mostly feature area. Tutorials, Examples, Getting started and Reference appear as sidebar sections among about twenty feature sections. The four Diátaxis types are not the top level of anything.

Mistake: a level label where two in three rows say "Beginner" and one says "Advanced" does little to sort 52 items.

### Wagtail

READ: the contributor page on documentation modes says the docs follow Diátaxis and defines the four modes. The navigation (`docs/index.rst`) does not follow them: Getting started, Tutorial, Usage guide, Advanced, Extending, Reference, Deployment & hosting, Packages, Support, Editor's guide, Contributing, Release notes. The landing page groups links as "First steps", "Using Wagtail" and "For editors".

EXECUTED counts (files): getting_started 6, tutorial 9, topics ("Usage guide") 15, advanced_topics 67, extending 18, reference 36.

INFERRED: Wagtail applies Diátaxis to each page, not to the navigation. Its navigation splits by level (Usage guide, then Advanced) and by audience (Editor's guide).

Mistake: "Advanced" has become the largest section (67 files), a mixture of how-to and explanation sorted only by difficulty.

### Hypothesis

READ (`hypothesis/docs/index.rst`): Quickstart, Tutorial (8 ordered lessons), How-to guides (5), Explanations (2), API Reference (4), then Stateful tests, Extras, Glossary, Changelog, and a captioned "About Hypothesis" group. No horizontal section bar. The landing page gives an example, then points to Tutorial or Quickstart, then one line for each of the four types. EXECUTED: the changelog (582 KB) and the landing page do not mention Diátaxis.

Mistake: "Stateful tests" sits at the top level beside the four types, untyped.

### Briefcase (BeeWare)

READ: BeeWare's contributor guide says it aims to follow Diátaxis, with four types called tutorials, how-to guides, topic guides and reference. Briefcase is built with Material for MkDocs (`docs/config.yml`), and its left sidebar is driven by `SUMMARY.md`: Tutorial, How-to guides, Topic guides, Reference, About Briefcase. Inside How-to guides the groups are tasks (code signing by platform, building, testing, debugging, publishing) and the whole contributing guide. Reference is grouped by commands, configuration and platform.

READ: the Tutorial section is one page that sends the reader to the BeeWare tutorial on another site. Topic guides holds one page. INFERRED: a site of about 80 pages with one explanation page and no local tutorial still keeps all four types in its top level.

Mistake: the contributing guide, about thirty pages, sits inside How-to guides and outweighs the product's own how-to content.

### minterpy

READ: the docs-design page says the docs follow Diátaxis and names five sections: Getting Started (tutorials), How-to Guides, Fundamentals (explanation), API Reference, Contributors Guide. The site uses a horizontal top bar holding exactly those five, plus GitHub and version links. The landing page has five cards, each led by a reader's question ("New to Minterpy?", "Familiar with Minterpy?", "What's behind the scene?", "Need API reference?", "Want to contribute?").

EXECUTED counts (files): getting-started 8, how-to 27, fundamentals 10, api 53, contributors 17.

Mistake: the top bar and the landing cards repeat the same five links, so the landing page adds a question and nothing else.

## The table across sites

| Site | Horizontal bar | Its axis | Sidebar top level | Four types named | Tutorials (count, grouping) | Multi-component answer |
|---|---|---|---|---|---|---|
| diataxis.fr | none | none | the framework's own topics | Diátaxis words (as subjects) | none | not applicable |
| Django | project site menu, version, language | the project, not the docs | type (intro, topics, howto, ref) | renamed: First steps, Topic guides, Reference guides; how-to kept | 8 numbered parts + 2 follow-on (entries) | one product; domains on the landing page |
| Canonical starter pack | none | none | the four types, then release notes and contribute | Diátaxis words | empty skeleton | one site per product |
| Ubuntu Server | none | none | Tutorial, How-to, Reference, Explanation | Diátaxis words | 5: Getting started 1, Next steps 4 (entries) | domains inside each type and on the landing page |
| Juju | none | none | the four types, then For contributors, Release notes | Diátaxis words | one section (entries not counted) | separate sites per component |
| LXD | none | none | the four types | Diátaxis words | 1 file | domains inside how-to and on landing cards |
| MAAS | none | none | Home, then the four types | Diátaxis words | one entry | domains inside how-to |
| pytest | none | none | Get Started, then three types, then Examples | three kept, tutorial renamed Get Started | 1 page | one product |
| NumPy | User Guide, API reference, Building, Development, Release notes, Learn, NEPs | audience and type mixed | per top-bar entry | renamed: Getting started, User guide, API reference, Learn | 12 notebooks on a separate site (files) | audience first (NEP 44) |
| LangChain v0.3 | Integrations, API Reference, More, version | reference and ecosystem | Tutorials, How-to guides, Conceptual guide | explanation renamed Conceptual guide | not counted | ecosystem links to separate sites |
| LangChain today | products, then component tabs | product, then component | per component tab, by feature | only Tutorials and Conceptual overviews survive, in a Learn tab | 14, grouped by component (entries) | component first, then feature |
| Cloudflare Workers | Docs Directory, API, SDKs, Changelog | cross-product utilities | about 26 sections, mostly feature areas | not as a top level | 20 in sidebar, 52 in the table with level labels | product first |
| Wagtail | none | none | Getting started, Tutorial, Usage guide, Advanced, Extending, Reference, ... | per page only; navigation by level and audience | 9 files | one product |
| Hypothesis | none | none | Quickstart, then the four types, then extras | Explanations, API Reference | 8, one ordered path | one product |
| Briefcase | none (Material for MkDocs, sidebar) | none | the four types, then About | Topic guides for explanation | 1 page pointing to another site | one product |
| minterpy | the five sections | type | the same five | renamed: Getting Started, Fundamentals | 8 files | one product |

## The pattern

INFERRED from the sections above. Each statement names the sites it stands on.

The four types as the top level is the common case among single-product sites that state they follow Diátaxis: the Canonical sites and starter pack, pytest, Hypothesis, Briefcase and minterpy. Django's master toctree is type first too, though its landing page is domain first.

The type names are mostly kept. "How-to guides" and "Reference" are kept almost everywhere. "Tutorial" is the name most often replaced, by "Get Started", "Getting Started" or "First steps". Explanation is the type renamed most, to "Topic guides" (Django, Briefcase), "Conceptual guide" (LangChain v0.3), "Fundamentals" (minterpy) or "User guide" (NumPy).

The types are vertical far more often than horizontal. Only NumPy and minterpy, both on the PyData Sphinx theme, put sections in a top bar, and only minterpy puts the four types there as such. Canonical, pytest, Hypothesis, Django, Wagtail and Briefcase have no horizontal section bar at all.

The second axis, the product's domains, lives one level down. Ubuntu Server, LXD, MAAS and Django's how-to index group each type's pages by domain. Ubuntu Server repeats the same domain names under how-to and explanation. The landing page is where the two axes meet: Ubuntu Server, Juju, LXD and Django each open with a domain index whose rows link into several types.

Outside the four, the same few things recur at the top level: a home or quickstart page before the types (MAAS, LXD, pytest, Hypothesis), and release notes, contributing and "about" after them (starter pack, Juju, pytest, Hypothesis, Briefcase). Reference often absorbs release notes and API (LXD).

Tutorials stay few. No type-first site I read has more than ten. Ubuntu Server has 5, Hypothesis 8, Django 8 plus 2, minterpy 8, Wagtail 9. How-to and reference grow into the dozens or hundreds: Ubuntu Server how-to 153 files, Django reference 120, LXD how-to 87. Where a site does have many "tutorials" (Cloudflare's 52), they are project builds sorted by a level label, and two thirds share one label.

A product with several components chooses one of two answers. Canonical gives each component its own site, each type first. LangChain moved to component first, then feature, and kept the types only in a "Learn" tab. I saw no site that is type first with components as the second level.

Sites that claim Diátaxis but do not use it for navigation (Wagtail, NumPy) apply it page by page and split the navigation by level or audience instead. Both show the cost: Wagtail's "Advanced" grew to 67 files of mixed types, and NumPy's how-tos shrank to one entry.

## What the vfs site should do

INFERRED throughout, with the evidence each part rests on.

### The horizontal bar and the sidebar

The horizontal bar should hold the types, not the domains. Use the Diátaxis words, because every literal adopter keeps at least "How-to guides" and "Reference", and a reader who knows the framework recognises them. A home tab comes first: Introduction and Overview, the role "Get Started" or "Home" plays on pytest, Hypothesis, LXD and MAAS. Then Tutorials, then How-to guides, Reference and Explanation, each added only when it holds pages. That last rule follows Diátaxis's own advice not to create empty sections ahead of the content, and Briefcase shows the cost of ignoring it: a Topic guides section of one page. History belongs in Explanation, or in a trailing About entry like Briefcase's and pytest's.

The domains should be the sidebar's groups inside each type, in one fixed order used in every type: the file system and its calls, the command line, storage and databases, search, permissions and governance, AI agents and MCP, mounts, operations. This is Ubuntu Server's shape: thirteen domain groups under How-to guides and the same names under Explanation. One order across types lets a reader who found "Permissions" in how-to find it in reference without hunting.

The landing page should be where the two axes cross: a short statement of what vfs is, then a domain list whose rows link into tutorial, how-to, reference and explanation pages for that domain. Ubuntu Server, LXD, Juju and Django each do this. A four-card grid that repeats the top bar (minterpy, MAAS) adds little.

The domains should not go in the top bar while vfs is one package. LangChain moved to component tabs only when it became several products with separate audiences. vfs has one install and one API. If a part of vfs ever ships and is versioned on its own, Canonical's answer, a separate site that is type first inside, is the precedent.

Put release notes and contributing after the types, as the starter pack, Juju and Hypothesis do. Do not nest a second set of types under contributing; Juju does, and it reads as a second site.

### Tutorials now at five, and later at thirty

At five, keep one ordered path, numbered in reading order. Django's Parts 1 to 8 and Hypothesis's eight lessons are both a single list, and both are type-first sites of about vfs's ambition. State at the top of each tutorial which one comes before it. That is all five need.

As the set grows past about eight, split it the way Ubuntu Server does: a short "Getting started" path that every newcomer takes in order, then a "Next steps" set of tutorials, each grouped under the same domain names the sidebar uses elsewhere. LangChain's Learn tab groups its 14 tutorials by component in the same way. Grouping by domain keeps one axis across the whole site.

Do not group by level. No literal adopter I read sorts its tutorials into beginner and advanced groups. Django's "Advanced tutorials" is a tail of two, one of them titled as a how-to. Wagtail's "Advanced" section and Cloudflare's level column both show the failure: level becomes the biggest bucket, or a label most rows share.

Treat a count near thirty as a signal to check the pages, not to add structure. No type-first site in this set has more than ten tutorials. Most pages that look like tutorial number twenty are how-to guides: they assume the reader already knows vfs and want one task done. Move those to How-to guides under their domain, where the counts on these sites show growth into the hundreds is normal.

### The one-line version

Put the four types across the top, the product's domains down the side inside each type in one fixed order, the domains again on the landing page, and keep tutorials one short ordered path that later branches by domain, never by level.

## What this study could not settle, and what would settle it

The removed complex-hierarchies page on diataxis.fr held the framework's own guidance on a second axis. Reading the page through the Wayback Machine and the project's git history for the commit that removed it would show what it said and why it went.

Cloudflare's sidebar order is inferred from `llms.txt`, not read. Reading the Starlight sidebar frontmatter (`sidebar.order`) in the cloudflare-docs repository, or a rendered sidebar in a browser, would confirm it.

Section landing pages were read for Django (intro and how-to), Ubuntu Server (tutorial), Briefcase (tutorial) and Cloudflare (tutorials), not for every section of every site. A pass over each site's how-to and reference index pages would show whether they carry the domain index the main landing pages do.

How Material for MkDocs's tabs feature scopes the sidebar to the chosen tab, and what happens on a phone, decides whether the recommended split works on the vfs site as built. That is a question about the tool, and it is settled by reading Material's navigation documentation and by building a two-tab trial of the vfs site.

Juju's tutorial count and LangChain v0.3's page counts were not taken. The git-trees API run against `juju/juju` and against the `v0.3` branch of `langchain-ai/langchain` would give them.
