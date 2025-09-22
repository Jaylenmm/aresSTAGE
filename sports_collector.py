"""
Sports Data Collector for Ares AI
Collects NFL and NBA game data from free APIs and web scraping
"""

import requests
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import time
import random
from app import app, db, Game

class SportsDataCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def collect_nfl_games(self):
        """Collect NFL games from ESPN API"""
        try:
            print("🏈 Collecting NFL games...")
            
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
                    
                    # Parse date
                    date_str = event['date']
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    
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
                    
                    games.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'date': game_date,
                        'sport': 'football',
                        'status': status,
                        'home_score': home_score,
                        'away_score': away_score
                    })
                    
                except (KeyError, ValueError, IndexError) as e:
                    print(f"Error parsing NFL game: {e}")
                    continue
            
            print(f"✅ Found {len(games)} NFL games")
            return games
            
        except Exception as e:
            print(f"❌ Error collecting NFL games: {e}")
            return []
    
    def collect_nba_games(self):
        """Collect NBA games from ESPN API"""
        try:
            print("🏀 Collecting NBA games...")
            
            # ESPN NBA API endpoint
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            games = []
            
            for event in data.get('events', []):
                try:
                    # Extract game info
                    home_team = event['competitions'][0]['competitors'][0]['team']['displayName']
                    away_team = event['competitions'][0]['competitors'][1]['team']['displayName']
                    
                    # Parse date
                    date_str = event['date']
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    
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
                    
                    games.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'date': game_date,
                        'sport': 'basketball',
                        'status': status,
                        'home_score': home_score,
                        'away_score': away_score
                    })
                    
                except (KeyError, ValueError, IndexError) as e:
                    print(f"Error parsing NBA game: {e}")
                    continue
            
            print(f"✅ Found {len(games)} NBA games")
            return games
            
        except Exception as e:
            print(f"❌ Error collecting NBA games: {e}")
            return []
    
    def scrape_espn_games(self):
        """Backup web scraping method for ESPN games"""
        try:
            print("🌐 Web scraping ESPN games as backup...")
            
            games = []
            
            # Scrape NFL games
            nfl_url = "https://www.espn.com/nfl/schedule"
            response = self.session.get(nfl_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # This is a simplified scraper - you'd need to parse the actual HTML structure
                # For now, we'll return empty and rely on API
                print("📝 ESPN scraping structure needs implementation")
            
            return games
            
        except Exception as e:
            print(f"❌ Error scraping ESPN: {e}")
            return []
    
    def save_games_to_db(self, games):
        """Save collected games to database"""
        try:
            with app.app_context():
                saved_count = 0
                
                for game_data in games:
                    # Check if game already exists
                    existing_game = Game.query.filter_by(
                        home_team=game_data['home_team'],
                        away_team=game_data['away_team'],
                        date=game_data['date']
                    ).first()
                    
                    if not existing_game:
                        game = Game(**game_data)
                        db.session.add(game)
                        saved_count += 1
                    else:
                        # Update existing game with new data
                        existing_game.status = game_data['status']
                        existing_game.home_score = game_data['home_score']
                        existing_game.away_score = game_data['away_score']
                
                db.session.commit()
                print(f"💾 Saved {saved_count} new games to database")
                
        except Exception as e:
            print(f"❌ Error saving games to database: {e}")
            db.session.rollback()
    
    def collect_all_games(self):
        """Main method to collect all sports data"""
        print("🚀 Starting sports data collection...")
        
        all_games = []
        
        # Try to get NFL games
        nfl_games = self.collect_nfl_games()
        all_games.extend(nfl_games)
        
        # Add delay between requests
        time.sleep(1)
        
        # Try to get NBA games
        nba_games = self.collect_nba_games()
        all_games.extend(nba_games)
        
        # If we got no games from API, try web scraping
        if not all_games:
            print("⚠️ No games from API, trying web scraping...")
            scraped_games = self.scrape_espn_games()
            all_games.extend(scraped_games)
        
        # Save to database
        if all_games:
            self.save_games_to_db(all_games)
            print(f"🎉 Successfully collected {len(all_games)} games total")
        else:
            print("❌ No games collected from any source")
        
        return all_games

def main():
    """Run the sports data collector"""
    collector = SportsDataCollector()
    games = collector.collect_all_games()
    
    if games:
        print("\n📊 Collected Games Summary:")
        for game in games[:10]:  # Show first 10 games
            print(f"  {game['sport'].title()}: {game['away_team']} @ {game['home_team']} - {game['status']}")
    else:
        print("\n❌ No games were collected")

if __name__ == '__main__':
    main()
