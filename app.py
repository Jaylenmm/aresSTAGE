from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import threading
import time
from sqlalchemy import inspect, text
from prediction_engine import PredictionEngine

# Initialize Flask app
app = Flask(__name__)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))

# Use PostgreSQL for production (Railway), SQLite for development
if os.getenv('DATABASE_URL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "ares_ai.db")}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Initialize prediction engine
prediction_engine = PredictionEngine()

# Background scheduler for automatic data collection
class DataScheduler:
    def __init__(self):
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the background scheduler"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._schedule_loop, daemon=True)
            self.thread.start()
    
    def stop(self):
        """Stop the background scheduler"""
        self.running = False
        if self.thread:
            self.thread.join()
    
    def _schedule_loop(self):
        """Main scheduling loop with intelligent refresh"""
        last_collection = 0
        collection_interval = 1800  # 30 minutes for more frequent updates
        
        while self.running:
            current_time = time.time()
            
            # Collect data every 30 minutes
            if current_time - last_collection >= collection_interval:
                try:
                    from sports_collector import SportsDataCollector
                    
                    collector = SportsDataCollector()
                    games = collector.collect_all_games()
                    
                    # Also clean up old predictions
                    self._cleanup_old_predictions()
                    
                    last_collection = current_time
                    
                except Exception as e:
                    pass
            
            # Sleep for 5 minutes before checking again
            time.sleep(300)
    
    def _cleanup_old_predictions(self):
        """Clean up old predictions automatically"""
        try:
            with app.app_context():
                from datetime import datetime, timedelta
                
                # Remove predictions older than 7 days
                cutoff_date = datetime.now() - timedelta(days=7)
                old_predictions = Prediction.query.filter(Prediction.created_at < cutoff_date).all()
                
                for prediction in old_predictions:
                    db.session.delete(prediction)
                
                db.session.commit()
                
        except Exception as e:
            pass

USE_THREAD_SCHEDULER = os.getenv('USE_THREAD_SCHEDULER', 'false').lower() == 'true'
data_scheduler = DataScheduler() if USE_THREAD_SCHEDULER else None

def ensure_game_schema():
    """Ensure new odds columns exist on Game table (simple runtime migration)."""
    try:
        with app.app_context():
            engine = db.engine
            inspector = inspect(engine)
            columns = {col['name'] for col in inspector.get_columns('game')}
            ddl_statements = []
            if 'home_moneyline' not in columns:
                ddl_statements.append("ALTER TABLE game ADD COLUMN home_moneyline FLOAT")
            if 'away_moneyline' not in columns:
                ddl_statements.append("ALTER TABLE game ADD COLUMN away_moneyline FLOAT")
            if 'bookmaker' not in columns:
                ddl_statements.append("ALTER TABLE game ADD COLUMN bookmaker VARCHAR(100)")
            if 'odds_last_updated' not in columns:
                ddl_statements.append("ALTER TABLE game ADD COLUMN odds_last_updated TIMESTAMP")
            if ddl_statements:
                try:
                    with engine.begin() as conn:
                        for ddl in ddl_statements:
                            try:
                                conn.execute(text(ddl))
                            except Exception:
                                continue
                except Exception:
                    pass
    except Exception:
        pass

# Database utility functions
def add_game(home_team, away_team, date, sport, spread=None, total=None, status='upcoming', home_score=0, away_score=0):
    """Add a new game to the database"""
    game = Game(
        home_team=home_team,
        away_team=away_team,
        date=date,
        sport=sport,
        spread=spread,
        total=total,
        status=status,
        home_score=home_score,
        away_score=away_score
    )
    db.session.add(game)
    db.session.commit()
    return game

def get_upcoming_games(limit=None):
    """Get all upcoming games"""
    query = Game.query.filter(Game.status == 'upcoming').order_by(Game.date.asc())
    if limit:
        query = query.limit(limit)
    return query.all()

def get_games_by_sport(sport, limit=None):
    """Get games filtered by sport"""
    query = Game.query.filter(Game.sport == sport).order_by(Game.date.desc())
    if limit:
        query = query.limit(limit)
    return query.all()

def get_games_with_betting_info():
    """Get games that have spread or total betting information"""
    return Game.query.filter(
        db.or_(Game.spread.isnot(None), Game.total.isnot(None))
    ).order_by(Game.date.asc()).all()

def update_game_score(game_id, home_score, away_score, status='completed'):
    """Update game scores and status"""
    game = Game.query.get(game_id)
    if game:
        game.home_score = home_score
        game.away_score = away_score
        game.status = status
        db.session.commit()
        return game
    return None

# Database Models
class Game(db.Model):
    """Model for storing game/sports match data with betting information"""
    id = db.Column(db.Integer, primary_key=True)
    home_team = db.Column(db.String(100), nullable=False)
    away_team = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    sport = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='upcoming')
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    spread = db.Column(db.Float, nullable=True)  # Point spread (negative for home team favorite)
    total = db.Column(db.Float, nullable=True)   # Over/under total points
    home_moneyline = db.Column(db.Float, nullable=True)
    away_moneyline = db.Column(db.Float, nullable=True)
    bookmaker = db.Column(db.String(100), nullable=True)
    odds_last_updated = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to predictions
    predictions = db.relationship('Prediction', backref='game', lazy=True)
    
    def __repr__(self):
        return f'<Game {self.home_team} vs {self.away_team}>'
    
    def to_dict(self):
        """Convert game to dictionary for API responses"""
        return {
            'id': self.id,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'date': self.date.isoformat(),
            'sport': self.sport,
            'status': self.status,
            'home_score': self.home_score,
            'away_score': self.away_score,
            'spread': self.spread,
            'total': self.total,
            'home_moneyline': self.home_moneyline,
            'away_moneyline': self.away_moneyline,
            'bookmaker': self.bookmaker,
            'odds_last_updated': self.odds_last_updated.isoformat() if self.odds_last_updated else None,
            'created_at': self.created_at.isoformat()
        }

class Prediction(db.Model):
    """Model for storing AI predictions"""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    predicted_winner = db.Column(db.String(100), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    prediction_type = db.Column(db.String(50), default='winner')
    odds = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Prediction: {self.predicted_winner} (confidence: {self.confidence})>'

# Routes
@app.route('/')
def dashboard():
    """Main dashboard page"""
    games = Game.query.filter(Game.status.in_(['upcoming', 'live'])).order_by(Game.date.asc()).limit(10).all()
    predictions = Prediction.query.order_by(Prediction.created_at.desc()).limit(5).all()
    return render_template('dashboard.html', games=games, predictions=predictions)

@app.route('/games')
def games():
    """Games listing page"""
    games = Game.query.filter(Game.status.in_(['upcoming', 'live', 'completed'])).order_by(Game.date.desc()).limit(50).all()
    return render_template('games.html', games=games)

@app.route('/predictions')
def predictions():
    """Predictions page"""
    predictions = Prediction.query.order_by(Prediction.created_at.desc()).limit(100).all()
    return render_template('predictions.html', predictions=predictions)

@app.route('/api/games', methods=['GET'])
def api_games():
    """API endpoint for games data"""
    games = Game.query.filter(Game.status.in_(['upcoming', 'live'])).order_by(Game.date.asc()).limit(20).all()
    return jsonify([game.to_dict() for game in games])

@app.route('/api/games/upcoming', methods=['GET'])
def api_upcoming_games():
    """API endpoint for upcoming games"""
    games = get_upcoming_games()
    return jsonify([game.to_dict() for game in games])

@app.route('/api/games/betting', methods=['GET'])
def api_games_with_betting():
    """API endpoint for games with betting information"""
    games = get_games_with_betting_info()
    return jsonify([game.to_dict() for game in games])

@app.route('/api/predictions', methods=['GET'])
def api_predictions():
    """API endpoint for predictions data"""
    predictions = Prediction.query.order_by(Prediction.created_at.desc()).all()
    return jsonify([{
        'id': prediction.id,
        'game_id': prediction.game_id,
        'predicted_winner': prediction.predicted_winner,
        'confidence': prediction.confidence,
        'created_at': prediction.created_at.isoformat()
    } for prediction in predictions])

@app.route('/collect-data', methods=['POST'])
def collect_sports_data():
    """Trigger sports data collection with automatic cleanup"""
    try:
        from sports_collector import SportsDataCollector
        
        # Force a complete refresh
        collector = SportsDataCollector()
        games = collector.collect_all_games()
        
        # Get updated game count
        with app.app_context():
            total_games = Game.query.count()
            upcoming_games = Game.query.filter(Game.status.in_(['upcoming', 'live'])).count()
        
        return jsonify({
            'success': True,
            'message': f'Successfully refreshed {len(games)} games',
            'games_count': len(games),
            'total_games': total_games,
            'upcoming_games': upcoming_games
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error collecting data: {str(e)}'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        with app.app_context():
            total_games = Game.query.count()
            recent_games = Game.query.filter(Game.status.in_(['upcoming', 'live'])).count()
            latest_collection = Game.query.order_by(Game.created_at.desc()).first()
            
        return jsonify({
            'status': 'healthy',
            'total_games': total_games,
            'active_games': recent_games,
            'last_update': latest_collection.created_at.isoformat() if latest_collection else None
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/predict', methods=['POST'])
def make_prediction():
    """Make a prediction for a game"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['home_team', 'away_team', 'sport']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400
        
        # Make prediction
        prediction = prediction_engine.make_full_prediction(
            data['home_team'],
            data['away_team'],
            data['sport']
        )
        
        # Save prediction to database if game_id provided
        if 'game_id' in data and data['game_id']:
            try:
                # Save spread prediction
                spread_pred = Prediction(
                    game_id=data['game_id'],
                    predicted_winner=f"{data['home_team']} -{prediction['spread_prediction']['predicted_spread']}" if prediction['spread_prediction']['predicted_spread'] > 0 else f"{data['away_team']} +{abs(prediction['spread_prediction']['predicted_spread'])}",
                    confidence=prediction['spread_prediction']['confidence'] / 100,
                    prediction_type='spread'
                )
                db.session.add(spread_pred)
                
                # Save total prediction
                total_pred = Prediction(
                    game_id=data['game_id'],
                    predicted_winner=f"Over {prediction['total_prediction']['predicted_total']}",
                    confidence=prediction['total_prediction']['confidence'] / 100,
                    prediction_type='total'
                )
                db.session.add(total_pred)
                
                db.session.commit()
            except Exception as e:
                print(f"Warning: Could not save prediction to database: {e}")
        
        return jsonify({
            'success': True,
            'prediction': prediction
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error making prediction: {str(e)}'
        }), 500

@app.route('/predictions/new')
def new_prediction():
    """Page for making new predictions"""
    games = Game.query.filter(Game.status == 'upcoming').order_by(Game.date.asc()).all()
    return render_template('new_prediction.html', games=games)

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()
        ensure_game_schema()
    
    # Start background scheduler if enabled
    if data_scheduler:
        data_scheduler.start()
    
    try:
        # Run the app
        port = int(os.getenv('PORT', 5000))
        debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        app.run(debug=debug, host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        if data_scheduler:
            data_scheduler.stop()
    except Exception as e:
        if data_scheduler:
            data_scheduler.stop()
        raise
