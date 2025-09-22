"""
Sports Data Collector for Ares AI - Enhanced Version
Collects NFL game data with proper week logic and accurate timezone handling
"""

import requests
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import time
import random
import hashlib
import pytz
import os
from app import app, db, Game
from providers.sportsdata_client import SportsDataIOClient
from providers.odds_client import OddsClient

class SportsDataCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # NFL 2025 season schedule - Week 1 starts September 4, 2025
        self.nfl_season_start = datetime(2025, 9, 4)  # Week 1 start date
        self.est_tz = pytz.timezone('US/Eastern')
        
        # Simple cache for API responses (15 minute TTL)
        self.cache = {}
        self.cache_ttl = 15 * 60  # 15 minutes
        self.sdio = SportsDataIOClient()
        self.odds = OddsClient()
        # Lookahead days for schedules (env override)
        try:
            self.lookahead_days = int(os.getenv('SDIO_LOOKAHEAD_DAYS', '7'))
        except Exception:
            self.lookahead_days = 7
    
    def get_nfl_week(self, date=None):
        """Calculate current NFL week based on date (Tuesday-Monday cycle)"""
        if date is None:
            date = datetime.now(self.est_tz)
        
        # Convert to EST if not already
        if date.tzinfo is None:
            date = self.est_tz.localize(date)
        
        # Calculate days since season start
        days_since_start = (date - self.nfl_season_start).days
        
        # Each NFL week runs Tuesday 12:00 AM to Monday 11:59 PM
        # Week 1: Sept 4-8, Week 2: Sept 9-15, etc.
        week_number = (days_since_start // 7) + 1
        
        # Cap at 18 weeks (regular season)
        return min(max(week_number, 1), 18)
    
    def get_week_date_range(self, week_number):
        """Get the date range for a specific NFL week (Tuesday-Monday)"""
        week_start = self.nfl_season_start + timedelta(weeks=week_number-1)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        return week_start, week_end
    
    def collect_nfl_games(self):
        """Collect NFL games from SportsDataIO"""
        try:
            return self.sdio.fetch_upcoming_games('nfl', days_ahead=self.lookahead_days)
        except Exception:
            return []
    
    def collect_nba_games(self):
        """Collect NBA games from SportsDataIO"""
        try:
            return self.sdio.fetch_upcoming_games('nba', days_ahead=self.lookahead_days)
        except Exception:
            return []

    def collect_mlb_games(self):
        try:
            return self.sdio.fetch_upcoming_games('mlb', days_ahead=self.lookahead_days)
        except Exception:
            return []

    def collect_cfb_games(self):
        try:
            return self.sdio.fetch_upcoming_games('cfb', days_ahead=self.lookahead_days)
        except Exception:
            return []

    def collect_soccer_games(self):
        try:
            return self.sdio.fetch_upcoming_games('soccer', days_ahead=self.lookahead_days)
        except Exception:
            return []

    def collect_golf_events(self):
        try:
            return self.sdio.fetch_upcoming_games('golf', days_ahead=self.lookahead_days)
        except Exception:
            return []
    
    def scrape_espn_games(self):
        """Backup web scraping method - not implemented"""
        return []
    
    def save_games_to_db(self, games):
        """Save collected games to database with automatic cleanup"""
        try:
            with app.app_context():
                # Clear old/stale games first (production-level cleanup)
                self._cleanup_stale_games()
                
                saved_count = 0
                updated_count = 0
                
                for game_data in games:
                    # Check if game already exists (more flexible matching)
                    existing_game = Game.query.filter(
                        Game.home_team == game_data['home_team'],
                        Game.away_team == game_data['away_team'],
                        Game.sport == game_data['sport']
                    ).first()
                    
                    if not existing_game:
                        game = Game(**game_data)
                        db.session.add(game)
                        saved_count += 1
                    else:
                        # Update existing game with new data
                        existing_game.date = game_data['date']
                        existing_game.status = game_data['status']
                        existing_game.home_score = game_data['home_score']
                        existing_game.away_score = game_data['away_score']
                        existing_game.spread = game_data.get('spread')
                        existing_game.total = game_data.get('total')
                        # Update odds fields if provided
                        if game_data.get('home_moneyline') is not None:
                            existing_game.home_moneyline = game_data.get('home_moneyline')
                        if game_data.get('away_moneyline') is not None:
                            existing_game.away_moneyline = game_data.get('away_moneyline')
                        if game_data.get('bookmaker'):
                            existing_game.bookmaker = game_data.get('bookmaker')
                        if game_data.get('odds_last_updated'):
                            existing_game.odds_last_updated = game_data.get('odds_last_updated')
                        updated_count += 1
                
                db.session.commit()
                
        except Exception as e:
            db.session.rollback()
    
    def _cleanup_stale_games(self):
        """Remove stale/duplicate games automatically"""
        try:
            # Remove games older than 30 days
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=30)
            
            old_games = Game.query.filter(Game.date < cutoff_date).all()
            for game in old_games:
                db.session.delete(game)
            
            # Remove duplicate games (keep the most recent)
            all_games = Game.query.all()
            seen_games = {}
            duplicates = []
            
            for game in all_games:
                key = (game.home_team, game.away_team, game.sport)
                if key in seen_games:
                    # Keep the newer game, mark older for deletion
                    if game.created_at < seen_games[key].created_at:
                        duplicates.append(game)
                    else:
                        duplicates.append(seen_games[key])
                        seen_games[key] = game
                else:
                    seen_games[key] = game
            
            for game in duplicates:
                db.session.delete(game)
                
        except Exception as e:
            pass  # Continue even if cleanup fails
    
    def collect_all_games(self):
        """Main method to collect all sports data"""
        all_games = []
        
        # NFL
        nfl = self.collect_nfl_games()
        print(f"NFL schedule fetched: {len(nfl)} games (lookahead {self.lookahead_days}d)")
        all_games.extend(nfl)
        time.sleep(0.5)
        # NBA
        nba = self.collect_nba_games()
        print(f"NBA schedule fetched: {len(nba)} games (lookahead {self.lookahead_days}d)")
        all_games.extend(nba)
        time.sleep(0.5)
        # MLB
        mlb = self.collect_mlb_games()
        print(f"MLB schedule fetched: {len(mlb)} games (lookahead {self.lookahead_days}d)")
        all_games.extend(mlb)
        time.sleep(0.5)
        # CFB
        cfb = self.collect_cfb_games()
        print(f"CFB schedule fetched: {len(cfb)} games (lookahead {self.lookahead_days}d)")
        all_games.extend(cfb)
        time.sleep(0.5)
        # Soccer (best-effort)
        soccer = self.collect_soccer_games()
        print(f"Soccer schedule fetched: {len(soccer)} events (lookahead {self.lookahead_days}d)")
        all_games.extend(soccer)
        time.sleep(0.5)
        # Golf (tournaments as events)
        golf = self.collect_golf_events()
        print(f"Golf events fetched: {len(golf)} (lookahead {self.lookahead_days}d)")
        all_games.extend(golf)
        
        # Save to database if SDIO provided games
        if all_games:
            self.save_games_to_db(all_games)
        else:
            # Fallback: seed upcoming from odds if schedules are empty
            try:
                fallback = self._build_games_from_odds()
                if fallback:
                    print(f"Fallback created {len(fallback)} games from odds events")
                    self.save_games_to_db(fallback)
                    all_games = fallback
            except Exception as e:
                print(f"Fallback from odds failed: {e}")
        
        # Also fetch odds to enrich current and upcoming games
        try:
            updated = self._update_odds_for_upcoming()
            print(f"Odds updated on {updated} games")
        except Exception:
            pass
        return all_games

    def _update_odds_for_upcoming(self):
        """Fetch odds from The Odds API and update matching games."""
        with app.app_context():
            # Query upcoming and live games only
            upcoming_games = Game.query.filter(Game.status.in_(['upcoming', 'live'])).all()
            if not upcoming_games:
                return 0
            # Fetch odds per sport and build a quick lookup
            sports = set(g.sport.lower() for g in upcoming_games)
            odds_by_key = {}
            for sport in sports:
                odds_list = self.odds.fetch_odds_for_sport(sport)
                print(f"Odds fetched for {sport}: {len(odds_list)} events")
                for o in odds_list:
                    key = (o['home_team'], o['away_team'], sport)
                    odds_by_key[key] = o
            # Update games
            updated = 0
            for g in upcoming_games:
                key = (g.home_team, g.away_team, g.sport.lower())
                match = odds_by_key.get(key)
                if not match:
                    # try reversed order if provider orders teams differently
                    key_rev = (g.away_team, g.home_team, g.sport.lower())
                    match = odds_by_key.get(key_rev)
                if match:
                    g.spread = match.get('spread', g.spread)
                    g.total = match.get('total', g.total)
                    g.home_moneyline = match.get('home_moneyline', g.home_moneyline)
                    g.away_moneyline = match.get('away_moneyline', g.away_moneyline)
                    g.bookmaker = match.get('bookmaker', g.bookmaker)
                    g.odds_last_updated = match.get('last_update') or g.odds_last_updated
                    updated += 1
            if updated:
                db.session.commit()
            return updated

    def _build_games_from_odds(self):
        """When schedules are empty, create upcoming games from odds events for supported sports."""
        created = []
        now = datetime.utcnow()
        for sport in ['nfl', 'nba', 'mlb', 'cfb']:
            odds_list = self.odds.fetch_odds_for_sport(sport)
            print(f"Fallback odds events for {sport}: {len(odds_list)}")
            for ev in odds_list:
                dt = ev.get('commence_time') or (now + timedelta(hours=4))
                created.append({
                    'home_team': ev.get('home_team'),
                    'away_team': ev.get('away_team'),
                    'date': dt,
                    'sport': sport,
                    'status': 'upcoming',
                    'home_score': 0,
                    'away_score': 0,
                    'spread': ev.get('spread'),
                    'total': ev.get('total'),
                    'home_moneyline': ev.get('home_moneyline'),
                    'away_moneyline': ev.get('away_moneyline'),
                    'bookmaker': ev.get('bookmaker'),
                    'odds_last_updated': ev.get('last_update'),
                })
        # If nothing, return empty list
        return created
    
    def _get_realistic_spread(self, home_team, away_team, sport):
        """Generate realistic spreads based on team strength"""
        # Simple team strength mapping
        team_strength = {
            'kansas city chiefs': 0.8, 'buffalo bills': 0.7, 'dallas cowboys': 0.6,
            'philadelphia eagles': 0.6, 'miami dolphins': 0.5, 'tampa bay buccaneers': 0.5,
            'green bay packers': 0.6, 'san francisco 49ers': 0.7, 'baltimore ravens': 0.6,
            'cincinnati bengals': 0.5, 'los angeles rams': 0.5, 'denver broncos': 0.4,
            'las vegas raiders': 0.3, 'new york jets': 0.2, 'new york giants': 0.2,
            'chicago bears': 0.3, 'detroit lions': 0.4, 'minnesota vikings': 0.4,
            'atlanta falcons': 0.3, 'carolina panthers': 0.2, 'new orleans saints': 0.4,
            'houston texans': 0.3, 'indianapolis colts': 0.4, 'jacksonville jaguars': 0.3,
            'tennessee titans': 0.4, 'arizona cardinals': 0.2, 'seattle seahawks': 0.4,
            'los angeles chargers': 0.4, 'washington commanders': 0.2, 'pittsburgh steelers': 0.5,
            'cleveland browns': 0.3, 'new england patriots': 0.3,
            
            # NBA teams
            'los angeles lakers': 0.7, 'boston celtics': 0.8, 'golden state warriors': 0.6,
            'phoenix suns': 0.5, 'denver nuggets': 0.7, 'miami heat': 0.5,
            'milwaukee bucks': 0.6, 'philadelphia 76ers': 0.5, 'brooklyn nets': 0.4,
            'new york knicks': 0.4, 'chicago bulls': 0.3, 'cleveland cavaliers': 0.4,
            'detroit pistons': 0.2, 'indiana pacers': 0.3, 'atlanta hawks': 0.3,
            'charlotte hornets': 0.2, 'orlando magic': 0.3, 'washington wizards': 0.2,
            'dallas mavericks': 0.5, 'houston rockets': 0.2, 'memphis grizzlies': 0.4,
            'new orleans pelicans': 0.3, 'san antonio spurs': 0.2, 'oklahoma city thunder': 0.3,
            'portland trail blazers': 0.3, 'utah jazz': 0.3, 'minnesota timberwolves': 0.3,
            'sacramento kings': 0.3, 'los angeles clippers': 0.5
        }
        
        home_strength = team_strength.get(home_team.lower(), 0.5)
        away_strength = team_strength.get(away_team.lower(), 0.5)
        
        # Calculate spread (positive = home team favored)
        strength_diff = home_strength - away_strength
        
        if sport == 'football':
            spread = strength_diff * 14  # Scale to realistic NFL spreads
            home_advantage = 3.0
        else:  # basketball
            spread = strength_diff * 8   # Scale to realistic NBA spreads
            home_advantage = 2.5
        
        final_spread = spread + home_advantage
        return round(final_spread * 2) / 2  # Round to nearest 0.5
    
    def _get_realistic_total(self, sport):
        """Generate realistic totals based on sport"""
        base_totals = {
            'football': 45.0,
            'basketball': 220.0,
            'baseball': 8.5
        }
        
        base_total = base_totals.get(sport, 10.0)
        # Add some variation
        variation = random.uniform(-3, 3)
        return round((base_total + variation) * 2) / 2
    

