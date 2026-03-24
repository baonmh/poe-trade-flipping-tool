"""
Crafting material demand analyzer.

"Top consumed items" = high trade volume * high price
This correlates to items that many players are actively
buying/using in crafting.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.poe_ninja import ItemPrice


@dataclass
class CraftingHotspot:
    name: str
    item_type: str
    chaos_value: float
    divine_value: float
    trade_volume: int
    listing_count: int
    demand_score: float     # chaos_value * volume = total chaos flowing through this item
    icon: str = ""


def compute_demand_score(item: ItemPrice) -> float:
    """
    Demand score = chaos_value * sqrt(volume)
    sqrt(volume) dampens outliers while still rewarding high liquidity.
    """
    if item.chaos_value <= 0 or item.count <= 0:
        return 0.0
    return item.chaos_value * (item.count ** 0.5)


def get_top_crafting_items(
    items: list[ItemPrice],
    top_n: int = 20,
    min_volume: int = 3,
    min_chaos_value: float = 1.0,
) -> list[CraftingHotspot]:
    """
    Filter and rank crafting materials by demand score.
    Returns the top_n hottest items.
    """
    hotspots: list[CraftingHotspot] = []

    for item in items:
        if item.count < min_volume:
            continue
        if item.chaos_value < min_chaos_value:
            continue

        score = compute_demand_score(item)
        hotspots.append(CraftingHotspot(
            name=item.name,
            item_type=item.item_type,
            chaos_value=item.chaos_value,
            divine_value=item.divine_value,
            trade_volume=item.count,
            listing_count=item.listing_count,
            demand_score=score,
            icon=item.icon,
        ))

    hotspots.sort(key=lambda h: h.demand_score, reverse=True)
    return hotspots[:top_n]


def group_by_category(hotspots: list[CraftingHotspot]) -> dict[str, list[CraftingHotspot]]:
    """Group hotspots by item_type for display."""
    groups: dict[str, list[CraftingHotspot]] = {}
    for h in hotspots:
        groups.setdefault(h.item_type, []).append(h)
    return groups


def find_bulk_flip_targets(
    items: list[ItemPrice],
    min_chaos_value: float = 5.0,
    min_volume: int = 10,
) -> list[ItemPrice]:
    """
    Items good for bulk buying and reselling:
    - Reasonable value (not too cheap)
    - High volume (liquid market)
    - Commonly needed in crafting
    """
    targets = [
        i for i in items
        if i.chaos_value >= min_chaos_value and i.count >= min_volume
    ]
    targets.sort(key=lambda i: i.count, reverse=True)
    return targets[:15]
