# Naming a write-path routing decision — precedent in the filesystem canon

**Date:** 2026-07-22. **Question:** `StagedEntry.created: bool` reads in
English as "already created" but means "this batch must INSERT a row."
Does the filesystem canon name this kind of decision, and how?

Read-only survey of `~/Git/Repos/{freebsd-src,plan9,linux}`. Every
citation below was read in the tree, not recalled.

## What the canon does

**1. BSD names the operation as an enum, not a flag.**
`freebsd-src/sys/sys/namei.h:43`

```c
enum nameiop { LOOKUP, CREATE, DELETE, RENAME };
```

Stored as `cn_nameiop` in `struct componentname` (`namei.h:51`) and
assigned through the `NDINIT` macro family (`namei.h:262`:
`_ndp->ni_cnd.cn_nameiop = op;`). One shared descent routine, one field
naming which way it will go. The values are **imperative verbs** — the
intent, not an accomplished fact.

**2. Plan 9 does the same thing, with a wider vocabulary.**
`plan9/sys/src/9/port/portdat.h:140-152`

```c
/* Access types in namec & channel flags */
enum {
	Aaccess,   /* as in stat, wstat */
	Abind,     /* for left-hand-side of bind */
	Atodir,    /* as in chdir */
	Aopen,     /* for i/o */
	Amount,    /* to be mounted or mounted upon */
	Acreate,   /* is to be created */
	Aremove,   /* will be removed by caller */
};
```

`namec(char *aname, int amode, int omode, ulong perm)`
(`sys/src/9/port/chan.c:1317`) branches on it — e.g.
`if(amode == Acreate){ ... }` around `chan.c:1428`. Note the comment
tenses: *"is to be created"*, *"will be removed by caller"* — future
intent, stated deliberately. Plan 9 had seven access modes and still
declined to encode any of them as a boolean.

**3. Linux names lifecycle states and documents that they are transient.**
`linux/include/linux/fs.h:643`

> Four bits define the lifetime of an inode. Initially, inodes are
> `I_NEW`, until that flag is cleared. `I_WILL_FREE`, `I_FREEING` and
> `I_CLEAR` are set at various stages of removing an inode.

A mutable state field whose transitions are part of the documented
contract — precedent for a discriminator that legitimately changes
mid-flight, provided the change is spelled out.

**4. Linux gives its sentinel a named predicate — and does not always use it.**
`linux/include/linux/dcache.h:465`

```c
static inline bool d_is_negative(const struct dentry *dentry)
```

A "negative dentry" (name exists, no inode behind it) is a sentinel
encoding, and the kernel provides a name for the test. It is not
disciplined about it: `fs/namei.c` still open-codes the check —
`if (child->d_inode)` at `:3737`, `dentry->d_inode` at `:1550` — in the
lookup/create paths most analogous to ours. The precedent is "a
routing sentinel deserves a name," not "the canon never open-codes one."

## The closest structural precedent points the other way on encoding

The fs citations above are about naming. The nearest *structural*
relative to our staging pass is SQLAlchemy's unit of work, and it
deserves its own hearing because it partly contradicts the enum
argument.

`sqlalchemy/lib/sqlalchemy/orm/persistence.py` routes each staged
object to INSERT or UPDATE in `_organize_states_for_save` (~:225-286)
using **a named predicate over a sentinel**, not an enum:

```python
has_identity = bool(state.key)          # :225
```

More striking: it has a first-class name for exactly our mid-flight
insert→update conversion — a **"row switch"** (`row_switch` at :229,
:270; the log message *"detected row switch for identity %s"* at :260),
carried as a **separate marker alongside** `has_identity` rather than
folded into one state. The version guard is then fetched for updates
and row switches alike (`:272`, gated on `mapper.version_id_col`).

So the most mature staged-write engine in Python: (a) confirms the
conversion is a real, nameable concept rather than an oddity of our
arbitration; (b) uses sentinel-plus-predicate where we are proposing a
one-of; (c) keeps the conversion marker *beside* the routing predicate
instead of collapsing both into a single field.

Postgres supports the other half. ON CONFLICT arbitration lives inside
the INSERT executor node — "Perform a speculative insertion",
`postgres/src/backend/executor/nodeModifyTable.c:1131`, with the
speculative-insertion token taken and released at `:1230`/`:1256`. The
insert statement owns its own upsert conflict; nothing hands off to an
update pass. That is independent support for keeping an upsert-path
clobber in the `"insert"` state.

## The lesson for us

- Name the **routing decision** for the intent, in the tense of intent —
  BSD and Plan 9 agree across two unrelated lineages, and neither uses a
  boolean or a past participle. This is the strong, uncontested part.
- **Enum-vs-sentinel is not settled by precedent.** BSD and Plan 9 use
  enums; SQLAlchemy, the closer structural match, uses a predicate over
  a sentinel plus a second marker. Our choice of a one-of has to be
  argued on our own terms — that our two discriminators admit a
  meaningless fourth combination, and that routing currently reads
  `base_version`, a field that otherwise carries data.
- A discriminator may be **mutated mid-execution** (Linux `I_NEW`,
  SQLAlchemy's row switch), but the transition must be documented where
  it happens.
- A **sentinel carrying routing meaning gets a name** — `d_is_negative`,
  `has_identity`. Ours (`base_version is None`) has none and is
  open-coded at three sites.
- **The pass owns its own conflict** (Postgres speculative insertion):
  an upsert clobber is not a hand-off.

## Limits of the analogy

The fs citations are not structural matches. `nameiop` and `amode` are
*inputs* to a path-lookup routine; our field is a per-entry plan item
inside a batched write. Linux's `i_state` is a bitmask of concurrent
flags, not a one-of. Their weight is on naming discipline and where a
discriminator lives, and should not be stretched into an argument about
the shape of the write pipeline.

SQLAlchemy is the real structural match, and it is evidence *against*
the specific encoding we chose as much as for the concept. Recorded
that way on purpose.

Consumed by spec 078.
