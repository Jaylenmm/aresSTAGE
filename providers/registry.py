"""
Provider capability registry and sport enablement.

This is a lightweight, deploy-safe registry that tells the collector which
providers to prioritize per sport and whether to seed from odds when schedule
is empty. It avoids schema changes and can be tuned by environment variables.
"""

import os
from typing import Dict, List


SPORT_CONFIG: Dict[str, Dict] = {
    'nfl': {'schedule': 'sdio', 'odds': 'oddsapi', 'fallback_odds_seed': True},
    'nba': {'schedule': 'sdio', 'odds': 'oddsapi', 'fallback_odds_seed': True},
    'mlb': {'schedule': 'sdio', 'odds': 'oddsapi', 'fallback_odds_seed': True},
    'nhl': {'schedule': 'sdio', 'odds': 'oddsapi', 'fallback_odds_seed': True},
    'cfb': {'schedule': 'sdio', 'odds': 'oddsapi', 'fallback_odds_seed': True},
    # soccer/golf best-effort via SDIO; odds integration varies by league/tournament
    'soccer': {'schedule': 'sdio', 'odds': None, 'fallback_odds_seed': False},
    'golf': {'schedule': 'sdio', 'odds': None, 'fallback_odds_seed': False},
}


def get_enabled_sports() -> List[str]:
    """
    Returns list of enabled sports. If env SPORT_ENABLED is set (csv), use it,
    else return the keys from SPORT_CONFIG.
    """
    env_val = os.getenv('SPORT_ENABLED')
    if env_val:
        parts = [p.strip().lower() for p in env_val.split(',') if p.strip()]
        return [p for p in parts if p in SPORT_CONFIG]
    return list(SPORT_CONFIG.keys())


def should_seed_from_odds(sport: str) -> bool:
    conf = SPORT_CONFIG.get((sport or '').lower(), {})
    return bool(conf.get('fallback_odds_seed'))


