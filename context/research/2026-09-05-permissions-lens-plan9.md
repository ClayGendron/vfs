# Permissions lens L2: Plan 9

- **Status**: research memo, Phase 1 lens L2 of the principals and
  permissions programme (`2026-09-05-principals-and-permissions-research-plan.md`).
  Commits us to nothing. It answers the plan's thirteen questions from
  Plan 9's primary sources and grades each answer against the plan's
  hypothesis (subject, actor, attenuation) and the §1.1 multiplayer
  intersection rule.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: Plan 9 binds identity per attach, not per process; it
  has a named least-privilege user (`none`); it keeps keys in an agent
  the process never sees (factotum); it gives every process its own
  name space; and its authentication server is a third party that rules
  on "who may speak for whom". Which of those mechanisms support,
  qualify, or contradict the hypothesis, and what should vfs take?
- **Method**: line-level read of the Plan 9 kernel (`auth.c`, `chan.c`,
  `sysfile.c`, `devcons.c`, `devproc.c`, `devmnt.c`, `devcap.c`,
  `dev.c`, `sysproc.c`), the auth server (`authsrv.c`), factotum, the
  `cpu`, `exportfs` and `listen` commands, the fossil file server's
  permission code (`9p.c`, `9auth.c`, `9user.c`), the `libauth` routines
  (`auth_chuid.c`, `newns.c`), `/lib/namespace`, and the manual pages
  `attach(5)`, `intro(5)`, `open(5)`, `stat(5)`, `walk(5)`, `auth(2)`,
  `auth(8)`, `authsrv(6)`, `factotum(4)`, `cap(3)`, `cons(3)`, `proc(3)`,
  `fork(2)`, `users(6)`, `exportfs(4)`, `cpu(1)`, `fossilcons(8)`. In
  plan9port: `9pserve.c`, `9pserve(4)`, `srv(4)`, `auth(3)`,
  `lib9pclient/fs.c`. Three papers read online. The April memo
  (`2026-04-19-plan9-and-plan9port.md`) covered the filesystem and 9P
  message shapes; none of that is repeated here. Cites and describes
  only; no code is copied.
- **License**: `plan9`: MIT (`LICENSE` at the root, Plan 9 Foundation,
  2021; `NOTICE` records the Lucent origin). `plan9port`: MIT (`LICENSE`,
  Plan 9 Foundation, with portions Russ Cox and Google). Study freely;
  copy nothing.
- **Sources line**: `plan9` @ `ed1a9c21e` (2025-10-28), **dirty and not
  refreshed** (five modified files under `rc/bin` and `sys/lib/troff`,
  none touched by this memo). `plan9port` @ `b6564bd9` (origin/master,
  refreshed 2026-08-26). Papers, all read 2026-09-05: "Security in
  Plan 9" (Cox, Grosse, Pike, Presotto, Quinlan, USENIX Security 2002),
  https://9p.io/sys/doc/auth.html; "The Use of Name Spaces in Plan 9"
  (Pike, Presotto, Thompson, Trickey, Winterbottom),
  https://9p.io/sys/doc/names.html; "Plan 9 from Bell Labs" (Pike et
  al.), https://9p.io/sys/doc/9.html; `attach(5)` online,
  https://9p.io/magic/man2html/5/attach.

---

## Bottom line

Plan 9 supports the hypothesis on attenuation and on enforcement, and
qualifies it on the actor/subject split. Identity is a text name fixed
at attach time (`Tattach uname`), stamped by the kernel from the calling
process, and proven, when the server asks, by a ticket a third party
minted. Every later request on that connection inherits it. A process
can drop to `none` at will and can never climb back except through a
single-use capability minted by the host owner's factotum. A name space
can be made narrowing-only with one flag (`RFNOMNT`) that is inherited
and can never be cleared. Enforcement is per request, inside the server
that holds the data, against the server's own user table. Those four
facts are the hypothesis in 1990s clothing. The qualification: Plan 9
does have an actor and a subject at authentication time (the ticket
request carries `hostid`, who speaks, and `uid`, who is spoken for), but
the auth server collapses them into one name before the ticket reaches
the file server, so the far side never learns who the actor was. Only
the auth server's log keeps the pair. Factotum is the cleanest prior art
for an actor that authenticates on behalf of a subject without holding
the credential: the process talks to an agent; the agent can demand
confirmation per use; a remote session can be pointed at the subject's
own agent. For Q13 there is no precedent: nothing in Plan 9 runs at the
meet of several users' rights, and the one shared-session mechanism
(`srv -a`, `9pserve -A`) does the opposite, collapsing every client into
the poster's identity.

---

## Q1. Subject, actor, "on behalf of"

**Verdict: qualified.** The subject is a text user name bound per
attach. An actor/subject pair exists at ticket-request time and is then
collapsed to one name.

Terms first. A *fid* is a 9P file handle. An *attach* is the 9P message
that opens a connection to a server's tree. *uname* is the user name in
that message. *aname* is the tree name.

The subject is `uname`. The kernel puts the calling process's own user
into the message; a process cannot claim a different name on the wire.
`mntauth` sets `r->request.uname = up->user`
(`plan9:sys/src/9/port/devmnt.c:281`) and `mntattach` does the same
(`plan9:sys/src/9/port/devmnt.c:347`). The manual is explicit that the
name is then the implicit user of *every* later request: "Every file
request has an implicit user id (copied from the original attach) and an
implicit set of groups" (`plan9:sys/man/5/0intro:544-546`). The server
stores it on the fid: fossil copies `m->t.uname` into `fid->uname` at
attach, and substitutes `none` if the name is empty
(`plan9:sys/src/cmd/fossil/9p.c:994-997`). There is no per-process
identity on the server side at all. A server sees fids, not processes.

Whether the name is *proven* is the server's choice, per attach. With
`afid = NOFID` the client asks for no proof (`plan9:sys/man/5/attach:59-69`).
Fossil then accepts the claimed name only if the server was configured
with no auth check; otherwise it runs `authCheck`, which replaces the
claimed `uname` with the authenticated `cuname` from the auth fid
(`plan9:sys/src/cmd/fossil/9p.c:1002-1010`;
`plan9:sys/src/cmd/fossil/9auth.c:152-155`). So the shape is: *claim in
the message, proof on a side channel, the server substitutes the proven
name for the claimed one.* This is 070's "verified principal" with the
verification moved into the mount handshake.

The actor/subject pair lives in the ticket request. A `Ticketreq`
carries `hostid` ("host's encryption id") and `uid` ("uid of requesting
user on host") (`plan9:sys/include/authsrv.h:64-65`). When factotum
speaks for another user it sets `hostid` to the key owner and `uid` to
the user spoken for (`plan9:sys/src/cmd/auth/factotum/p9sk1.c:259-264`).
The auth server checks `speaksfor(hostid, uid)` against `/lib/ndb/auth`
(`plan9:sys/src/cmd/auth/authsrv.c:130`, `:791-821`). The record format
is `hostid=bootes uid=!sys uid=!adm uid=*`: a host may speak for
everyone except two named users (`plan9:lib/ndb/auth:1-10`). That is a
delegation table with a deny list, kept at the third party.

Then the collapse. The ticket the server receives has `cuid` and `suid`,
but the auth server writes the *requested uid* into both
(`plan9:sys/src/cmd/auth/authsrv.c:129-131`). The `hostid` is dropped.
It survives only in the auth server's own syslog line
`tr-ok uid@hostid(raddr) -> uid@authid`
(`plan9:sys/src/cmd/auth/authsrv.c:153-155`). The file server's
`AuthInfo.cuid` is therefore the subject alone (`plan9:sys/man/2/auth:161-173`).
The paper confirms the intent: the cpu server "reattaches to all relevant
file servers using the authentication protocol to identify itself as
Peter" ("Plan 9 from Bell Labs", section on the cpu command). The actor
becomes the subject, fully, on the far side.

For vfs: Plan 9 gives the subject shape (a verified text name, bound per
mount, implicit on every request) and the delegation shape (a third
party rules on who may speak for whom, with a deny list). It does not
give the audit shape; it loses the actor. The hypothesis says the audit
must name both. Plan 9 is the cautionary example of what happens when it
does not: the only record of the actor is on a machine the data owner
does not run.

## Q2. Attenuation: how authority narrows, whether it widens

**Verdict: supports.** Identity can always be dropped and never raised
except by a single-use capability minted by a trusted process. A name
space can be locked narrowing-only with one inherited, unclearable flag.

Identity. Any process may write `none` to `/dev/user`; the kernel
accepts exactly that string and nothing else
(`plan9:sys/src/9/port/auth.c:109-116`, comment: "anyone can become
none"). The listener does this before it runs any network service
(`plan9:sys/src/cmd/aux/listen.c:367-377`). Going up has one door: the
capability device. A trusted process (one running as the host owner)
writes an HMAC of `old@new@key` to `#¤/caphash`; a process running as
`old` writes the capability string to `#¤/capuse` and becomes `new`
(`plan9:sys/man/3/cap`). Only `eve`, the host owner, may open `caphash`
(`plan9:sys/src/9/port/devcap.c:95-98`). Hashes are consumed on use and
expire after one minute (`plan9:sys/man/3/cap`). The trusted process
that mints them is factotum, after it has run the server side of an
authentication and knows who the peer is: `auth_chuid` writes the
capability to `capuse`, re-mounts factotum as the new user, and rebuilds
the name space (`plan9:sys/src/libauth/auth_chuid.c:9-39`). So widening
is: an authenticated proof, converted by a trusted agent into a
one-shot, time-boxed token, spent once. That is a session token in the
hypothesis's sense, and it is the *only* way up.

Name space. A process may normally mount and bind freely, so a name space
alone is not narrowing-only. `rfork(RFNOMNT)` sets `noattach` on the
process group; it is inherited on every later `rfork` and nothing clears
it (`plan9:sys/src/9/port/sysproc.c:56-66`, `:131-143`). With it set,
`mount` fails (`plan9:sys/src/9/port/sysfile.c:1009-1010`) and `#`
device names cannot be dereferenced except pipes, fds, env, cons and
proc, which the kernel comment itself calls "the iffy exceptions"
(`plan9:sys/src/9/port/chan.c:1361-1377`). The manual states the
contract in one line: "subsequent mounts into the new name space and
dereferencing of pathnames starting with # are disallowed"
(`plan9:sys/man/2/fork:71-75`). This is the closest thing in Plan 9 to a
session profile that only narrows: build the view, then set the flag.
The paper's own example is the window system giving each client its own
`/dev/cons` ("The Use of Name Spaces in Plan 9", 8½ section).

Where it sits: identity is per process (`up->user`), proven per attach,
narrowed per process group (the name space). Nothing is per token
except the one-minute capability.

For vfs: this is the session law. Two mechanisms, both monotone: drop
identity (never regain it without a fresh proof) and freeze the name
space (never re-widen). vfs's per-session narrowing should have the same
two properties, and the "widen" path should exist only as a fresh
authentication producing a fresh session, never as an in-session
escalation.

## Q3. Where enforcement lives

**Verdict: supports.** Per request, inside the server that holds the
data, against the server's own user table. The kernel checks only what
the kernel serves.

The kernel has one name funnel, `namec`
(`plan9:sys/src/9/port/chan.c:1317`), and one permission check for
kernel devices, `devpermcheck`, which compares `up->user` to the file's
owner, then to `eve`, then falls to "other" bits
(`plan9:sys/src/9/port/dev.c:339-355`). For anything mounted from a 9P
server the kernel checks nothing: it sends the request and the server
decides. `open(5)` puts the check on the server: "the open request asks
the file server to check permissions" (`plan9:sys/man/5/open:33-35`).
Fossil's `permFile` is that check: owner bits if the fid's user owns the
file, group bits if the user is a member, other bits otherwise, with
`none` restricted to other bits (`plan9:sys/src/cmd/fossil/9p.c:18-63`).
It is called on every walk (`:854`), open (`:709`, `:722`, `:731`),
create (`:593`) and remove.

The trust chain is explicit: the kernel trusts the mounted server; the
server trusts the auth server; the auth server trusts its key database.
"Plan 9 has no super-user. Each server is responsible for maintaining
its own security" ("Plan 9 from Bell Labs", file server section). The
host owner is deliberately weak: "just a regular user that happens to
own the resources of the local machine" ("Security in Plan 9", §2.3).

For vfs: this is ADR 021's funnel. One resolver, and the check compiled
into the store that holds the rows. Plan 9 adds a design point vfs has
been circling: a mount is a trust boundary. The near side does not
re-check what the far side owns; it attaches under a principal and lets
the far side enforce under its own principal space. That is the remote
mount story in one sentence.

## Q4. The unit of protection

**Verdict: qualified.** Per-file mode bits keyed on the server's file
identity, plus per-path binding in the name space. `omode` cannot
express attenuation of a handle.

Two units. On the server: a file, with owner, group and three rwx
triples; the walk into a directory "is regarded as executing the
directory, not reading it" (`plan9:sys/man/5/0intro:563-566`). Fossil
keys the check on the file's directory entry, not its path
(`plan9:sys/src/cmd/fossil/9p.c:18-25`). In the kernel: a path prefix,
because `bind` and `mount` attach trees at names, and the mount table is
hashed on the qid of the mount point (`plan9:sys/src/9/port/chan.c:693`).
So Plan 9 has both of ADR 021's forks and does not choose: identity on
the server, prefix in the name space.

`omode` is four values, read, write, read-write, execute, plus three
flag bits (`plan9:sys/src/9/port/sysfile.c:162-170`;
`plan9:sys/man/5/open:41-81`). What it cannot say: create-without-write
(creation is "write permission in the directory", `open(5)`),
list-without-traverse, a right that lasts less than the fid (there is no
way to derive a weaker fid from a stronger one), or a right scoped to a
subtree. The April memo's "don't adopt 9P omode" stands for a sharper
reason than tidiness: `omode` is an I/O mode, not a right. It is
consulted once, at open, and after that the fid is a bearer handle
("permissions are checked at the time of the open request; subsequent
changes to the permissions of files do not affect the ability to read,
write, or remove an open file", `plan9:sys/man/5/open:90-93`). That is a
capability, which is fine for a kernel and wrong for a store that must
re-check after a grant is revoked.

For vfs: keep ids as the unit and prefixes as the grant scope
(ADR 021 D2), and do not model rights as open modes.

## Q5. Hide versus deny, and traversal

**Verdict: supports, with two mechanisms.** Hide is the name space and
the export filter; deny is the server. They are separate layers and
Plan 9 never confuses them.

Hide. A file that is not bound into a process's name space cannot be
named, so there is nothing to deny. `exportfs -P patternfile` filters
what a server will admit exists: `excludefile` returns non-zero when an
include pattern fails or an exclude pattern matches
(`plan9:sys/src/cmd/exportfs/pattern.c:73-97`); `file()` then returns
nil, which the walk reports as a missing file
(`plan9:sys/src/cmd/exportfs/exportfs.c:627-630`); and directory reads
skip the entry (`plan9:sys/src/cmd/exportfs/pattern.c:126-131`). The
manual: "For a file to be exported, all lines with a prefix + must match
and all those with prefix - must not match" (`plan9:sys/man/4/exportfs`,
`-P`). That is a per-session projection: the excluded file is not
refused, it is absent. The auth server hides at the identity layer too:
for an unknown user it "silently generates one-time random keys ... so
that clients cannot probe the AS to learn whether a user name is valid"
(`plan9:sys/man/6/authsrv`, Ticket Service).

Deny. Fossil returns the string "permission denied" from `permFile`
(`plan9:sys/src/cmd/fossil/9p.c:15`, `:63`). Walk requires execute on
each directory, and `..` is always walkable "so that you can't walk into
a directory and then not be able to walk out of it"
(`plan9:sys/src/cmd/fossil/9p.c:845-861`). A walk that fails part way
returns the qids of the successful prefix (`plan9:sys/man/5/walk:100-118`),
so the client learns exactly how far it got. Deny is loud by design.

Union directories add a third case. A union is one name backed by an
ordered list of directories; lookup tries each in order
(`plan9:sys/src/9/port/chan.c:1026-1040`). Creation goes to the first
element bound with `-c`, and "if that directory does not have write
permission, the create fails" (`plan9:sys/man/1/bind:118-125`;
`createdir`, `plan9:sys/src/9/port/chan.c:1140-1161`). So a union can
show a file from one server and refuse to create beside it because the
creatable element is a different server with different rights. What a
9P server can say about a file it will not show is therefore: nothing.
It either serves the entry or it does not, and the name space decides
what is asked of it.

For vfs: 058's `invisible` rung and the Mirage leak rules are the
export-filter shape: the entry is absent from every list and every walk
reports "not found". Deny stays a classified refusal on things the
caller can name. The two must never share a code path, which is what
`exportfs` shows by filtering in `file()` before any stat.

## Q6. Groups, roles, tenants

**Verdict: supports on resolution timing; groups widen, as in Unix.**

Groups are per file server, in `/adm/users`, one line per user:
`id:name:leader:members` (`plan9:sys/man/6/users:9-40`). "Such a line
defines a user and a group with the given name", so every user is a
group; a group has an optional leader; if the leader field is empty
every member leads (`:29-37`). "The idea of group is unusual: any user
name is potentially a group name" ("Plan 9 from Bell Labs"). The file
is owned by `adm` and changed only from the console (`:66-71`). There is
no cross-server group; each file server has its own table, and the
auth server has none (it holds keys and the speaks-for table only).

Resolution. The name-to-id mapping happens once, at attach
(`plan9:sys/src/cmd/fossil/9p.c:1006`). Group membership is looked up
at every check: `permFile` re-derives the owner's name because "it
might have changed during the lifetime of this Fid"
(`plan9:sys/src/cmd/fossil/9p.c:29-35`), and `groupMember` walks the
in-memory user box each call (`plan9:sys/src/cmd/fossil/9user.c:140-160`,
`:261-273`). A member "is automatically in their own group" (`:146-152`).
So: identity at login, groups per query.

Two restrictive groups sit above the bits. If a `write` group exists,
only its members can write "no matter what the permission bits say"
(`plan9:sys/src/cmd/fossil/9user.c:164-192`), and every write path
checks it (`9p.c:134`, `:585`, `:690`). Members of `noworld` get no
"other" permissions at all (`plan9:sys/src/cmd/fossil/9p.c:48-56`;
`noworld()` in `plan9:sys/man/2/auth:141-149`, used "to provide
sandboxed access for some users"). These are AND gates on top of an OR
model; they narrow. Ordinary groups widen: membership adds the group
bits to what the user could already do.

Tenants: `aname` selects a tree per attach (`plan9:sys/man/5/attach:32-40`),
and fossil parses it into a file system name and a path
(`plan9:sys/src/cmd/fossil/9p.c:986`). That is a tenant selector at
mount time, not a row label.

For vfs: per-query group resolution is the answer to ADR 021's open
fork, with the caveat that Plan 9's table is in memory and tiny. The
`write` and `noworld` groups are the seed of a restrictive-policy layer
(Q13 below).

## Q7. Defaults on creation, ownership transfer, move and copy

**Verdict: supports.** Created files inherit a mask from the directory;
the owner is the requesting user and can never be changed; group change
needs membership on both sides; rename needs write on the parent.

Creation: "The owner of the file is the implied user id of the request,
the group of the file is the same as dir, and the permissions are the
value of perm & (~0666 | (dir.perm & 0666))" for a file and `0777` for
a directory (`plan9:sys/man/5/open:105-118`). The directory is the umask.
A file cannot be created more open than its parent.

Ownership: "it is illegal to attempt to change the owner of a file"
(`plan9:sys/man/5/stat:222-223`). Fossil enforces it unless the server
was started with `-W` (`plan9:sys/man/8/fossilcons`, `-W`: "allow wstat
to make arbitrary changes to the user and group fields"), an
initial-state escape hatch. Group: "by the owner if also a member of
the new group; or by the group leader of the file's current group if
also leader of the new group" (`plan9:sys/man/5/stat:209-214`;
`plan9:sys/src/cmd/fossil/9p.c:287-310`). Mode and mtime: owner or
group leader only (`stat(5):200-205`). `none` may never `wstat`
(`plan9:sys/src/cmd/fossil/9p.c:130-133`).

Move: `wstat` may change the name "by anyone with write permission in
the parent directory" (`stat(5):190-193`), and 9P has no cross-directory
rename; a move between directories is a copy and a remove under the
actor's own rights. Copy has no special case at all.

For vfs: 058's open forks close the way Plan 9 closes them. Owner is
immutable; inheritance is a mask from the parent, never wider; a move is
two ordinary operations, each checked.

## Q8. Audit: what is recorded, attributed to whom

**Verdict: qualified.** The subject is recorded on the file (`muid`)
and in the auth server's log; the actor is recorded nowhere the data
owner controls.

Every stat carries `muid`, "name of the user who last modified the
file" (`plan9:sys/man/5/stat:82-83`). Fossil sets it from the fid's user
on write and refuses any `wstat` that tries to alter it
(`plan9:sys/src/cmd/fossil/9p.c:175-181`). That is one field, the last
writer, no history. Fossil's snapshots (the dump) keep older versions as
a file system with the same permissions ("it is not possible to subvert
security by looking at the backup", "The Use of Name Spaces in Plan 9").

The auth server logs every ticket with both names,
`tr-ok uid@hostid(raddr) -> uid@authid`
(`plan9:sys/src/cmd/auth/authsrv.c:153-155`). Factotum keeps its own
`log` file (`plan9:sys/man/4/factotum:58-59`). Neither is visible to
the file server.

For vfs: ADR 013's per-entry revisions already beat `muid`. What Plan 9
adds is the negative lesson from Q1: if the actor is dropped at the
boundary, the only record is a log on a different machine. The version
row must carry both names because nothing downstream can reconstruct
the actor later.

## Q9. Failure modes on record

**Verdict: supports** (the threat table gets rows, and defences).

- *Anyone may claim `none`.* The paper says so ("anyone may claim to be
  none", "Plan 9 from Bell Labs"). Defences: fossil refuses `none` on a
  connection until some real user has authenticated on it, so an
  anonymous socket cannot attach at all (`con->aok`,
  `plan9:sys/src/cmd/fossil/9auth.c:84-96`, `:168-172`;
  `plan9:sys/man/8/fossilcons:411-419`); `exportfs` refuses to serve as
  `none` unless `-n` is given (`plan9:sys/src/cmd/exportfs/exportfs.c:47`,
  `:189-190`); the kernel stops `none` from touching other processes'
  control files (`nonone`, `plan9:sys/src/9/port/devproc.c:321-331`).
- *Confused deputy at the mount.* `cpu -u` warns: "resources in the
  local name space will be made available to that user"
  (`plan9:sys/man/1/cpu:199-204`). The terminal exports its own name
  space to a session running as someone else; `-P` is the only
  attenuation offered.
- *Unauthenticated attach as any name.* With `afid = NOFID` the server
  gets a bare claim (`plan9:sys/man/5/attach:59-69`). `9pserve -n`
  rejects `Tauth` outright (`plan9port:src/cmd/9pserve.c:463-466`), so
  every plan9port service that uses it runs on claims. `srvold9p` cannot
  authenticate, so "the likeliest value of user is none"
  (`plan9:sys/man/4/srv:239-245`).
- *Key theft through `/proc`.* Factotum marks itself `private` and
  `noswap` (`plan9:sys/src/cmd/auth/factotum/fs.c:201-215`;
  `plan9:sys/man/3/proc`, `private`: "Make it impossible to read the
  process's user memory").
- *Impersonation via the agent.* Factotum's `rpc` file is `0666`
  (`plan9:sys/src/cmd/auth/factotum/fs.c:264-269`), so any local user
  may ask it to authenticate. The guard is in the protocol: for a client
  who is not the owner, factotum "will only vouch for their name on the
  local system" (`plan9:sys/src/cmd/auth/factotum/p9sk1.c:223-227`,
  `:234-249`), and the auth server enforces the speaks-for table on top
  (Q1). Keys may also carry `confirm`, forcing a human to approve each
  use ("Security in Plan 9", §2.4; `plan9:sys/man/4/factotum:52-53`).
- *TOCTOU.* Rights are checked at open and never again
  (`plan9:sys/man/5/open:90-93`). A revoked user keeps open fids until
  clunk. This is a capability model's known cost.
- *Bypassing the name space.* `#` device names name kernel devices
  directly; `RFNOMNT` closes that door (Q2), and `namec` still allows
  five devices through it "unfortunately" (`plan9:sys/src/9/port/chan.c:1361-1377`).
- *The host owner.* Writing `/dev/hostowner` renames `eve` everywhere
  and is itself gated on being `eve` (`plan9:sys/src/9/port/auth.c:124-140`).
  Only `eve` may change another process's user via `wstat` on `/proc`
  (`plan9:sys/src/9/port/devproc.c:487-497`).

## Q10. Reversibility and permission together

**Verdict: supports.** History is a file system with the same
permissions, and a revert is an ordinary write under the actor's rights.

Fossil's dump is a read-only tree of snapshots served through the same
`permFile` (`plan9:sys/man/8/fossilcons`, `snap`/`epoch`). "None ... is
not allowed to examine dump files and can read only world-readable
files" ("Plan 9 from Bell Labs"). Restoring is copying from the dump
into the live tree, which needs write on the target directory and file.
No revert can exceed the reverter's rights, because there is no revert
verb; there is only read from history and write to now.

For vfs: this answers the plan's question directly. The revert of a
version row is a write of that content by the current actor, attributed
to the current actor and subject, and permitted only if a fresh write
would be. History is readable exactly as far as the live rows are.

## Q11. Scale and portability

**Verdict: no precedent.** Nothing here runs against a SQL engine or a
10k batch.

What transfers is the shape of names. Every identity on the wire is a
text name, never a number (`plan9:sys/man/5/0intro:470`: "The owner and
group identifications are textual names"). Each file server maps names
to its own ids at attach (`plan9:sys/src/cmd/fossil/9p.c:1006`;
`plan9:sys/man/6/users:46-66`). So a principal crosses a mount as a
name and is resolved into local terms on arrival. For vfs's remote
mounts that is the right portability story: the far side owns its
principal table; the near side ships a verified name.

## Q12. Take, adapt, reject

See the table below.

## Q13. Many subjects at once

**Verdict: no precedent.** Nothing in Plan 9 computes the meet of
several users' rights. The shared-session mechanisms do the opposite.

Searched for: any place a fid, connection, process, or name space is
governed by more than one user's rights at once.

- `srv -a` (plan9port) posts "a pre-authenticated connection"
  (`plan9port:man/man4/srv.4:32-36`). `9pserve -A aname afid` implements
  it by rewriting every client's `Tattach` to the poster's `afid`,
  `aname` and `getuser()` (`plan9port:src/cmd/9pserve.c:429-437`;
  `plan9port:man/man4/9pserve.4`, `-A`). Every client becomes the
  poster. That is a widening by sharing, the exact failure the
  multiplayer rule exists to prevent.
- `9pserve` otherwise keeps clients apart only at the fid level: each
  client connection has its own fid hash and its own `Tattach`
  (`plan9port:src/cmd/9pserve.c:414-428`, `:441-456`), and fids are
  clunked when a client hangs up (`plan9port:man/man4/9pserve.4`). It
  never combines two clients' identities; it forwards each attach as
  received.
- `exportfs -S` makes "a separate mount ... for each attach message, to
  correctly handle servers in which each mount corresponds to a
  different client" (`plan9:sys/man/4/exportfs`, `-S`;
  `plan9:sys/src/cmd/exportfs/exportsrv.c:93-122`). Isolation per
  client, not composition across clients.
- The kernel mount table is per process group and any process in the
  group may widen it (Q2). A shared name space is a shared *view*, not a
  shared *right*; each process still sends its own `up->user`.

The nearest kin is fossil's pair of restrictive gates, `write` and
`noworld` (Q6). Both are an AND applied after the OR of the mode bits,
both narrow, and both are per user. They show that a restrictive layer
above an OR model is cheap and well understood. They do not show a set
of subjects.

On the sub-questions: ownership of what a set creates has no precedent
(a file has exactly one `uid`, immutable); audit of a set has none
(`muid` is one name); a member joining mid-session has none (an attach
is fixed for the life of the fid; the only re-binding is a new attach).
Hide-for-a-set has a suggestive analogue: the union directory shows the
first match across several servers, so a set's view could be built as
the intersection of per-member exports, which `exportfs -P` already
makes a per-session filter. That is a construction, not a precedent.

---

## Take / adapt / reject for vfs

| Item | Plan 9 mechanism | Decision | For vfs |
|---|---|---|---|
| Identity per mount | `Tattach uname`, stamped by the kernel, proven by `afid` (`devmnt.c:347`; `attach(5)`) | **Take** | A mount is attached as a principal; the far side enforces under its own principal table; the near side never re-checks what the far side owns. |
| Claim plus proof, server substitutes the proven name | `authCheck` replaces `uname` with `cuname` (`fossil/9auth.c:152-155`) | **Take** | 070's verified principal: the session carries the *verified* name, never the claimed one. |
| Named least-privilege default | `none`: always accepted, other-bits only, no `wstat`, cannot touch other processes, refused until the connection has one real user (`fossil/9p.c:29`, `:130`; `9auth.c:84-96`) | **Adapt** | 070 fails closed on absent identity. Plan 9 argues for a *named* floor as well: an explicit `none` principal with a declared, tiny grant set, so "no identity" and "anonymous but allowed" are different states in the audit. Keep fail-closed for the absent case. |
| Drop always, raise only by minted token | `/dev/user` accepts only `none`; `#¤/capuse` one-shot, one-minute, minted by `eve`'s factotum (`auth.c:109-116`; `cap(3)`) | **Take** | The session law: a session can narrow itself at any time; widening is a new session from a fresh proof. No in-session escalation. |
| Narrowing-only name space | `RFNOMNT`, inherited, unclearable (`sysproc.c:56-66`; `fork(2)`) | **Take** | The profile freeze: once a session's view is set, no operation may add a mount or bypass a mount. Roadmap 023's per-session namespace should have this flag semantic by default. |
| Agent holds the key, process proxies | factotum `rpc`, `auth_proxy` (`auth(2)`), `private`/`noswap` (`factotum/fs.c:201-215`) | **Take** | The MCP passthrough ban, solved structurally: the actor never sees the subject's credential; it holds a channel to the subject's agent. For remote mounts, the far side authenticates through the near side's agent, never through a forwarded token. |
| Per-use confirmation on a key | `confirm` attribute, `/mnt/factotum/confirm` ("Security in Plan 9" §2.4) | **Adapt** | The "ask" of Mirage and of MCP elicitation, placed at the credential rather than the operation. Both placements are worth having. |
| Third party rules on delegation | `speaksfor(hostid, uid)` with `uid=*` and `uid=!name` deny entries (`authsrv.c:791-821`; `lib/ndb/auth`) | **Adapt** | A delegation table (who may act for whom) with a deny list, kept by the verifier. vfs's version lives in the grant spine, not an external server. |
| Collapse actor into subject at the boundary | ticket `cuid = suid = uid` (`authsrv.c:129-131`) | **Reject** | The version row records actor and subject. Never let a boundary drop the actor. |
| Enforcement in the server, per request | `permFile` on every walk/open/create/remove (`fossil/9p.c:18-63`) | **Take** | ADR 021 D3: compiled into the query, at the store. |
| Rights checked at open, never again | `open(5):90-93` | **Reject** | vfs re-checks per call; a grant revoked mid-session takes effect on the next call. |
| `omode` as the right | four I/O modes (`sysfile.c:162-170`) | **Reject** | Already rejected in April; the reason is now precise: an I/O mode is not a right and cannot be attenuated. |
| Hide by projection, deny by refusal, separate layers | `exportfs -P` returns nil before stat (`exportfs.c:627-630`; `pattern.c:73-97`); `permFile` says "permission denied" | **Take** | 058's `invisible` rung is a projection applied before any lookup; deny is a classified refusal on nameable things. Distinct code paths. |
| Enumeration defence at identity | random keys for unknown users (`authsrv(6)`) | **Take** | An unknown principal and a wrong proof must be indistinguishable at the edge. |
| Every user is a group; leaders | `/adm/users` (`users(6)`) | **Adapt** | Cheap group model: a principal id doubles as a group id; leaders own group edits. Resolve membership per query. |
| Restrictive gates above the OR | `write` and `noworld` groups (`fossil/9user.c:164-192`; `9p.c:48-56`) | **Adapt** | The AND layer the multiplayer rule needs, generalised from "per user" to "per subject set". |
| Creation inherits a mask; owner immutable | `open(5):105-118`; `stat(5):222-223` | **Take** | 058's defaults: never wider than the parent; ownership never transfers. |
| Revert is a write from history | dump served under the same permissions | **Take** | Q10: no revert verb exceeds a write's rights. |
| Shared pre-authenticated session | `srv -a`, `9pserve -A` (`9pserve.c:429-437`) | **Reject** | The anti-pattern for multiplayer: every client becomes the poster. |
| Text names on the wire, ids per server | `intro(5):470`; `9p.c:1006` | **Take** | Remote mounts ship a verified name; each side owns its id table. |

---

## Limits

- The `plan9` clone was dirty and not refreshed. Its head is
  `ed1a9c21e` (2025-10-28). The modified files are unrelated to this
  memo, but a later refresh could move line numbers.
- Fossil is one 9P server. Other servers (kfs, cwfs, ramfs, the
  synthetic devices) implement permissions differently or not at all.
  Where this memo says "the server", read "fossil and the kernel
  devices"; the protocol leaves the rest to each implementation.
- The papers were read through a summarising fetch, not in full text.
  Quotations from them are short and were checked against the source
  code where the code exists; treat the section attributions as
  approximate.
- Plan 9's scale is a workgroup: one auth server, a user table small
  enough to hold in memory, tickets over DES. Nothing here was measured
  at vfs's target sizes, and Q11 says so.
- `rx` was not studied separately; it is a thin wrapper over the same
  `cpu`/`exportfs` identity path, and the memo cites that path instead.
- Q13 is a negative result from a search of the mechanisms named in the
  brief plus fossil's group code. A conjunctive precedent could hide in
  a corner of the tree not searched (the old `ipserv` services, the
  `auth/as` command, `secstore`). None of those is a file-serving path,
  so the negative stands for the question as asked.
