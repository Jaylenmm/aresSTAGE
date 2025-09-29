"""
SportsGameOdds (SGO) API client for player props only.

Docs: https://sportsgameodds.com/docs/

This client focuses on fetching player prop markets for staging. If the API
returns errors or an unexpected shape, the client fails gracefully and returns
an empty list so callers can fall back to the existing props provider.
"""

import os
import time
from typing import Dict, List, Optional

import requests


class SportsGameOddsClient:
    BASE_URL = os.getenv('SGO_BASE_URL', 'https://api.sportsgameodds.com/v2')

    # Default markets per sport for alpha
    DEFAULT_MARKETS = {
        'nfl': ['player_pass_yards', 'player_rush_yards', 'player_receiving_yards'],
        'mlb': ['player_hits', 'player_home_runs', 'player_strikeouts'],
        'nba': ['player_points', 'player_rebounds', 'player_assists'],
    }

    def __init__(self):
        self.session = requests.Session()
        self.api_key = os.getenv('SGO_API_KEY')
        self.timeout_seconds = 15
        # Simple in-memory TTL cache
        self._cache: Dict[str, Dict] = {}
        try:
            self.ttl_seconds = int(os.getenv('PROPS_CACHE_TTL_SECONDS', '300'))
        except Exception:
            self.ttl_seconds = 300

    def _get(self, path: str, params: Dict) -> Optional[Dict]:
        if not self.api_key:
            return None
        url = f"{self.BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        headers = {'Authorization': f"Bearer {self.api_key}"}
        # Cache key
        key = f"GET:{url}:{sorted(params.items())}"
        now = time.time()
        cached = self._cache.get(key)
        if cached and (now - cached['t'] < self.ttl_seconds):
            return cached['data']
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            self._cache[key] = {'t': now, 'data': data}
            return data
        except Exception:
            return None

    def fetch_player_props_for_sport(self, sport: str, markets: Optional[List[str]] = None, limit: int = 200) -> List[Dict]:
        """
        Return a normalized list for the given sport and prop markets.
        Shape per item:
          {
            'player_name', 'market', 'line', 'over_price', 'under_price',
            'team', 'opponent', 'bookmaker', 'last_update'
          }
        """
        sport_l = (sport or '').lower()
        mkts = markets or self.DEFAULT_MARKETS.get(sport_l, [])
        if not mkts or not self.api_key:
            return []
        # Attempt a generic props endpoint; adjust if needed as we learn exact SGO paths
        data = self._get('/props', {'sport': sport_l, 'markets': ','.join(mkts), 'limit': limit})
        if not data:
            return []
        items = []
        # Expected structure assumption: { events: [ { player_name, market, line, over_price, under_price, team, opponent, bookmaker, last_update } ] }
        events = data.get('events') if isinstance(data, dict) else None
        if not events and isinstance(data, list):
            events = data
        if not events:
            return []
        for ev in events:
            try:
                player_name = ev.get('player_name') or ev.get('name')
                market = ev.get('market')
                line = ev.get('line')
                over_price = ev.get('over_price')
                under_price = ev.get('under_price')
                team = ev.get('team')
                opponent = ev.get('opponent')
                bookmaker = ev.get('bookmaker') or ev.get('book')
                last_update = ev.get('last_update')
                if player_name and market:
                    items.append({
                        'player_name': player_name,
                        'market': market,
                        'line': line,
                        'over_price': over_price,
                        'under_price': under_price,
                        'team': team,
                        'opponent': opponent,
                        'bookmaker': bookmaker,
                        'last_update': last_update
                    })
            except Exception:
                continue
        return items


