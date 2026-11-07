<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Starts from a goal a competent user already has. No teaching,
no concepts. Title every guide "How to X". It can branch and handle variation.
-->

# How to install and pin vfs

The package on PyPI is `vfs-py`; the module imports as `vfs`. vfs is in alpha on the lane to `0.1.0`, and during the alpha stage the install line is also the pin:

```bash
pip install "vfs-py>=0.1.0a1,<0.2"
```

## Why the specifier

The earlier `0.0.x` releases are yanked, so the only versions on the index are alphas. An alpha may change anything between releases: verbs, models, result shapes, the schema, and the `<0.2` bound keeps the next minor out.

The `a1` in the specifier is what lets pip see an alpha. pip shows a pre-release only to a specifier that names one, or under `--pre`, and it still counts a yanked final when it decides whether pre-releases are allowed, so with `0.0.22` yanked beside the alphas a bare `pip install vfs-py` answers "Ignored the following yanked versions: 0.0.22" and then "No matching distribution", and so does `vfs-py<0.2`. uv resolves the bare line to the newest alpha, because it judges "all versions are pre-release" per package. The pinned line installs the newest alpha under both. When `0.1.0` final ships, the bare line installs it under both and the pre-release marker can go.

An exact pin on a yanked version, `vfs-py==0.0.22`, still installs it, with a yank warning; that is the one escape hatch for an old project.

## Platforms

Wheels ship for Linux (glibc, `manylinux_2_28`) on x86_64 and aarch64, macOS on arm64 and x86_64, and Windows on x64, for CPython 3.11 and later. No compiler or Rust toolchain is needed on these.

Alpine and other musl-based images cannot install vfs: `sqlite-vec`, a core dependency, ships no musl wheel and no sdist, so resolution fails before vfs is reached. Use a glibc image such as `python:3.13-slim`.

A platform without a wheel falls back to the sdist, which builds the Rust extension locally. That needs a C compiler on the machine; `maturin` bootstraps the Rust toolchain itself.

## Check what you have

```bash
python -c "import vfs, vfs.native; print(vfs.__version__)"
```

`vfs.native` is the compiled engine; importing it proves the wheel matched the platform. The version printed is the installed distribution's, read from its metadata.
