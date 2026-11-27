"""The kernel's own records: one store for each file system, in the place its root storage names.

The store is private to the kernel and carries no compatibility promise.
Every statement about a record is written in this package, so the
kernel, its sessions and its synchronous face import no SQLAlchemy.
"""

from __future__ import annotations

from vfs.kernel_store.behind import BEHIND_CAPACITY, FLUSH_ROWS, BehindKind
from vfs.kernel_store.store import KernelStore, KernelStoreUnavailable, Transaction
from vfs.kernel_store.sweep import SWEEP_CHUNK, Sweeper, expiry_sweeper
from vfs.models.kernel_rows import KERNEL_FORMAT_VERSION, KERNEL_TABLE_PREFIXES

__all__ = [
    "BEHIND_CAPACITY",
    "FLUSH_ROWS",
    "KERNEL_FORMAT_VERSION",
    "KERNEL_TABLE_PREFIXES",
    "SWEEP_CHUNK",
    "BehindKind",
    "KernelStore",
    "KernelStoreUnavailable",
    "Sweeper",
    "Transaction",
    "expiry_sweeper",
]
