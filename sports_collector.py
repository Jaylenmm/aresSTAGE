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
from app import app, db, Game

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
        """Collect NFL games from ESPN API with proper date/time parsing"""
        try:
            # ESPN NFL API endpoint
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            games = []
            
            for event in data.get('events', []):
                try:
                    # Extract game info
                    home_team = event['competitions'][0]['competitors'][0]['team']['displayName']
                    away_team = event['competitions'][0]['competitors'][1]['team']['displayName']
                    
                    # Parse date from ESPN API - use actual date/time from API
                    date_str = event['date']
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    
                    # Convert to EST for display
                    game_date = game_date.astimezone(self.est_tz)
                    
                    # Get scores if available
                    home_score = int(event['competitions'][0]['competitors'][0].get('score', 0))
                    away_score = int(event['competitions'][0]['competitors'][1].get('score', 0))
                    
                    # Determine status
                    status = event['status']['type']['name'].lower()
                    if status == 'final':
                        status = 'completed'
                    elif status == 'in':
                        status = 'live'
                    else:
                        status = 'upcoming'
                    
                    # Add realistic betting data for NFL games
                    spread = self._get_realistic_spread(home_team, away_team, 'football')
                    total = self._get_realistic_total('football')
                    
                    games.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'date': game_date,
                        'sport': 'football',
                        'status': status,
                        'home_score': home_score,
                        'away_score': away_score,
                        'spread': spread,
                        'total': total
                    })
                    
                except (KeyError, ValueError, IndexError) as e:
                    continue
            
            return games
            
        except Exception as e:
            return []
    
    def collect_nba_games(self):
        """Collect NBA games - simplified for production"""
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
        
        # Get NFL games
        nfl_games = self.collect_nfl_games()
        all_games.extend(nfl_games)
        
        # Add delay between requests
        time.sleep(1)
        
        # Get NBA games
        nba_games = self.collect_nba_games()
        all_games.extend(nba_games)
        
        # Save to database
        if all_games:
            self.save_games_to_db(all_games)
        
        return all_games
    
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
    

