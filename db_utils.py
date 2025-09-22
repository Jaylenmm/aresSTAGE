"""
Database utility functions for testing and managing the Ares AI database
"""

from app import app, db, Game, Prediction, add_game, get_upcoming_games, get_games_by_sport, get_games_with_betting_info
from datetime import datetime, timedelta

def show_all_games():
    """Display all games in the database"""
    with app.app_context():
        games = Game.query.order_by(Game.date.desc()).all()
        print(f"\n📊 All Games ({len(games)} total):")
        print("-" * 80)
        for game in games:
            spread_str = f"Spread: {game.spread}" if game.spread else "No spread"
            total_str = f"Total: {game.total}" if game.total else "No total"
            print(f"{game.id:2d}. {game.home_team} vs {game.away_team}")
            print(f"    📅 {game.date.strftime('%Y-%m-%d %H:%M')} | 🏆 {game.sport.title()} | 📊 {game.status.title()}")
            print(f"    💰 {spread_str} | {total_str}")
            if game.status == 'completed':
                print(f"    🏁 Final: {game.home_score} - {game.away_score}")
            print()

def show_upcoming_games():
    """Display upcoming games"""
    with app.app_context():
        games = get_upcoming_games()
        print(f"\n⏰ Upcoming Games ({len(games)} total):")
        print("-" * 60)
        for game in games:
            spread_str = f"Spread: {game.spread}" if game.spread else "No spread"
            total_str = f"Total: {game.total}" if game.total else "No total"
            print(f"🏆 {game.sport.title()}: {game.home_team} vs {game.away_team}")
            print(f"📅 {game.date.strftime('%Y-%m-%d %H:%M')} | 💰 {spread_str} | {total_str}")
            print()

def show_games_by_sport(sport):
    """Display games filtered by sport"""
    with app.app_context():
        games = get_games_by_sport(sport)
        print(f"\n🏆 {sport.title()} Games ({len(games)} total):")
        print("-" * 60)
        for game in games:
            spread_str = f"Spread: {game.spread}" if game.spread else "No spread"
            total_str = f"Total: {game.total}" if game.total else "No total"
            print(f"{game.home_team} vs {game.away_team}")
            print(f"📅 {game.date.strftime('%Y-%m-%d %H:%M')} | 📊 {game.status.title()}")
            print(f"💰 {spread_str} | {total_str}")
            if game.status == 'completed':
                print(f"🏁 Final: {game.home_score} - {game.away_score}")
            print()

def show_betting_games():
    """Display games with betting information"""
    with app.app_context():
        games = get_games_with_betting_info()
        print(f"\n💰 Games with Betting Info ({len(games)} total):")
        print("-" * 70)
        for game in games:
            spread_str = f"Spread: {game.spread}" if game.spread else "No spread"
            total_str = f"Total: {game.total}" if game.total else "No total"
            print(f"🏆 {game.sport.title()}: {game.home_team} vs {game.away_team}")
            print(f"📅 {game.date.strftime('%Y-%m-%d %H:%M')} | 📊 {game.status.title()}")
            print(f"💰 {spread_str} | {total_str}")
            print()

def add_test_game():
    """Add a test game to the database"""
    with app.app_context():
        game = add_game(
            home_team="Test Home Team",
            away_team="Test Away Team",
            date=datetime.now() + timedelta(days=1),
            sport="football",
            spread=-3.5,
            total=45.0
        )
        print(f"✅ Added test game: {game.home_team} vs {game.away_team}")
        return game

def show_predictions():
    """Display all predictions"""
    with app.app_context():
        predictions = Prediction.query.order_by(Prediction.created_at.desc()).all()
        print(f"\n🎯 All Predictions ({len(predictions)} total):")
        print("-" * 80)
        for pred in predictions:
            game = Game.query.get(pred.game_id)
            print(f"🎯 {pred.predicted_winner} ({pred.confidence*100:.0f}% confidence)")
            print(f"   Game: {game.home_team} vs {game.away_team}")
            print(f"   Type: {pred.prediction_type.title()} | Created: {pred.created_at.strftime('%Y-%m-%d %H:%M')}")
            print()

if __name__ == '__main__':
    print("🔧 Ares AI Database Utilities")
    print("=" * 50)
    
    while True:
        print("\nChoose an option:")
        print("1. Show all games")
        print("2. Show upcoming games")
        print("3. Show games by sport")
        print("4. Show games with betting info")
        print("5. Show predictions")
        print("6. Add test game")
        print("7. Exit")
        
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == '1':
            show_all_games()
        elif choice == '2':
            show_upcoming_games()
        elif choice == '3':
            sport = input("Enter sport (football/basketball/baseball): ").strip().lower()
            if sport in ['football', 'basketball', 'baseball']:
                show_games_by_sport(sport)
            else:
                print("❌ Invalid sport. Use: football, basketball, or baseball")
        elif choice == '4':
            show_betting_games()
        elif choice == '5':
            show_predictions()
        elif choice == '6':
            add_test_game()
        elif choice == '7':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1-7.")
