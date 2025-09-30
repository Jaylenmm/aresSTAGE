"""
Lightweight ESPN scoreboard client for schedules (NFL/MLB).

Endpoints pattern:
  https://site.api.espn.com/apis/site/v2/sports/{sport_group}/{league}/scoreboard?dates=YYYYMMDD

This client returns a list of canonical game dicts compatible with Game(**dict).
"""

from datetime import datetime, timedelta
from typing import List, Dict
import requests


LEAGUE_MAP = {
    'nfl': ('football', 'nfl'),
    'mlb': ('baseball', 'mlb'),
}


class ESPNClient:
    BASE = 'https://site.api.espn.com/apis/site/v2/sports'

    def __init__(self):
        self.session = requests.Session()
        self.timeout_seconds = 12

    def fetch_upcoming_games(self, sport: str, days_ahead: int = 7) -> List[Dict]:
        sport_l = (sport or '').lower()
        if sport_l not in LEAGUE_MAP:
            return []
        group, league = LEAGUE_MAP[sport_l]
        today = datetime.utcnow()
        out: List[Dict] = []
        for d in range(0, max(0, days_ahead) + 1):
            date_str = (today + timedelta(days=d)).strftime('%Y%m%d')
            url = f"{self.BASE}/{group}/{league}/scoreboard"
            try:
                resp = self.session.get(url, params={'dates': date_str}, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json() or {}
            except Exception:
                continue
            events = data.get('events') or []
            for ev in events:
                competitions = ev.get('competitions') or []
                if not competitions:
                    continue
                comp = competitions[0]
                competitors = comp.get('competitors') or []
                if len(competitors) < 2:
                    continue
                # Determine home/away
                home = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
                away = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[-1])
                home_name = (home.get('team') or {}).get('displayName') or home.get('team', {}).get('name') or ''
                away_name = (away.get('team') or {}).get('displayName') or away.get('team', {}).get('name') or ''
                # Time
                dt_raw = ev.get('date') or comp.get('date')
                try:
                    dt = datetime.fromisoformat(dt_raw.replace('Z', '+00:00')) if dt_raw else None
                except Exception:
                    dt = None
                if not (home_name and away_name and dt):
                    continue
                # Status mapping
                status_text = ((ev.get('status') or {}).get('type') or {}).get('name') or ((comp.get('status') or {}).get('type') or {}).get('name') or ''
                status = 'upcoming'
                st_l = status_text.lower()
                if st_l in ('in', 'inprogress', 'status_in_progress'):
                    status = 'live'
                elif st_l in ('final', 'status_final', 'post'):
                    status = 'completed'
                # Scores
                try:
                    home_score = int(home.get('score')) if home.get('score') is not None else 0
                    away_score = int(away.get('score')) if away.get('score') is not None else 0
                except Exception:
                    home_score = 0
                    away_score = 0
                out.append({
                    'home_team': home_name,
                    'away_team': away_name,
                    'date': dt,
                    'sport': sport_l,
                    'status': status,
                    'home_score': home_score,
                    'away_score': away_score,
                    'spread': None,
                    'total': None,
                })
        return out


