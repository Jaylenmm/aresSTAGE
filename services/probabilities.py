from typing import Dict, Optional
from math import erf, sqrt, exp

# Placeholder calibrated conversions with transparent logic

def ml_probability(home_team: str, away_team: str, sport: str, home_ml: Optional[float], away_ml: Optional[float]) -> Dict:
    """Blend market-implied with strength prior via logistic; return calibrated probabilities."""
    from utils.pricing import implied_prob, remove_vig_two_way
    from services.calibration import ML_MARKET_WEIGHT, ML_STRENGTH_SLOPE
    if home_ml is None or away_ml is None:
        return {'home': None, 'away': None}
    # Market baseline (vig-free)
    ph = implied_prob(home_ml)
    pa = implied_prob(away_ml)
    ph_fair, pa_fair = remove_vig_two_way(ph, pa)
    # Team strength prior via PlayerAnalyzer (simple heuristic for now)
    from services.team_strength import strength_delta as _sd
    strength_delta = _sd(sport, home_team, away_team) - 0.5
    slope = ML_STRENGTH_SLOPE.get(sport, 2.0)
    prior_home = 1.0 / (1.0 + exp(-slope * strength_delta))
    w = ML_MARKET_WEIGHT.get(sport, 0.9)
    p_home = w * ph_fair + (1.0 - w) * prior_home
    p_away = 1.0 - p_home
    return {'home': p_home, 'away': p_away}

def spread_cover_probability(spread_home: Optional[float], sport: str = 'nfl') -> Dict:
    """Assume margin ~ Normal(0, sigma). Convert spread to cover prob.
    Sigma tuned per sport later. Here use sigma=13 NFL, 12 NBA.
    """
    if spread_home is None:
        return {'home': None, 'away': None}
    from services.calibration import SPREAD_SIGMA
    sigma = SPREAD_SIGMA.get(sport, 12.0)
    z = (0 - spread_home) / sigma
    # home cover = P(margin > -spread)
    # Using Normal CDF approximation via erf
    def cdf(x):
        return 0.5 * (1.0 + erf(x / sqrt(2.0)))
    p_home = 1.0 - cdf(z)
    p_away = 1.0 - p_home
    return {'home': p_home, 'away': p_away}

def total_over_under_probability(total_line: Optional[float], sport: str = 'nfl') -> Dict:
    if total_line is None:
        return {'over': None, 'under': None}
    # Conservative baseline: 50/50 without model; will replace with pace/scoring.
    return {'over': 0.5, 'under': 0.5}

