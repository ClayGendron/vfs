# How we work

This page says how a person and a coding agent work together on VFS. It is a first draft, written on 2026-11-15, and it is revised at the end of every session.

## Before any work starts

- **Understand the goal first.** The agent asks what the goal is before any in-depth work. It then questions the goal the way an analyst would: is it specified, is it the right thing to build, what is left out. Work starts when the person and the agent agree on it.
- **Ask which mode.** If the person has not said guided or autonomous, the agent asks.
- **Ask questions through the question dialog** whenever there is more than one.
- **Ask before pushing to a remote.** Every time.

## Guided mode

Guided mode is a person and an agent working together, live, for one to four hours. The goal is set before the session and is sized to fit inside it.

A session moves through six kinds of work. They are not a fixed order, and spikes and decisions loop.

1. Set the goal.
2. Understand the constraints.
3. Study prior art.
4. Spike: try an idea in throwaway code before deciding on it.
5. Make the key decisions.
6. Implement.

How the agent behaves in a guided session:

- It acts toward the goal. Guided mode prefers action to correction.
- It explains as it goes, and it reasons with the person, not ahead of them.
- It does most of the work itself. Subagents are for work that is better done in parallel, such as research, and the agent says so before starting one.
- It keeps long-running processes to a minimum. It does not run the full test suite or the database engine legs.
- It still writes the test before the code.
- It writes no document for the person. The session is chat, code and documentation.
- It commits to save work. A guided commit has no gate.

A session ends with a short retro. Work it found and did not do is written as a new spec. No handoff note is written, and there is no list of outstanding work. A decision and its reason go where they will be read: the spec, a page in this section, or a docstring.

## Autonomous mode

Autonomous mode is the agent working alone, before or after a guided session. Before, it prepares: constraints and prior art, so the session starts at the decisions. After, it takes a 90% solution to a reviewed 100% solution.

- More research.
- Code, security and structural reviews of the code and of the feature. It may question whether the feature is the right thing to build.
- End-to-end tests and deeper spikes.
- A check of the documentation: whether the change needs a docstring, a page for users, a Maintainers page or a glossary term. The answer and its reason go in the review record and in the pull request, also when the answer is no.
- The full gate: `scripts/ci.sh`, `scripts/docs.sh check` and the database engine legs.

What it may do alone: fix anything that keeps the behaviour of the feature and the project. What it reports instead of doing: a big finding, and any fix that would change behaviour significantly.

Autonomous mode uses subagents freely and can take its time.

- **It states its scope before it starts,** and it works to that scope.
- **A reviewer is given the diff and the spec, never the author's summary.** A second model can review beside the first. [How we run Codex](how-we-run-codex.md) says how.
- **It may use a git worktree.** A worktree lets one agent write on a branch while others read the main checkout. It is made outside the checkout, nothing is left uncommitted in it, and it is removed when its work is committed.
- **It ends with every finding it did not act on written as a new spec.** A finding is never left in a review record or a pull request alone.

## Branches

1. Create a branch off `dev` for the work.
2. Guided commits land on that branch.
3. The autonomous pass runs on that branch.
4. The branch is pushed and a pull request to `dev` is opened. The agent asks before every push.
5. The pull request runs the gate. The same gate can be run locally first.
6. A person presses merge, always. The pull request is squashed to one commit on `dev`, whose subject names the change in words. Merging is done on GitHub, not on a laptop.
7. A release moves `dev` to `main`.

Squashing is the common practice for short-lived branches: `dev` reads as one line per piece of work, and the save-point commits of a guided session stay out of it.

## Where prose lives

| Directory | Written by | Read by | Published |
|---|---|---|---|
| `agents/` | agents | agents, and people now and then | never |
| `documentation/` | people, and agents under a person's guidance | people | yes, to docs.vfs.dev |

`agents/` holds `templates/`, the guides for writing an intent, a research memo, a spec and a review, and one work directory per piece of work, named `YYYY-MM-DD-short-descriptive-title`. Work that is not yet done is a spec in a work directory of its own. There is no separate list of tasks.

- A work directory holds whatever the work needs: intents, research, specs, reviews, spike code. It may hold several of each.
- Everything in `agents/` is written in an objective, impersonal voice. It names no person and no agent, and it has no "I", "we" or "you". It says what was found, what was decided and why, and what was done, never who did it. "Decided: the stamp is read twice, because a posture can move between the reads", not "Clay ruled" or "the reviewer found".
- A subdirectory inside a work directory has at most 16 children. A directory with more is too much for a person to navigate.
- A work directory is short-lived. It may be deleted once the work has been released, and not before.

`documentation/` holds everything durable. If something in a work directory must outlive the work, it is promoted to documentation, or it is lost.

- It has six sections: Home, Tutorials, How-to Guides, Reference, Explanation and Maintainers. The first five are for people who use VFS. Maintainers is for people who change it: this page, the constitution, the standards and the roadmap. All six are published.
- Reference pages are generated from the code. Every other page is written by a person or under a person's guidance, and the person reviews each change as it is made. A page carries no record of who wrote it.
- No directory under `documentation/` holds more than 16 children. A section that outgrows 16 is split.

## The retro

At the end of a session the person and the agent ask what to change on this page, and change it. Three numbers are noted each time: how long the person spent reading per landed change, how many stories landed, and how many findings the autonomous pass raised against guided work.

## Still to settle

- When the autonomous pass starts.
- The tests that hold the structure of `documentation/`, and which pages are generated.
- The migration of the old `context/` tree into `agents/` and `documentation/`.
- The templates in `agents/templates/`, and the review skills, which still write to `context/reviews/`.
- GitHub itself: `dev` does not exist yet, and the gate on a pull request needs the workflows to run on pull requests to `dev`.
