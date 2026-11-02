# VFS: Goverened Data Access for AI Agents

Welcome to VFS, the framework that connects data to AI agents.

I want to tell you all about the technical details of this library, but first I think it would be helpful to explain the whole story of how VFS came to be because if you understand the backstory, I beleive VFS will be extremly intitutive to work with.

The VFS project started to improve upon vanilla RAG systems and ended up building a cloud-native file system kernel. Vector search is a great tool when the knowledgebases are small, well curated, and when using an LLM that is not that capable in tool calling. These three conditions are almost never the case today, so we need something else. But the industry at large is yet to develop a unified pattern for engineering data for AI agents, especially for enterprise use cases. This project proposes that a file system is that unifying pattern for two reasons: it is already a proven abstraction for agentic search styled retreival, or progressive disclosure, and it has a single unit to build a pattern around, the file.

I want to start with disecting what a *file* is and why VFS chose to be a *file system* because it did not start out looking to be one. This is where I tell you the first version of VFS was built as something that was trying to be a graph database (listen, it seemed like a good idea at the time). 

The basic idea was that after chunking and embedding the documents, or files, that would make up a knowledge base, developers would then create connections between those chunks. This could be connecting documents that reference other documents, chunks in the order that they appear in a document, or through any other type of relationship that could be determined while ingesting documents. To query you would embed your search query and retrieve N number of semantically simial chunks, just like typical RAG, but then follow the connections created to find additionall conadidate chunks that connecting the semantically similar ones. It was similar to the concept of GraphRAG but did not require an LLM to parse every document for entities and relationships, and was ideally simplier to implement. But, it got so many things wrong.

One, it was not clear that for any given knowledge base this semantic-traversal type search mentioned would meaningfully improve search quality. There are some types of knowledgebases where I got evidence that it 

'Progressive Disclosure' and 'Everything is a File' are the two main design patterns that VFS adopted, and they are two of the most reliable design patterns in computing.



We as developers need to structure our data in a way that lets capable tool calling agents explore an environment. We need to build around an **agentic search paradigm**.

But, isn't this already a solved problem with `glob` and `grep`, or more generally by giving agents access to a command line? 

The VFS project started with one goal — develop a library that supports developers in building capable and deployable agents that can deliver for enterprise use cases. 

Over the course of a year of research and development of this project there was, and will continue to be, rapid change and evolution of the development patterns in applied AI as the overall capability of LLMs continues to grow. There have been tremendous amounts of great work to push the capability fronteir of what LLMs can do while operating in a loop, however, it is the beleif of this project that there are still not solution out there that brings data to AI agents and delivers a great product for **all** of the following entities.

1. **Developers:** Delivers a great developer experience for every developer on an AI project.
2. **Enterprises:** Meets security and scale requirements.
3. **LLMs:** Implements a native interface that works in any environment.

This project worked to find the first princples to draw from and it came to find **progressive disclosure** and **everything is a file** as the core design principle to build VFS around. These two principles directed exactly How and What to build.

Progressive Disclosure: How to design a system.

Everything is a File: What system to design

This is why the name is VFS, it stands for virtual file system.

The core design, scope, and capability of LLMs changed several times over the course of this project, and it has now landed in a place that feels best positioned to deliver on that stated goal. 

This project is called VFS which stands for virtual file system as this library delivers if core features of governed data access through the abstraction of a file system.

Over the course of development and learning from the work of others, it was discovered that to build a system to make web-based agents powerful there were a few specific concepts that this project wanted to deliver on.

1. **Simple:** VFS is `pip` installable and, in the vast majority of cases, does not require resources that are not already in a developers project stack.
2. **Governed:** VFS routes everything through a single governance layer so permissions and reversability are enforced on every action.
3. **Universal:** VFS is built of AI and human users. It is designed as a file system to be a familiar UI for humans a power CLI-based agentic search tool for AI.
4. **Performant:** VFS is fast and designed to scale to enterprise-sized workloads. Use `grep` and other search tools in all of your data with little setup.
5. **Open:** VFS is, and will always be, fully open sourced.

