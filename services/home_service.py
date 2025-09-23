from datetime import timedelta
from typing import List, Dict

def get_featured_upcoming(sport: str, now_est, window_days: int = 7, limit: int = 4) -> List[Game]:
    try:
        # Local import to avoid circular dependency
        from app import Game, db
        window_end = now_est + timedelta(days=window_days)
        q = Game.query.filter(
            Game.status == 'upcoming',
            Game.date >= now_est,
            Game.date <= window_end
        )
        if sport:
            q = q.filter(Game.sport == sport)
        with_bets = q.filter(
            db.or_(
                Game.spread.isnot(None), Game.total.isnot(None),
                Game.home_moneyline.isnot(None), Game.away_moneyline.isnot(None)
            )
        ).order_by(Game.date.asc()).limit(limit*2).all()
        featured = []
        seen = set()
        for g in with_bets:
            if g.id not in seen:
                featured.append(g)
                seen.add(g.id)
            if len(featured) >= limit:
                break
        if len(featured) < limit:
            need = limit - len(featured)
            fillers = q.order_by(Game.date.asc()).limit(need).all()
            for g in fillers:
                if g.id not in seen:
                    featured.append(g)
                    seen.add(g.id)
        return featured[:limit]
    except Exception:
        return []

def get_featured_props(sport: str, limit: int = 4) -> List[Dict]:
    try:
        from providers.odds_client import OddsClient
        oc = OddsClient()
        props = oc.fetch_player_props_for_sport(sport)
        seen = set()
        out = []
        for p in props:
            name = p.get('player_name')
            if not name or name in seen:
                continue
            out.append(p)
            seen.add(name)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []

def get_news(sport: str, limit: int = 5) -> List[Dict]:
    try:
        # Local import to avoid circular dependency
        from app import fetch_espn_articles
        return fetch_espn_articles(sport, limit=limit)
    except Exception:
        return []

