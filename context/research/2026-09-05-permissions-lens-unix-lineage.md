# Permissions lens L1: the Unix lineage

- **Status**: research memo, Phase 1 lens L1 of the principals and
  permissions programme (`2026-09-05-principals-and-permissions-research-plan.md`).
  Commits us to nothing. Feeds the Phase 3 synthesis, ADR 021, spec 058,
  spec 070.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: What does fifty years of Unix permission design (V7
  through today's FreeBSD and Linux) say about the plan's hypothesis:
  a subject, a distinct actor, and authority that only narrows? And
  does anything in the lineage compute a meet (a greatest lower bound)
  of several principals' rights, which the multiplayer rule (plan §1.1)
  needs?
- **Method**: line-level read of the V7 kernel (`usr/sys/sys/`,
  `usr/sys/h/`); two parallel source sweeps of FreeBSD (`kern_prot.c`,
  `kern_priv.c`, `vfs_subr.c`, `subr_acl_nfs4.c`, `subr_acl_posix1e.c`,
  `vfs_lookup.c`, `vfs_syscalls.c`, `vfs_vnops.c`, `kern_jail.c`,
  `sys_capability.c`, `kern_descrip.c`, `ufs_lookup.c`) and Linux
  (`security/landlock/`, `security/commoncap.c`, `security/security.c`,
  `fs/namei.c`, `fs/open.c`, `fs/namespace.c`, `fs/posix_acl.c`,
  `kernel/sys.c`, `kernel/cred.c`, `kernel/user_namespace.c`,
  `kernel/groups.c`); pjdfstest read as a conformance-suite model; four
  external documents read on 2026-09-05. Every citation is
  `repo:path:line` against the commit in the Sources line. Cites and
  describes only; no code copied.
- **License**: `unix-history-repo`: Caldera license for V7 (root
  `LICENSE`, `Caldera-license.pdf`; study only). `freebsd-src`: sparse
  checkout with no root `COPYRIGHT` file; the studied files carry
  `SPDX-License-Identifier: BSD-3-Clause` (`sys/kern/kern_prot.c:2`).
  `linux`: GPL-2.0 with the Linux syscall note (`COPYING`). `pjdfstest`:
  BSD-2-Clause (`COPYING`). All four are study-only under the standing
  no-copy rule.
- **Sources line**: `unix-history-repo` @ `e005199` on branch
  `Research-V7-Snapshot-Development`, **dirty** (`usr/doc/yacc/ssA`,
  `ssB` modified), **not refreshed**; only the V7 branch is present in
  the clone, so the BSD-release trace for saved uid and supplementary
  groups comes from the Setuid Demystified paper (§4), not from git.
  `freebsd-src` @ `2e33355ee2bf` (origin/main, refreshed 2026-09-05);
  sparse checkout holds `share/` and `sys/` only, and `sys/security/`
  (the MAC framework) is absent. `linux` @ `faeab1661`, **dirty** (13
  files under `include/uapi/linux/netfilter/`), **not refreshed**, no
  history beyond HEAD. `pjdfstest` @ `85a8aea` (refreshed 2026-08-07).
  Papers: Chen, Wagner, Dean, *Setuid Demystified*, USENIX Security
  2002, read via <https://css.csail.mit.edu/6.858/2012/readings/setuid.pdf>
  (2026-09-05). POSIX `access()` rationale,
  <https://pubs.opengroup.org/onlinepubs/9699919799/functions/access.html>
  (2026-09-05). Watson, Anderson, Laurie, Kennaway, *Capsicum: practical
  capabilities for UNIX*, USENIX Security 2010, read via
  <https://www.cl.cam.ac.uk/research/security/capsicum/papers/2010usenix-security-capsicum-website.pdf>
  (2026-09-05). Landlock kernel docs,
  <https://docs.kernel.org/userspace-api/landlock.html> (2026-09-05).
  LWN, *Landlock (finally) sets sail*, 2021-06-17,
  <https://lwn.net/Articles/859908/> (2026-09-05).

---

## Bottom line

The lineage supports two of the hypothesis's three parts and quietly
undercuts the third. **Enforcement at the object, per call, in one
chokepoint** is the whole design (`namei`, `vaccess`,
`inode_permission`, then LSM and MAC hooks with a veto each).
**Narrowing-only authority** is the lesson the lineage learned late and
then applied everywhere: Capsicum rights only shrink, Landlock layers
only stack, the capability bounding set only drops, jail flags are
masked by the parent, `no_new_privs` is set-only. But the **actor and
subject split is not what the plan says it is**. The real uid is the
invoker and the effective uid is the authority in force, and the kernel
decides on the effective uid alone. The split was built so a program
could run *above* its invoker (setuid), and the saved uid was added so
it could *regain* that authority after dropping it. The precedent for
the split is a precedent for widening, and the bugs in Setuid
Demystified are the bugs of that widening. For the multiplayer rule:
the lineage computes a meet in five places, but every one is a single
principal narrowing itself over time. Nowhere does Unix act at the meet
of several people's rights. Its only multi-principal structures, groups
and the sticky bit, are joins. Ownership by a set, audit of a set, and
mid-session change of a set have no precedent here.

## Q1. Subject, actor, and "on behalf of"

**Verdict: qualified.** The two-uid split exists, but the roles are not
subject and actor, and the kernel checks only one of them.

V7 holds four ids per process: effective uid and gid, real uid and gid
(`unix-history-repo:usr/sys/h/user.h:28-31`). Every access decision
reads the effective uid: `access()` grants root by `u_uid == 0`, then
picks the owner, group, or other bits by comparing `u_uid` and `u_gid`
to the inode (`unix-history-repo:usr/sys/sys/fio.c:162-167`). New files
are owned by the effective uid (`unix-history-repo:usr/sys/sys/iget.c:294-295`).
The real uid appears in exactly two places: `setuid` may set the ids to
the real uid without privilege (`unix-history-repo:usr/sys/sys/sys4.c:73-77`),
and the `access` syscall swaps the real ids in for the duration of one
check (`unix-history-repo:usr/sys/sys/sys2.c:300-315`). Exec of a setuid
binary replaces the effective uid with the file owner
(`unix-history-repo:usr/sys/sys/sys1.c:254-260`). So the real uid is
"who invoked this", the effective uid is "whose authority is in force",
and only the second one governs.

The paper states the design intent plainly: the real uid "identifies
the owner of the process", the effective uid "is used in most access
control decisions", and the saved uid "stores a previous user ID so
that it can be restored later" (Setuid Demystified §3). Early Unix
"could not temporarily drop the root privilege ... and restore it
later", which is the problem System V's saved uid solved (§4.1, §4.2).

Modern kernels keep the shape. FreeBSD's `struct ucred` carries
effective, real, and saved uid and gid, plus the group list, the
prison, and the MAC label (`freebsd-src:sys/sys/ucred.h:80-95`). Linux
adds an fsuid used for filesystem checks (`linux:fs/namei.c:619-620`).
The real ids surface again for visibility: FreeBSD's
`cr_canseeotheruids` compares *real* uids and returns `ESRCH` when they
differ (`freebsd-src:sys/kern/kern_prot.c:1884-1891`).

What is missing is the plan's meaning of the pair. Nothing in the
lineage records "actor X acted for subject Y". The pair records "this
process was started by X and currently wields Y's authority", and Y is
usually *more* powerful than X. The hypothesis's actor is at most the
subject; Unix's effective uid is at least the real uid.

## Q2. Attenuation: how authority narrows, and whether it widens

**Verdict: supports for the capability-era mechanisms; the uid lineage
contradicts.** The lineage contains both a widening design and, later,
four narrowing-only designs built to contain it.

The widening design is setuid plus the saved uid. FreeBSD deliberately
does not define `_POSIX_SAVED_IDS`, because that would let
`setuid(getuid())` leave the saved uid alone, which is "dangerous for
traditional BSD programs" (`freebsd-src:sys/kern/kern_prot.c:870-879`);
its `setuid` sets all three ids in every permitted case
(`freebsd-src:sys/kern/kern_prot.c:950-968`), and `seteuid` may move the
effective uid to the real or saved uid without privilege
(`freebsd-src:sys/kern/kern_prot.c:1041-1051`), which is regain by
design. Linux's non-root `setuid` sets only the effective and fs uids
(`linux:kernel/sys.c:669-680`), so the saved uid survives and privilege
can be restored. That is the mechanism behind both sendmail incidents
(Q9).

The narrowing-only designs:

- **Capsicum.** `cap_enter` sets a cred flag with no clearing path
  (`freebsd-src:sys/kern/sys_capability.c:101-118`); the paper: "once
  set, the flag is inherited by all descendent processes, and cannot be
  cleared" (§2.1). `cap_rights_limit` refuses any new rights mask that
  is not a subset of the current one, returning `ENOTCAPABLE`
  (`freebsd-src:sys/kern/sys_capability.c:230-261`); the same subset
  rule governs ioctl and fcntl lists
  (`freebsd-src:sys/kern/sys_capability.c:396-412`, `:599-602`). A file
  opened relative to a limited directory fd inherits the *directory's*
  rights, not full rights (`freebsd-src:sys/kern/kern_descrip.c:3375-3416`,
  `freebsd-src:sys/kern/vfs_syscalls.c:1321-1331`). `dup` and `fork`
  copy the caps (`freebsd-src:sys/kern/kern_descrip.c:1144-1155`, `:2602`).
- **Landlock.** Each `landlock_restrict_self` merges one more layer onto
  the domain; the cap is 16 layers and `E2BIG` after that
  (`linux:security/landlock/ruleset.c:539-575`,
  `linux:security/landlock/limits.h:19`). There are three syscalls
  (create, add rule, restrict self) and none detaches a domain
  (`linux:security/landlock/syscalls.c:203`, `:426`, `:487`). The docs:
  "there is no way to remove its security policy; only adding more
  restrictions is allowed" (Landlock docs). The domain rides in the
  cred and is copied on every `prepare_creds`
  (`linux:security/landlock/cred.c:19-33`).
- **Capability bounding set and `no_new_privs`.** `PR_CAPBSET_DROP` has
  no raise counterpart (`linux:security/commoncap.c:1267-1282`); on
  exec the permitted set is intersected with the old one
  (`linux:security/commoncap.c:959-960`); `PR_SET_NO_NEW_PRIVS` accepts
  only `1` (`linux:kernel/sys.c:2706-2710`) and forces a setuid exec to
  keep the real ids (`linux:security/commoncap.c:946-957`).
- **Jails.** A child jail starts with `JAIL_DEFAULT_ALLOW & parent`
  (`freebsd-src:sys/kern/kern_jail.c:1841`), enabling a flag the parent
  lacks is `EPERM` (`freebsd-src:sys/kern/kern_jail.c:2027-2031`), and
  clearing a flag on a parent clears it in every descendant
  (`freebsd-src:sys/kern/kern_jail.c:3997-4010`).

Where the narrowing sits: in the process credential (Capsicum flag,
Landlock domain, bounding set, prison pointer), never in a token that
crosses a wire. Linux creds are copy-on-write and immutable once
committed (`linux:kernel/cred.c:166-192`, `:358-359`;
`linux:Documentation/security/credentials.rst:255-256`), which is the
property that makes "cannot widen" checkable.

## Q3. Where enforcement lives

**Verdict: supports.** One chokepoint per object, evaluated per call,
with stacked veto hooks.

V7 checks every directory component for execute permission inside
`namei` (`unix-history-repo:usr/sys/sys/nami.c:89-93`), checks read or
write at `open` (`unix-history-repo:usr/sys/sys/sys2.c:131-138`), and
checks write on the parent directory when creating
(`unix-history-repo:usr/sys/sys/nami.c:111-119`). Nothing is checked at
the syscall boundary; everything is checked at the inode.

FreeBSD's `vaccess` is the single DAC evaluator
(`freebsd-src:sys/kern/vfs_subr.c:5660-5765`), called through
`VOP_ACCESS` from open (`freebsd-src:sys/kern/vfs_vnops.c:480-484`),
lookup (`freebsd-src:sys/kern/vfs_subr.c:7354-7362`), and delete
(`freebsd-src:sys/ufs/ufs/ufs_lookup.c:112`). Privilege is a separate
pipeline: `priv_check_cred` runs MAC deny, then the jail allow-list,
then the uid-0 rule, then MAC grant, then default deny
(`freebsd-src:sys/kern/kern_priv.c:148-267`). MAC hooks precede the
DAC check at open, write, access, and unlink
(`freebsd-src:sys/kern/vfs_vnops.c:474`, `:1323-1325`;
`freebsd-src:sys/kern/vfs_syscalls.c:2086-2089`, `:2196-2199`). The
Capsicum paper makes the argument explicit: constraints are applied "at
the point of implementation of kernel services, rather than by simply
filtering system calls", so that blocking the global namespace "can be
implemented in one place, `namei`" (§3.1).

Linux: `inode_permission` runs the read-only-superblock check, then
DAC, then `security_inode_permission` (`linux:fs/namei.c:623-656`). The
LSM dispatcher calls every registered module in order and the first
non-default return wins, so each module holds a veto and none can grant
(`linux:security/security.c:479-496`). The hook list is the
enforcement surface: `inode_permission`, `file_open`, `path_unlink`,
`file_permission`, `cred_prepare`, `capable`
(`linux:include/linux/lsm_hook_defs.h:44`, `:91`, `:142`, `:190`,
`:215`, `:223`).

Nothing here is compiled into a query; the kernel has no queries. The
transferable part is the shape: one evaluator per object, called by
every verb, with additive-deny hooks around it.

## Q4. The unit of protection

**Verdict: qualified.** The base unit is the object (inode) with its own
mode or ACL; path-shaped and handle-shaped units are layered on top and
depend on the walk.

- **Object.** Mode bits and ACLs live on the inode. Exactly one class
  is consulted: if you are the owner, the group and other bits are
  never read (`freebsd-src:sys/kern/vfs_subr.c:5679-5693`;
  `linux:fs/namei.c:461-466`; V7 `fio.c:164-167`). The POSIX.1e ACL
  keeps that rule for the owner entry
  (`freebsd-src:sys/kern/subr_acl_posix1e.c:119-142`).
- **Path prefix, by walking.** A directory's execute bit gates every
  name beneath it because the walk checks each component
  (`linux:fs/namei.c:1951-1957`, `:685`;
  `freebsd-src:sys/kern/vfs_cache.c:3192-3212`). Landlock makes the
  prefix explicit: the only rule type is `PATH_BENEATH`
  (`linux:include/uapi/linux/landlock.h:152`, `:165`), and the check
  walks from the file up to the real root, collecting rules, and denies
  at the root if any layer is still unsatisfied
  (`linux:security/landlock/fs.c:821-889`).
- **Handle.** A Capsicum capability is a file descriptor with a rights
  mask; every fd fetch checks the needed rights
  (`freebsd-src:sys/kern/kern_descrip.c:3087-3091`, `:3656-3659`). In
  capability mode absolute paths, `..`, and `AT_FDCWD` are refused so
  that a directory handle delegates exactly its subtree
  (`freebsd-src:sys/kern/vfs_lookup.c:312-323`, `:370-373`,
  `:1264-1285`; paper §2.2). `O_RESOLVE_BENEATH` gives the same
  containment outside capability mode
  (`freebsd-src:sys/kern/vfs_lookup.c:414-423`, `:276-300`); Linux's
  `RESOLVE_BENEATH` refuses `/` and `..` at the root with `EXDEV`
  (`linux:fs/namei.c:1127-1130`, `:2217-2219`).
- **Label.** FreeBSD creds carry a MAC label
  (`freebsd-src:sys/sys/ucred.h:94`), but the MAC modules are outside
  this sparse checkout, so the label unit is noted, not studied.

Relevance for ADR 021's ids-vs-paths fork: the lineage protects ids and
derives prefix semantics from the walk. When the walk is not available
(a flat query), Landlock's answer is to walk anyway, up the hierarchy,
per check.

## Q5. Hide versus deny, and traversal

**Verdict: qualified.** The filesystem denies; it never lies about
existence. Hiding is real but lives in the process and mount
namespaces, and in one emergent directory rule.

The directory rule: read on a directory permits listing; execute
permits resolving a known name. With `x` and no `r`, a caller who
already knows a name can open it but cannot enumerate; with `r` and no
`x`, the caller sees names but every access beneath fails with
`EACCES`. The kernel does not turn a denied traversal into `ENOENT`;
pjdfstest pins this as "returns EACCES when search permission is
denied for a component of the path prefix" for open, chmod, and unlink
(`pjdfstest:tests/open/05.t:4`, `pjdfstest:tests/chmod/05.t:4`,
`pjdfstest:tests/unlink/05.t:4`). So "known-name access without
listing" exists, but "invisible" in the Mirage sense (answer as if it
were not there) does not, for files.

Hiding proper appears for processes and mounts. With
`security.bsd.see_other_uids=0`, a process of another real uid is
reported as `ESRCH`, "no such process"
(`freebsd-src:sys/kern/kern_prot.c:1870-1891`); the same for other
gids and other jails (`:1914-1931`, `:1956-1963`). `cr_cansee` chains
prison, MAC, and these BSD rules (`:2028-2040`). Jails hide mounts:
`prison_canseemount` shows only mounts under the jail path when
`enforce_statfs=1` (`freebsd-src:sys/kern/kern_jail.c:4296-4328`).

Two refinements worth taking. NFSv4's `VEXPLICIT_DENY` distinguishes
"a deny ACE was hit" from "nothing allowed it"
(`freebsd-src:sys/kern/subr_acl_nfs4.c:247-248`), and the plain mode
path zeroes that request because modes have no deny rules
(`freebsd-src:sys/kern/vfs_subr.c:6941-6944`). Capsicum returns a
distinct errno, `ENOTCAPABLE`, and traces the failing right, so a
sandbox failure is never confused with a permission failure
(`freebsd-src:sys/kern/sys_capability.c:157-168`; paper §3.1). Landlock
chose the opposite, plain `EACCES` (`linux:security/landlock/fs.c:642`,
`:970`).

## Q6. Groups, roles, tenants

**Verdict: contradicts on groups (they widen); supports on tenants
(they nest and narrow).**

Groups are resolved at login and carried in the cred. V7 had one group
per process (`unix-history-repo:usr/sys/h/user.h:29-31`); supplementary
groups arrived with 4.2BSD (paper §4.3 places the BSD changes there;
the git trace was not possible from this clone). FreeBSD stores a
sorted array, capped by `kern.ngroups` with a floor of `NGROUPS_MAX`
1023 (`freebsd-src:sys/sys/syslimits.h:56`,
`freebsd-src:sys/kern/subr_param.c:245-253`); Linux caps at 65536
(`linux:include/uapi/linux/limits.h:7`). Membership is a binary search
and **any hit grants**: `groupmember` returns true on the effective gid
or any supplementary match
(`freebsd-src:sys/kern/kern_prot.c:1792-1818`); `in_group_p` the same
(`linux:kernel/groups.c:91-109`, `:227-235`). POSIX ACLs go further:
among several matching group entries, any one that grants all the
requested bits suffices (`linux:fs/posix_acl.c:399-413`;
`freebsd-src:sys/kern/subr_acl_posix1e.c:221-269`). That is a union.
Each group a subject belongs to can only add rights.

One place shows groups doing the opposite job, and it is the evidence
that a union model cannot express a deny. A mode like `rwx---rwx`
denies the *group* while allowing everyone else, so dropping a group
widens access. Linux therefore lets an unprivileged user map their own
gid into a new user namespace only after `setgroups` has been
permanently denied there (`linux:kernel/user_namespace.c:1181-1195`,
`:1266-1278`, `:1292-1302`). The invariant, in the source: mappings
must not "allow anything that wouldn't be allowed without the
establishment of unprivileged mappings" (`:1181-1182`).

Tenants are the nesting structures. A FreeBSD prison has an id, a
parent, children, a root vnode, a path, and an allow mask
(`freebsd-src:sys/sys/jail.h:182-216`); `prison_check` lets a cred see
only its own prison and descendants (`freebsd-src:sys/kern/kern_jail.c:4124-4129`,
`:4160-4167`); root inside a jail keeps only an allow-listed set of
privileges and everything else is `EPERM`
(`freebsd-src:sys/kern/kern_jail.c:4384-4401`, `:4635-4640`). Linux user
namespaces give the creator a full capability set that is "useless for
doing anything" outside, because capabilities bind to the namespace
(`linux:kernel/user_namespace.c:43-54`); a capability held in a parent
namespace applies to all children, never the reverse
(`linux:security/commoncap.c:79-103`); nesting stops at 33 levels
(`linux:kernel/user_namespace.c:91-93`); ids are translated on the way
in and out and unmapped ids collapse to an overflow id
(`linux:kernel/user_namespace.c:422-444`, `:466-472`).

Resolution time: groups at login, tenants at process creation, both
frozen into the cred. Nothing is re-resolved per query.

## Q7. Creation defaults, ownership, move and copy

**Verdict: supports.** This is the richest precedent in the lens.

- **umask.** V7 applies `~u_cmask` at node creation
  (`unix-history-repo:usr/sys/sys/iget.c:292`;
  `unix-history-repo:usr/sys/sys/sys4.c:386-397`). Linux applies the
  umask **only if the parent directory has no default ACL**; with one,
  the default ACL is cloned and the mode is masked by it instead
  (`linux:fs/posix_acl.c:646-659`, `:445-451`). The container's default
  wins over the creator's default.
- **NFSv4 inheritance.** Entries carry `FILE_INHERIT`,
  `DIRECTORY_INHERIT`, `NO_PROPAGATE`, `INHERIT_ONLY`; the inherited
  copy is stamped `INHERITED`, and new owner@ and everyone@ entries are
  appended from the creation mode
  (`freebsd-src:sys/kern/subr_acl_nfs4.c:1007-1086`, `:1166-1181`).
  chmod rewrites the ACL to a trivial one under the current semantics,
  and setting an ACL recomputes the mode (`:705-713`, `:717-760`).
- **Owner.** The creator's effective (fs) uid owns the new object
  (`unix-history-repo:usr/sys/sys/iget.c:294-295`). Ownership transfer
  is root-only in V7 (`unix-history-repo:usr/sys/sys/sys4.c:255-266`)
  and a named privilege on FreeBSD
  (`freebsd-src:sys/ufs/ufs/ufs_vnops.c:955-958`); pjdfstest pins that
  setuid and setgid bits are cleared when a non-owner chowns
  (`pjdfstest:tests/granular/06.t:4`).
- **Owner-only operations.** `chmod` requires owner or root
  (`unix-history-repo:usr/sys/sys/fio.c:185-198`); FreeBSD folds this
  into `VADMIN`, which the owner holds unconditionally
  (`freebsd-src:sys/kern/vfs_subr.c:5681`) and which non-owners cannot
  get from an ACL at all
  (`freebsd-src:sys/kern/subr_acl_nfs4.c:224-227`). The owner also
  always keeps read and write of the ACL and attributes, so they cannot
  lock themselves out (`:208-210`).
- **Delete authority lives on the container.** Unlink needs write and
  execute on the directory, not on the file
  (`linux:fs/namei.c:3699`; `pjdfstest:tests/unlink/06.t:4`). The
  sticky bit adds owner-of-file or owner-of-directory or `CAP_FOWNER`
  (`linux:fs/namei.c:3647-3670`;
  `freebsd-src:sys/ufs/ufs/ufs_lookup.c:116-125`); pjdfstest enumerates
  270 sticky cases (`pjdfstest:tests/unlink/11.t:4-45`). NFSv4 splits
  this into `DELETE` on the child and `DELETE_CHILD` on the parent
  (`pjdfstest:tests/granular/03.t:4`, `05.t:4`).
- **Read-only mounts.** V7 refuses write access with `EROFS` before any
  other check (`unix-history-repo:usr/sys/sys/fio.c:150-153`). FreeBSD
  returns `EROFS` in `ufs_accessx` for any modify bit on a read-only
  mount, before DAC (`freebsd-src:sys/ufs/ufs/ufs_vnops.c:386-397`),
  and in lookup for delete and rename
  (`freebsd-src:sys/kern/vfs_cache.c:3206-3208`); writes take
  `vn_start_write` before `VOP_WRITE`
  (`freebsd-src:sys/kern/vfs_vnops.c:1307-1327`). Linux's
  `sb_permission` is the first thing `inode_permission` does
  (`linux:fs/namei.c:604-606`, `:628`). The refusal is whole, before
  the first byte.

## Q8. Audit

**Verdict: no precedent** for versioned, attributed audit; thin
signals only.

V7's `suser()` sets an accounting flag when root is used
(`unix-history-repo:usr/sys/sys/fio.c:207-209`); that is the whole
audit story in 1979. Modern kernels add tracing of capability failures
(`freebsd-src:sys/kern/sys_capability.c:157-168`), an audit record for
refused sticky-directory creates (`linux:fs/namei.c:1427-1428`), and
Landlock's per-domain log flags (ABI v7; Landlock docs). Nothing
records "on behalf of", and nothing ties an action to a version. The
real uid survives across setuid as the only durable "who started
this", and even that is overwritten by a root `setuid`.

## Q9. Failure modes on record

**Verdict: supports.** Every row below belongs in the threat table.

1. **The overloaded `setuid`.** sendmail 8.10.1 called
   `setuid(getuid())` to drop root; a pre-2.2.16 Linux bug let an
   attacker clear the SETUID capability first, so the call changed only
   the effective uid, returned success, and left root in the saved uid
   for `setreuid(-1, 0)` to restore (paper §7.1). Root cause: one call,
   two semantics, one return code. Fix: `setresuid`, then verify with
   `getresuid`, then verify that restoring *fails* (§8.1.3, Fig. 12).
2. **Order of drops.** sendmail 8.12.0 dropped the uid before the gid;
   without root the `setgid` touched only the effective gid, leaving
   the privileged group in the saved gid (§7.2). Rule: drop the wider
   authority last, and verify each.
3. **Wrong documentation.** The FreeBSD `setreuid` and Red Hat `setgid`
   man pages described semantics the kernel did not implement (§6.4.1).
4. **`access()` TOCTOU.** POSIX: "acting upon the information always
   leads to a time-of-check-to-time-of-use race condition", and the
   application "should instead attempt the action itself and handle
   the [EACCES] error" (POSIX rationale). Linux says the same of its
   own `EROFS` report in `access`: "we accept that this access is
   inherently racy" (`linux:fs/open.c:509-519`;
   `linux:fs/namespace.c:349-358`).
5. **Symlink and hardlink races in shared directories.** Linux ignores
   `CAP_DAC_OVERRIDE` when following a symlink in a sticky
   world-writable directory, "to protect privileged processes from
   failing races against path names that may change out from under
   them" (`linux:fs/namei.c:1258-1290`); the same family covers
   hardlinks and `O_CREAT` on existing FIFOs
   (`:1337-1372`, `:1383-1428`).
6. **Confused deputy by ambient authority.** The Capsicum paper's
   framing: a browser "acts with the full power of the user" (§1), and
   `chroot` failed because two colluding sandboxes can race renames so
   a `..` check always passes (§2.2). The fix is to deny the global
   namespace rather than filter it.
7. **Groups as denials.** Dropping a group can widen access; see Q6.
8. **Root as an exec bypass.** Root cannot execute a file with no
   execute bit, on purpose (`freebsd-src:sys/kern/vfs_subr.c:5738-5746`;
   `linux:fs/namei.c:549-555`; POSIX `access` rationale on `X_OK`).
9. **Best-effort sandboxing.** Landlock rights vary by ABI version and
   cannot cover `stat`, `chmod`, `chown`, `access`, and others
   (`linux:include/uapi/linux/landlock.h:334-338`); the docs tell
   callers to probe the version and enforce what exists. A sandbox that
   silently covers less than it claims is a leak.

## Q10. Reversibility and permission together

**Verdict: no precedent.** Unix has no undo, so the question of who may
revert does not arise. Three adjacent facts are still useful. Delete
authority belongs to the container, not the object (Q7), so a caller
can remove a file they cannot read; if vfs keeps that shape, "revert my
delete" is a right on the parent. Immutable and append-only flags are a
no-destroy invariant enforced ahead of every permission check
(`freebsd-src:sys/ufs/ufs/ufs_vnops.c:419-424`, `:1054-1056`;
`linux:fs/namei.c:3705`), and only privilege clears them; that is the
closest thing to "delete never destroys". And the NFSv4 owner keeps
`WRITE_ACL` no matter what the ACL says, "to prevent ... undoing the
change" from locking the owner out
(`freebsd-src:sys/kern/subr_acl_nfs4.c:208-210`); a revert rule needs
the same floor.

## Q11. Scale and portability

**Verdict: qualified.** Nothing here touches SQL caps, but the lineage
answers the shape question S1 will measure.

The subject's group set is bounded (1023 or 65536), sorted once at
login, and searched by binary search per check
(`freebsd-src:sys/kern/kern_prot.c:1792-1804`;
`linux:kernel/groups.c:84-109`). That is exactly "a pre-resolved set
shipped as a bounded literal", the third shape in S1. ACL evaluation is
a linear walk over a small per-object list
(`freebsd-src:sys/kern/subr_acl_nfs4.c:120-166`). Landlock caps layers
at 16 and walks the hierarchy per check; the rule count per layer is
unbounded but the walk depth is the path depth. Nothing is evaluated
across objects; every check is O(path depth + ACL length + log groups).
The portability lesson is the ABI-version probe: declare what a mechanism
handles and refuse to pretend (`linux:Documentation/userspace-api/landlock.rst:430-442`).

## Q12. Take, adapt, reject

See the table below.

## Q13. Many subjects at once: is there a conjunctive model?

**Verdict: qualified, leaning no precedent.** The lineage computes a
meet in five places, and every one of them is one principal narrowing
itself. No mechanism acts at the meet of several principals.

The five meets:

1. **Landlock layers.** Within a layer, rules union: "at least one of
   its rules encountered on the path grants the access". Across
   layers, intersection: a thread "can only access a file path if all
   its enforced policy layers grant the access"
   (`linux:Documentation/userspace-api/landlock.rst:292-296`;
   `linux:security/landlock/ruleset.c:639-657`). This is the exact
   algebra of §1.1 (union inside one principal's grants, intersection
   across principals), but every layer is added by the same thread on
   its own behalf (`linux:security/landlock/syscalls.c:527-536`).
2. **Capsicum rights.** New rights must be contained in old rights;
   the merge and remove helpers are OR and AND-NOT over the mask
   (`freebsd-src:sys/kern/subr_capability.c:320-388`). The paper's
   `..` warning is a set warning in disguise: two capabilities held
   together can be more than either alone (§2.2).
3. **Capability bounding set.** `cap_intersect` on exec
   (`linux:security/commoncap.c:959-960`).
4. **Jail flags.** Child allow mask is ANDed with the parent
   (`freebsd-src:sys/kern/kern_jail.c:1841`).
5. **Veto chains.** NFSv4 walks ACEs in order and a deny on any
   still-needed bit ends the walk, while all bits must be allowed for
   success (`freebsd-src:sys/kern/subr_acl_nfs4.c:151-166`); every LSM
   module and every MAC policy can deny and none can grant
   (`linux:security/security.c:479-496`;
   `freebsd-src:sys/kern/kern_priv.c:99-108`).

Against these, the multi-principal structures are joins: any group
grants (Q6); the sticky bit lets the file owner *or* the directory owner
delete (`linux:fs/namei.c:3647-3656`); a POSIX ACL takes the best
matching group entry (`freebsd-src:sys/kern/subr_acl_posix1e.c:221-226`).

The sub-questions:

- **Who owns what a set creates.** No precedent. An inode has one uid
  and one gid; the group is the only set-shaped owner and it widens.
- **How the audit records a set.** No precedent (Q8).
- **Mid-session change.** The nearest analogue is Landlock: a new
  layer applies immediately to the calling thread and all its future
  descendants, and since ABI v8 `TSYNC` applies it to sibling threads
  too (Landlock docs, ABI list). So "a principal joining narrows the
  session at once" has a mechanical precedent, but only for narrowing;
  a principal *leaving* cannot widen, because layers never come off.
- **Hide for a set.** No filesystem precedent; the process-visibility
  rule is per-viewer, not per-set.
- **Composition with the actor's profile and admin.** Landlock's
  ptrace rule is the one composition law: the tracer must hold a
  superset of the tracee's rights, checked as "is the tracee's domain a
  sub-domain of mine"
  (`linux:security/landlock/task.c:33-73`;
  `linux:Documentation/userspace-api/landlock.rst:346-348`). Admin in
  this lineage is a principal that goes through the same pipeline and
  can be vetoed before its uid is consulted (Q3).

## Take, adapt, reject for vfs

| Idea | Verdict | One line |
|---|---|---|
| Enforcement at the object, per verb, one evaluator | take | `vaccess` and `inode_permission` are the shape; vfs's funnel is the analogue. |
| Additive-deny hooks around the evaluator (LSM, MAC, priv pipeline) | take | Profiles, session narrowing, and the subject set are each a veto layer; none may grant. |
| Narrowing is irreversible and rides in the credential, not a token | take | Landlock domain, Capsicum flag, bounding set: the session object should be copy-on-write and never widen. |
| Distinct error for "the sandbox refused" versus "permission refused" | take | `ENOTCAPABLE` versus `EACCES`; vfs should classify profile refusals apart from grant refusals. |
| Directory execute as traverse; `EACCES` on a denied component, never `ENOENT` | adapt | Keep the split; add the explicit `invisible` rung the filesystem lacks, with Mirage's leak rules. |
| Exactly one class consulted (owner short-circuit) | adapt | Owner-first evaluation is cheap and predictable; vfs owner should be a floor, not a class. |
| Default from the container beats default from the creator | take | Default ACL replaces umask; NFSv4 inherit flags; vfs creation defaults come from the parent grant. |
| Delete authority on the parent, sticky owner-only delete | adapt | Revert and delete rights on the container, with an owner floor. |
| `EROFS` whole, before the first byte | take | Read-only mounts refuse before any partial write; batches must fail whole at the gate. |
| Owner keeps `WRITE_ACL` and attributes no matter the ACL | take | A principal can never be locked out of its own grants by a narrowing. |
| Root as a principal through the same pipeline, with `suser_enabled` | take | Admin is one principal; jail and MAC can veto it; never a bypass. |
| Groups resolved at login into a bounded sorted set | adapt | Resolve the subject's group closure once per session and ship it as a bounded literal (S1 shape 3). |
| Supplementary groups as union | reject | The multiplayer rule is a meet; a group is a widening device and must not be reused for the subject set. |
| `access()` check-then-act | reject | No pre-check verb; `explain` must be labelled advisory, and every verb re-checks at execution. |
| Setuid, saved uid, regain of privilege | reject | The split exists to widen; vfs never regains a narrowed right within a session. |
| Return-code-only verification of a privilege drop | reject | Verify the resulting state, and verify that widening fails (Setuid Demystified Fig. 12). |
| Best-effort sandbox with ABI probing | adapt | Declare which verbs a profile governs; refuse to serve a verb the profile cannot govern rather than serve it unguarded. |
| pjdfstest's shape: one file per man-page clause, `expect <errno> -u uid -g gid <op>` | take | vfs's permission suite should enumerate (principal, object state, verb) triples the same way, one result kind per clause. |

## Limits

- The `freebsd-src` clone is sparse. `sys/security/` is absent, so MAC
  label dominance and the `MAC_POLICY_CHECK` chaining are cited only
  through their kernel-side callers. Adding `sys/security/` to the
  sparse set would close that.
- `unix-history-repo` holds only the V7 branch locally. The arrival of
  saved uids and supplementary groups in 4.2BSD and 4.4BSD is taken
  from Setuid Demystified §4, not from a diff of the releases.
- `linux` is dirty, unrefreshed, and has no commit history in the
  clone. The user-namespace `setgroups` rationale is cited from the
  code that enforces it, not from the commit message that explains it.
- Landlock's LWN article was read at its 2021 version; the ABI list
  comes from the current kernel docs.
- pjdfstest was studied for shape only. Its granular NFSv4 tests run
  only on FreeBSD ZFS (`pjdfstest:tests/granular/00.t:9`), so their
  assertions were not executed here.
- No experiments were run. Every claim is a reading of source or a
  document; the measured questions (S1, S2) stay with Phase 2.
