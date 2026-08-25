"""A fixture module: enough structure to force real chunk boundaries."""

from dataclasses import dataclass


@dataclass
class Inventory:
    """Tracks stock levels for one warehouse aisle."""

    aisle: int
    bins: dict[str, int]

    def total(self) -> int:
        return sum(self.bins.values())

    def restock(self, sku: str, count: int) -> None:
        if count <= 0:
            raise ValueError(f"count must be positive, got {count}")
        self.bins[sku] = self.bins.get(sku, 0) + count

    def drain(self, sku: str, count: int) -> int:
        held = self.bins.get(sku, 0)
        taken = min(held, count)
        self.bins[sku] = held - taken
        return taken


LONG_NOTICE = """
This block exists to be an indivisible oversized leaf when the chunk
budget is small: a single string node that no walker can split on tree
boundaries, so the character splitter must take it piece by piece. It
rambles on purpose, line after line, well past any small byte budget,
because the fixture wants the oversized-leaf path exercised against a
committed expectation rather than a synthetic one-off in a test body.
"""


def audit(inventories: list[Inventory]) -> dict[int, int]:
    totals: dict[int, int] = {}
    for inventory in inventories:
        totals[inventory.aisle] = inventory.total()
    return totals


def merge(left: Inventory, right: Inventory) -> Inventory:
    merged = Inventory(aisle=left.aisle, bins=dict(left.bins))
    for sku, count in right.bins.items():
        merged.bins[sku] = merged.bins.get(sku, 0) + count
    return merged
