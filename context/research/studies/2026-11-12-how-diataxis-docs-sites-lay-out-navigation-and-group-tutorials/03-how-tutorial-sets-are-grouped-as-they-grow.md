# Tutorial sets stay one ordered path up to about fifteen lessons; past that, sites keep one marked first path and group the rest by domain, and a level split, where it appears, is a two-way Basic/Advanced cut whose Advanced half turns into domain groups or how-to guides

I was asked on 2026-11-12 how documentation sites with many tutorials group and order them as the set grows, with a count for each site, the size at which one ordered list becomes groups, and what Diátaxis's own pages say about advanced tutorials. The time box was 30 minutes and I used about 28. I covered all seventeen sites in the brief, some more thinly than others: LXD's tutorial page did not render and I counted it from its repository instead, scikit-learn's tutorial pages no longer exist, and HashiCorp's tutorial library did not render a count. I did not save navigation outlines to the experiments folder; every count below comes from the fetch named in Sources.

## Sources

All read on 2026-11-12 through the WebFetch tool. That tool converts a page to text and answers through a small model, so the counts are that extraction's counts of the navigation source and may be off by one or two in a long list.

- Django docs index source: https://raw.githubusercontent.com/django/django/main/docs/index.txt
- Django intro toctree: https://raw.githubusercontent.com/django/django/main/docs/intro/index.txt
- FastAPI navigation: https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/mkdocs.yml
- FastAPI tutorial landing: https://fastapi.tiangolo.com/tutorial/
- FastAPI advanced landing: https://fastapi.tiangolo.com/advanced/
- Svelte tutorial, rendered navigation: https://svelte.dev/tutorial/svelte/welcome-to-svelte
- React Learn sidebar: https://raw.githubusercontent.com/reactjs/react.dev/main/src/sidebarLearn.json
- Vue site config: https://raw.githubusercontent.com/vuejs/docs/main/.vitepress/config.ts
- Vue tutorial steps: https://api.github.com/repos/vuejs/docs/contents/src/tutorial/src (and https://vuejs.org/tutorial/ and https://vuejs.org/tutorial.md, which rendered nothing useful)
- Kubernetes tutorials index: https://kubernetes.io/docs/tutorials/
- Kubernetes tutorials source: https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/tutorials/_index.md and https://api.github.com/repos/kubernetes/website/contents/content/en/docs/tutorials
- PyTorch tutorials index source: https://raw.githubusercontent.com/pytorch/tutorials/main/index.rst
- PyTorch Learn the Basics: https://docs.pytorch.org/tutorials/beginner/basics/intro.html
- TensorFlow tutorials table of contents: https://raw.githubusercontent.com/tensorflow/docs/master/site/en/tutorials/_toc.yaml
- Hugging Face Transformers table of contents: https://raw.githubusercontent.com/huggingface/transformers/main/docs/source/en/_toctree.yml
- Hugging Face Learn: https://huggingface.co/learn
- Hugging Face LLM Course chapter 1: https://huggingface.co/learn/llm-course/chapter1/1
- LangChain and LangGraph navigation: https://raw.githubusercontent.com/langchain-ai/docs/main/src/docs.json (first 100,000 of 257,342 characters)
- HashiCorp Terraform tutorials: https://developer.hashicorp.com/terraform/tutorials
- HashiCorp tutorial library: https://developer.hashicorp.com/tutorials/library?product=terraform (rendered only a title)
- SQLAlchemy Unified Tutorial: https://docs.sqlalchemy.org/en/20/tutorial/index.html
- pandas getting started: https://pandas.pydata.org/docs/getting_started/index.html
- scikit-learn getting started: https://scikit-learn.org/stable/getting_started.html
- scikit-learn tutorial index and basic tutorial, both 404: https://scikit-learn.org/stable/tutorial/index.html and https://scikit-learn.org/stable/tutorial/basic/tutorial.html
- Supabase getting started: https://supabase.com/docs/guides/getting-started
- Stripe quickstarts: https://docs.stripe.com/quickstarts
- Juju tutorial: https://canonical.com/juju/docs/juju-cli/3.6/tutorial/ (redirected from documentation.ubuntu.com/juju/3.6/tutorial/)
- LXD tutorial: https://canonical.com/lxd/docs/latest/tutorial/ (redirected from documentation.ubuntu.com, rendered empty) and https://api.github.com/repos/canonical/lxd/contents/doc/tutorial
- Diátaxis tutorials: https://diataxis.fr/tutorials/
- Diátaxis tutorials against how-to guides: https://diataxis.fr/tutorials-how-to/
- Diátaxis complex hierarchies: https://diataxis.fr/complex-hierarchies/ (404)

EXECUTED marks a fetch I ran whose output I report, including a count taken from it. READ marks something stated on a page cited above, read on 2026-11-12. INFERRED marks my own reasoning from the two.

## Terms

A tutorial in the Diátaxis sense is a lesson: a learner is led step by step to build something and gains skill by doing it. A how-to guide serves someone already competent who has a task to finish. A curriculum, in this study, is a set of tutorials meant to be taken in one order, each building on the last. A library is a set of tutorials that each stand alone, so a reader picks one. A level axis groups by difficulty (basic, advanced). A domain axis groups by product area or feature (security, storage). A platform axis groups by the reader's framework or cloud.

## What each site does

### Django

EXECUTED: the docs index lists a numbered tutorial of eight parts (Part 1 to Part 8, setup through third-party packages) and then a group called "Follow-on tutorials" holding two pages: writing reusable apps and writing a first contribution to Django. That is 10 tutorials, counted from `docs/index.txt`. The intro toctree runs overview, install, the eight parts, reusable apps, what's next, contributing, under the heading "Getting started". READ: the brief and common accounts call the follow-on group "Advanced tutorials"; today's source calls it "Follow-on tutorials", so the label has changed and I report what it is now. INFERRED: the axis is a single linear path; the first path is Part 1 and is unmistakable; these are tutorials in the Diátaxis sense, one app built across eight lessons. The rest of the index is organised by layer (model, view, template), a domain axis, but that is the topic guides and reference, not the tutorials. Mistake, INFERRED: the follow-on group mixes a user lesson with a contributor lesson, two audiences in one two-item group.

### FastAPI

EXECUTED: in `mkdocs.yml` an untitled top-level group holds Learn (3 pages: an index, Python types, async), Tutorial (51 pages, with two feature subgroups, Dependencies of 6 and Security of 5) and Advanced (35 pages, with a Security subgroup of 3), beside Deployment and How-to. The tabs feature is on (`navigation.tabs`, `navigation.tabs.sticky`, `navigation.indexes`). READ: the pages are titled "Tutorial - User Guide" and "Advanced User Guide". The tutorial landing says each section builds on the previous ones, that a reader can jump straight to a topic, and that it is built to work as a future reference. The advanced landing says its sections assume the Tutorial was read, and that they are "not necessarily 'advanced'". INFERRED: the axis is level, a two-way cut, and inside each half the order is by feature. The first path is marked (Tutorial, then Advanced). The Tutorial half is a curriculum that doubles as reference; the Advanced half is a library of feature pages, closer to how-to guides. Mistake, INFERRED: the site's own label for its second half is one its landing page disowns.

### Svelte

EXECUTED: the interactive tutorial has four parts with these exact labels: Basic Svelte (9 chapters, 46 lessons), Advanced Svelte (9 chapters, 30 lessons), Basic SvelteKit (9 chapters, 25 lessons) and Advanced SvelteKit (7 chapters, 25 lessons). That is 126 lessons, counted from the rendered navigation. Chapters are features: Reactivity, Props, Bindings, Transitions; then Advanced reactivity, Advanced bindings, Advanced transitions. INFERRED: the axis is product, then level, then feature, and the whole is one curriculum read front to back. The first lesson, "Welcome to Svelte", is the marked start. These are tutorials in the Diátaxis sense: each lesson has an editor and an expected result. Several Advanced chapters are named by prefixing a Basic chapter's name with "Advanced", so the level split here partly means "the rest of the same feature". Mistake, INFERRED: single-lesson chapters (Context API, Next steps, Conclusion) add sidebar rows without adding structure.

### React

EXECUTED: `sidebarLearn.json` has two sections. Get Started holds Quick Start with two children (Tutorial: Tic-Tac-Toe, and Thinking in React), Installation (3), Setup (3) and React Compiler (4). Learn React holds four chapters: Describing the UI (9), Adding Interactivity (7), Managing State (7, tagged intermediate) and Escape Hatches (8, tagged advanced). That is 31 pages in the curriculum, counted. INFERRED: the axis is one linear curriculum ordered by concept, with level carried as a tag on the later chapters rather than as a separate section. Only one page is named a tutorial; the 31-page Learn React curriculum is a blend of tutorial and explanation, with exercises. Mistake, INFERRED: the one page called "Tutorial" sits under Quick Start, so the word names a single game and not the curriculum a newcomer actually follows.

### Vue

EXECUTED: the top bar's Docs menu lists Quick Start, Guide, Tutorial, Examples, API and Glossary. The interactive tutorial has 15 steps (`step-1` to `step-15` in the repository), one flat list. The Guide sidebar has 51 pages in nine groups: Getting Started (2), Essentials (13), Components In-Depth (8), Reusability (3), Built-in Components (5), Scaling Up (6), Best Practices (4), TypeScript (3), Extra Topics (7). Examples has three groups: Basic, Practical and 7 GUIs. INFERRED: the tutorial is a short single path; the Guide is the long curriculum, ordered from essentials to in-depth to scaling up, a level progression expressed through group names rather than level labels. Mistake, INFERRED: Tutorial and Guide are two beginner paths offered side by side in one menu, and the menu does not say which to take first.

### Kubernetes

EXECUTED: the tutorials index lists 21 entries in nine groups: Basics (3, one an external edX course), Configuration (1), Authoring Pods (1), Stateless Applications (2), Stateful Applications (4), Services (2), Security (4), Cluster Management (4). The repository folder holds seven subfolders plus Hello Minikube. READ: the index defines a tutorial as reaching a goal "larger than a single" task, linking to Tasks, and states no prerequisites beyond bookmarking the glossary. INFERRED: the axis is domain, with a Basics group first as the implicit newcomer path; no level labels. Several entries are titled "Example: Deploying ..." and read as how-to guides that happen to be long. Mistake, READ and INFERRED: the index lists fewer tutorials than the sidebar, and lists an external course as if it were a page of the site.

### PyTorch

EXECUTED: the tutorials index source has 97 cards in 13 sections (Learning PyTorch 9, Image/Video 7, Audio 10, NLP 3, ONNX 3, Reinforcement Learning 6, Deploying Models in Production 5, FX 1, Frontend APIs 17, Model Optimization 15, Parallel and Distributed Training 13, Edge 6, Recommendation Systems 2), filtered by 32 tags. A "Learn the Basics" callout leads to an 8-step path numbered 0 to 7, Quickstart through saving a model. READ: that path assumes "basic familiarity with Python and Deep Learning concepts", and sends newcomers to Tensors and readers from other frameworks to Quickstart. Recipes are a separate index. INFERRED: a marked first path of 8, then a domain library of about 90 with tag filters; no level grouping beyond "Getting-Started". Mistake, EXECUTED: card placement and tags disagree (Ray Train sits under Image/Video and is tagged Text), and two cards are duplicated.

### TensorFlow

EXECUTED: the tutorials table of contents has 77 entries. Three come first, ungrouped: an overview, "Quickstart for beginners" and "Quickstart for experts". A Beginner divider holds two groups (ML basics with Keras 8, Load and preprocess data 10). An Advanced divider holds eleven groups by domain (Customization 3, Distributed training 9, Vision 11, Text 3, Audio 3, Structured data 5, Generative 10, Model optimization 2, Model Understanding 3, Reinforcement learning 2, tf.Estimator 5 marked deprecated). INFERRED: this is the clearest hybrid: level at the top, two tiers, and domain inside the Advanced tier, which holds three quarters of the entries. The Beginner tier is small and ordered; the Advanced tier is a library. Mistake, EXECUTED: a deprecated API keeps a group under Advanced, and "Quickstart for experts" sits above the Beginner divider.

### Hugging Face

EXECUTED: the Transformers docs have no Tutorials section; there is a Get started group of 3 pages, and "Task recipes" sits under Resources with 33 pages by modality (NLP 8, Audio 4, Computer vision 14, Multimodal 7). The Learn hub lists 12 courses in one ungrouped list with no level labels. READ: the LLM Course groups its 12 chapters into four parts, Transformers library basics (1 to 4), core tools and techniques (5 to 8), demos (9) and advanced LLM topics (10 to 12), and states prerequisites (good Python, ideally an introductory deep learning course). INFERRED: the product docs carry how-to recipes grouped by domain; the tutorials live in a separate courses site, each course a curriculum that ends in an "advanced" part. Mistake, INFERRED: the 12 courses are an unordered list with no grouping or level, so a newcomer gets no first path at the hub level.

### LangChain and LangGraph

EXECUTED: the docs are now one Mintlify site whose Build menu has Python and TypeScript dropdowns, each with tabs per product and a Learn tab. Each product sidebar has a Get started group with one quickstart (5 quickstarts across the Python Build menu). The Python Learn tab holds 14 tutorials in four groups (Deep Agents 4, LangChain 4, Multi-agent 4, LangGraph 2), plus 8 conceptual overviews and 4 resource pages. TypeScript has 13. INFERRED: the axis is product, with one quickstart per product as the first path; no level labels. This is the third structure these docs have had in my knowledge, so claims about LangChain's tutorials from older sources describe a site that no longer exists. Mistake, INFERRED: the groups mix three products with one theme (Multi-agent), and the quickstarts live in a different tab from the tutorials they lead into.

### HashiCorp Developer (Terraform)

READ: the Terraform tutorials sidebar has groups Get Started (by platform: AWS, Azure, Docker, GCP, HCP Terraform, OCI, plus Sandbox and the developer portal), Fundamentals (by feature: CLI, Configuration Language, Modules, Provision, State), Use Cases (ten, by integration target), Certification Prep, Production and Integrations. Get Started collections hold 6 to 8 tutorials each, counted on the page; the library total did not render. No level labels; new tutorials show a duration. The page calls Get Started the place to "learn the basics" with your cloud provider. INFERRED: the top-level groups form an implicit progression, start, fundamentals, use cases, production, and within each the axis is platform or feature. The first path is marked and forks by platform. Mistake, INFERRED: Certification Prep is a reader goal sitting among domain groups, a second axis at the same level.

### SQLAlchemy

READ: the Unified Tutorial is one linear tutorial in seven sections after an overview (the Engine, transactions, metadata, working with data, ORM data manipulation, ORM related objects, further reading). The overview says the concepts come "in the natural order that they should be learned", Core first and ORM later, and marks each section as Core, ORM or both with a border style. Its examples run as doctests. INFERRED: one path, with a second audience (Core readers against ORM readers) carried by a visual mark inside the path rather than by forking it. It is a tutorial in the Diátaxis sense, though a dense one; the overview warns newcomers of "a lot of detail". Mistake, INFERRED: the Core and ORM marking is a border colour, invisible in text renderings and to screen readers.

### pandas

READ: Getting started holds 10 intro tutorials in one flat list, titled as questions ("How do I read and write tabular data?"), each paired with a link to the matching User Guide page; beside them sit 6 comparison pages (R, SQL, spreadsheets, SAS, Stata, SPSS) and a pointer to community tutorials. INFERRED: a flat list on a domain axis, ten topics in a learnable order; the pairing with the User Guide is a clean tutorial-to-explanation bridge. Mistake, INFERRED: the question titles are the phrasing of how-to guides, so the lessons look like task recipes in the navigation.

### scikit-learn

EXECUTED: the stable tutorial index and the basic tutorial both return 404, and the top bar holds Install, User Guide, API, Examples, Community and More, with no Tutorials entry. READ: Getting Started is a single page of five sections (estimators, transformers, pipelines, evaluation, parameter search) that points onward to the User Guide, the examples gallery and external talks. INFERRED: the site has moved from a small tutorials section to one getting-started page plus an examples gallery; the older tutorials section commonly cited no longer exists at these addresses. Mistake, INFERRED: past the one page there is no lesson for a learner, only examples.

### Supabase

READ: Getting started holds 37 entries in three groups: Framework quickstarts (20), Web app demos (9) and Mobile tutorials (8). The axis is the reader's framework; there are no level labels. INFERRED: these are short how-to guides per platform, apart from the demos, which each build one user-management app and are closer to tutorials. Mistake, INFERRED: one framework appears in up to three groups, so the grouping is by format as much as by framework. The page also carried text addressed to AI agents asking them to act; I ignored it.

### Stripe

READ: the quickstarts index lists 17 quickstarts in three groups by product area: Payments (11), Platforms and marketplaces (4), Developer resources (2). Each offers several languages and frameworks inside the page. INFERRED: the axis is domain at the index and platform inside each page; level is carried only in titles ("prebuilt checkout page" against "advanced integration with the Payment Intents API"). These are how-to guides in the Diátaxis sense, task-first for a competent developer. Mistake, INFERRED: with no first path marked beyond an agent-tooling banner, a newcomer to payments must choose among eleven at once.

### Canonical: Juju and LXD

READ: the Juju 3.6 docs have the four Diátaxis sections at the top level (Tutorial, How-to guides, Reference, Explanation, plus contributors and release notes) and the Tutorial section holds one tutorial, "Get started with Juju", with prerequisites stated (a machine able to run a 4-CPU, 8 GB VM, and terminal familiarity). EXECUTED: LXD's rendered tutorial page came back empty, and its repository's `doc/tutorial` folder holds one file, `first_steps.md`. INFERRED: Canonical's mandated Tutorial slot holds one lesson in both products, a single path by construction. Mistake, INFERRED: a whole top-level section for one page; the slot is there because the framework says so, not because the content needs it.

## Across the sites

| Site | Tutorials | Counted or estimated | Axis | Level labels | First path marked | Prerequisites between lessons | Diátaxis tutorials? |
|---|---|---|---|---|---|---|---|
| Juju | 1 | counted | single path | none | yes | stated | yes |
| LXD | 1 | counted (repo folder) | single path | none | yes | not read | yes |
| SQLAlchemy | 1 tutorial, 7 sections | counted | single path, Core/ORM marked inside | none | yes | implied by order | yes |
| PyTorch Learn the Basics | 8 | counted | single path | none | yes | stated | yes |
| Django | 8 + 2 | counted | single numbered path, then follow-on | "Follow-on" | yes | by order | yes |
| pandas | 10 | counted | flat list by topic | none | yes | none | partly; how-to titles |
| LangChain (Python) | 14 + 5 quickstarts | counted | product groups | none | one quickstart per product | not read | mostly |
| Vue tutorial | 15 steps | counted | single path | none | yes | by order | yes |
| Stripe | 17 | counted | product area | in titles only | no | none | no; how-to |
| Kubernetes | 21 on index | counted | domain groups, Basics first | none | implied | none on index | mixed |
| React Learn | 31 + 1 | counted | single curriculum in 4 chapters | intermediate, advanced tags | yes | by order | blended with explanation |
| Hugging Face | 12 courses; 33 task recipes | counted | courses flat; recipes by modality | course parts end "advanced" | no at hub; yes in a course | stated in a course | courses yes, recipes how-to |
| Supabase | 37 | counted | framework, then format | none | no | none | mostly how-to |
| Vue Guide | 51 | counted | depth-ordered groups | none | yes | by order | blended |
| TensorFlow | 77 | counted | Beginner/Advanced, then domain | Beginner, Advanced; "for beginners", "for experts" | yes | none in TOC | mixed |
| FastAPI | 51 + 35 | counted | Tutorial/Advanced, then feature | "Tutorial - User Guide", "Advanced User Guide" | yes | Advanced assumes Tutorial | Tutorial yes; Advanced mostly how-to |
| PyTorch index | 97 | counted | domain sections, tag filters | Getting-Started tag | yes | per page | mixed |
| Svelte | 126 lessons | counted | product, then Basic/Advanced, then feature | Basic, Advanced | yes | by order | yes |
| Terraform | 6 to 8 per collection; total not rendered | counted per collection | start, fundamentals, use cases, production; platform or feature inside | none; durations | yes, forked by platform | per collection | mixed |
| scikit-learn | 0 (one getting-started page) | counted | none | none | one page | none | no tutorials left |

## The pattern

INFERRED from the table: every set of up to about fifteen tutorials is one ordered list, with no groups at all (Juju, LXD, SQLAlchemy, PyTorch's basics, Django's ten, pandas's ten, Vue's fifteen). Groups first appear between fourteen and twenty (LangChain's fourteen in four, Stripe's seventeen in three, Kubernetes's twenty-one in nine). So the change from list to groups happens at roughly fifteen, which is also about the length of a sidebar section a reader can scan without scrolling.

INFERRED: what the groups become depends on which of two kinds of set the site has. A curriculum, one path read in order, grows by chapters named for features, and when it gets long it is cut in two by level: Basic and Advanced (Svelte), Tutorial and Advanced User Guide (FastAPI), Beginner and Advanced (TensorFlow), intermediate and advanced tags (React), a closing "advanced" part (the Hugging Face LLM Course). A library, lessons that stand alone, is grouped by domain (Kubernetes, PyTorch, Stripe, Hugging Face's recipes) or by the reader's platform (Supabase, Terraform's Get Started), and carries no level labels.

INFERRED: the mature sites combine the two. They keep one short marked first path, a curriculum of about eight lessons, and put a domain-grouped library after it: PyTorch's Learn the Basics then 13 domain sections; TensorFlow's Beginner tier then 11 domain groups; Kubernetes's Basics group first; Terraform's Get Started then Fundamentals and Use Cases; LangChain's quickstart per product then the Learn tab. Said another way: the first path is ordered by what to learn first, and everything after it is grouped by what it is about.

INFERRED: where a level split exists, it is never more than two tiers, and the Advanced tier does not stay a level. It turns into domain groups (TensorFlow's Advanced is eleven domains), into a library of feature pages that read as how-to guides (FastAPI's Advanced User Guide, whose own landing page says its sections are "not necessarily 'advanced'"), or into "the rest of the same feature" (Svelte's Advanced bindings, Advanced transitions). Level is a weak axis for anything but the first cut.

INFERRED: many pages called tutorials are how-to guides under another name. Stripe's and Supabase's quickstarts, Kubernetes's "Example: Deploying" pages, pandas's question-titled pages and Hugging Face's task recipes all serve a reader with a task, not a learner. The sites whose tutorials are lessons in the strict sense are the ones with a single path (Django, Svelte, Vue, SQLAlchemy, Juju, PyTorch's basics).

## What Diátaxis says about advanced tutorials

READ, diataxis.fr/tutorials-how-to/, section "The basic and the advanced": the page names the belief that tutorials are basic and how-to guides advanced as a common mistake. It says how-to guides "can, do and often should cover basic procedures", and that "a tutorial can present something complex or advanced". The difference lies in "the need they serve": tutorials are for learners at study, how-to guides for skilled practitioners at work. Its example of an advanced tutorial is a training course in a difficult clinical procedure, still a managed lesson. READ, diataxis.fr/tutorials/: the tutorials page does not mention advanced tutorials or how many a product should have; it says that ignoring alternatives keeps a tutorial "shorter and crisper" and that many products lack tutorials altogether. EXECUTED: diataxis.fr/complex-hierarchies/ returned 404 on this date.

INFERRED: so Diátaxis allows advanced tutorials, but it says level is not what separates a tutorial from a how-to guide. An "Advanced" bucket of tutorials is legitimate only if each item is still a lesson, and FastAPI's experience suggests that in practice such a bucket fills with how-to material.

## What the vfs site should do

The horizontal bar and the sidebar. INFERRED, on thin evidence from my sites because the top bar is Researcher 02's question: the sites here that split their top bar by content type (Vue's Docs menu of Quick Start, Guide, Tutorial, Examples, API; scikit-learn's Install, User Guide, API, Examples; pandas's Getting started, User Guide, API; FastAPI's tabs for Learn, Reference, Resources, About; Canonical's four sections) all keep the domain inside the section, in the sidebar. For a single product of vfs's size that is the shape to follow: the bar holds the content types (a home or overview entry, Tutorials, How-to guides, Reference, Explanation), and the sidebar is scoped to the chosen entry and holds that type's pages grouped by domain. A product-first bar, as LangChain and Terraform use, serves sites with several products, which vfs is not.

Tutorials now, at five. Keep them one ordered, numbered list with no groups, and mark the first as the place to start. The reason: every site with up to fifteen tutorials does this, and vfs's five already form one path (build a file system, use the CLI, move it to a database, give it to an agent, control access). Each tutorial should say in one line which earlier one it builds on, as Django's parts and FastAPI's advanced landing do, because a numbered list alone does not tell a reader arriving from search what to have done first.

Tutorials later, at thirty. Keep the first path as its own group at the top, named for starting out, about five to eight lessons, still ordered. Group everything after it by domain, using the same domain names the how-to guides use (storage and databases, search, permissions and governance, AI agents and MCP, mounts, operations), so a reader can step from a lesson to the guides on the same subject. Split into groups when the list passes about fifteen, not before. Do not add an "Advanced" group. The reasons: PyTorch, TensorFlow, Kubernetes and Terraform all settle on a marked first path followed by domain groups; TensorFlow's Advanced tier is domain groups under a level label; FastAPI's Advanced half disowns its own label; and Diátaxis says level is not the axis that defines a tutorial. Where a lesson is demanding, say so on the lesson, with its prerequisites and a time estimate as Terraform and PyTorch do, rather than in the navigation.

Watch one risk. INFERRED: as the set grows, lessons drift into how-to guides (Stripe, Supabase, Kubernetes's examples). A new page that starts from the reader's task rather than from what they will learn belongs in How-to guides, whatever it is called.

In one line: one ordered path while there are fewer than about fifteen tutorials, then that path as a "start here" group followed by domain groups that match the how-to guides, and no Advanced bucket.

## What this study could not settle

The exact point near fifteen at which a list becomes groups rests on seventeen sites and no measurement of readers; a usability test with vfs's own readers, or the site's analytics once it has traffic, would settle it. The full counts for HashiCorp's tutorial library, Kubernetes's sidebar beyond its index, and LXD's rendered tutorial section need a browser that executes the pages' scripts, since the text fetch did not render them. What Diátaxis says about structure at scale beyond the two pages read here, including the missing complex-hierarchies page, is Researcher 04's question and should be read from that study.
