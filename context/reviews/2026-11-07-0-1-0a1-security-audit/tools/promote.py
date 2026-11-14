#!/usr/bin/python3 -I
"""Trusted parent-side promotion: promote.py <agent-dir> <per-file-bytes> <total-bytes> <relpath>...

Copies each allowlisted scratch-relative file into <agent-dir>/artifacts/ with no-follow,
dir_fd-relative traversal, regular-file and link-count-1 checks, size bounds re-enforced
while reading, a post-copy fstat identity check, and exclusive no-follow destination creation.
"""
import os, stat, sys
agent, per_file, total = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
NF = os.O_NOFOLLOW | os.O_CLOEXEC
def opendir(parent_fd, name, create=False):
    if create:
        try: os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError: pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | NF, dir_fd=parent_fd)
    if not stat.S_ISDIR(os.fstat(fd).st_mode): raise OSError("not a directory")
    return fd
def parts(rel):
    if not rel or rel.startswith("/"): raise ValueError("absolute or empty")
    ps = rel.split("/")
    if any(p in ("", ".", "..") for p in ps): raise ValueError("bad component")
    return ps
root = os.open(agent, os.O_RDONLY | os.O_DIRECTORY | NF)
sroot, aroot = opendir(root, "scratch"), opendir(root, "artifacts", create=True)
spent, status = 0, 0
for rel in sys.argv[4:]:
    try:
        ps = parts(rel)
        sfd, dfd = sroot, aroot
        for p in ps[:-1]:
            sfd = opendir(sfd, p); dfd = opendir(dfd, p, create=True)
        src = os.open(ps[-1], os.O_RDONLY | os.O_NONBLOCK | NF, dir_fd=sfd)
        st = os.fstat(src)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1: raise OSError("not a single-link regular file")
        if st.st_size > per_file or spent + st.st_size > total: raise OSError("over byte bound")
        data, left = b"", st.st_size
        while left:
            chunk = os.read(src, min(left, 65536))
            if not chunk: break
            data += chunk; left -= len(chunk)
        if os.read(src, 1) or len(data) != st.st_size: raise OSError("file changed size")
        st2 = os.fstat(src)
        if (st2.st_ino, st2.st_dev, st2.st_nlink, st2.st_size, stat.S_IFMT(st2.st_mode)) != (st.st_ino, st.st_dev, st.st_nlink, st.st_size, stat.S_IFMT(st.st_mode)):
            raise OSError("file identity changed")
        dst = os.open(ps[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | NF, 0o600, dir_fd=dfd)
        dst_st = os.fstat(dst)
        if not stat.S_ISREG(dst_st.st_mode) or dst_st.st_nlink != 1: raise OSError("bad destination")
        os.write(dst, data); os.close(dst); os.close(src); spent += len(data)
        print(f"promoted {rel} ({len(data)} bytes)")
    except (OSError, ValueError) as e:
        status = 1; print(f"REFUSED {rel}: {e}", file=sys.stderr)
sys.exit(status)
