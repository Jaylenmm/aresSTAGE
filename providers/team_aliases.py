"""
Canonical team name normalization and aliases across providers.
This helps match SportsDataIO schedule names with The Odds API names.
"""

import re
from typing import Dict


ALIAS_MAP_PER_SPORT: Dict[str, Dict[str, str]] = {
    'nfl': {
        'la rams': 'los angeles rams',
        'la chargers': 'los angeles chargers',
        'washington football team': 'washington commanders',
        'ari cardinals': 'arizona cardinals',
        'sf 49ers': 'san francisco 49ers',
        'ny giants': 'new york giants',
        'ny jets': 'new york jets',
    },
    'nba': {
        'la lakers': 'los angeles lakers',
        'la clippers': 'los angeles clippers',
        'gs warriors': 'golden state warriors',
        'ny knicks': 'new york knicks',
        'bk nets': 'brooklyn nets',
    },
    'mlb': {
        'la dodgers': 'los angeles dodgers',
        'la angels': 'los angeles angels',
        'sd padres': 'san diego padres',
        'sf giants': 'san francisco giants',
        'ny yankees': 'new york yankees',
        'ny mets': 'new york mets',
    },
    'nhl': {
        'la kings': 'los angeles kings',
        'ny rangers': 'new york rangers',
        'ny islanders': 'new york islanders',
        'nj devils': 'new jersey devils',
    },
    'cfb': {},
    'soccer': {},
    'golf': {},
}


_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def canonicalize_team_name(sport: str, name: str) -> str:
    if not name:
        return ''
    s = name.lower().strip()
    s = _NON_ALNUM.sub('', s)
    s = re.sub(r"\s+", " ", s)
    # Expand common prefixes
    s = s.replace(' st ', ' saint ')
    s = s.replace(' ny ', ' new york ')
    s = s.replace(' la ', ' los angeles ')
    s = s.replace(' sf ', ' san francisco ')
    s = s.replace(' sd ', ' san diego ')
    # Apply alias map
    alias_map = ALIAS_MAP_PER_SPORT.get(sport.lower(), {})
    return alias_map.get(s, s)


