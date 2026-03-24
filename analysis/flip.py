"""
Flip opportunity calculator — direct buy/sell spread only (no multi-hop routes).

POE1: chaos-denominated thresholds; POE2: exalted for display, chaos internally.
"""
from __future__ import annotations

from dataclasses import dataclass

import config
import settings as cfg
from api.poe_ninja import CurrencyRate

_TRUSTED_ANCHORS = frozenset({"chaos", "divine", "exalted"})


@dataclass
class FlipOpportunity:
    name: str
    buy_currency: str
    sell_currency: str
    buy_at: float               # chaos per unit when buying
    sell_at: float              # chaos per unit when selling
    profit_per_trade: float     # chaos profit per 1 unit traded
    profit_percent: float
    volume: int
    listings: int
    strategy: str               # "direct"


def passes_max_buy_budget(rate: CurrencyRate, game: str, cpe: float) -> bool:
    """
    When max buy is set (>0), drop rows where you cannot buy 1 unit within budget
    (buy cost in chaos for POE1, in exalted for POE2). 0 = no cap.
    """
    max_c = float(cfg.get("MAX_BUY_COST_CHAOS") or 0.0)
    max_e = float(cfg.get("MAX_BUY_COST_EXALTED") or 0.0)
    g = (game or "poe2").lower()
    capped = (max_c > 0.0) if g == "poe1" else (max_e > 0.0)
    if not capped:
        return True
    buy = rate.buy_cost_chaos
    if buy <= 0:
        return False
    if g == "poe1":
        return buy <= max_c
    if cpe <= 0:
        return True
    return (buy / cpe) <= max_e


def key_rates_visible(rates: list[CurrencyRate], game: str) -> dict[str, float]:
    """Like summarize_key_rates but zeros out entries whose buy cost exceeds max buy settings."""
    cpe = get_chaos_per_exalted(rates)
    raw = summarize_key_rates(rates)
    result: dict[str, float] = {}
    for name in config.KEY_CURRENCIES:
        val = raw.get(name, 0.0)
        if val <= 0:
            result[name] = 0.0
            continue
        r_match = next((r for r in rates if r.name == name), None)
        if r_match is not None and not passes_max_buy_budget(r_match, game, cpe):
            result[name] = 0.0
        else:
            result[name] = val
    return result


def find_direct_flips(rates: list[CurrencyRate], game: str = "poe2") -> list[FlipOpportunity]:
    """
    Direct spread: buy low, sell high (same currency round-trip vs chaos/ex snapshot).

    POE1: two-sided chaos stash listings; min buy filter in chaos.
    POE2: exchange anchors; min buy filter in exalted (converted via chaos/ex rate).
    """
    opportunities: list[FlipOpportunity] = []
    g = (game or "poe2").lower()
    cpe = get_chaos_per_exalted(rates)

    for rate in rates:
        if rate.chaos_equivalent <= 0:
            continue
        buy = rate.buy_cost_chaos
        sell = rate.sell_price_chaos
        if buy <= 0 or sell <= 0:
            continue
        if not passes_max_buy_budget(rate, g, cpe):
            continue
        if g == "poe1":
            if rate.pay_listings <= 0 or rate.receive_listings <= 0:
                continue
            if "chaos" not in rate.anchors:
                continue
            if buy < cfg.get("MIN_BUY_COST_CHAOS"):
                continue
        elif g == "poe2":
            if not (rate.anchors & _TRUSTED_ANCHORS):
                continue
            min_ex = float(cfg.get("MIN_BUY_COST_EXALTED") or 0.0)
            if cpe > 0 and (buy / cpe) < min_ex:
                continue
        if rate.volume < cfg.get("MIN_VOLUME"):
            continue

        profit = sell - buy
        if profit <= 0:
            continue

        profit_pct = profit / buy * 100
        if profit_pct < cfg.get("MIN_PROFIT_PERCENT"):
            continue

        if g == "poe2":
            route = f"Exalted → {rate.name} → Exalted"
            bcur = "Exalted Orb"
        else:
            route = f"Chaos → {rate.name} → Chaos"
            bcur = "Chaos Orb"
        opportunities.append(FlipOpportunity(
            name=route,
            buy_currency=bcur,
            sell_currency=rate.name,
            buy_at=buy,
            sell_at=sell,
            profit_per_trade=profit,
            profit_percent=profit_pct,
            volume=rate.volume,
            listings=rate.listings,
            strategy="direct",
        ))

    opportunities.sort(key=lambda o: o.profit_percent, reverse=True)
    return opportunities


def get_chaos_per_divine(rates: list[CurrencyRate]) -> float:
    for r in rates:
        if r.name == "Divine Orb":
            return r.chaos_equivalent
    return 0.0


def get_chaos_per_exalted(rates: list[CurrencyRate]) -> float:
    for r in rates:
        if r.name == "Exalted Orb":
            return r.chaos_equivalent
    return 0.0


def summarize_key_rates(rates: list[CurrencyRate]) -> dict[str, float]:
    """Return chaos equivalent for each key currency (first row wins — prefer Currency category)."""
    rate_map: dict[str, float] = {}
    for r in rates:
        if r.name not in rate_map:
            rate_map[r.name] = r.chaos_equivalent
    result: dict[str, float] = {}
    for name in config.KEY_CURRENCIES:
        result[name] = rate_map.get(name, 0.0)
    return result
