"""
SportsDataIO REST client for schedules across multiple sports.

Environment variables supported:
- SPORTSDATAIO_API_KEY (fallback if per-sport keys are not set)
- SDIO_NFL_KEY, SDIO_NBA_KEY, SDIO_MLB_KEY, SDIO_CFB_KEY, SDIO_SOCCER_KEY, SDIO_GOLF_KEY

Notes:
- This client fetches upcoming games for a short horizon (today .. +2 days)
- Returned games are mapped to the app's canonical game dict format
"""

import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz


class SportsDataIOClient:
    BASE_URLS = {
        'nfl': 'https://api.sportsdata.io/v3/nfl/scores/json',
        'nba': 'https://api.sportsdata.io/v3/nba/scores/json',
        'mlb': 'https://api.sportsdata.io/v3/mlb/scores/json',
        'cfb': 'https://api.sportsdata.io/v3/cfb/scores/json',
        'nhl': 'https://api.sportsdata.io/v3/nhl/scores/json',
        # Soccer and Golf APIs have different structures; partial support below
        'soccer': 'https://api.sportsdata.io/v3/soccer/scores/json',
        'golf': 'https://api.sportsdata.io/v3/golf/scores/json',
    }

    def __init__(self):
        self.session = requests.Session()
        self.timeout_seconds = 15
        self.est_tz = pytz.timezone('US/Eastern')

    def _get_key_for_sport(self, sport: str) -> Optional[str]:
        fallback = os.getenv('SPORTSDATAIO_API_KEY')
        per_sport = {
            'nfl': os.getenv('SDIO_NFL_KEY') or fallback,
            'nba': os.getenv('SDIO_NBA_KEY') or fallback,
            'mlb': os.getenv('SDIO_MLB_KEY') or fallback,
            'cfb': os.getenv('SDIO_CFB_KEY') or fallback,
            'nhl': os.getenv('SDIO_NHL_KEY') or fallback,
            'soccer': os.getenv('SDIO_SOCCER_KEY') or fallback,
            'golf': os.getenv('SDIO_GOLF_KEY') or fallback,
        }
        return per_sport.get(sport)

    def _headers(self, sport: str) -> Dict[str, str]:
        key = self._get_key_for_sport(sport)
        if not key:
            raise RuntimeError(f"SportsDataIO API key for {sport} is not configured")
        return {
            'Ocp-Apim-Subscription-Key': key,
        }

    def _get(self, sport: str, path: str) -> List[Dict]:
        base = self.BASE_URLS.get(sport)
        if not base:
            return []
        url = f"{base}/{path}"
        last_exc = None
        for _ in range(3):
            try:
                resp = self.session.get(url, headers=self._headers(sport), timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                last_exc = exc
                continue
        else:
            # All retries failed
            return []
        if isinstance(data, list):
            return data
        return []

    def _date_str(self, dt: datetime) -> str:
        return dt.strftime('%Y-%m-%d')

    def fetch_upcoming_games(self, sport: str, days_ahead: int = 2) -> List[Dict]:
        """
        Fetch upcoming games for a sport for a short range: today .. today+days_ahead.
        Returns a list of canonical game dicts matching the app schema.
        """
        normalized_sport = sport.lower()
        results: List[Dict] = []
        today = datetime.utcnow()

        for delta in range(0, max(0, days_ahead) + 1):
            date_str = self._date_str(today + timedelta(days=delta))

            if normalized_sport in ('nfl', 'nba', 'mlb', 'cfb'):
                # Common GamesByDate endpoint
                try:
                    items = self._get(normalized_sport, f"GamesByDate/{date_str}")
                    for g in items:
                        mapped = self._map_game(normalized_sport, g)
                        if mapped:
                            results.append(mapped)
                except Exception:
                    continue
            elif normalized_sport == 'soccer':
                # Soccer requires competition context; attempt AllGamesByDate if available
                try:
                    items = self._get('soccer', f"Schedule/{date_str}")
                    for g in items:
                        mapped = self._map_soccer_game(g)
                        if mapped:
                            results.append(mapped)
                except Exception:
                    # Best-effort; many accounts require specifying leagues
                    continue
            elif normalized_sport == 'golf':
                # Golf is tournament-based; map next tournaments as upcoming events
                try:
                    tournaments = self._get('golf', 'Tournaments')
                    for t in tournaments:
                        mapped = self._map_golf_event(t)
                        if mapped:
                            results.append(mapped)
                except Exception:
                    continue

        return results

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            # Parse to aware datetime (assume UTC if tz missing), then convert to US/Eastern and return naive
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=pytz.UTC)
            est_dt = parsed.astimezone(self.est_tz)
            return est_dt.replace(tzinfo=None)
        except Exception:
            return None

    def _map_team_name(self, item: Dict, fallback_field: str = 'Team') -> str:
        # Prefer full name fields when available
        return (
            item.get('HomeTeamName')
            or item.get('HomeTeam')
            or item.get(fallback_field)
            or ''
        )

    def _map_game(self, sport: str, item: Dict) -> Optional[Dict]:
        home = item.get('HomeTeam') or item.get('HomeTeamName') or ''
        away = item.get('AwayTeam') or item.get('AwayTeamName') or ''
        dt = self._parse_datetime(item.get('DateTime') or item.get('Day'))
        if not home or not away or not dt:
            return None
        status = 'upcoming'
        if item.get('Status') in ('InProgress', 'InProgressDelayed', 'Scheduled'):
            status = 'live' if item.get('Status', '').startswith('InProgress') else 'upcoming'
        elif item.get('Status') in ('Final', 'F/OT', 'Completed'):
            status = 'completed'

        home_score = item.get('HomeTeamScore') or item.get('HomeScore') or 0
        away_score = item.get('AwayTeamScore') or item.get('AwayScore') or 0

        return {
            'home_team': str(home),
            'away_team': str(away),
            'date': dt,
            'sport': sport,
            'status': status,
            'home_score': int(home_score or 0),
            'away_score': int(away_score or 0),
            'spread': None,
            'total': None,
        }

    def _map_soccer_game(self, item: Dict) -> Optional[Dict]:
        # Soccer schedule structures vary; best-effort mapping
        home = item.get('HomeTeamName') or item.get('HomeTeam') or ''
        away = item.get('AwayTeamName') or item.get('AwayTeam') or ''
        dt = self._parse_datetime(item.get('DateTime') or item.get('Day'))
        if not home or not away or not dt:
            return None
        status = 'upcoming'
        if item.get('Status') in ('InProgress', 'InProgressDelayed'):
            status = 'live'
        elif item.get('Status') in ('Final', 'Completed'):
            status = 'completed'
        return {
            'home_team': str(home),
            'away_team': str(away),
            'date': dt,
            'sport': 'soccer',
            'status': status,
            'home_score': int(item.get('HomeTeamScore') or 0),
            'away_score': int(item.get('AwayTeamScore') or 0),
            'spread': None,
            'total': None,
        }

    def _map_golf_event(self, item: Dict) -> Optional[Dict]:
        # Represent a tournament as a pseudo-game between Field and Field
        name = item.get('Name') or 'Tournament'
        dt = self._parse_datetime(item.get('StartDate'))
        if not dt:
            return None
        return {
            'home_team': f"{name} Field",
            'away_team': "Field",
            'date': dt,
            'sport': 'golf',
            'status': 'upcoming',
            'home_score': 0,
            'away_score': 0,
            'spread': None,
            'total': None,
        }


