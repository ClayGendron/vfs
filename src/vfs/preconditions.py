"""Preconditions at the kernel: the vids a change requires, routed to the mount that holds each path.

A caller that requires a row to be as it read it passes the row's vid
back: ``if_vid=`` beside the single form of a change, ``if_vids=`` beside
its batch form, a mapping of paths to vids. The kernel turns the single
form into a mapping of one key, resolves each key as it resolves the
call's own targets, and hands each mount the keys of its own targets as
that mount's storage sees them:

    sites = {resolved: Site(mount.path, local) for each target of the call}
    required = required_by_mount(if_vids, sites, noun="a file in entries")
    refusal = vids_unissued(required, mounts)

A key that names no target of the call, or names a path that another key
names, is refused ``invalid`` before any storage is called. So is a key
for a mount whose storage declares no ``vid`` trait, as ``unsupported``:
a storage that issues no vid cannot honour one, and a precondition it
dropped would be a change the caller believes is guarded and is not.

This module is not public. ``vfs.base`` calls it for each change that
requires something.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from vfs.paths import Path, resolve_path
from vfs.results import ErrorKind, ResultError, classified
from vfs.storage import SupportsTraits

if TYPE_CHECKING:
    from collections.abc import Mapping

    from vfs.mounts import Mount
    from vfs.vid import VidOrAbsent

Required = dict[Path, dict[Path, "VidOrAbsent"]]
"""The vids a call requires, by the path of the mount that holds each key, then by the key as that mount sees it."""


class Site(NamedTuple):
    """Where one target of a change goes: the path of its mount, and its own path as that mount's storage sees it."""

    mount: Path
    local: Path


# ---------------------------------------------------------------------------
# Routing the keys
# ---------------------------------------------------------------------------


def required_by_mount(
    if_vids: Mapping[str, VidOrAbsent], sites: Mapping[Path, Site], *, noun: str
) -> Required | ResultError:
    """Each key of *if_vids* resolved, matched to its target in *sites*, and keyed as its mount sees it.

    *noun* names what a key must be, in the refusal of one that is not:
    ``"a file in entries"``, ``"a row in observations"``. A key that is
    no valid path names no target either, so it answers the same way.
    """
    required: Required = {}
    for key, vid in if_vids.items():
        resolved = resolve_path(key, mutation=True)
        site = sites.get(resolved.path) if resolved.path is not None else None
        if site is None:
            detail = f"each key of if_vids must be the path of {noun}"
            return classified(ErrorKind.invalid, detail=detail, data={"raw": str(key)})
        keyed = required.setdefault(site.mount, {})
        if site.local in keyed:
            return classified(ErrorKind.invalid, detail="if_vids names one path twice", data={"raw": str(key)})
        keyed[site.local] = vid
    return required


def vids_unissued(required: Required, mounts: Mapping[Path, Mount]) -> ResultError | None:
    """The refusal of the first mount that receives a key and whose storage declares no ``vid`` trait, or nothing."""
    for path in required:
        if not issues_vids(mounts[path]):
            detail = "the storage mounted here issues no vid, so a change there cannot require one"
            return classified(ErrorKind.unsupported, path, detail=detail)
    return None


def issues_vids(mount: Mount) -> bool:
    """Whether the storage of *mount* declares the ``vid`` trait, and so honours a vid a change requires."""
    storage = mount.storage
    return isinstance(storage, SupportsTraits) and storage.traits().get("vid") == "entry_version"
