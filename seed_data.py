"""
Script to populate the database with sample data for testing
Run this after setting up the database to add some sample games and predictions
"""

from app import app, db, Game, Prediction, add_game
from datetime import datetime, timedelta
import random

def seed_database():
    """Initialize database tables and add sample data"""
    
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Clear existing data
        db.session.query(Prediction).delete()
        db.session.query(Game).delete()
        db.session.commit()
        
        # Sample games with betting information
        sample_games = [
            # NFL Games
            {
                'home_team': 'Kansas City Chiefs',
                'away_team': 'Buffalo Bills',
                'date': datetime.now() + timedelta(days=1, hours=20),
                'sport': 'football',
                'spread': -3.5,
                'total': 52.5,
                'status': 'upcoming'
            },
            {
                'home_team': 'Dallas Cowboys',
                'away_team': 'Philadelphia Eagles',
                'date': datetime.now() + timedelta(days=2, hours=16),
                'sport': 'football',
                'spread': -1.5,
                'total': 48.0,
                'status': 'upcoming'
            },
            {
                'home_team': 'Miami Dolphins',
                'away_team': 'New York Jets',
                'date': datetime.now() + timedelta(days=3, hours=13),
                'sport': 'football',
                'spread': -7.0,
                'total': 45.5,
                'status': 'upcoming'
            },
            
            # NBA Games
            {
                'home_team': 'Los Angeles Lakers',
                'away_team': 'Boston Celtics',
                'date': datetime.now() + timedelta(days=1, hours=19),
                'sport': 'basketball',
                'spread': -2.5,
                'total': 225.5,
                'status': 'upcoming'
            },
            {
                'home_team': 'Golden State Warriors',
                'away_team': 'Phoenix Suns',
                'date': datetime.now() + timedelta(days=2, hours=20),
                'sport': 'basketball',
                'spread': -4.0,
                'total': 230.0,
                'status': 'upcoming'
            },
            
            # MLB Games
            {
                'home_team': 'New York Yankees',
                'away_team': 'Boston Red Sox',
                'date': datetime.now() + timedelta(days=1, hours=18),
                'sport': 'baseball',
                'spread': -1.5,
                'total': 8.5,
                'status': 'upcoming'
            },
            {
                'home_team': 'Los Angeles Dodgers',
                'away_team': 'San Francisco Giants',
                'date': datetime.now() + timedelta(days=2, hours=19),
                'sport': 'baseball',
                'spread': -1.5,
                'total': 7.5,
                'status': 'upcoming'
            },
            
            # Completed games for testing
            {
                'home_team': 'Tampa Bay Buccaneers',
                'away_team': 'New Orleans Saints',
                'date': datetime.now() - timedelta(days=1),
                'sport': 'football',
                'spread': -3.0,
                'total': 50.0,
                'status': 'completed',
                'home_score': 24,
                'away_score': 17
            },
            {
                'home_team': 'Denver Nuggets',
                'away_team': 'Miami Heat',
                'date': datetime.now() - timedelta(days=2),
                'sport': 'basketball',
                'spread': -5.5,
                'total': 220.0,
                'status': 'completed',
                'home_score': 108,
                'away_score': 95
            },
            {
                'home_team': 'Houston Astros',
                'away_team': 'Seattle Mariners',
                'date': datetime.now() - timedelta(days=1, hours=12),
                'sport': 'baseball',
                'spread': -1.5,
                'total': 9.0,
                'status': 'completed',
                'home_score': 6,
                'away_score': 4
            }
        ]
        
        # Add sample games
        games_added = []
        for game_data in sample_games:
            game = add_game(**game_data)
            games_added.append(game)
            print(f"✅ Added: {game.home_team} vs {game.away_team} ({game.sport})")
        
        # Add some sample predictions
        sample_predictions = [
            {
                'game_id': games_added[0].id,  # Chiefs vs Bills
                'predicted_winner': 'Kansas City Chiefs',
                'confidence': 0.75,
                'prediction_type': 'spread'
            },
            {
                'game_id': games_added[0].id,  # Chiefs vs Bills
                'predicted_winner': 'Over',
                'confidence': 0.68,
                'prediction_type': 'total'
            },
            {
                'game_id': games_added[3].id,  # Lakers vs Celtics
                'predicted_winner': 'Los Angeles Lakers',
                'confidence': 0.72,
                'prediction_type': 'spread'
            },
            {
                'game_id': games_added[5].id,  # Yankees vs Red Sox
                'predicted_winner': 'New York Yankees',
                'confidence': 0.65,
                'prediction_type': 'spread'
            }
        ]
        
        for pred_data in sample_predictions:
            prediction = Prediction(**pred_data)
            db.session.add(prediction)
            print(f"✅ Added prediction: {prediction.predicted_winner} ({prediction.confidence*100:.0f}% confidence)")
        
        db.session.commit()
        
        print(f"\n🎉 Database seeded successfully!")
        print(f"📊 Added {len(games_added)} games with betting information")
        print(f"🎯 Added {len(sample_predictions)} sample predictions")
        print(f"🏈 NFL: {len([g for g in games_added if g.sport == 'football'])} games")
        print(f"🏀 NBA: {len([g for g in games_added if g.sport == 'basketball'])} games")
        print(f"⚾ MLB: {len([g for g in games_added if g.sport == 'baseball'])} games")

if __name__ == '__main__':
    seed_database()
