from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import threading
import time
from sqlalchemy import inspect, text
from prediction_engine import PredictionEngine
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))

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

# Auth setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

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

class Parlay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default='active')  # active/completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SavedBet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parlay_id = db.Column(db.Integer, db.ForeignKey('parlay.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    sport = db.Column(db.String(50), nullable=False)
    team = db.Column(db.String(120), nullable=True)
    opponent = db.Column(db.String(120), nullable=True)
    bet_type = db.Column(db.String(50), nullable=False)  # moneyline/spread/total
    line = db.Column(db.Float, nullable=True)
    price = db.Column(db.Float, nullable=True)
    probability = db.Column(db.Float, nullable=True)
    event_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parlay = db.relationship('Parlay', backref=db.backref('bets', lazy=True))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None

# Routes
@app.route('/')
def home():
    """Mobile-first home page showing live, featured, and upcoming games"""
    try:
        selected_sport = request.args.get('sport')
        date_range = (request.args.get('range') or 'today').lower()
        sort_by = (request.args.get('sort') or 'time').lower()

        base_query = Game.query.filter(Game.status.in_(['upcoming', 'live']))
        if selected_sport:
            base_query = base_query.filter(Game.sport == selected_sport)
        # Date range filter (assumes stored datetimes are US/Eastern naive)
        from datetime import timedelta, datetime as _dt
        import pytz as _p
        est = _p.timezone('US/Eastern')
        now_est = _dt.now(est).replace(tzinfo=None)
        if date_range == '3d':
            end = now_est + timedelta(days=3)
            base_query = base_query.filter(Game.date <= end)
        elif date_range == '7d':
            end = now_est + timedelta(days=7)
            base_query = base_query.filter(Game.date <= end)
        else:  # today
            end = _dt(now_est.year, now_est.month, now_est.day, 23, 59, 59)
            base_query = base_query.filter(Game.date <= end)

        all_upcoming = base_query.order_by(Game.date.asc()).limit(100).all()

        live_games = [g for g in all_upcoming if g.status == 'live'][:10]
        upcoming_games = [g for g in all_upcoming if g.status != 'live']

        # Sorting
        if sort_by == 'odds':
            def odds_weight(g):
                has = int(any([g.home_moneyline is not None, g.away_moneyline is not None, g.spread is not None, g.total is not None]))
                return (-has, g.date)
            upcoming_games.sort(key=odds_weight)
        elif sort_by == 'sport':
            upcoming_games.sort(key=lambda g: (g.sport or '', g.date))
        else:  # time
            upcoming_games.sort(key=lambda g: g.date)
        upcoming_games = upcoming_games[:50]

        # Featured: games with betting info
        featured_query = Game.query.filter(
            Game.status.in_(['upcoming', 'live'])
        )
        if selected_sport:
            featured_query = featured_query.filter(Game.sport == selected_sport)
        featured_games = featured_query.filter(
            db.or_(Game.spread.isnot(None), Game.total.isnot(None), Game.home_moneyline.isnot(None), Game.away_moneyline.isnot(None))
        ).order_by(Game.date.asc()).limit(12).all()

        # Available sports for quick filters
        distinct_sports = [row[0] for row in db.session.query(Game.sport).distinct().all()]
        # Maintain a familiar order
        preferred_order = ['nfl', 'nba', 'mlb', 'nhl', 'cfb', 'soccer', 'golf']
        sports = [s for s in preferred_order if s in distinct_sports] + [s for s in distinct_sports if s not in preferred_order]

        return render_template('home.html',
                               sports=sports,
                               selected_sport=selected_sport,
                               date_range=date_range,
                               sort_by=sort_by,
                               live_games=live_games,
                               featured_games=featured_games,
                               upcoming_games=upcoming_games)
    except Exception as e:
        # Safe fallback: render home with minimal context
        try:
            distinct_sports = [row[0] for row in db.session.query(Game.sport).distinct().all()]
        except Exception:
            distinct_sports = []
        return render_template('home.html',
                               sports=distinct_sports,
                               selected_sport=None,
                               date_range='today',
                               sort_by='time',
                               live_games=[],
                               featured_games=[],
                               upcoming_games=[])

 

@app.route('/games')
def games():
    """Reuse home layout for games page for consistency"""
    return redirect(url_for('home'))

 

@app.route('/check-your-bet')
def check_your_bet():
    """Mobile-first page to search teams/players and evaluate bets"""
    return render_template('check_bet.html')

@app.route('/api/search', methods=['GET'])
def api_search():
    """Autosuggest teams from upcoming/live games (players TBD)"""
    try:
        q = (request.args.get('q') or '').strip().lower()
        if not q:
            return jsonify([])
        games = Game.query.filter(Game.status.in_(['upcoming', 'live'])).all()
        suggestions = set()
        for g in games:
            if q in (g.home_team or '').lower():
                suggestions.add(g.home_team)
            if q in (g.away_team or '').lower():
                suggestions.add(g.away_team)
        result = [{'type': 'team', 'name': name} for name in sorted(suggestions)][:20]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check_bet_games', methods=['GET'])
def api_check_bet_games():
    """Return normalized game cards with ML, spread, total for a team query."""
    try:
        q = (request.args.get('q') or '').strip().lower()
        if not q:
            return jsonify({'success': True, 'games': []})
        games = Game.query.filter(Game.status.in_(['upcoming', 'live']))\
            .filter(db.or_(Game.home_team.ilike(f"%{q}%"), Game.away_team.ilike(f"%{q}%")))\
            .order_by(Game.date.asc()).limit(20).all()
        cards = []
        for g in games:
            cards.append({
                'game_id': g.id,
                'sport': g.sport,
                'date': g.date.isoformat(),
                'home_team': g.home_team,
                'away_team': g.away_team,
                'home_moneyline': g.home_moneyline,
                'away_moneyline': g.away_moneyline,
                'spread': g.spread,  # interpret as home spread
                'total': g.total,
                'bookmaker': g.bookmaker,
            })
        return jsonify({'success': True, 'games': cards})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check_bet_options', methods=['GET'])
def api_check_bet_options():
    """Given an entity (team), return available bets with probabilities and reasons."""
    try:
        name = (request.args.get('entity') or '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Missing entity'}), 400
        normalized = name.lower()
        # Find upcoming/live games involving this team
        games = Game.query.filter(
            Game.status.in_(['upcoming', 'live']),
            db.or_(Game.home_team.ilike(f"%{name}%"), Game.away_team.ilike(f"%{name}%"))
        ).order_by(Game.date.asc()).limit(5).all()
        options = []
        for g in games:
            is_home = g.home_team.lower() == normalized
            is_away = g.away_team.lower() == normalized
            if not (is_home or is_away):
                # Fuzzy match may not be exact; determine closest
                is_home = normalized in (g.home_team or '').lower()
                is_away = normalized in (g.away_team or '').lower()

            # Use prediction engine for probability estimates
            try:
                pred = prediction_engine.make_full_prediction(g.home_team, g.away_team, g.sport)
            except Exception:
                pred = None

            # Moneyline
            if g.home_moneyline is not None or g.away_moneyline is not None:
                price = g.home_moneyline if is_home else (g.away_moneyline if is_away else None)
                if price is not None:
                    prob = None
                    reason = 'Based on recent form and matchup.'
                    if pred and 'spread_prediction' in pred:
                        prob = round(pred['spread_prediction'].get('confidence', 60), 1)
                        reason = f"Predicted edge on the spread suggests {name} value."
                    options.append({
                        'game_id': g.id,
                        'type': 'moneyline',
                        'team': name,
                        'price': price,
                        'probability': prob,
                        'reason': reason,
                        'opponent': g.away_team if is_home else g.home_team,
                        'date': g.date.isoformat(),
                        'sport': g.sport
                    })

            # Spread
            if g.spread is not None:
                team_line = g.spread if is_home else (-g.spread if is_away else None)
                if team_line is not None:
                    prob = None
                    reason = 'Line vs predicted spread analysis.'
                    if pred and 'spread_prediction' in pred:
                        model_spread = pred['spread_prediction'].get('predicted_spread')
                        conf = pred['spread_prediction'].get('confidence')
                        prob = round(conf, 1) if conf is not None else None
                        if model_spread is not None:
                            edge = (model_spread - team_line) if is_home else ((-model_spread) - team_line)
                            reason = f"Model edge {edge:+.1f} vs line {team_line:+.1f}."
                    options.append({
                        'game_id': g.id,
                        'type': 'spread',
                        'team': name,
                        'line': team_line,
                        'probability': prob,
                        'reason': reason,
                        'opponent': g.away_team if is_home else g.home_team,
                        'date': g.date.isoformat(),
                        'sport': g.sport
                    })

            # Total
            if g.total is not None:
                prob = None
                reason = 'Total vs model projection.'
                if pred and 'total_prediction' in pred:
                    model_total = pred['total_prediction'].get('predicted_total')
                    conf = pred['total_prediction'].get('confidence')
                    prob = round(conf, 1) if conf is not None else None
                    if model_total is not None:
                        diff = model_total - g.total
                        reason = f"Model total {model_total:.1f} vs line {g.total:.1f} (Δ {diff:+.1f})."
                options.append({
                    'game_id': g.id,
                    'type': 'total',
                    'line': g.total,
                    'probability': prob,
                    'reason': reason,
                    'teams': f"{g.away_team} @ {g.home_team}",
                    'date': g.date.isoformat(),
                    'sport': g.sport
                })

        return jsonify({'success': True, 'options': options})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bets/save', methods=['POST'])
def api_save_bet():
    """Save a user's selected bet and our probability for later accuracy checks."""
    try:
        data = request.get_json() or {}
        # Minimal required: bet type and sport (sport can be inferred from game if provided)
        if not data.get('type'):
            return jsonify({'success': False, 'error': 'Missing field: type'}), 400
        group_type = (data.get('group_type') or 'single').lower()  # 'single' or 'parlay'
        parlay_name = (data.get('parlay_name') or '').strip()

        # Resolve or create parlay
        active_parlays = Parlay.query.filter_by(status='active').all()
        if group_type == 'parlay':
            if not parlay_name:
                return jsonify({'success': False, 'error': 'parlay_name required'}), 400
            parlay = Parlay.query.filter_by(name=parlay_name, status='active').first()
            if not parlay:
                # Enforce up to 5 active setups
                if len(active_parlays) >= 5:
                    return jsonify({'success': False, 'error': 'Maximum 5 active setups reached'}), 400
                parlay = Parlay(name=parlay_name)
                db.session.add(parlay)
                db.session.flush()
        else:  # single -> create a dedicated setup
            # Reuse a single bucket named Single-# if under 5
            # Prefer a parlay named 'Singles' if exists and <5 legs
            parlay = Parlay.query.filter_by(name='Singles', status='active').first()
            if not parlay:
                if len(active_parlays) >= 5:
                    return jsonify({'success': False, 'error': 'Maximum 5 active setups reached'}), 400
                parlay = Parlay(name='Singles')
                db.session.add(parlay)
                db.session.flush()

        # Map to a game if provided
        g = None
        game_id = data.get('game_id')
        if game_id:
            try:
                g = Game.query.get(int(game_id))
            except Exception:
                g = None

        saved = SavedBet(
            parlay_id=parlay.id,
            game_id=g.id if g else None,
            sport=data.get('sport') or (g.sport if g else ''),
            team=data.get('team'),
            opponent=data.get('opponent'),
            bet_type=data.get('type'),
            line=float(data.get('line')) if data.get('line') is not None else None,
            price=float(data.get('price')) if data.get('price') is not None else None,
            probability=float(data.get('probability')) if data.get('probability') is not None else None,
            event_date=g.date if g else (datetime.fromisoformat(data.get('date')) if data.get('date') else None),
        )
        db.session.add(saved)
        db.session.commit()
        return jsonify({'success': True, 'id': saved.id, 'parlay_id': parlay.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/parlays', methods=['GET'])
def api_list_parlays():
    try:
        # Active parlays only; a parlay is completed when all linked games are completed
        parlays = Parlay.query.filter_by(status='active').all()
        result = []
        for p in parlays:
            bets = []
            active_bets = 0
            for b in p.bets:
                # If linked to a game, consider active only if game not completed
                is_active = True
                if b.game_id:
                    g = Game.query.get(b.game_id)
                    if g and g.status == 'completed':
                        is_active = False
                if is_active:
                    active_bets += 1
                bets.append({
                    'id': b.id,
                    'game_id': b.game_id,
                    'sport': b.sport,
                    'team': b.team,
                    'opponent': b.opponent,
                    'type': b.bet_type,
                    'line': b.line,
                    'price': b.price,
                    'probability': b.probability,
                    'date': b.event_date.isoformat() if b.event_date else None,
                    'active': is_active
                })
            # Auto-complete parlay if no active bets remain
            if active_bets == 0 and bets:
                p.status = 'completed'
                db.session.commit()
                continue
            result.append({'id': p.id, 'name': p.name, 'status': p.status, 'bets': bets})
        return jsonify({'success': True, 'parlays': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bets/delete', methods=['POST'])
def api_delete_bet():
    try:
        data = request.get_json() or {}
        bet_id = data.get('id')
        if not bet_id:
            return jsonify({'success': False, 'error': 'Missing id'}), 400
        bet = SavedBet.query.get(int(bet_id))
        if not bet:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        parlay = bet.parlay
        db.session.delete(bet)
        db.session.commit()
        # Optionally mark parlay completed if empty
        if parlay and not parlay.bets:
            parlay.status = 'completed'
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

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

@app.route('/api/diagnostics/providers', methods=['GET'])
def provider_diagnostics():
    """Quick diagnostics to verify provider responses and DB counts"""
    try:
        from sports_collector import SportsDataCollector
        col = SportsDataCollector()
        summary = {}
        summary['lookahead_days'] = getattr(col, 'lookahead_days', None)
        # Fetch without saving
        nfl = col.collect_nfl_games()
        nba = col.collect_nba_games()
        mlb = col.collect_mlb_games()
        nhl = col.collect_nhl_games()
        cfb = col.collect_cfb_games()
        soccer = col.collect_soccer_games()
        golf = col.collect_golf_events()
        summary['schedules'] = {
            'nfl': len(nfl), 'nba': len(nba), 'mlb': len(mlb), 'nhl': len(nhl), 'cfb': len(cfb), 'soccer': len(soccer), 'golf': len(golf)
        }
        # DB counts
        total_games = Game.query.count()
        upcoming = Game.query.filter(Game.status.in_(['upcoming','live'])).count()
        summary['db'] = {'total_games': total_games, 'upcoming_or_live': upcoming}
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/diagnostics/odds', methods=['GET'])
def odds_diagnostics():
    """Inspect raw odds events per sport to verify feed and naming."""
    try:
        from providers.odds_client import OddsClient
        sport = (request.args.get('sport') or '').strip().lower() or 'nfl'
        oc = OddsClient()
        events = oc.fetch_odds_for_sport(sport)
        preview = [{
            'home_team': e.get('home_team'),
            'away_team': e.get('away_team'),
            'commence_time': e.get('commence_time').isoformat() if e.get('commence_time') else None,
            'bookmaker': e.get('bookmaker')
        } for e in events[:20]]
        return jsonify({'success': True, 'sport': sport, 'count': len(events), 'sample': preview})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/seed_from_odds', methods=['POST'])
def admin_seed_from_odds():
    """Force seeding upcoming games from odds events (real provider data)."""
    try:
        from sports_collector import SportsDataCollector
        col = SportsDataCollector()
        created = col._build_games_from_odds()
        if created:
            col.save_games_to_db(created)
        return jsonify({'success': True, 'created': len(created)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        if not email or not password:
            return render_template('register.html', error='Email and password required')
        exists = User.query.filter_by(email=email).first()
        if exists:
            return render_template('register.html', error='Email already registered')
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# Ensure database is ready at import time (for Gunicorn & Celery)
def ensure_database_initialized():
    try:
        with app.app_context():
            db.create_all()
            ensure_game_schema()
    except Exception:
        pass

# Run initialization immediately so health checks and workers have tables
ensure_database_initialized()

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
