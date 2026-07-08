# VFS: Agentic Search on any SQL Database

VFS is built on a conviction that creating effective AI agents, from the scale of small local development to the size of an enterprise, is first and foremost a **data engineering** problem. This conviction comes from observing how AI agents work on tasks, noticing the flaws in some components of their current harnesses and tooling, and applying the well established patterns of data science and engineering that . The beliefs below capture an opinionated framework of how LLMs and AI agents actually work, and how to build for them.

## 1. Building AI Agents is a Data Engineering Problem

It is important to ground any understanding of LLMs (and thus AI agents) with an awareness that these are predictive models that run in a loop. This means that AI agents are bound by the age old saying in data science and machine learning: garabe in, garabe out.

Context engineering, a term that grown from prompt engineering, gained a lot of popularity because it re-framed the task of desining good agents from one that put an emphasis on the wording of the request to the agent (prompt engineering) to one that looked at how to fill up the context window of the LLM as a method to optimize the output. This is the m

## 2. LLMs Output Two Things, Human Consumable Content and Code

## 3. File Systems Create Environments for AI Agents

Every blog or tutorial about AI agents will describe the simplest form of them as something like the following.

> *"An AI agent is an LLM that operates in a loop by using tools to interact with an environment."*

This definition is fair, but the term **environment** is the least understood term in this phrase — and often not considered at all. Developers, and people generally, think about agents as an LLM with tools, not an LLM in an environment — but Claude Code has demonstrated to us all what an LLM is capable of doing inside the well-defined environment of a computer terminal. 

But what is it about a computer terminal that makes it a good environment for an LLM? There are two main reasons.

One, the terminal is a text-in, text-out environment, or a command line interface. Because software development tasks, and many others, can be done completely through a computer terminal, AI labs are able to continually run reinforcement learning loops in a nice environment that provides feedback and rewards that train the LLM. This means that out of the box, LLMs know how to use a CLI as a tool to get work done.

Two, the terminal is directly integrated with a computer's file system, and critically, **everything in a computer is a file**. Agents can use the file system to search a computer, find anything they need, and then perform the actions required to complete a task. File systems allow for this navigation because they define a **namespace**, and the namespace arguably provides as much contextual information to the LLM as the content of the files. For example, the next time you do a Google search, imagine having to select a link without knowing which website it goes to. Knowing the source of information, and how it relates to other sources of information, is critical.

Now lets re-write the agent defintion to make it specific to a coding agent:

> *"An AI **coding** agent is an LLM that operates in a loop by using a **terminal** to interact with a **file system**."*

This framing helps explain why coding agents generally perform better than other types of AI agents. Instead of having dozens, or hundreds, of tools, coding agents have a small set of tools with a text-based interface for composing commands. Instead of having a poorly defined environment to work in, coding agents have a well-defined and structured namespace where they can navigate, perform actions, and get feedback.

This is why VFS adopts the file system as its core abstraction. File systems produce environments well-suited for LLMs to act as agents.

## 4. Agentic Search has Four Verbs

Agentic search is autonomous knowledge retervial where an LLM is identfying the intent of a task, planning a multi-step retrieval strategy, executing searches, evaluating results, and then applying that knowledge to copmlete the task. Agentic search is seperate and different from RAG (retrival augmented generation) with RAG being a non-autonomous search where knowledge is injected into context without action by an LLM.

What does not exist today is a framework for developers to use for the data engineering and tool building required to make the agentic search process effective. Some have argued that agentic search is solved by using the `glob` and `grep` commands within a Unix terminal, but this falls short in the following areas.

1. **Spec-Driven Development:** This development pattern, popularized by agentic coding, has development teams focus much more effort on writing prose than code. The code base is now meant to contain much more documentation about the code than the code itself. The `glob` and `grep` commands are still useful, but do not allow for searching semantically or in a way that understands the dependacy structure of prose.
2. **Enterprise Search:** Enterprise knowledge is much less structured than a codebase and pattern matching techniques do not meet the needs for most searches. Search tools that understand the semantic meaning of documents and the relationships between them is critical for the scale and type of content that would in an enterprises-wide knowledge base.
3. **Multi-Layered Information:** There are four types of information that can be contained by a file in a file sytem. These are, (1) its path of where it is located in the namespace, (2) specific string patterns in its content (3) the meaning of its content, and (4) how it relates to other files in the file system. `glob` achieves number one, `grep` covers number 2, but neither is able to help with number three or four. Agents need to be able to search a knowledge base in all of these ways directions, and crucially, concert with each other.

These use cases highlight the need for four specific verbs that can compose and define agentic seach.

Three of these verbs are already familiar — `glob` and `grep` from any Unix terminal and `graph` from how we already think about connected data. One is new, and we are calling it `glean`. This verb is coined to represent semantic and lexical search patterns that rank documents by relevance, and because it has nice alliteration.

- `glob` searches on the dimension of **location**. It produces file matches against the structure of the file's path providing agents a way to reason on the meaning carried by a files place in the namespace.
- `grep` searches on the dimension of **content**. It matches exact strings and regular expressions inside files, which makes it precise and predictable for finding structured content and literal strings.
- `glean` searches on the dimension of **meaning**. It ranks files by semantic and lexical relevance to a specific query enabling search with natural language.
- `graph` searches on the dimension of **connection**. It traverses the edges between files and ranks files with centrality algorithms to present a topological view of how information flows within a knowledge base.

Together, these four verbs cover every dimension along which a file carries information, and thus these verbs cover the needs of agentic search. Additionally, the outputs of one search method can be used as input to the next because everything is addressable by a file path. A file system with these four verbs allows agents to navigate and search an environment in an interative and preditable fashion. This meets the definition of agentic search, and thus provides us with a framework for how to engineer data for it.

## 5. Knowledge and Capabilities are Distributed





















