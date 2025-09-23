from typing import Tuple

def american_to_decimal(odds: float) -> float:
    o = float(odds)
    if o >= 0:
        return 1.0 + o / 100.0
    else:
        return 1.0 + 100.0 / abs(o)

def implied_prob(odds: float) -> float:
    o = float(odds)
    if o >= 0:
        return 100.0 / (o + 100.0)
    else:
        return abs(o) / (abs(o) + 100.0)

def remove_vig_two_way(p1: float, p2: float) -> Tuple[float, float]:
    s = p1 + p2
    if s <= 0:
        return 0.5, 0.5
    return p1 / s, p2 / s

def ev_from_prob_and_odds(p: float, odds: float) -> float:
    dec = american_to_decimal(odds)
    payout = dec - 1.0
    return p * payout - (1.0 - p)

def kelly_fraction(p: float, odds: float, k: float = 0.25, cap: float = 0.02) -> float:
    dec = american_to_decimal(odds)
    b = dec - 1.0
    edge = p * (b + 1) - 1.0
    if b <= 0:
        return 0.0
    f_star = edge / b
    f_star = max(0.0, f_star)
    f_star *= k
    return min(f_star, cap)

