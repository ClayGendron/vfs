# Why VFS Stores Files in a Database

The first thing most developers notice about VFS is that the files are not on a disk. A file written to VFS becomes a row in a database, and nothing appears in a folder on the machine. This page explains what that means, why VFS was built this way, and what it costs.

## What "A File Is a Row" Means

Each file and each folder is one row in a table. The row holds the path, the name, the size, the owner, and when the file was created and last changed. The content is stored beside it in the same database.

The things around a file are rows too. An earlier version of a file is a row. A grant that gives someone access is a row. A deleted file is the same row with a mark that says when it was deleted, which is why it can be restored. The indexes that `grep` and `search` use are tables in the same database.

**The database holds the whole file system, not only the bytes.** The files, their history, their permissions, and their indexes are one body of data in one place.

## Why Not a Disk

A disk is the obvious home for files, and for an AI agent it is the wrong one for four reasons.

**A disk belongs to one machine.** AI agents mostly run inside web applications, on servers that are many and replaceable. A file on one server's disk is invisible to the next server and gone when the server is replaced. Giving every user a sandbox with its own disk solves that, at the price of running a machine for each user. A database is already where a web application keeps what must last, and every server reaches the same one.

**A disk knows operating system users, not your users.** An enterprise needs each person, and each AI agent acting for them, to see only the files they are permitted to see. A disk cannot express that, so the check would have to live in application code around every read. In VFS a caller's access becomes a condition on the query itself. A search does not fetch files and then filter them. It never returns a file the caller cannot read.

**A disk has no search.** Finding a term across a million files needs an index, and an index beside a disk is a second system that has to be kept in step with the first. In VFS the files and their indexes live in one database, are backed up together, and answer to the same permissions.

**A disk forgets.** An overwrite destroys the earlier content, and a delete destroys the file. In a database both are records. VFS keeps the version an overwrite replaced and marks a deleted file instead of removing it, so a mistake made by an AI agent can be undone. A batch of ten thousand files is also written together or not at all, so a failed load never leaves half a folder behind.

There is a fifth reason, which is safety. **Because the files are not on the host, an AI agent working in VFS has nothing on the host to reach.** The [Overview](../overview.md#where-vfs-runs) covers that choice.

## Why Not Object Storage or a Vector Database

**Object storage** is shared and durable, and it is the right place for very large files. But it stores objects by key and does little else. It cannot search inside content, it cannot change many objects as one step, and its permissions are written for buckets and prefixes, not checked per person on every call. A system built on it still needs a database beside it for everything in the section above.

**A vector database** finds text that is similar to a question. That is one way to find something, and an AI agent needs the others too: an exact term, the contents of a folder, the file at a known path. VFS began as an attempt to improve vector search and became a file system when it was clear that search is many tools and not one. [The History](../history.md) tells that story.

## What It Costs

The choice has real costs, and they are worth knowing before adopting VFS.

- **Other programs cannot open the files.** An editor, a shell, or a compiler on the machine cannot read a file in VFS. Everything goes through VFS. That is also the point, because it is what makes the kernel the only path to the data.
- **Every call is a database query.** With SQLite in the same process that is fast. With a database server, each call is a trip across the network.
- **There is a database to run.** On a laptop it is a single SQLite file. In production it is Postgres, which most teams already operate.

## The Short Version

An AI agent's file system has to be shared by every server, checked for every user, searchable, and reversible. **A database already does all four in one place**, so VFS presents a file system and stores it in a database.
