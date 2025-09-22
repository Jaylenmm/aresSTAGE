"""
Test script for the sports data collector
Run this to test data collection without starting the full web app
"""

from sports_collector import SportsDataCollector
from app import app, db

def test_collector():
    """Test the sports data collector"""
    print("🧪 Testing Sports Data Collector...")
    
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Initialize collector
        collector = SportsDataCollector()
        
        # Test data collection
        games = collector.collect_all_games()
        
        if games:
            print(f"\n✅ Successfully collected {len(games)} games!")
            print("\n📊 Sample games:")
            for i, game in enumerate(games[:5]):
                print(f"  {i+1}. {game['sport'].title()}: {game['away_team']} @ {game['home_team']}")
                print(f"     Date: {game['date']}")
                print(f"     Status: {game['status']}")
                if game['status'] in ['completed', 'live']:
                    print(f"     Score: {game['away_score']} - {game['home_score']}")
                print()
        else:
            print("❌ No games were collected")
        
        # Show database contents
        from app import Game
        db_games = Game.query.all()
        print(f"📁 Total games in database: {len(db_games)}")

if __name__ == '__main__':
    test_collector()
