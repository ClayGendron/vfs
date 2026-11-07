<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Starts from a goal a competent user already has. No teaching,
no concepts. Title every guide "How to X". It can branch and handle variation.
-->

# How to install and pin vfs

The package on PyPI is `vfs-py`; the module imports as `vfs`.

```bash
pip install vfs-py
```

## Pin it

vfs is in alpha on the lane to `0.1.0`. A bare install resolves to the newest alpha, because the earlier `0.0.x` releases are yanked and nothing else is on the index. An alpha may change anything between releases: verbs, models, result shapes, the schema. Pin to the lane with the pre-release marker in the specifier:

```text
vfs-py>=0.1.0a1,<0.2
```

The `a1` matters. pip and uv hide pre-releases from any specifier that does not name one, so `vfs-py<0.2` matches no release until `0.1.0` final exists and pip answers "no matching distribution". The same rule means an alpha never reaches a project that pinned a final.

## Platforms

Wheels ship for Linux (glibc, `manylinux_2_28`) on x86_64 and aarch64, macOS on arm64 and x86_64, and Windows on x64, for CPython 3.11 and later. No compiler or Rust toolchain is needed on these.

Alpine and other musl-based images cannot install vfs: `sqlite-vec`, a core dependency, ships no musl wheel and no sdist, so resolution fails before vfs is reached. Use a glibc image such as `python:3.13-slim`.

A platform without a wheel falls back to the sdist, which builds the Rust extension locally. That needs a C compiler on the machine; `maturin` bootstraps the Rust toolchain itself.

## Check what you have

```bash
python -c "import vfs, vfs.native; print(vfs.__version__)"
```

`vfs.native` is the compiled engine; importing it proves the wheel matched the platform. The version printed is the installed distribution's, read from its metadata.
