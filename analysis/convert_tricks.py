"""
Convert / vendor-loop profit helpers.

Uses the same CurrencyRate buy/sell chaos semantics as the rest of the app:
  buy_cost_chaos  = chaos to acquire 1 unit from trade
  sell_price_chaos = chaos when selling 1 unit
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import config

from api.poe_ninja import CurrencyRate


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def find_rate_by_names(rates: list[CurrencyRate], names: list[str]) -> Optional[CurrencyRate]:
    """First rate whose name matches any alias (case-insensitive, substring ok for partial)."""
    aliases = [_norm(n) for n in names if n]
    for r in rates:
        rn = _norm(r.name)
        for a in aliases:
            if len(a) >= 3 and a in rn:
                return r
            if rn == a:
                return r
    return None


def _last_token(name: str) -> str:
    parts = (name or "").replace("—", " ").split()
    return parts[-1].rstrip(".,;") if parts else ""


# In-game: 3 identical Liquid Emotions → 1 of the next tier (reforge bench).
# Last word of the item name is the emotion step (Ire → Guilt → …).
POE2_LIQUID_EMOTION_ORDER = [
    "Ire",
    "Guilt",
    "Greed",
    "Envy",
    "Paranoia",
    "Suffering",
    "Despair",
    "Disgust",
    "Spite",
    "Isolation",
]


def _liquid_emotion_by_keyword(rates: list[CurrencyRate]) -> dict[str, CurrencyRate]:
    """Map emotion keyword (last word) → one representative rate (Liquid Emotions category)."""
    out: dict[str, CurrencyRate] = {}
    for r in rates:
        if _norm(r.category) != "liquid emotions":
            continue
        kw = _last_token(r.name)
        if kw not in POE2_LIQUID_EMOTION_ORDER:
            continue
        prev = out.get(kw)
        if prev is None or (r.volume > prev.volume):
            out[kw] = r
    return out


@dataclass
class TrickResult:
    id: str
    game: str
    title: str
    summary: str
    steps: list[str]
    profit_chaos: Optional[float] = None
    profit_pct: Optional[float] = None
    viable: Optional[bool] = None
    primary_unit: str = "chaos"
    detail: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


def _fmt_chaos(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x:,.2f}c"


def _fmt_ex(x: Optional[float], cpe: float) -> str:
    if x is None or cpe <= 0:
        return "—"
    return f"{x / cpe:,.4f}e"


def _uniform_rng_detail(sell_prices: list[float], cost_in: float) -> dict[str, Any]:
    """
    Baseline if each listed bid price were equally likely (uniform discrete).
    GGG does not publish true weights — use min/max as hard bounds for listed outcomes.
    """
    if not sell_prices:
        return {}
    n = len(sell_prices)
    mean_s = sum(sell_prices) / n
    mn = min(sell_prices)
    mx = max(sell_prices)
    stdev_s = 0.0 if n <= 1 else (sum((x - mean_s) ** 2 for x in sell_prices) / n) ** 0.5
    ev = mean_s - cost_in
    worst = mn - cost_in
    best = mx - cost_in
    return {
        "model": "uniform_discrete",
        "outcomes_n": n,
        "profit_ev_chaos": round(ev, 4),
        "profit_min_chaos": round(worst, 4),
        "profit_max_chaos": round(best, 4),
        "stdev_sell_chaos": round(stdev_s, 4),
        "risky_ev": ev > 0 and worst < 0,
        "caveat": (
            "True in-game weights are unknown. Uniform EV is a baseline; "
            "min/max are worst/best among listed poe.ninja outcomes only."
        ),
    }


def compute_poe1_wisdom_portal_loop(rates: list[CurrencyRate], cpe: float) -> TrickResult:
    """
    NPC vendors sell 1 Portal Scroll for 3 Scrolls of Wisdom (Act vendors).
    Loop: buy Wisdom with chaos → vendor 3:1 → Portal → sell Portal for chaos.
    Profit per portal produced: sell(portal) - 3 * buy(wisdom).
    """
    w = find_rate_by_names(rates, ["Scroll of Wisdom", "Scroll Of Wisdom"])
    p = find_rate_by_names(rates, ["Portal Scroll"])
    missing = []
    if not w:
        missing.append("Scroll of Wisdom")
    if not p:
        missing.append("Portal Scroll")
    if missing:
        return TrickResult(
            id="poe1_wisdom_portal_vendor",
            game="poe1",
            title="Wisdom → Portal (vendor) → Chaos",
            summary="Vendor buys 3 Wisdom for 1 Portal (town NPC). Compare trade prices.",
            steps=[
                "Buy Scrolls of Wisdom with chaos (trade).",
                "Vendor: trade 3 Wisdom → 1 Portal Scroll.",
                "Sell Portal Scroll for chaos.",
            ],
            missing=missing,
            detail={"note": "Spread uses listed buy/sell; large stacks reduce relative fee impact."},
        )

    buy_w = w.buy_cost_chaos
    sell_p = p.sell_price_chaos
    cost_3w = 3.0 * buy_w
    profit = sell_p - cost_3w
    profit_pct = (profit / cost_3w * 100.0) if cost_3w > 0 else None
    viable = profit > 0 and buy_w > 0 and sell_p > 0
    needs_manual = buy_w <= 0 or sell_p <= 0

    return TrickResult(
        id="poe1_wisdom_portal_vendor",
        game="poe1",
        title="Wisdom → Portal (vendor) → Chaos",
        summary=(
            f"Net per Portal produced: {_fmt_chaos(profit)} "
            f"({profit_pct:+.1f}% vs 3×Wisdom buy)" if profit_pct is not None else ""
        ),
        steps=[
            f"Buy 1 Wisdom ≈ {_fmt_chaos(buy_w)} (ask).",
            "Vendor 3 Wisdom → 1 Portal.",
            f"Sell 1 Portal ≈ {_fmt_chaos(sell_p)} (bid).",
        ],
        profit_chaos=round(profit, 4) if profit is not None else None,
        profit_pct=round(profit_pct, 2) if profit_pct is not None else None,
        viable=viable,
        primary_unit="chaos",
        detail={
            "buy_wisdom_chaos": round(buy_w, 4),
            "sell_portal_chaos": round(sell_p, 4),
            "cost_3_wisdom_chaos": round(cost_3w, 4),
            "profit_ex": round(profit / cpe, 6) if cpe and profit is not None else None,
            "needs_manual": needs_manual,
        },
    )


def lifeforce_buy_chaos_per_unit(rates: list[CurrencyRate], lifeforce_name: str) -> float:
    """Buy cost in chaos per 1 unit of a specific Crystallised Lifeforce."""
    for r in rates:
        if (r.name or "") == lifeforce_name and r.buy_cost_chaos > 0:
            return float(r.buy_cost_chaos)
    alt = find_rate_by_names(rates, [lifeforce_name])
    if alt and alt.buy_cost_chaos > 0:
        return float(alt.buy_cost_chaos)
    return 0.0


POE1_PRIMAL_LIFEFORCE = "Primal Crystallised Lifeforce"
POE1_VIVID_LIFEFORCE = "Vivid Crystallised Lifeforce"


def compute_poe1_deafening_essence_harvest(
    essence_rates: list[CurrencyRate],
    main_rates: list[CurrencyRate],
    cpe: float,
) -> TrickResult:
    """
    Naive: buy cheapest Deafening Essence of X + Primal lifeforce cost vs mean sell of *other* Deafening essences.
    Default: 270 Primal / 9 essences in stack → 30 Primal per essence reroll (configurable).
    """
    stack = max(1, int(getattr(config, "POE1_HARVEST_ESSENCE_STACK_SIZE", 9) or 9))
    primal_stack = float(getattr(config, "POE1_HARVEST_ESSENCE_LIFEFORCE_PRIMAL_PER_STACK", 270) or 270)
    lf_units = primal_stack / float(stack)
    lf_chaos_u = lifeforce_buy_chaos_per_unit(main_rates, POE1_PRIMAL_LIFEFORCE)
    pool = [
        r for r in essence_rates
        if (r.name or "").startswith("Deafening Essence of") and r.buy_cost_chaos > 0
    ]
    if len(pool) < 2:
        return TrickResult(
            id="poe1_harvest_deafening_essence",
            game="poe1",
            title="Harvest: Deafening Essence reroll (Lifeforce)",
            summary="Need Essence exchange lines on poe.ninja for this league.",
            steps=[
                "Buy the cheapest Deafening Essence of X (trade).",
                "Horticrafting: reroll toward another Deafening essence (Primal Crystallised Lifeforce).",
                "Sell the result — compare to mean sell of other Deafening essences.",
            ],
            missing=["Deafening essences (exchange)"],
            detail={
                "note": "Primal lifeforce: POE1_HARVEST_ESSENCE_LIFEFORCE_PRIMAL_PER_STACK / POE1_HARVEST_ESSENCE_STACK_SIZE.",
            },
        )

    pool.sort(key=lambda r: r.buy_cost_chaos)
    cheapest = pool[0]
    others = pool[1:]
    lf_cost = lf_units * lf_chaos_u
    cost_in = cheapest.buy_cost_chaos + lf_cost
    sells_other = [r.sell_price_chaos for r in others]
    avg_sell_others = sum(sells_other) / len(sells_other)
    profit = avg_sell_others - cost_in
    profit_pct = (profit / cost_in * 100.0) if cost_in > 0 else None
    viable = profit > 0 and cost_in > 0 and lf_chaos_u > 0
    rng = _uniform_rng_detail(sells_other, cost_in)

    return TrickResult(
        id="poe1_harvest_deafening_essence",
        game="poe1",
        title="Harvest: Deafening Essence reroll (Lifeforce)",
        summary=(
            f"Uniform EV: {_fmt_chaos(profit)} ({profit_pct:+.1f}%) · "
            f"worst {_fmt_chaos(rng.get('profit_min_chaos'))} … best {_fmt_chaos(rng.get('profit_max_chaos'))} · "
            f"{lf_units:.1f} Primal LF @ {_fmt_chaos(lf_chaos_u)}/u"
            if profit_pct is not None and rng else f"Naive net: {_fmt_chaos(profit)}"
        ),
        steps=[
            f"Cheapest: {cheapest.name} @ {_fmt_chaos(cheapest.buy_cost_chaos)} buy.",
            (
                f"Primal lifeforce: {primal_stack:.0f} / {stack} essence ≈ {lf_units:.1f} Primal × "
                f"{_fmt_chaos(lf_chaos_u)}/u = {_fmt_chaos(lf_cost)}."
            ),
            f"Other Deafening essences (n={len(others)}): mean bid {_fmt_chaos(avg_sell_others)} — "
            f"uniform baseline EV vs min bid {_fmt_chaos(min(sells_other))} / max {_fmt_chaos(max(sells_other))}.",
            "True roll weights are not public; min/max are only among listed outcomes on poe.ninja.",
            "Verify exact Horticrafting cost in-game if your stack size differs.",
        ],
        profit_chaos=round(profit, 4),
        profit_pct=round(profit_pct, 2) if profit_pct is not None else None,
        viable=viable if lf_chaos_u > 0 else None,
        primary_unit="chaos",
        detail={
            "lf_type": "Primal",
            "lf_per_stack": round(primal_stack, 2),
            "stack_size": stack,
            "lf_units_per_roll": round(lf_units, 4),
            "lf_chaos_per_unit": round(lf_chaos_u, 4),
            "lf_total_chaos": round(lf_cost, 4),
            "cheapest_name": cheapest.name,
            "avg_sell_others_chaos": round(avg_sell_others, 4),
            "needs_manual": lf_chaos_u <= 0,
            "rng": rng,
        },
    )


def compute_poe1_catalyst_harvest(main_rates: list[CurrencyRate], cpe: float) -> TrickResult:
    """Jewellery catalysts from currency tab + Vivid lifeforce (typical 300 / 10 stack)."""
    stack = max(1, int(getattr(config, "POE1_HARVEST_CATALYST_STACK_SIZE", 10) or 10))
    vivid_stack = float(getattr(config, "POE1_HARVEST_CATALYST_LIFEFORCE_VIVID_PER_STACK", 300) or 300)
    lf_units = vivid_stack / float(stack)
    lf_chaos_u = lifeforce_buy_chaos_per_unit(main_rates, POE1_VIVID_LIFEFORCE)
    cats = [
        r for r in main_rates
        if "Catalyst" in (r.name or "")
        and "Lifeforce" not in (r.name or "")
        and r.buy_cost_chaos > 0
    ]
    if len(cats) < 2:
        return TrickResult(
            id="poe1_harvest_catalyst",
            game="poe1",
            title="Harvest: Catalyst reroll (Lifeforce)",
            summary="No jewellery catalyst listings in merged currency data.",
            steps=[
                "Buy the cheapest catalyst you can reroll.",
                "Horticrafting: reroll catalyst (Vivid Crystallised Lifeforce).",
                "Compare mean sell of other catalysts.",
            ],
            missing=["Catalyst prices in stash currency"],
            detail={},
        )

    cats.sort(key=lambda r: r.buy_cost_chaos)
    cheapest = cats[0]
    others = cats[1:]
    lf_cost = lf_units * lf_chaos_u
    cost_in = cheapest.buy_cost_chaos + lf_cost
    sells_other = [r.sell_price_chaos for r in others]
    avg_sell_others = sum(sells_other) / len(sells_other)
    profit = avg_sell_others - cost_in
    profit_pct = (profit / cost_in * 100.0) if cost_in > 0 else None
    viable = profit > 0 and cost_in > 0 and lf_chaos_u > 0
    rng = _uniform_rng_detail(sells_other, cost_in)

    return TrickResult(
        id="poe1_harvest_catalyst",
        game="poe1",
        title="Harvest: Catalyst reroll (Lifeforce)",
        summary=(
            f"Uniform EV: {_fmt_chaos(profit)} ({profit_pct:+.1f}%) · "
            f"worst {_fmt_chaos(rng.get('profit_min_chaos'))} … best {_fmt_chaos(rng.get('profit_max_chaos'))} · "
            f"{lf_units:.1f} Vivid LF · {len(cats)} catalysts"
            if profit_pct is not None and rng else f"Naive net: {_fmt_chaos(profit)}"
        ),
        steps=[
            f"Cheapest: {cheapest.name} @ {_fmt_chaos(cheapest.buy_cost_chaos)} buy.",
            (
                f"Vivid lifeforce: {vivid_stack:.0f} / {stack} catalyst ≈ {lf_units:.1f} Vivid × "
                f"{_fmt_chaos(lf_chaos_u)}/u = {_fmt_chaos(lf_cost)}."
            ),
            f"Other catalysts (n={len(others)}): mean bid {_fmt_chaos(avg_sell_others)} — "
            f"uniform baseline vs min bid {_fmt_chaos(min(sells_other))} / max {_fmt_chaos(max(sells_other))}.",
            "True roll weights are not public; min/max are only among listed outcomes on poe.ninja.",
            "Verify exact craft cost in-game if your stack size differs.",
        ],
        profit_chaos=round(profit, 4),
        profit_pct=round(profit_pct, 2) if profit_pct is not None else None,
        viable=viable if lf_chaos_u > 0 else None,
        primary_unit="chaos",
        detail={
            "lf_type": "Vivid",
            "lf_per_stack": round(vivid_stack, 2),
            "stack_size": stack,
            "lf_units_per_roll": round(lf_units, 4),
            "lf_chaos_per_unit": round(lf_chaos_u, 4),
            "lf_total_chaos": round(lf_cost, 4),
            "cheapest_name": cheapest.name,
            "avg_sell_others_chaos": round(avg_sell_others, 4),
            "needs_manual": lf_chaos_u <= 0,
            "rng": rng,
        },
    )


def compute_poe1_tattoo_three_to_one(
    tattoo_rates: list[CurrencyRate],
    color_map: dict[str, str],
) -> list[TrickResult]:
    """Vendor: 3 tattoos same colour → 1 random tattoo of that colour."""
    by: dict[str, list[CurrencyRate]] = {}
    for r in tattoo_rates:
        if _norm(r.category) != "tattoos":
            continue
        col = color_map.get(r.name, "Other")
        if col in ("Journey", "Other"):
            continue
        by.setdefault(col, []).append(r)

    out: list[TrickResult] = []
    for col in ("STR", "DEX", "INT"):
        group = by.get(col) or []
        valid = [r for r in group if r.buy_cost_chaos > 0 and r.sell_price_chaos > 0]
        if len(valid) < 2:
            continue
        valid.sort(key=lambda r: r.buy_cost_chaos)
        cheapest = valid[0]
        floor_cost = 3.0 * cheapest.buy_cost_chaos
        sells = [r.sell_price_chaos for r in valid]
        avg_sell = sum(sells) / len(sells)
        profit = avg_sell - floor_cost
        profit_pct = (profit / floor_cost * 100.0) if floor_cost > 0 else None
        viable = profit > 0
        rng = _uniform_rng_detail(sells, floor_cost)
        tid = f"poe1_tattoo_{col.lower()}"
        out.append(
            TrickResult(
                id=tid,
                game="poe1",
                title=f"Tattoo vendor: 3 → 1 random ({col})",
                summary=(
                    f"Uniform EV: {_fmt_chaos(profit)} ({profit_pct:+.1f}%) · "
                    f"worst {_fmt_chaos(rng.get('profit_min_chaos'))} … best {_fmt_chaos(rng.get('profit_max_chaos'))} · "
                    f"{len(valid)} tattoos"
                    if profit_pct is not None and rng else f"Naive: {_fmt_chaos(profit)}"
                ),
                steps=[
                    f"Floor: 3× {cheapest.name} @ {_fmt_chaos(cheapest.buy_cost_chaos)} = {_fmt_chaos(floor_cost)}.",
                    "Vendor: 3 Tattoos of the same colour → 1 random Tattoo of that colour.",
                    f"Mean bid (all {col} tattoos): {_fmt_chaos(avg_sell)}.",
                    f"Uniform baseline: min bid {_fmt_chaos(min(sells))} / max {_fmt_chaos(max(sells))} — "
                    "weights are unknown; many trials approach mean only if odds are stable.",
                ],
                profit_chaos=round(profit, 4),
                profit_pct=round(profit_pct, 2) if profit_pct is not None else None,
                viable=viable,
                primary_unit="chaos",
                detail={
                    "colour": col,
                    "cheapest_name": cheapest.name,
                    "floor_chaos": round(floor_cost, 4),
                    "mean_sell_chaos": round(avg_sell, 4),
                    "n": len(valid),
                    "rng": rng,
                },
            )
        )
    return out


def compute_poe2_liquid_emotion_upgrades(rates: list[CurrencyRate], cpe: float) -> list[TrickResult]:
    """3× tier N → 1× tier N+1; profit if 3*buy(low) < sell(high)."""
    by_kw = _liquid_emotion_by_keyword(rates)
    out: list[TrickResult] = []
    for i in range(len(POE2_LIQUID_EMOTION_ORDER) - 1):
        low_k = POE2_LIQUID_EMOTION_ORDER[i]
        high_k = POE2_LIQUID_EMOTION_ORDER[i + 1]
        lo = by_kw.get(low_k)
        hi = by_kw.get(high_k)
        if not lo or not hi:
            continue
        cost = 3.0 * lo.buy_cost_chaos
        rev = hi.sell_price_chaos
        profit = rev - cost
        profit_pct = (profit / cost * 100.0) if cost > 0 else None
        viable = profit > 0 and lo.buy_cost_chaos > 0 and hi.sell_price_chaos > 0
        needs_manual = lo.buy_cost_chaos <= 0 or hi.sell_price_chaos <= 0
        tid = f"poe2_emotion_{low_k}_{high_k}".lower()
        out.append(
            TrickResult(
                id=tid,
                game="poe2",
                title=f"Liquid Emotion: 3× {low_k} → 1× {high_k}",
                summary=(
                    f"Net (reforge bench): {_fmt_chaos(profit)} · {_fmt_ex(profit, cpe)} "
                    f"({profit_pct:+.1f}%)" if profit_pct is not None else ""
                ),
                steps=[
                    f"Buy 3× {lo.name} @ {_fmt_chaos(lo.buy_cost_chaos)} each (3× = {_fmt_chaos(cost)}).",
                    "Reforge bench: 3 identical → 1 next tier.",
                    f"Sell 1× {hi.name} @ {_fmt_chaos(hi.sell_price_chaos)} (bid).",
                ],
                profit_chaos=round(profit, 4),
                profit_pct=round(profit_pct, 2) if profit_pct is not None else None,
                viable=viable,
                primary_unit="exalted",
                detail={
                    "low_name": lo.name,
                    "high_name": hi.name,
                    "buy_low_chaos": round(lo.buy_cost_chaos, 4),
                    "sell_high_chaos": round(hi.sell_price_chaos, 4),
                    "profit_ex": round(profit / cpe, 6) if cpe else None,
                    "needs_manual": needs_manual,
                },
            )
        )
    return out


def compute_poe2_soulcore_reforge_hint(rates: list[CurrencyRate], cpe: float) -> TrickResult:
    """
    3 identical Soul Cores → 1 random Soul Core. No exact EV without drop weights;
    compare floor cost (3× cheapest buy) to mean sell across category.
    """
    souls = [r for r in rates if _norm(r.category) == "soul cores" and r.buy_cost_chaos > 0 and r.sell_price_chaos > 0]
    if len(souls) < 2:
        return TrickResult(
            id="poe2_soulcore_reforge",
            game="poe2",
            title="Soul Core reforge (3 → 1 random)",
            summary="Need Soul Core listings on poe.ninja for this league.",
            steps=[
                "Buy 3× the same Soul Core (trade).",
                "Reforge bench: 3 identical → 1 random Soul Core.",
                "Sell result or repeat.",
            ],
            missing=["Soul Core exchange data"],
            detail={"note": "Output is random — EV needs sim or manual samples."},
        )

    cheapest = min(souls, key=lambda r: r.buy_cost_chaos)
    sells = [r.sell_price_chaos for r in souls]
    avg_sell = sum(sells) / len(sells)
    floor_cost = 3.0 * cheapest.buy_cost_chaos
    naive_ev = avg_sell - floor_cost
    profit_pct = (naive_ev / floor_cost * 100.0) if floor_cost > 0 else None
    rng = _uniform_rng_detail(sells, floor_cost)

    return TrickResult(
        id="poe2_soulcore_reforge",
        game="poe2",
        title="Soul Core reforge (3 → 1 random)",
        summary=(
            f"Uniform EV: {_fmt_chaos(naive_ev)} ({profit_pct:+.1f}%) · "
            f"worst {_fmt_chaos(rng.get('profit_min_chaos'))} … best {_fmt_chaos(rng.get('profit_max_chaos'))} · "
            f"{len(souls)} cores (weights unknown)"
            if profit_pct is not None and rng else "Need weights for true EV."
        ),
        steps=[
            f"Floor: 3× {_fmt_chaos(cheapest.buy_cost_chaos)} = {_fmt_chaos(floor_cost)} on {cheapest.name}.",
            f"Mean bid (all listed cores): {_fmt_chaos(avg_sell)}.",
            f"Uniform baseline: min bid {_fmt_chaos(min(sells))} / max {_fmt_chaos(max(sells))}.",
            "GGG does not publish reforge weights — uniform mean is not true EV; min/max bound listed outcomes.",
        ],
        profit_chaos=round(naive_ev, 4),
        profit_pct=round(profit_pct, 2) if profit_pct is not None else None,
        viable=None,
        primary_unit="exalted",
        detail={
            "cheapest_name": cheapest.name,
            "floor_cost_chaos": round(floor_cost, 4),
            "mean_sell_chaos": round(avg_sell, 4),
            "profit_ex": round(naive_ev / cpe, 6) if cpe else None,
            "rng": rng,
            "warning": "True weights are not public; σ and EV only match the uniform baseline.",
        },
    )


# Reference-only ideas (no live pricing) — expand over time.
RESEARCH_TRICKS: list[dict[str, Any]] = [
    {
        "id": "poe1_chromatic_gem_quality",
        "game": "poe1",
        "title": "Single-socket gems + chromatics (vendor)",
        "body": (
            "Vendor recipes turn quality gems and socketed gear into Chromatic Orbs. "
            "Profitable when chroms trade above the opportunity cost of inputs — usually bulk."
        ),
    },
    {
        "id": "poe1_quality_weapon_gcp",
        "game": "poe1",
        "title": "40% combined quality weapon → Gemcutter's Prism",
        "body": (
            "Weapons (and some gear) with total quality on linked pieces vendor to GCP. "
            "Watch GCP vs sum of component prices."
        ),
    },
    {
        "id": "poe1_flask_bauble",
        "game": "poe1",
        "title": "Utility flasks → Glassblower's Bauble",
        "body": "Some flask combinations vendor to Baubles; compare bauble price vs ingredient cost.",
    },
    {
        "id": "poe2_omen_compose",
        "game": "poe2",
        "title": "Omens / catalyst combos (league-dependent)",
        "body": (
            "Some leagues expose compose/split recipes with fixed ratios. "
            "Track patch notes — add here when a stable recipe maps to exchange prices."
        ),
    },
    {
        "id": "poe2_map_fragments",
        "game": "poe2",
        "title": "Fragment sets → boss / map access",
        "body": (
            "Buying fragments separately vs set listings sometimes diverges. "
            "Same logic as currency arb but with fragment tab names."
        ),
    },
    {
        "id": "poe1_chaos_vendor_set",
        "game": "poe1",
        "title": "Chaos recipe (rare full sets)",
        "body": (
            "Vendor a full set of rare items (60–74 ilvl etc.) for Chaos. "
            "Compare to selling pieces; sometimes bulk chaos recipe beats chaos-starved slots."
        ),
    },
    {
        "id": "poe1_divine_vendor_sixlink",
        "game": "poe1",
        "title": "Six-link + quality → Divine (league-dependent)",
        "body": (
            "Some leagues expose a 6-link + 20% quality vendor path to a Divine Orb. "
            "Check current wiki/patch notes — ratio vs raw 6-link price."
        ),
    },
    {
        "id": "poe2_uncut_gem_split",
        "game": "poe2",
        "title": "Uncut gems: split vs level",
        "body": (
            "Uncut gem tiers sometimes trade below the implied value of cutting/levelling. "
            "Watch for wide spreads between adjacent tiers on poe.ninja."
        ),
    },
    {
        "id": "poe2_rune_socket_service",
        "game": "poe2",
        "title": "Runes / soul cores vs bench fee",
        "body": (
            "Before reforging expensive bases, compare trade price of the finished mod "
            "vs average cost of rolls (bench + materials)."
        ),
    },
]


def all_trick_results(
    rates: list[CurrencyRate],
    game: str,
    cpe: float,
    *,
    poe1_essence_rates: Optional[list[CurrencyRate]] = None,
    poe1_tattoo_colors: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    g = (game or "poe2").lower()
    computed: list[TrickResult] = []
    if g == "poe1":
        computed.append(compute_poe1_wisdom_portal_loop(rates, cpe))
        er = poe1_essence_rates or []
        computed.append(compute_poe1_deafening_essence_harvest(er, rates, cpe))
        computed.append(compute_poe1_catalyst_harvest(rates, cpe))
        tattoo_rates = [r for r in rates if _norm(r.category) == "tattoos"]
        tc = poe1_tattoo_colors or {}
        if tc:
            computed.extend(compute_poe1_tattoo_three_to_one(tattoo_rates, tc))
    else:
        computed.extend(compute_poe2_liquid_emotion_upgrades(rates, cpe))
        computed.append(compute_poe2_soulcore_reforge_hint(rates, cpe))

    def serial(tr: TrickResult) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": tr.id,
            "game": tr.game,
            "title": tr.title,
            "summary": tr.summary,
            "steps": tr.steps,
            "missing": tr.missing,
            "detail": tr.detail,
        }
        if tr.profit_chaos is not None:
            d["profit_chaos"] = tr.profit_chaos
        if tr.profit_pct is not None:
            d["profit_pct"] = tr.profit_pct
        if tr.viable is not None:
            d["viable"] = tr.viable
        d["primary_unit"] = tr.primary_unit
        return d

    return {
        "computed": [serial(t) for t in computed],
        "research": [x for x in RESEARCH_TRICKS if x.get("game") == g],
    }
