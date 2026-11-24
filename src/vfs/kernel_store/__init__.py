"""The kernel's own records: one store for each file system, in the place its root storage names.

The store is private to the kernel and carries no compatibility promise.
Every statement about a record is written in this package, so the
kernel, its sessions and its synchronous face import no SQLAlchemy.
"""

from __future__ import annotations

from vfs.kernel_store.store import KernelStore, KernelStoreUnavailable, Transaction
from vfs.models.kernel_rows import KERNEL_FORMAT_VERSION, KERNEL_TABLE_PREFIXES

__all__ = ["KERNEL_FORMAT_VERSION", "KERNEL_TABLE_PREFIXES", "KernelStore", "KernelStoreUnavailable", "Transaction"]
