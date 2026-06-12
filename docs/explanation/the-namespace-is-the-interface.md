# The Namespace is the Interface

It is hard to explain what a namespace is in a way that conveys its importance in the world of computing, so lets try doing an experiment instead.

I want you to Google search namespace, and instead of clicking on any links to read more, I want you to slowly scroll down the first page of results and take stock of all the different types of results based on interpretations of the search that were returned. For me, I recieved an AI overview, two ads, four articles, two code documentation pages, three images, and two more ads.

Now I want you to imagine that you are an AI agent and you are trying to answer my question of "What is a namespace?" You do not already have a good answer to this question so you have to use the search results. Lastly, imagine these search results are striped of anything that indicates what is and is not an add, and crutially, these results are striped of the website name and url for which the result is coming from. Navigating a search space without access to some form of useful name for which your information is coming from makes the process much harder as I hope this small experiment shows. 

But of course Google provides us with that relevant name information so we can skip past the ads, click on the Wikipedia article, and find a trustworthy answer to our human's question.

> In [computing](https://en.wikipedia.org/wiki/Computing), a **namespace** is a set of signs (*names*) that are used to identify and refer to [objects](https://en.wikipedia.org/wiki/Object_(computer_science)) of various kinds. A namespace ensures that all of a given set of objects have unique names so that they can be easily [identified](https://en.wikipedia.org/wiki/Identifier).

The two namespace that most of us are most familiar with in computing is the file system and internet domain names. VFS went with the file system as its namepace design.

## Names in a File System

When creating a name for a file in a file system — or a file path — the IEEE Computer Society defined a set of operating system standards, abbrieviated as POSIX, which includes specific rules for how file system paths can look. Here they are:

- A path is a string of bytes. The Portable Filename Character Set `A–Z`, `a–z`, `0–9`, `.`, `_`, and `-` is guaranteed to work across conforming systems with the restriction of `-` not be a component's first character.
- It is absolute when it begins with `/` and relative when it does not: `.` names the current directory, `..` names the parent directory.
- The slash `/` is the only character that separates a path into components and `/` is the root directory.
- A component may hold any byte *except* the slash `/` and the null byte `\0`.
- Lengths are bounded by `NAME_MAX` for components and by `PATH_MAX` for whole paths.
- Redundant slashes between components collapse to one.
- A trailing slash means the path must resolve to a directory.

VFS inhertis these rules — with some reasonable additions — to construct a namespace that agents and humans can navigate around, find what they need, and take actions.

## Meanining Comes from Design

Nothing about the POSIX file naming rules above gives you file names that mean something
