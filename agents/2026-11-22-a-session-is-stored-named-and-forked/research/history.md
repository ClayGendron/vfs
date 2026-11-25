# The session, from its roots to today: a historical analysis

## Sources and method

Primary sources (papers, RFCs, POSIX, official docs) were read on 2026-11-22 and are listed at the end. A claim marked **(memory)** was not checked against a source. No repository was read.

The hypothesis: a vfs session is several older ideas under one name, and a design goes wrong when they are not told apart. The history supports it. Six lineages reduce to three concepts.

## Lineage 1: the session as a named, lasting context for one party's work

**Timeline.**

- **1962, CTSS.** Corbató, Daggett and Daley describe the first working time-sharing system at the Spring Joint Computer Conference (May 1962). A user logs in at a terminal and works interactively. The login defines a span of one user's work. Files belong to the user and outlive the login **(memory, for the files)**.
- **1965 onward, Multics.** A login creates a process that holds the user's working directory and running state for the length of the login **(memory)**.
- **About 1980, job control.** Jim Kulp, then at IIASA, adds job control to the C shell using signals in the 4.1BSD kernel; Bill Joy folds it into 4.1BSD (TUHS mailing list recollections; Wikipedia). A "job" is a process group the shell can stop, move to the background and resume.
- **1988, POSIX.1.** The session becomes a kernel object. `setsid()` makes a new session; the caller becomes its leader and the leader of a new process group, "and shall have no controlling terminal" (POSIX `setsid`). A session holds process groups (jobs). It is tied to one controlling terminal. When the terminal disconnects, "the SIGHUP signal shall be sent to the controlling process," and "unless other arrangements have been made, this shall cause the controlling process to terminate" (POSIX General Terminal Interface, 11.1.10). The 1988 date for `setsid` is **(memory)**.
- **1987, screen; 2007, tmux.** Oliver Laumann publishes screen in 1987; Nicholas Marriott releases tmux on 20 November 2007. Both move the shell's session out from under the terminal and into a server process. The user can detach, disconnect and reattach later, from another terminal.
- **2012, mosh.** Winstein and Balakrishnan (USENIX ATC 2012) observe that SSH, "because it runs over TCP," does not support roaming or intermittent connectivity. Mosh keeps terminal state at both ends and synchronizes "the most recent state of the screen" rather than replaying a byte stream. Each datagram is "an idempotent operation." The session survives a change of IP address because it is named by the protocol, not by the connection.

**What belonged to the session.** The working directory, the environment, the jobs and the terminal. Files did not; they belonged to the user.

**The failure that forced each step.** A hangup killed the work. Screen and tmux moved the session to one server process, which a reboot still kills. Mosh named the session and synced its latest state.

**Lesson.** A session that lives in a connection or a process dies with it; a session that must outlive a disconnect needs a name and a home that is neither.

A Unix job dies with its session unless "other arrangements" are made. A vfs job is stored and outlives any process, so it is closer to a detached tmux window than to a Unix job.

## Lineage 2: the session as state a server keeps about a client, named by an id the client presents

**Timeline.**

- **1984 to 1988, OSI session layer.** ITU-T X.225 (11/1988) and ISO 8327 define a session protocol above transport. It has dialogue control by tokens, and major and minor synchronization points with a "Resynchronize" exchange that resets a session connection to an earlier agreed point (X.225 table of contents; X.215 concepts). It was a session bound to a connection, with checkpoints inside it. It saw little use **(memory, for the adoption)**.
- **1994, cookies.** Lou Montulli invents the cookie at Netscape in 1994 to support electronic commerce (Kristol's 2002 IETF list message; secondary histories). HTTP is stateless, so the server sends a token and the browser returns it on every request.
- **1997 to 2011, the cookie RFCs.** RFC 2109 (1997) and RFC 2965 (2000) tried to standardize cookies **(memory, for the years)**. RFC 6265 (Barth, April 2011) replaced them, saying none of the earlier texts described "how the Cookie and Set-Cookie headers are actually used on the Internet." It names the common pattern: servers "store a nonce (or 'session identifier') in a cookie" and look up state with it.
- **2000, REST.** Fielding's dissertation (section 5.1.3) makes statelessness a constraint: "each request from client to server must contain all of the information necessary to understand the request," and "session state is therefore kept entirely on the client." The gains are visibility, reliability and scalability. The cost is repeated data per request and less server control.
- **2002, session fixation.** Mitja Kolšek (ACROS Security, December 2002) names a new attack. He sorts servers into two classes. "Permissive" servers "accept arbitrary session IDs, and create a new session with proposed session ID if one doesn't exist yet." "Strict" servers "only accept known session IDs, which have been locally generated." On a permissive server the attacker "only needs to make up a random trap session ID." His central fix: "Web applications must ignore any session ID provided by the user's browser at login and must always generate a new session."
- **Today, OWASP.** Ids need "at least 64 bits of entropy"; applications "should never accept a session ID they have never generated"; the id must be regenerated "after any privilege level change"; every session needs idle and absolute timeouts. RFC 6265 §8.2 adds that cookies are "a form of ambient authority," the root of cross-site request forgery.
- **2025 to 2026, MCP.** The Model Context Protocol's Streamable HTTP transport (2025-03-26) let a server assign an `Mcp-Session-Id` at initialization; a client receiving 404 "MUST start a new session." The 2026-07-28 revision removes the header and the initialize handshake (SEP-2567, SEP-2575). Each request now carries its own version and capabilities. The official post says any request can then reach any server instance "without shared storage." For state an application needs, it recommends that a tool mint an explicit handle the model passes back as an argument, because the model can see it.

**The failure that forced each step.** Session stores in one process's memory forced "sticky sessions," where a load balancer pins a client to one server **(memory)**. Ids accepted from the client led to fixation. Ids used as credentials led to hijacking and CSRF. Hidden transport sessions in MCP blocked horizontal scaling.

**Lesson.** An id may name state, but it must never be the thing that grants access to it, and a server that creates a session for any id it is shown has handed that choice to an attacker.

## Lineage 3: the session as a consistency guarantee

**Timeline.**

- **1994, Bayou.** Terry, Demers, Petersen, Spreitzer, Theimer and Welch (Xerox PARC, PDIS 1994) define it: "A session is an abstraction for the sequence of read and write operations performed during the execution of an application." It is not a transaction. It gives an application "a view of the database that is consistent with their own actions." Four guarantees follow: Read Your Writes, Monotonic Reads, Writes Follow Reads, Monotonic Writes. A session manager in the client stub keeps two sets per session: a read-set ("WIDs for the Writes that are relevant to session Reads") and a write-set. A WID is a write identifier. In practice the state is "only two version vectors." A version vector is a compact summary of which writes a replica has seen. If no server can meet a guarantee, the system "informs the calling application that the guarantee cannot be met." The servers keep no session state: "no system-wide state is maintained." Sessions "are lightweight entities, a single application may create several sessions."
- **PgBouncer pooling.** A Postgres session is a connection plus its settings, prepared statements, temporary tables and locks. In session pooling a server connection is held "for the whole duration" the client stays connected. In transaction pooling it is held "only during a transaction." The docs list what then breaks: SET/RESET, LISTEN, WITH HOLD cursors, PREPARE, temp tables that persist across transactions, session advisory locks. State that hid inside a connection was lost when connections became shared.
- **2017, MongoDB logical sessions (3.6).** The driver specification says drivers "SHOULD generate session IDs locally," as a v4 UUID, with no round trip. So the client mints the id. But the server's session key is not the UUID alone. SERVER-30298 (fixed in 3.5.11) added "a sha256 digest of the full username" to the logical session id. Passing that digest yourself is "illegal ... unless the currently auth'd user has the impersonate privilege." Sessions expire after 30 minutes idle by default. "Only one thread at a time" may use one. The session carries `operationTime` and `clusterTime`, Bayou's vectors under another name.

**The failure that forced each step.** Weak replication made a user's own writes vanish (Bayou). Connection-bound state broke under pooling (PgBouncer).

**Lesson.** A consistency session is small, client-owned and optional, it refuses rather than guesses when it cannot hold its promise, and a client-minted id is safe only when the server adds the owner to the key.

## Lineage 4: the session as a record of what was read, used to refuse a stale write

**Timeline.**

- **1981, optimistic concurrency control.** Kung and Robinson (ACM TODS 6(2), June 1981) split a transaction into a read phase, a validation phase and a write phase. Writes go to local copies. The read set is checked at validation. A transaction that fails validation is restarted. No locks are held while the work is done.
- **1997 to 2022, HTTP validators.** The entity tag (ETag) and the `If-Match` precondition arrive with HTTP/1.1 (RFC 2068, 1997; RFC 2616, 1999) **(memory, for those two dates)**. The W3C note by Nielsen and LaLiberte (May 1999) names the "lost update problem": two people fetch a document, one saves, the other saves over it without having seen the first change. Its fix is "unreserved checkout": the client keeps the ETag and sends it on each PUT in `If-Match`; a mismatch fails the save. `If-None-Match: *` guards a create. RFC 9110 (June 2022) keeps both: `If-Match` is used "to prevent the 'lost update' problem," and `If-None-Match: *` prevents a PUT from "inadvertently modifying an existing representation."
- **1999 and 2007, WebDAV locks.** The pessimistic alternative: lock, read, edit, write, unlock. RFC 4918 (June 2007) records the experience: "exclusive locks are often too rigid," "locks are not always properly released," timeouts "may be long." It concedes that locks "cannot guarantee that updates will never be lost," because a client that does not lock can still overwrite. The W3C note said the same in 1999: locks time out or are broken, so lost updates must still be detected.
- **2025 to 2026, coding agents.** Agent tools refuse an edit to a file the agent has not read in this conversation, or that changed since it was read **(memory, for Claude Code's tool behaviour; not checked in docs here)**. vfs's stamp design (pull request 42) is this lineage: a stamp is an ETag held per session, and "strict" is Kolšek's word turned to a new use, refusing a change to a file the session never read.

**The design choice and the failure.** Remember the version read, send it with the write, and let the server refuse if it moved. Locks held across think time were not released, and blind writes lost other people's work.

**Lesson.** The read record is a per-resource validator checked at write time, so it is safe to copy, safe to lose (losing it only causes a refusal) and safe to send with the request instead of storing it.

## Lineage 5: the conversation as a tree, and the fork

**Timeline.**

- **1970s, fork(2).** Unix `fork` copies the whole process. The child inherits open file descriptors, which share the parent's file offsets **(memory, for offsets)**. Baumann, Appavoo, Krieger and Roscoe ("A fork() in the road," HotOS 2019) list the costs. Fork is "not thread-safe": the child has only a copy of the calling thread. Buffered IO must be flushed "lest output be duplicated." It is "insecure": "a forked child inherits everything from its parent," violating least privilege. Even Linux's `clone` only offers, per resource, two options: "either share the resource between parent and child, or else copy it."
- **1982 to 2005, version control.** RCS (Tichy, 1982), CVS (1986) and Subversion branch by copying **(memory)**. Git (2005) makes a branch "a lightweight movable pointer" to a commit, "a simple file that contains the 40 character SHA-1," so "branches are cheap to create and destroy" (Pro Git).
- **2005 onward, copy-on-write storage.** ZFS snapshots and clones, then btrfs, make a writable copy of a whole file system in constant time by sharing blocks until one side writes **(memory)**.
- **2023 to 2026, OpenAI.** Assistants threads held messages on the server, with runs executing against them **(memory, for the November 2023 launch)**. The API was sunset on 26 August 2026; threads map to Conversations and runs to Responses. Conversations hold "streams of items instead of just messages." The docs describe chaining by `previous_response_id`, not forking a Conversation. ChatGPT added "Branch in new chat" around 5 September 2025 (press coverage).
- **2024 onward, LangGraph.** A thread is named by a caller-supplied `thread_id`. Checkpoints snapshot graph state per step. A fork is `update_state` on an old checkpoint, which "does not roll back a thread. It creates a new checkpoint that branches." Replay re-runs every node after the checkpoint, and "LLM calls, API requests, and interrupts fire again and may return different results." On resume an interrupted node "restarts from its beginning," so "side effects called before interrupt must be idempotent."
- **Claude Agent SDK and Claude Code.** The SDK generates the session id; the caller reads it from the result and passes it to `resume`. Sessions are JSONL files on one machine; another host needs a `SessionStore` adapter or a copied file. Fork "creates a new session that starts with a copy of the original's history." The docs warn twice: "Sessions persist the conversation, not the filesystem," and "Forking branches the conversation history, not the filesystem. If a forked agent edits files, those changes are real and visible to any session working in the same directory." File checkpointing is a separate feature, does not undo Bash changes, and is "tied to the session that created them."
- **2025, Agent Client Protocol.** The agent "MUST respond with a unique Session ID" to `session/new`, which takes a working directory. `session/load` replays history. No fork is defined.

**What a fork copies.** Every modern system copies the conversation cheaply. None forks the outside world. Files and API calls are shared, and the docs say so in warnings. Whole copies were slow, so branches became pointers. Implicit inheritance surprised people, so better designs became explicit. Replay repeated side effects, so the docs now demand idempotence.

**Lesson.** A fork must state, resource by resource, what it copies and what it shares, because the world outside the history is always shared and a user who is not told assumes it was copied.

## Lineage 6: workflow identity

**Timeline.**

- **Idempotency keys (Stripe).** The client generates the key; Stripe suggests v4 UUIDs. Stripe saves the status code and body of the first request "after endpoint execution begins," and returns them for retries. A reused key with different parameters is an error. Keys may be pruned after 24 hours, after which reuse makes a new request.
- **AWS Step Functions.** An execution name is optional; without one a UUID is generated. For standard workflows it must be unique per account, region and state machine. The same name with the same input while running returns the original response. A different input, or a closed execution, gives `ExecutionAlreadyExists`. A name can be reused 90 days after it closes.
- **Temporal.** The Workflow Id is "chosen by your application" and usually carries business meaning. At most one open execution per Workflow Id per namespace. Each execution also gets a system Run Id, which changes on retry, reset or continue-as-new. Two policies govern reuse. The conflict policy, for an open execution: Fail (default), Use Existing, or Terminate Existing. The reuse policy, for closed ones: Allow Duplicate (default), Allow Duplicate Failed Only, Reject Duplicate, Terminate if Running, checked within retention (30 days by default).

**The design choice.** Let the business name the long-lived thing, scope the name, keep a system id per run, and make reuse an explicit policy. The failure behind it was retries over unreliable networks making duplicates **(memory)**.

**Lesson.** A caller-chosen name is safe when its scope is declared, its reuse rule is explicit, a mismatched reuse is refused, and each run under it has its own system id.

## The most fundamental concept

At bottom, a session is **a name for a continuing relationship between one party and a system, so that a later request can be understood in light of earlier ones.** Every lineage is a case of it. What differs is what "in light of earlier ones" carries.

It is really three concepts, and history keeps them apart wherever it works well.

1. **A context.** Who is acting, where (working directory, environment), and for which conversation. This is Lineage 1, plus the ownership half of Lineage 2. It needs a stable name, an owner, a lifetime, and a parent if forked.
2. **A causal record.** What this party has seen and written, used to check later operations. This is Lineages 3 and 4: Bayou's read-set and write-set, the ETag, the OCC read set, vfs's stamps. It is a set of validators. It is safe to copy, safe to lose and safe to send with the request.
3. **A run.** A unit of execution with its own id, which may pause and resume. This is Lineage 6, the Unix job, the LangGraph interrupt and the vfs job. It belongs to a context, but it has its own identity and lifecycle (Temporal's Workflow Id and Run Id).

The connection is not on this list. Every lineage that bound a session to one later had to unbind it.

These should be separate objects, or separate tables keyed by the session id: one small context row, many bounded and evictable record rows, and run rows that point at the context. A fork then copies the context under a new id with a parent pointer, copies the record, and never takes the runs.

## The recurring mistakes

- **State in one process's memory, or bound to a connection.** Unix sessions died on hangup. Web session stores needed sticky load balancing. PgBouncer broke connection state. MCP's header blocked scaling until it was removed. Claude Code sessions live in files on one machine. vfs's in-memory stamps repeat this.
- **An id that doubles as a credential.** Cookies became "ambient authority" (RFC 6265), and fixation and hijacking followed. MongoDB avoided it by adding a server-computed user digest to a client-made UUID.
- **Get-or-create on a caller-supplied id with no owner check.** These are Kolšek's "permissive" servers. Temporal and Step Functions avoid it with explicit conflict policies and input comparison.
- **No expiry.** OWASP requires idle and absolute timeouts. Every mature system has a retention rule: MongoDB 30 minutes idle, Stripe 24 hours, Temporal 30 days. WebDAV locks that were never released show what happens without one.
- **A fork that silently shares what the user thought was copied.** fork(2)'s inherited descriptors, the Agent SDK's fork that shares the file system, and LangGraph's replay that re-fires API calls.
- **Pessimistic locks held across think time.** Reserved checkout and WebDAV locks were too rigid. Optimistic validators replaced them.
- **One session used concurrently.** MongoDB forbids it. Bayou serializes a session through one manager. Two devices on one chat will do it anyway.
- **Hidden state.** MCP moved to explicit handles because the model could not see transport state.

## What history suggests for vfs

1. **Key a session by (owner, id), never by id alone.** The caller may supply the id, as MongoDB clients mint UUIDs and Temporal callers pick Workflow Ids. Ownership must come from the `Authority`, as MongoDB adds the user digest on the server. Opening an existing id under a different authority should fail as not found, so the id is never an oracle and never a credential (Kolšek; RFC 6265 §8.2; SERVER-30298). This bears on the caller-supplied id.

2. **Make "the id exists" an explicit, named policy.** Offer create (fail if it exists), open (fail if absent) and open-or-create. Open-or-create returns the existing session only to its owner, and compares any creation parameters, refusing a mismatch (Temporal conflict policy; Step Functions input check; Stripe parameter check). Never be permissive in Kolšek's sense. A generated id should use a CSPRNG with at least 64 bits (OWASP), but its secrecy is not the defence.

3. **Store the session in the database, keyed by its id.** Fielding, PgBouncer, MCP and the Agent SDK's `SessionStore` agree: a stateless handler on another process must find the session by name. The in-memory object becomes a cache over rows, which ends "every edit refused as unread on the next turn."

4. **Treat stamps as a causal record of validators.** Bayou kept "only two version vectors" and refused when it could not keep its promise. ETags are checked at write time. So stamps can be bounded and evicted, because a lost stamp only causes a refusal. They can also travel with the request, as `If-Match` does, for hosts that keep state themselves. A stamp row written on every read puts a write on the read path, about three calls in four at the reference deployment, so that cost must be counted.

5. **Keep three things apart: the session context, its causal record, and its jobs.** Give each its own id and table. A job records the session id it ran under; the session does not own the job's state (Temporal Workflow Id versus Run Id; Unix sessions holding jobs).

6. **On fork, copy the session's own records, share the files, and say so.** Copy the context under a new id with a parent id. Copy the stamps; that is safe because each is re-checked at write time (Kung and Robinson; If-Match). Share the files, as every agent system does, and state it in the API, not a footnote (Agent SDK notes; Baumann et al.). A copy-on-write view of files, like a ZFS clone or a git branch, is a separate decision.

7. **A fork never takes the source's pending jobs.** fork(2) copies only the calling thread. LangGraph re-fires interrupts on time travel rather than sharing them. A pending interrupt stays with the session that raised it. The fork starts with none.

8. **Resume by session id, not by object.** A resumed job loads its session from the database by the id stored in the job, checks that the resuming authority owns it, and refreshes that session's stamps (LangGraph requires "the same thread ID when resuming"). Because vfs journals replies rather than re-running a node from its start, it avoids LangGraph's duplicated side effects; keep it that way.

9. **Give sessions a lifetime and a delete.** Declare idle and absolute expiry, enforced in storage, plus delete and list by owner (OWASP; MongoDB; Temporal). An expired session costs only re-reads under strict.

10. **Do not require a session, and expect concurrent use of one.** Bayou sessions were optional, several per application. HTTP preconditions work per request. MCP removed its mandatory session. A verb without a session keeps today's behaviour, and a one-call session (as `fs.cli` uses) covers one-shot work. Two devices on one conversation will use a session at once; MongoDB forbids that, vfs cannot. Stamps that merge by keeping the higher version, checked at write time, make the race safe.

**One line.** History says a session is a named, owned context with a small record of what was seen, stored where any process can find it, never a connection, never a credential, and never a container for the runs it started.

## Sources

- Corbató, Daggett, Daley, "An Experimental Time-Sharing System," SJCC, May 1962. https://en.wikipedia.org/wiki/Compatible_Time-Sharing_System and https://history.computer.org/pubs/2011-06-ctss.pdf
- TUHS mailing list, job control history, 2017. https://minnie.tuhs.org/mailman3/hyperkitty/list/tuhs@tuhs.org/message/32NM5M2DEN7LLISB2PJ5NJOXREL5QM23/
- The Open Group, POSIX `setsid`. https://pubs.opengroup.org/onlinepubs/9799919799/functions/setsid.html
- The Open Group, POSIX General Terminal Interface, 11.1.10. https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap11.html
- GNU Screen and tmux histories. https://en.wikipedia.org/wiki/GNU_Screen and https://en.wikipedia.org/wiki/Tmux
- Winstein, Balakrishnan, "Mosh: An Interactive Remote Shell for Mobile Clients," USENIX ATC 2012. https://www.usenix.org/system/files/conference/atc12/atc12-final32.pdf
- ITU-T X.225 (11/1988), session protocol. https://www.itu.int/dms_pubrec/itu-t/rec/x/T-REC-X.225-198811-S!!TOC-HTM-E.htm
- Montulli and cookies, 1994. https://lists.w3.org/Archives/Public/ietf-http-wg/2002OctDec/0008.html and https://en.wikipedia.org/wiki/Lou_Montulli
- Barth, RFC 6265, "HTTP State Management Mechanism," April 2011. https://www.rfc-editor.org/rfc/rfc6265
- Fielding, "Architectural Styles and the Design of Network-based Software Architectures," chapter 5, 2000. https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm
- Kolšek, "Session Fixation Vulnerability in Web-based Applications," ACROS Security, December 2002. http://www.acrossecurity.com/papers/session_fixation.pdf ; Bugtraq post https://seclists.org/bugtraq/2002/Dec/179
- OWASP, Session Management Cheat Sheet. https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- MCP specification 2025-03-26, transports. https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
- MCP blog, "2026-07-28" release post. https://blog.modelcontextprotocol.io/posts/2026-07-28/
- Terry et al., "Session Guarantees for Weakly Consistent Replicated Data," PDIS 1994. https://pages.cs.wisc.edu/~remzi/Classes/739/Fall2016/Papers/bayou-sessions94.pdf
- PgBouncer, features and pooling modes. https://www.pgbouncer.org/features.html
- MongoDB driver sessions specification. https://github.com/mongodb/specifications/blob/master/source/sessions/driver-sessions.md
- MongoDB SERVER-30298, user digest in logical session id. https://jira.mongodb.org/browse/SERVER-30298
- MongoDB causal consistency. https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/
- Kung, Robinson, "On Optimistic Methods for Concurrency Control," ACM TODS 6(2), June 1981. https://www.eecs.harvard.edu/~htk/publication/1981-tods-kung-robinson.pdf
- Nielsen, LaLiberte, "Editing the Web: Detecting the Lost Update Problem Using Unreserved Checkout," W3C Note, May 1999. https://www.w3.org/1999/04/Editing/
- Fielding, Nottingham, Reschke, RFC 9110, "HTTP Semantics," June 2022. https://www.rfc-editor.org/rfc/rfc9110
- Dusseault, RFC 4918, "WebDAV," June 2007. https://www.rfc-editor.org/rfc/rfc4918
- Baumann, Appavoo, Krieger, Roscoe, "A fork() in the road," HotOS 2019. https://www.microsoft.com/en-us/research/wp-content/uploads/2019/04/fork-hotos19.pdf
- Chacon, Straub, Pro Git, "Branches in a Nutshell." https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell
- OpenAI, Assistants migration guide and conversation state guide. https://developers.openai.com/api/docs/assistants/migration and https://developers.openai.com/api/docs/guides/conversation-state
- ChatGPT "Branch in new chat," September 2025 (press). https://www.techradar.com/ai-platforms-assistants/chatgpt/chatgpt-has-added-a-great-new-feature-and-its-one-i-know-ill-be-using-a-lot
- LangGraph persistence, time travel and interrupts. https://docs.langchain.com/oss/python/langgraph/persistence , https://docs.langchain.com/oss/python/langgraph/use-time-travel , https://docs.langchain.com/oss/python/langgraph/interrupts
- Claude Agent SDK, sessions and file checkpointing. https://code.claude.com/docs/en/agent-sdk/sessions and https://code.claude.com/docs/en/agent-sdk/file-checkpointing
- Agent Client Protocol, session setup. https://agentclientprotocol.com/protocol/session-setup
- Stripe, idempotent requests. https://docs.stripe.com/api/idempotent_requests
- AWS Step Functions, StartExecution. https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html
- Temporal, Workflow Id and Run Id. https://docs.temporal.io/workflow-execution/workflowid-runid
