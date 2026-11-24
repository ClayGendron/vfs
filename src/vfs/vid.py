"""The vid: a short opaque value that names one entry at one version of one mount.

A storage mints a vid for every row it reports a version on. Two vids are
equal when, and only when, they name the same entry at the same version of
the same mount, so a caller that read a row can pass its vid back to a
change and the change lands only on that row in that state. A vid is
compared and never taken apart: it is a keyed digest, so it does not give
back the entry or the version, and it grants nothing.

```python
mint = VidMint(mount_identity)
vid = mint.mint(entry_key, version)  # 20 lowercase hex characters
assert is_vid(vid)
```

The module imports the standard library alone.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Final

VID_LENGTH: Final = 20
"""How many characters a vid has."""

Vid = Annotated[str, "20 lowercase hex characters that name one entry at one version; compared, never parsed"]
"""Twenty lowercase hex characters that name one entry at one version of one mount."""

# The digest is half the vid's length in bytes; ``person`` names this form of the vid.
_DIGEST_BYTES: Final = VID_LENGTH // 2
_PERSON: Final = b"vfs.vid.1"
_HEX: Final[frozenset[str]] = frozenset("0123456789abcdef")


# ---------------------------------------------------------------------------
# The shape
# ---------------------------------------------------------------------------


def is_vid(value: object) -> bool:
    """Whether *value* has the shape of a vid: a ``str`` of exactly 20 characters from ``0-9`` and ``a-f``.

    The shape is all that can be known of a vid without its mount: a value
    of this shape that no storage minted passes here and matches no row.
    """
    return isinstance(value, str) and len(value) == VID_LENGTH and _HEX.issuperset(value)


# ---------------------------------------------------------------------------
# The mint
# ---------------------------------------------------------------------------


class VidMint:
    """The vid of each row of one mount, keyed by the mount's identity.

    A storage builds one at first touch from the identity its database was
    provisioned with, so every storage object over one database mints the
    same vid for one row, and a storage over another database mints none of
    its vids. A storage that wants to issue vids may build one over any
    identity that is its own.

    ``mint(entry_key, 0)`` is lawful: no row is at version 0, so the value
    names the entry alone, is on no row and satisfies no precondition.
    """

    __slots__ = ("_key",)

    def __init__(self, mount_identity: str) -> None:
        self._key = mount_identity.encode("ascii")

    def mint(self, entry_key: bytes, version: int) -> Vid:
        """The vid of the entry whose 16 stored id bytes are *entry_key*, at *version*."""
        digest = hashlib.blake2b(
            entry_key + version.to_bytes(8, "big"), digest_size=_DIGEST_BYTES, key=self._key, person=_PERSON
        )
        return digest.hexdigest()
