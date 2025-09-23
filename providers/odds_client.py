"""
The Odds API client to fetch betting odds across multiple sports.

Env:
- ODDS_API_KEY: API key for The Odds API
- ODDS_REGIONS: comma-separated regions, default "us" (e.g., us,us2,eu,uk)
- ODDS_BOOKMAKERS: optional comma-separated bookmaker keys to filter; default all
"""

import os
import requests
from datetime import datetime
from typing import Dict, List, Optional
import pytz


class OddsClient:
    BASE_URL = 'https://api.the-odds-api.com/v4'

    SPORT_KEYS = {
        'nfl': 'americanfootball_nfl',
        'nba': 'basketball_nba',
        'mlb': 'baseball_mlb',
        'cfb': 'americanfootball_ncaaf',
        'nhl': 'icehockey_nhl',
        # soccer and golf omitted for now due to varied league keys
    }

    def __init__(self):
        self.session = requests.Session()
        self.api_key = os.getenv('ODDS_API_KEY')
        if not self.api_key:
            # Allow construction; methods will no-op without key
            pass
        self.timeout_seconds = 15
        self.regions = os.getenv('ODDS_REGIONS', 'us,us2')
        self.bookmakers_filter = self._parse_list(os.getenv('ODDS_BOOKMAKERS'))
        self.est_tz = pytz.timezone('US/Eastern')

    def _parse_list(self, value: Optional[str]) -> Optional[List[str]]:
        if not value:
            return None
        return [v.strip() for v in value.split(',') if v.strip()]

    def _normalize(self, name: str) -> str:
        return (name or '').lower().strip()

    def fetch_odds_for_sport(self, sport: str) -> List[Dict]:
        """
        Fetch aggregated odds per event for a sport. Returns list of dicts with
        home_team, away_team, home_moneyline, away_moneyline, spread, total, bookmaker, last_update.
        """
        sport_key = self.SPORT_KEYS.get(sport.lower())
        if not sport_key or not self.api_key:
            return []
        url = f"{self.BASE_URL}/sports/{sport_key}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': self.regions,
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'american',
        }
        last_exc = None
        for _ in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                events = resp.json() or []
                break
            except Exception as exc:
                last_exc = exc
                continue
        else:
            return []

        results: List[Dict] = []
        for ev in events:
            home = ev.get('home_team') or ''
            away = ev.get('away_team') or ''
            commence_time = self._parse_time(ev.get('commence_time'))
            bookmakers = ev.get('bookmakers') or []
            if self.bookmakers_filter:
                bookmakers = [b for b in bookmakers if b.get('key') in self.bookmakers_filter]
            if not bookmakers:
                continue

            best = self._pick_best_bookmaker(bookmakers)
            if not best:
                continue

            markets = best.get('markets') or []
            moneylines = self._extract_moneylines(markets, home, away)
            spread = self._extract_spread(markets, home, away)
            total = self._extract_total(markets)

            results.append({
                'home_team': home,
                'away_team': away,
                'commence_time': commence_time,
                'home_moneyline': moneylines.get('home'),
                'away_moneyline': moneylines.get('away'),
                'spread': spread,
                'total': total,
                'bookmaker': best.get('title') or best.get('key'),
                'last_update': self._parse_time(best.get('last_update')),
            })
        return results

    def _pick_best_bookmaker(self, bookmakers: List[Dict]) -> Optional[Dict]:
        # Choose the most recently updated bookmaker
        def parse(b):
            t = self._parse_time(b.get('last_update'))
            return t or datetime.min
        if not bookmakers:
            return None
        return sorted(bookmakers, key=parse, reverse=True)[0]

    def _parse_time(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=pytz.UTC)
            est_dt = parsed.astimezone(self.est_tz)
            return est_dt.replace(tzinfo=None)
        except Exception:
            return None

    def _extract_moneylines(self, markets: List[Dict], home: str, away: str) -> Dict[str, Optional[float]]:
        result = {'home': None, 'away': None}
        for m in markets:
            if m.get('key') != 'h2h':
                continue
            for outcome in m.get('outcomes', []):
                name = self._normalize(outcome.get('name'))
                if name == self._normalize(home):
                    result['home'] = float(outcome.get('price')) if outcome.get('price') is not None else None
                elif name == self._normalize(away):
                    result['away'] = float(outcome.get('price')) if outcome.get('price') is not None else None
        return result

    def _extract_spread(self, markets: List[Dict], home: str, away: str) -> Optional[float]:
        for m in markets:
            if m.get('key') != 'spreads':
                continue
            for outcome in m.get('outcomes', []):
                name = self._normalize(outcome.get('name'))
                if name == self._normalize(home) and outcome.get('point') is not None:
                    try:
                        return float(outcome.get('point'))
                    except Exception:
                        continue
        return None

    def _extract_total(self, markets: List[Dict]) -> Optional[float]:
        for m in markets:
            if m.get('key') != 'totals':
                continue
            # pick the point once
            outcomes = m.get('outcomes', [])
            if not outcomes:
                continue
            point = outcomes[0].get('point')
            try:
                return float(point) if point is not None else None
            except Exception:
                continue
        return None

    # ---------------- Player Props ----------------
    def fetch_player_props_for_sport(self, sport: str, markets: Optional[List[str]] = None) -> List[Dict]:
        """
        Fetch player prop markets for a sport. Returns list of dicts:
        {
          'player_name', 'market' (e.g., player_points), 'line', 'over_price', 'under_price',
          'team' (best-effort), 'opponent' (optional), 'bookmaker', 'last_update'
        }
        """
        sport_l = sport.lower()
        sport_key = self.SPORT_KEYS.get(sport_l)
        if not sport_key or not self.api_key:
            return []
        # Default markets per sport
        default_markets_by_sport = {
            'nba': ['player_points','player_rebounds','player_assists'],
            'nfl': ['player_pass_yards','player_rush_yards','player_receiving_yards'],
            'mlb': ['player_hits','player_home_runs','player_total_bases','player_strikeouts'],
        }
        mkts = markets or default_markets_by_sport.get(sport_l, ['player_points'])
        url = f"{self.BASE_URL}/sports/{sport_key}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': self.regions,
            'markets': ','.join(mkts),
            'oddsFormat': 'american',
        }
        last_exc = None
        for _ in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                events = resp.json() or []
                break
            except Exception as exc:
                last_exc = exc
                continue
        else:
            return []

        results: List[Dict] = []
        for ev in events:
            opponents = (ev.get('home_team') or '', ev.get('away_team') or '')
            bookmakers = ev.get('bookmakers') or []
            if self.bookmakers_filter:
                bookmakers = [b for b in bookmakers if b.get('key') in self.bookmakers_filter]
            if not bookmakers:
                continue
            best = self._pick_best_bookmaker(bookmakers)
            if not best:
                continue
            for m in (best.get('markets') or []):
                key = m.get('key')
                if key not in mkts:
                    continue
                # Expect outcomes for Over/Under with point and description = player name
                over = None
                under = None
                player_name = None
                for outcome in (m.get('outcomes') or []):
                    nm = (outcome.get('name') or '').lower()
                    desc = outcome.get('description') or outcome.get('player_name') or ''
                    if not player_name and desc:
                        player_name = desc
                    if nm == 'over':
                        over = outcome
                    elif nm == 'under':
                        under = outcome
                if player_name and (over or under):
                    line = None
                    if over and over.get('point') is not None:
                        line = float(over.get('point'))
                    elif under and under.get('point') is not None:
                        line = float(under.get('point'))
                    results.append({
                        'player_name': player_name,
                        'market': key,
                        'line': line,
                        'over_price': float(over.get('price')) if over and over.get('price') is not None else None,
                        'under_price': float(under.get('price')) if under and under.get('price') is not None else None,
                        'team': None,
                        'opponent': None,
                        'bookmaker': best.get('title') or best.get('key'),
                        'last_update': self._parse_time(best.get('last_update')),
                    })
        return results


