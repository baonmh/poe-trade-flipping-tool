"""
Trade Lab: cross-pair suggestions from rates, and manual auction-style pair spread math.

Pair diff: two opposite listings (I want / I have) for the same currency pair; spread is the
absolute gap between implied prices in the first leg's \"from\" currency.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from api.poe_ninja import CurrencyRate


def _rate_by_name(rates: list[CurrencyRate], name: str) -> Optional[CurrencyRate]:
    for r in rates:
        if r.name == name:
            return r
    return None


def suggest_from_rates(
    rates: list[CurrencyRate],
    *,
    top_direct: int = 25,
    top_cross: int = 15,
) -> dict[str, Any]:
    """
    Direct: best buy/sell spreads already on each item.
    Cross: triangle via Chaos — compare implied cross vs product of legs for liquid anchors.
    """
    # Direct: sort by spread * log(volume+1)
    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rates:
        if r.chaos_equivalent <= 0:
            continue
        buy_c = r.buy_cost_chaos
        sell_c = r.sell_price_chaos
        if buy_c <= 0 or sell_c <= 0:
            continue
        sp = r.spread_percent
        profit_raw_chaos = sell_c - buy_c
        score = sp * (1.0 + math.log1p(max(0, r.volume)))
        scored.append((score, {
            "name": r.name,
            "category": getattr(r, "category", "") or "",
            "buy_chaos": round(buy_c, 4),
            "sell_chaos": round(sell_c, 4),
            "spread_pct": round(sp, 2),
            "profit_raw_chaos": round(profit_raw_chaos, 4),
            "volume": r.volume,
            "kind": "direct",
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    direct = [d for _, d in scored[:top_direct]]

    # Cross (via Chaos): Exalted <-> Divine using chaos valuations
    chaos = _rate_by_name(rates, "Chaos Orb")
    div = _rate_by_name(rates, "Divine Orb")
    ex = _rate_by_name(rates, "Exalted Orb")
    cross: list[dict[str, Any]] = []
    if chaos and div and ex and chaos.chaos_equivalent > 0:
        # Implied ex per div from chaos prices
        ce, cd, cc = ex.chaos_equivalent, div.chaos_equivalent, chaos.chaos_equivalent
        implied_ex_per_div = (cd / ce) if ce > 0 else 0.0
        # Market buy/sell for Divine in chaos terms
        div_buy = div.buy_cost_chaos
        div_sell = div.sell_price_chaos
        ex_buy = ex.buy_cost_chaos
        ex_sell = ex.sell_price_chaos
        if all(x > 0 for x in (div_buy, div_sell, ex_buy, ex_sell, ce, cd)):
            # Synthetic: sell Ex for Div path vs direct — rough edge check
            cross.append({
                "name": "Triangle: Exalted ↔ Divine (via chaos valuation)",
                "category": "hint",
                "note": "Compare listing ratios; high spread on both orbs amplifies cross risk.",
                "chaos_per_ex": round(ce, 2),
                "chaos_per_div": round(cd, 2),
                "implied_ex_per_div": round(implied_ex_per_div, 4),
                "kind": "cross",
            })
    cross = cross[:top_cross]

    return {"direct": direct, "cross": cross}


def _first_token(name: str) -> str:
    return (name or "").strip().split()[0] or "?"


def pair_label_short(to_cur: str, from_cur: str) -> str:
    """Short label like \"Div-chaos\" from currency display names."""
    a = _first_token(to_cur)
    b = _first_token(from_cur)
    left = a[:3].capitalize()
    right = b.lower() if len(b) <= 5 else b[:4].lower()
    return f"{left}-{right}"


def _lex_lo_hi(a: str, b: str) -> tuple[str, str]:
    """Stable order for the two currencies in a pair (for canonical rate)."""
    x, y = a.strip(), b.strip()
    return (x, y) if x.lower() <= y.lower() else (y, x)


def lo_currency_per_hi_currency(f: str, t: str, want: float, have: float) -> float:
    """
    Auction: I want `want` of `to`, I have `have` of `from`.
    Returns units of lexicographically-lower currency per 1 unit of lexicographically-higher
    currency, so two opposite listings are comparable regardless of section order.
    """
    lo, hi = _lex_lo_hi(f, t)
    if f == lo and t == hi:
        return have / want
    if f == hi and t == lo:
        return want / have
    raise ValueError("from/to mismatch")


def pair_diff_opposite_listings(
    leg_a: dict[str, Any],
    leg_b: dict[str, Any],
) -> dict[str, Any]:
    """
    One auction row: I want `want` of `to`, I have `have` of `from`.
    Second row must list the opposite trade direction (same two currencies).

    Spread = absolute difference of the two implied prices in one canonical form
    (lower-named currency per higher-named currency).
    """
    f1 = str(leg_a.get("from") or "").strip()
    t1 = str(leg_a.get("to") or "").strip()
    w1 = float(leg_a.get("want") or 0.0)
    h1 = float(leg_a.get("have") or 0.0)
    f2 = str(leg_b.get("from") or "").strip()
    t2 = str(leg_b.get("to") or "").strip()
    w2 = float(leg_b.get("want") or 0.0)
    h2 = float(leg_b.get("have") or 0.0)

    if not f1 or not t1:
        return {"error": "First listing: From and To are required."}
    if not f2 or not t2:
        return {"error": "Second listing: From and To are required."}
    if w1 <= 0 or h1 <= 0 or w2 <= 0 or h2 <= 0:
        return {"error": "All I want / I have amounts must be greater than zero."}
    if f2 != t1 or t2 != f1:
        return {
            "error": (
                f"Second listing must be the opposite pair of the first "
                f"(expected From={t1!r}, To={f1!r}; got From={f2!r}, To={t2!r})."
            ),
        }

    try:
        k1 = lo_currency_per_hi_currency(f1, t1, w1, h1)
        k2 = lo_currency_per_hi_currency(f2, t2, w2, h2)
    except ValueError:
        return {"error": "Invalid From/To combination."}

    diff = abs(k2 - k1)
    lo, hi = _lex_lo_hi(f1, t1)
    label = pair_label_short(hi, lo)
    unit_lo = _first_token(lo).lower()
    line = f"{label} diff: {_fmt_amount(diff)} {unit_lo}"
    return {
        "pair_label": label,
        "line": line,
        "diff_amount": round(diff, 8),
        "lower_currency": lo,
        "higher_currency": hi,
        "canonical_lo_per_hi_leg1": round(k1, 8),
        "canonical_lo_per_hi_leg2": round(k2, 8),
    }


def _fmt_amount(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    s = f"{x:.6g}"
    return s


def pair_diff_from_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Sections are paired in order: (0,1), (2,3), … Each pair must be opposite listings.
    """
    errors: list[str] = []
    pairs_out: list[dict[str, Any]] = []
    n = len(sections)
    if n == 0:
        return {"pairs": [], "errors": ["Add two sections with opposite From/To for one pair."]}

    pairs_count = n // 2
    for k in range(pairs_count):
        i, j = k * 2, k * 2 + 1
        res = pair_diff_opposite_listings(sections[i], sections[j])
        if "error" in res:
            errors.append(f"Pair {k + 1} (sections {i + 1}–{j + 1}): {res.get('error', 'Unknown error')}")
        else:
            pairs_out.append(res)

    if n % 2 == 1:
        errors.append(f"Section {n} has no opposite pair; add another section or remove it.")

    return {"pairs": pairs_out, "errors": errors}
