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
from typing import Dict, List, Optional, Tuple
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
        # Broaden default coverage beyond MVP
        self.regions = os.getenv('ODDS_REGIONS', 'us,us2,eu,uk')
        self.bookmakers_filter = self._parse_list(os.getenv('ODDS_BOOKMAKERS'))
        self.est_tz = pytz.timezone('US/Eastern')

    def _parse_list(self, value: Optional[str]) -> Optional[List[str]]:
        if not value:
            return None
        return [v.strip() for v in value.split(',') if v.strip()]

    def _normalize(self, name: str) -> str:
        return (name or '').lower().strip()

    # ---------- Event-level helpers for best-line evaluation ----------
    def _fetch_events(self, sport: str) -> List[Dict]:
        sport_key = self.SPORT_KEYS.get((sport or '').lower())
        if not sport_key or not self.api_key:
            return []
        url = f"{self.BASE_URL}/sports/{sport_key}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': self.regions,
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'american',
        }
        for _ in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                return resp.json() or []
            except Exception:
                continue
        return []

    def fetch_event_bookmakers(self, sport: str, home_team: str, away_team: str) -> List[Dict]:
        """
        Return the list of bookmaker objects for the matching event (home vs away).
        Each bookmaker has shape: { key, title, last_update, markets: [...] }
        """
        try:
            home_n = self._normalize(home_team)
            away_n = self._normalize(away_team)
            events = self._fetch_events(sport)
            for ev in events:
                if self._normalize(ev.get('home_team')) == home_n and self._normalize(ev.get('away_team')) == away_n:
                    bms = ev.get('bookmakers') or []
                    if self.bookmakers_filter:
                        bms = [b for b in bms if b.get('key') in self.bookmakers_filter]
                    return bms
        except Exception:
            pass
        return []

    def fetch_event_full(self, sport: str, home_team: str, away_team: str) -> Optional[Dict]:
        """
        Return the full event dict from The Odds API for the given matchup, including all bookmakers and markets.
        Shape (per The Odds API): { id, commence_time, home_team, away_team, bookmakers: [ { key, title, last_update, markets: [...] } ] }
        """
        sport_key = self.SPORT_KEYS.get((sport or '').lower())
        if not sport_key or not self.api_key:
            return None
        url = f"{self.BASE_URL}/sports/{sport_key}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': self.regions,
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'american',
        }
        home_n = self._normalize(home_team)
        away_n = self._normalize(away_team)
        # Canonical aliases to improve matching across providers
        try:
            from providers.team_aliases import canonicalize_team_name
            home_can = self._normalize(canonicalize_team_name(home_team))
            away_can = self._normalize(canonicalize_team_name(away_team))
        except Exception:
            home_can, away_can = home_n, away_n
        for _ in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                events = resp.json() or []
                # Try strict canonical match
                for ev in events:
                    ev_home = self._normalize(ev.get('home_team'))
                    ev_away = self._normalize(ev.get('away_team'))
                    if (ev_home == home_can and ev_away == away_can) or (ev_home == home_n and ev_away == away_n):
                        bms = ev.get('bookmakers') or []
                        if self.bookmakers_filter:
                            bms = [b for b in bms if b.get('key') in self.bookmakers_filter]
                        ev['bookmakers'] = bms
                        return ev
                # Try reversed home/away if provider differs on designation
                for ev in events:
                    ev_home = self._normalize(ev.get('home_team'))
                    ev_away = self._normalize(ev.get('away_team'))
                    if (ev_home == away_can and ev_away == home_can) or (ev_home == away_n and ev_away == home_n):
                        bms = ev.get('bookmakers') or []
                        if self.bookmakers_filter:
                            bms = [b for b in bms if b.get('key') in self.bookmakers_filter]
                        ev['bookmakers'] = bms
                        return ev
                # Fallback fuzzy: both names substrings
                for ev in events:
                    ev_home = self._normalize(ev.get('home_team') or '')
                    ev_away = self._normalize(ev.get('away_team') or '')
                    if (home_can in ev_home or home_n in ev_home) and (away_can in ev_away or away_n in ev_away):
                        bms = ev.get('bookmakers') or []
                        if self.bookmakers_filter:
                            bms = [b for b in bms if b.get('key') in self.bookmakers_filter]
                        ev['bookmakers'] = bms
                        return ev
                break
            except Exception:
                continue
        return None

    def best_moneyline_prices(self, bookmakers: List[Dict], home_team: str, away_team: str) -> Dict[str, Optional[Tuple[float, str]]]:
        """
        For the given event bookmakers, find the best moneyline price for home and away.
        Returns { 'home': (price, book_title), 'away': (price, book_title) } with None if missing.
        """
        from utils.pricing import american_to_decimal
        best_home: Optional[Tuple[float, str]] = None
        best_away: Optional[Tuple[float, str]] = None
        for bm in bookmakers:
            title = bm.get('title') or bm.get('key') or ''
            for m in (bm.get('markets') or []):
                if m.get('key') != 'h2h':
                    continue
                for outcome in (m.get('outcomes') or []):
                    name = self._normalize(outcome.get('name'))
                    price = outcome.get('price')
                    if price is None:
                        continue
                    dec = american_to_decimal(float(price))
                    if name == self._normalize(home_team):
                        if best_home is None or american_to_decimal(best_home[0]) < dec:
                            best_home = (float(price), title)
                    elif name == self._normalize(away_team):
                        if best_away is None or american_to_decimal(best_away[0]) < dec:
                            best_away = (float(price), title)
        return {'home': best_home, 'away': best_away}

    def best_spread_prices(self, bookmakers: List[Dict], home_team: str, away_team: str, home_line: Optional[float], away_line: Optional[float]) -> Dict[str, Optional[Tuple[float, str]]]:
        """
        For a specific spread point (home_line for home, away_line for away), find best price across books.
        Returns keys 'home' and 'away' with (price, book_title) or None if not found.
        """
        def isclose(a: float, b: float) -> bool:
            try:
                return abs(float(a) - float(b)) < 1e-6
            except Exception:
                return False
        best_home: Optional[Tuple[float, str]] = None
        best_away: Optional[Tuple[float, str]] = None
        for bm in bookmakers:
            title = bm.get('title') or bm.get('key') or ''
            for m in (bm.get('markets') or []):
                if m.get('key') != 'spreads':
                    continue
                for outcome in (m.get('outcomes') or []):
                    try:
                        name = self._normalize(outcome.get('name'))
                        point = outcome.get('point')
                        price = outcome.get('price')
                        if price is None or point is None:
                            continue
                        point = float(point)
                        price = float(price)
                    except Exception:
                        continue
                    if name == self._normalize(home_team) and home_line is not None and isclose(point, float(home_line)):
                        if best_home is None or american_to_decimal(best_home[0]) < american_to_decimal(price):
                            best_home = (price, title)
                    if name == self._normalize(away_team) and away_line is not None and isclose(point, float(away_line)):
                        if best_away is None or american_to_decimal(best_away[0]) < american_to_decimal(price):
                            best_away = (price, title)
        return {'home': best_home, 'away': best_away}

    def best_total_prices(self, bookmakers: List[Dict], point: Optional[float]) -> Dict[str, Optional[Tuple[float, str]]]:
        """
        For a specific total point, find best Over and Under prices across books at that exact point.
        Returns { 'over': (price, title), 'under': (price, title) }.
        """
        def isclose(a: float, b: float) -> bool:
            try:
                return abs(float(a) - float(b)) < 1e-6
            except Exception:
                return False
        best_over: Optional[Tuple[float, str]] = None
        best_under: Optional[Tuple[float, str]] = None
        if point is None:
            return {'over': None, 'under': None}
        for bm in bookmakers:
            title = bm.get('title') or bm.get('key') or ''
            for m in (bm.get('markets') or []):
                if m.get('key') != 'totals':
                    continue
                for outcome in (m.get('outcomes') or []):
                    name = (outcome.get('name') or '').lower()
                    opoint = outcome.get('point')
                    price = outcome.get('price')
                    try:
                        if opoint is None or price is None:
                            continue
                        opoint = float(opoint)
                        price = float(price)
                    except Exception:
                        continue
                    if not isclose(opoint, float(point)):
                        continue
                    if name == 'over':
                        if best_over is None or american_to_decimal(best_over[0]) < american_to_decimal(price):
                            best_over = (price, title)
                    elif name == 'under':
                        if best_under is None or american_to_decimal(best_under[0]) < american_to_decimal(price):
                            best_under = (price, title)
        return {'over': best_over, 'under': best_under}

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


