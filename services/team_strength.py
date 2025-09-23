from typing import Optional

def get_team_strength(sport: str, team: str) -> float:
    """Return team strength in [0,1]. Uses PlayerAnalyzer when available; defaults to 0.5."""
    try:
        from player_analyzer import PlayerAnalyzer
        pa = PlayerAnalyzer()
        return float(pa.get_team_strength(team))
    except Exception:
        return 0.5

def strength_delta(sport: str, home_team: str, away_team: str) -> float:
    h = get_team_strength(sport, home_team or '')
    a = get_team_strength(sport, away_team or '')
    return h - a

