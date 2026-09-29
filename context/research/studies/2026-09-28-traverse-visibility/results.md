# Results: traverse vs list above a usable subtree

Captured 2026-09-28. One non-root user, no sudo. The script chmods its
own directory `P`, so the **owner** bits decide. Owner mode `0100`
(`--x`) stands in for the classic `0711` home directory as seen by
everyone else: search, no list.

Tree: `P/alpha/file.txt` is the file the caller may use (think
`/projects/alpha`). `P/beta` is a sibling the caller should not learn
about.

## Summary table (identical on macOS and Linux)

| Operation | `0700` rwx | `0100` --x (search only) | `0400` r-- (list only) | `0000` |
|---|---|---|---|---|
| list `P` | names | **EACCES** | names (and each entry's kind) | EACCES |
| stat `P` itself | ok | **ok, full metadata** | ok | ok |
| stat `P/beta` (exists) | ok | **ok** | EACCES | EACCES |
| stat `P/nope` (missing) | ENOENT | **ENOENT** | **EACCES** | **EACCES** |
| read `P/alpha/file.txt` | ok | **ok** | EACCES | EACCES |
| list `P/alpha` | ok | **ok** | EACCES | EACCES |
| glob `P/*` | both names | **empty, no error** | both names | empty, no error |
| `mkdir -p P/alpha/new/deep` | ok | **ok** | EACCES | EACCES |
| `mkdir P/gamma` (sibling) | ok | EACCES | EACCES | EACCES |

Read it this way:

- **Search only (`--x`)** is "reach by name". The caller reaches the
  deep file, lists the deep directory, and creates under it. It cannot
  list `P`. But it can stat `P` with full metadata, and it can probe
  any guessed name: an existing sibling answers ok, a missing one
  answers ENOENT.
- **No search (`r--` or `---`)** is "stopped at the door". Everything
  below `P` answers EACCES, **whether or not the name exists**. So a
  missing search right hides existence below that directory.
- **stat of `P` itself** never needs a right on `P`. It needs search on
  `P`'s parent only. So a traverse-only directory leaks its metadata.
- **The leak probe** shows what that metadata carries. A hidden sibling
  appeared, and the search-only caller saw `P`'s link count go up by
  one and its mtime move (and on APFS its size grow). It could then
  confirm the new name by guessing it.

Tool quirks, not kernel differences: macOS `ls` on an `r--` directory
prints the names and then exits 1 (`fts_read: Permission denied`),
because BSD `ls` also tries to enter the directory; `os.listdir` returns
the names cleanly on both systems. Shell and Python `glob` both turn a
denied directory into "no matches" silently.

## macOS, `sh repro.sh`

```text
# platform: Darwin 25.5.0  user: uid=501 (non-root)

## P mode 0700  (rwx: list + search (control))
  ls P            (list the ancestor)      rc=0   alpha beta
  stat P          (the ancestor itself)    rc=0   mode=drwx------ links=4 size=128 mtime=1790644958
  stat P/beta     (existing sibling)       rc=0   mode=drwxr-xr-x links=3 size=96 mtime=1790644958
  stat P/nope     (missing name)           rc=1   stat: P/nope: stat: No such file or directory
  cat P/alpha/file.txt (the grant)         rc=0   alpha data
  ls P/alpha      (list the grant)         rc=0   file.txt
  glob P/*                                 rc=0   P/alpha P/beta 
  glob P/alpha/*                           rc=0   P/alpha/file.txt 
  find P                                   rc=0   P P/beta P/beta/secret.txt P/alpha P/alpha/file.txt
  mkdir -p P/alpha/new/deep                rc=0   
  mkdir P/gamma   (create sibling)         rc=0   

## P mode 0100  (--x: search only (the 0711 home-dir pattern))
  ls P            (list the ancestor)      rc=1   ls: P: Permission denied
  stat P          (the ancestor itself)    rc=0   mode=d--x------ links=4 size=128 mtime=1790644959
  stat P/beta     (existing sibling)       rc=0   mode=drwxr-xr-x links=3 size=96 mtime=1790644958
  stat P/nope     (missing name)           rc=1   stat: P/nope: stat: No such file or directory
  cat P/alpha/file.txt (the grant)         rc=0   alpha data
  ls P/alpha      (list the grant)         rc=0   file.txt
  glob P/*                                 rc=0   P/* 
  glob P/alpha/*                           rc=0   P/alpha/file.txt 
  find P                                   rc=1   P find: P: Permission denied
  mkdir -p P/alpha/new/deep                rc=0   
  mkdir P/gamma   (create sibling)         rc=1   mkdir: P/gamma: Permission denied

## P mode 0400  (r--: list only, no search)
  ls P            (list the ancestor)      rc=1   ls: fts_read: Permission denied alpha beta
  stat P          (the ancestor itself)    rc=0   mode=dr-------- links=4 size=128 mtime=1790644959
  stat P/beta     (existing sibling)       rc=1   stat: P/beta: stat: Permission denied
  stat P/nope     (missing name)           rc=1   stat: P/nope: stat: Permission denied
  cat P/alpha/file.txt (the grant)         rc=1   cat: P/alpha/file.txt: Permission denied
  ls P/alpha      (list the grant)         rc=1   ls: P/alpha: Permission denied
  glob P/*                                 rc=0   P/alpha P/beta 
  glob P/alpha/*                           rc=0   P/alpha/* 
  find P                                   rc=1   find: P: Permission denied
  mkdir -p P/alpha/new/deep                rc=1   mkdir: P/alpha: Permission denied
  mkdir P/gamma   (create sibling)         rc=1   mkdir: P/gamma: Permission denied

## P mode 0000  (---: nothing)
  ls P            (list the ancestor)      rc=1   ls: P: Permission denied
  stat P          (the ancestor itself)    rc=0   mode=d--------- links=4 size=128 mtime=1790644959
  stat P/beta     (existing sibling)       rc=1   stat: P/beta: stat: Permission denied
  stat P/nope     (missing name)           rc=1   stat: P/nope: stat: Permission denied
  cat P/alpha/file.txt (the grant)         rc=1   cat: P/alpha/file.txt: Permission denied
  ls P/alpha      (list the grant)         rc=1   ls: P/alpha: Permission denied
  glob P/*                                 rc=0   P/* 
  glob P/alpha/*                           rc=0   P/alpha/* 
  find P                                   rc=1   find: P: Permission denied
  mkdir -p P/alpha/new/deep                rc=1   mkdir: P/alpha: Permission denied
  mkdir P/gamma   (create sibling)         rc=1   mkdir: P/gamma: Permission denied

## Leak probe: what a search-only (--x) caller learns from stat P
  before hidden sibling: mode=d--x------ links=4 size=128 mtime=1790644959
  after  hidden sibling: mode=d--x------ links=5 size=160 mtime=1790644962
  stat P/gamma (guess the new name)        rc=0   mode=drwxr-xr-x links=2 size=64 mtime=1790644962
```

## Linux (Docker `python:3.13-slim`, linux/arm64, `--user 1000:1000`), `sh repro.sh`

```text
# platform: Linux 7.0.12-linuxkit  user: uid=1000 (non-root)

## P mode 0700  (rwx: list + search (control))
  ls P            (list the ancestor)      rc=0   alpha beta
  stat P          (the ancestor itself)    rc=0   mode=drwx------ links=4 size=4096 mtime=1790644995
  stat P/beta     (existing sibling)       rc=0   mode=drwxr-xr-x links=2 size=4096 mtime=1790644995
  stat P/nope     (missing name)           rc=1   stat: cannot statx 'P/nope': No such file or directory
  cat P/alpha/file.txt (the grant)         rc=0   alpha data
  ls P/alpha      (list the grant)         rc=0   file.txt
  glob P/*                                 rc=0   P/alpha P/beta 
  glob P/alpha/*                           rc=0   P/alpha/file.txt 
  find P                                   rc=0   P P/beta P/beta/secret.txt P/alpha P/alpha/file.txt
  mkdir -p P/alpha/new/deep                rc=0   
  mkdir P/gamma   (create sibling)         rc=0   

## P mode 0100  (--x: search only (the 0711 home-dir pattern))
  ls P            (list the ancestor)      rc=2   ls: cannot open directory 'P': Permission denied
  stat P          (the ancestor itself)    rc=0   mode=d--x------ links=4 size=4096 mtime=1790644995
  stat P/beta     (existing sibling)       rc=0   mode=drwxr-xr-x links=2 size=4096 mtime=1790644995
  stat P/nope     (missing name)           rc=1   stat: cannot statx 'P/nope': No such file or directory
  cat P/alpha/file.txt (the grant)         rc=0   alpha data
  ls P/alpha      (list the grant)         rc=0   file.txt
  glob P/*                                 rc=0   P/* 
  glob P/alpha/*                           rc=0   P/alpha/file.txt 
  find P                                   rc=1   P find: 'P': Permission denied
  mkdir -p P/alpha/new/deep                rc=0   
  mkdir P/gamma   (create sibling)         rc=1   mkdir: cannot create directory 'P/gamma': Permission denied

## P mode 0400  (r--: list only, no search)
  ls P            (list the ancestor)      rc=0   alpha beta
  stat P          (the ancestor itself)    rc=0   mode=dr-------- links=4 size=4096 mtime=1790644995
  stat P/beta     (existing sibling)       rc=1   stat: cannot statx 'P/beta': Permission denied
  stat P/nope     (missing name)           rc=1   stat: cannot statx 'P/nope': Permission denied
  cat P/alpha/file.txt (the grant)         rc=1   cat: P/alpha/file.txt: Permission denied
  ls P/alpha      (list the grant)         rc=2   ls: cannot access 'P/alpha': Permission denied
  glob P/*                                 rc=0   P/alpha P/beta 
  glob P/alpha/*                           rc=0   P/alpha/* 
  find P                                   rc=1   P find: 'P/beta': Permission denied P/beta find: 'P/alpha': Permission denied P/alpha
  mkdir -p P/alpha/new/deep                rc=1   mkdir: cannot create directory 'P': Permission denied
  mkdir P/gamma   (create sibling)         rc=1   mkdir: cannot create directory 'P/gamma': Permission denied

## P mode 0000  (---: nothing)
  ls P            (list the ancestor)      rc=2   ls: cannot open directory 'P': Permission denied
  stat P          (the ancestor itself)    rc=0   mode=d--------- links=4 size=4096 mtime=1790644995
  stat P/beta     (existing sibling)       rc=1   stat: cannot statx 'P/beta': Permission denied
  stat P/nope     (missing name)           rc=1   stat: cannot statx 'P/nope': Permission denied
  cat P/alpha/file.txt (the grant)         rc=1   cat: P/alpha/file.txt: Permission denied
  ls P/alpha      (list the grant)         rc=2   ls: cannot access 'P/alpha': Permission denied
  glob P/*                                 rc=0   P/* 
  glob P/alpha/*                           rc=0   P/alpha/* 
  find P                                   rc=1   P find: 'P': Permission denied
  mkdir -p P/alpha/new/deep                rc=1   mkdir: cannot create directory 'P': Permission denied
  mkdir P/gamma   (create sibling)         rc=1   mkdir: cannot create directory 'P/gamma': Permission denied

## Leak probe: what a search-only (--x) caller learns from stat P
  before hidden sibling: mode=d--x------ links=4 size=4096 mtime=1790644995
  after  hidden sibling: mode=d--x------ links=5 size=4096 mtime=1790644998
  stat P/gamma (guess the new name)        rc=0   mode=drwxr-xr-x links=2 size=4096 mtime=1790644998
```

## `errno_matrix.py` on macOS

The Linux run (`# Linux 7.0.12-linuxkit, Python 3.13.15, uid=1000`, same container) printed byte-identical rows; only the header line differs.

```text
# Darwin 25.5.0, Python 3.13.11, uid=501

## P mode 0o700 (rwx (control))
  listdir(P)                 ok: ['alpha', 'beta']
  scandir(P) kinds           ok: ['alpha:dir', 'beta:dir']
  stat(P)                    ok: mode=0o700
  stat(P/beta) exists        ok: True
  stat(P/nope) missing       ENOENT
  open(P/alpha/file.txt)     ok: alpha data
  listdir(P/alpha)           ok: ['file.txt']
  glob(P/*)                  ok: ['alpha', 'beta']
  makedirs(P/alpha/x/y)      ok: None
  mkdir(P/gamma)             ok: None

## P mode 0o100 (--x search only)
  listdir(P)                 EACCES
  scandir(P) kinds           EACCES
  stat(P)                    ok: mode=0o100
  stat(P/beta) exists        ok: True
  stat(P/nope) missing       ENOENT
  open(P/alpha/file.txt)     ok: alpha data
  listdir(P/alpha)           ok: ['file.txt']
  glob(P/*)                  ok: []
  makedirs(P/alpha/x/y)      ok: None
  mkdir(P/gamma)             EACCES

## P mode 0o400 (r-- list only)
  listdir(P)                 ok: ['alpha', 'beta']
  scandir(P) kinds           ok: ['alpha:dir', 'beta:dir']
  stat(P)                    ok: mode=0o400
  stat(P/beta) exists        EACCES
  stat(P/nope) missing       EACCES
  open(P/alpha/file.txt)     EACCES
  listdir(P/alpha)           EACCES
  glob(P/*)                  ok: ['alpha', 'beta']
  makedirs(P/alpha/x/y)      EACCES
  mkdir(P/gamma)             EACCES

## P mode 0o0 (--- nothing)
  listdir(P)                 EACCES
  scandir(P) kinds           EACCES
  stat(P)                    ok: mode=0o0
  stat(P/beta) exists        EACCES
  stat(P/nope) missing       EACCES
  open(P/alpha/file.txt)     EACCES
  listdir(P/alpha)           EACCES
  glob(P/*)                  ok: []
  makedirs(P/alpha/x/y)      EACCES
  mkdir(P/gamma)             EACCES
```
