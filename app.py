from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import threading
import time
from sqlalchemy import inspect, text
from prediction_engine import PredictionEngine
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup
from utils.pricing import implied_prob as _implied_prob, ev_from_prob_and_odds as _ev_from_prob_and_odds

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))
# Session cookie hardening and persistence
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=14)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['REMEMBER_COOKIE_SECURE'] = False

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
# --- Jinja filters ---
def namecase(value: str) -> str:
    try:
        s = (value or '').strip()
        if not s:
            return ''
        # Handle hyphens and apostrophes properly (e.g., O'Neal, St. Louis)
        parts = []
        for token in s.split(' '):
            if not token:
                parts.append(token)
                continue
            subtokens = token.split('-')
            subcased = []
            for st in subtokens:
                st_l = st.lower()
                if "'" in st_l:
                    apos = st_l.split("'")
                    apos = [a.capitalize() if a else a for a in apos]
                    subcased.append("'".join(apos))
                else:
                    subcased.append(st_l.capitalize())
            parts.append('-'.join(subcased))
        return ' '.join(parts)
    except Exception:
        try:
            return str(value)
        except Exception:
            return ''

app.jinja_env.filters['namecase'] = namecase

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
                    # Roll status forward so we never keep stale 'upcoming' games around
                    _rollover_game_statuses()
                    
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

def _now_est_naive():
    try:
        from utils.time_utils import now_est_naive
        return now_est_naive()
    except Exception:
        from datetime import datetime
        return datetime.now()

def _rollover_game_statuses():
    """Mark past games completed and set near-term games to live. Keeps only ongoing/upcoming visible."""
    try:
        with app.app_context():
            from datetime import timedelta
            now_est = _now_est_naive()
            # Mark clearly past games as completed (older than 6 hours ago)
            past_cutoff = now_est - timedelta(hours=6)
            past = Game.query.filter(Game.status.in_(['upcoming','live']), Game.date < past_cutoff).all()
            for g in past:
                g.status = 'completed'
            # Mark events started within last 6 hours as live if still upcoming
            starting = Game.query.filter(Game.status == 'upcoming', Game.date <= now_est, Game.date >= past_cutoff).all()
            for g in starting:
                g.status = 'live'
            if past or starting:
                db.session.commit()
    except Exception:
        pass

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
            # SavedBet metric columns runtime-migration (SQLite-friendly best effort)
            try:
                sb_columns = {col['name'] for col in inspector.get_columns('saved_bet')}
            except Exception:
                sb_columns = set()
            if 'p_model' not in sb_columns:
                ddl_statements.append("ALTER TABLE saved_bet ADD COLUMN p_model FLOAT")
            if 'implied_prob' not in sb_columns:
                ddl_statements.append("ALTER TABLE saved_bet ADD COLUMN implied_prob FLOAT")
            if 'edge' not in sb_columns:
                ddl_statements.append("ALTER TABLE saved_bet ADD COLUMN edge FLOAT")
            if 'ev' not in sb_columns:
                ddl_statements.append("ALTER TABLE saved_bet ADD COLUMN ev FLOAT")
            if 'ev_per_100' not in sb_columns:
                ddl_statements.append("ALTER TABLE saved_bet ADD COLUMN ev_per_100 FLOAT")
            if 'kelly' not in sb_columns:
                ddl_statements.append("ALTER TABLE saved_bet ADD COLUMN kelly FLOAT")
            # Parlay ownership
            try:
                parlay_columns = {col['name'] for col in inspector.get_columns('parlay')}
            except Exception:
                parlay_columns = set()
            if 'user_id' not in parlay_columns:
                ddl_statements.append("ALTER TABLE parlay ADD COLUMN user_id INTEGER")
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
            'is_odds_stale': (False if not self.odds_last_updated else ((datetime.utcnow() - self.odds_last_updated).total_seconds() > 12*3600)),
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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

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
    # Stored Ares metrics at save time (immutable snapshot)
    p_model = db.Column(db.Float, nullable=True)
    implied_prob = db.Column(db.Float, nullable=True)
    edge = db.Column(db.Float, nullable=True)
    ev = db.Column(db.Float, nullable=True)
    ev_per_100 = db.Column(db.Float, nullable=True)
    kelly = db.Column(db.Float, nullable=True)
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
        selected_sport = request.args.get('sport') or 'nfl'
        date_range = (request.args.get('range') or 'today').lower()
        sort_by = (request.args.get('sort') or 'time').lower()

        base_query = Game.query.filter(Game.status.in_(['upcoming', 'live']))
        if selected_sport:
            base_query = base_query.filter(Game.sport == selected_sport)
        # Date range filter (assumes stored datetimes are US/Eastern naive)
        from utils.time_utils import now_est_naive
        from datetime import datetime as _dt, timedelta
        now_est = now_est_naive()
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

        from services.home_service import get_featured_upcoming, get_featured_props, get_news
        featured_games = get_featured_upcoming(selected_sport, now_est, window_days=7, limit=4)

        # Available sports for quick filters
        distinct_sports = [row[0] for row in db.session.query(Game.sport).distinct().all()]
        # Maintain a familiar order
        preferred_order = ['nfl', 'nba', 'mlb', 'nhl', 'cfb', 'soccer', 'golf']
        sports = [s for s in preferred_order if s in distinct_sports] + [s for s in distinct_sports if s not in preferred_order]

        # If a sport is selected, prepare featured props and news
        featured_props = get_featured_props(selected_sport, limit=4) if selected_sport else []
        news_articles = get_news(selected_sport, limit=5) if selected_sport else []

        return render_template('home.html',
                               sports=sports,
                               selected_sport=selected_sport,
                               date_range=date_range,
                               sort_by=sort_by,
                               live_games=live_games,
                               featured_games=featured_games,
                               upcoming_games=upcoming_games,
                               featured_props=featured_props,
                               news_articles=news_articles)
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
    """Games explorer: filter by sport and search by team names"""
    try:
        selected_sport = (request.args.get('sport') or '').lower()
        q = (request.args.get('q') or '').strip()
        # Show upcoming and live by default
        query = Game.query.filter(Game.status.in_(['upcoming', 'live']))
        if selected_sport and selected_sport != 'all':
            query = query.filter(Game.sport == selected_sport)
        if q:
            query = query.filter(db.or_(Game.home_team.ilike(f"%{q}%"), Game.away_team.ilike(f"%{q}%")))
        games = query.order_by(Game.date.asc()).limit(200).all()
        # Distinct sports for filters
        distinct_sports = [row[0] for row in db.session.query(Game.sport).distinct().all()]
        preferred_order = ['nfl', 'nba', 'mlb', 'nhl', 'cfb', 'soccer', 'golf']
        sports = [s for s in preferred_order if s in distinct_sports] + [s for s in distinct_sports if s not in preferred_order]
        return render_template('games.html', sports=sports, selected_sport=selected_sport or 'all', q=q, games=games)
    except Exception as e:
        return render_template('games.html', sports=[], selected_sport='all', q='', games=[])

 

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

@app.route('/api/picks/evaluate', methods=['POST'])
def api_picks_evaluate():
    """Evaluate a pick: return model probability, implied prob (book), edge, EV, Kelly, and reason."""
    try:
        from services.probabilities import ml_probability, spread_cover_probability, total_over_under_probability
        from utils.pricing import implied_prob, ev_from_prob_and_odds, kelly_fraction, remove_vig_two_way
        data = request.get_json() or {}
        pick_type = (data.get('type') or '').lower()
        sport = (data.get('sport') or '').lower()
        game_id = data.get('game_id')
        team = data.get('team')
        opponent = data.get('opponent')
        line = data.get('line')
        price = data.get('price')
        g = Game.query.get(int(game_id)) if game_id else None
        result = {
            'p_model': None,              # model probability
            'implied_prob': None,         # book-implied from provided price
            'edge': None,                 # p_model - implied_prob
            'ev': None,                   # EV per $1 stake (fraction)
            'ev_per_100': None,           # EV dollars per $100 stake
            'kelly': None,                # Kelly fraction (capped)
            'reason': 'Informational only. Not betting advice.'
        }
        if not g:
            return jsonify({'success': True, 'result': result})
        # Moneyline
        if pick_type == 'moneyline':
            probs = ml_probability(g.home_team, g.away_team, sport, g.home_moneyline, g.away_moneyline)
            if team and g.home_team.lower() == (team or '').lower():
                p_model = probs.get('home')
                implied = implied_prob(price) if price is not None else None
            else:
                p_model = probs.get('away')
                implied = implied_prob(price) if price is not None else None
            result['p_model'] = p_model
            result['implied_prob'] = implied
            result['edge'] = (p_model - implied) if (p_model is not None and implied is not None) else None
            # Also include vig-free baseline for two-way market if both ML prices known
            if g.home_moneyline is not None and g.away_moneyline is not None:
                ph = implied_prob(g.home_moneyline)
                pa = implied_prob(g.away_moneyline)
                ph_fair, pa_fair = remove_vig_two_way(ph, pa)
                result['vig_free_home'] = ph_fair
                result['vig_free_away'] = pa_fair
            if p_model is not None and price is not None:
                ev = ev_from_prob_and_odds(p_model, float(price))
                kelly = kelly_fraction(p_model, float(price))
                result['ev'] = ev
                result['ev_per_100'] = ev * 100.0
                result['kelly'] = kelly
                if implied is not None:
                    result['reason'] = f"We estimate {p_model:.1%} vs book {implied:.1%}, edge {(p_model-implied)*100:.1f}%, EV ${ev*100:.1f} per $100. Not advice."
        # Spread
        elif pick_type == 'spread':
            # line is the selected side line; home side baseline is g.spread
            probs = spread_cover_probability(g.spread, sport=sport or g.sport)
            if team and g.home_team.lower() == (team or '').lower():
                p_model = probs.get('home')
            else:
                p_model = probs.get('away')
            result['p_model'] = p_model
            if p_model is not None and price is not None:
                ev = ev_from_prob_and_odds(p_model, float(price))
                kelly = kelly_fraction(p_model, float(price))
                result['ev'] = ev
                result['ev_per_100'] = ev * 100.0
                result['kelly'] = kelly
                imp = implied_prob(price)
                result['implied_prob'] = imp
                result['edge'] = (p_model - imp) if imp is not None else None
                result['reason'] = f"Cover {p_model:.1%} vs book {imp:.1%}, edge {(p_model-imp)*100:.1f}%, EV ${ev*100:.1f} per $100. Not advice."
        # Total
        elif pick_type == 'total':
            probs = total_over_under_probability(g.total, sport=sport or g.sport)
            # If payload includes over/under selection, we treat both as 0.5 for now
            p_model = 0.5
            result['p_model'] = p_model
            if p_model is not None and price is not None:
                ev = ev_from_prob_and_odds(p_model, float(price))
                kelly = kelly_fraction(p_model, float(price))
                result['ev'] = ev
                result['ev_per_100'] = ev * 100.0
                result['kelly'] = kelly
                imp = implied_prob(price)
                result['implied_prob'] = imp
                result['edge'] = (p_model - imp) if imp is not None else None
                result['reason'] = f"Total {g.total}. Prior 50/50 vs book {imp:.1%}, EV ${ev*100:.1f} per $100. Not advice."
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/picks/suggest', methods=['GET'])
def api_picks_suggest():
    """
    Suggest up to two highlighted picks for a game, evaluated by Edge then EV.
    Query: sport, game_id
    Response: { picks: [ {type, team, opponent, line, price, p_model, implied_prob, edge, ev, ev_per_100, kelly, source_book} ] }
    """
    try:
        from services.probabilities import ml_probability, spread_cover_probability, total_over_under_probability
        from utils.pricing import implied_prob, ev_from_prob_and_odds, kelly_fraction
        from providers.odds_client import OddsClient
        sport = (request.args.get('sport') or '').lower()
        game_id = request.args.get('game_id')
        g = Game.query.get(int(game_id)) if game_id else None
        if not g:
            return jsonify({'success': True, 'picks': []})

        # Build candidate picks
        candidates = []
        # Gather best-line moneylines if possible
        source_map = {'home': None, 'away': None}
        home_ml = g.home_moneyline
        away_ml = g.away_moneyline
        try:
            oc = OddsClient()
            bms = oc.fetch_event_bookmakers(g.sport or sport, g.home_team, g.away_team)
            best = oc.best_moneyline_prices(bms, g.home_team, g.away_team) if bms else {}
            if best.get('home'):
                home_ml, source_map['home'] = best['home'][0], best['home'][1]
            if best.get('away'):
                away_ml, source_map['away'] = best['away'][0], best['away'][1]
            # For spreads and totals: get best prices at the posted points
            best_sp = oc.best_spread_prices(bms, g.home_team, g.away_team, g.spread, (-g.spread if g.spread is not None else None)) if (bms and g.spread is not None) else {}
            best_tot = oc.best_total_prices(bms, g.total) if (bms and g.total is not None) else {}
        except Exception:
            best_sp, best_tot = {}, {}
        

        # Moneyline candidates
        if home_ml is not None or away_ml is not None:
            probs = ml_probability(g.home_team, g.away_team, g.sport or sport, home_ml, away_ml)
            if away_ml is not None:
                p = probs.get('away')
                imp = implied_prob(away_ml)
                edge = (p - imp) if (p is not None and imp is not None) else None
                ev = ev_from_prob_and_odds(p, away_ml) if (p is not None) else None
                kelly = kelly_fraction(p, away_ml) if (p is not None) else None
                candidates.append({'type':'moneyline','team':g.away_team,'opponent':g.home_team,'line':None,'price':away_ml,'p_model':p,'implied_prob':imp,'edge':edge,'ev':ev,'ev_per_100':(ev*100.0 if ev is not None else None),'kelly':kelly,'source_book':source_map['away']})
            if home_ml is not None:
                p = probs.get('home')
                imp = implied_prob(home_ml)
                edge = (p - imp) if (p is not None and imp is not None) else None
                ev = ev_from_prob_and_odds(p, home_ml) if (p is not None) else None
                kelly = kelly_fraction(p, home_ml) if (p is not None) else None
                candidates.append({'type':'moneyline','team':g.home_team,'opponent':g.away_team,'line':None,'price':home_ml,'p_model':p,'implied_prob':imp,'edge':edge,'ev':ev,'ev_per_100':(ev*100.0 if ev is not None else None),'kelly':kelly,'source_book':source_map['home']})

        # Spread candidates
        if g.spread is not None:
            probs = spread_cover_probability(g.spread, sport=g.sport or sport)
            # Home
            p = probs.get('home')
            home_price = (best_sp.get('home')[0] if best_sp.get('home') else -110)
            imp = implied_prob(home_price)
            edge = (p - imp) if (p is not None and imp is not None) else None
            ev = ev_from_prob_and_odds(p, home_price) if (p is not None) else None
            kelly = kelly_fraction(p, home_price) if (p is not None) else None
            candidates.append({'type':'spread','team':g.home_team,'opponent':g.away_team,'line':g.spread,'price':home_price,'p_model':p,'implied_prob':imp,'edge':edge,'ev':ev,'ev_per_100':(ev*100.0 if ev is not None else None),'kelly':kelly,'source_book':(best_sp.get('home')[1] if best_sp.get('home') else g.bookmaker)})
            # Away line is negative
            away_line = -g.spread
            p = probs.get('away')
            away_price = (best_sp.get('away')[0] if best_sp.get('away') else -110)
            imp = implied_prob(away_price)
            edge = (p - imp) if (p is not None and imp is not None) else None
            ev = ev_from_prob_and_odds(p, away_price) if (p is not None) else None
            kelly = kelly_fraction(p, away_price) if (p is not None) else None
            candidates.append({'type':'spread','team':g.away_team,'opponent':g.home_team,'line':away_line,'price':away_price,'p_model':p,'implied_prob':imp,'edge':edge,'ev':ev,'ev_per_100':(ev*100.0 if ev is not None else None),'kelly':kelly,'source_book':(best_sp.get('away')[1] if best_sp.get('away') else g.bookmaker)})

        # Total candidates (use neutral probabilities)
        if g.total is not None:
            probs = total_over_under_probability(g.total, sport=g.sport or sport)
            for side in ['over','under']:
                p = probs.get(side)
                side_best = best_tot.get(side) if best_tot else None
                price = side_best[0] if side_best else -110
                imp = implied_prob(price)
                edge = (p - imp) if (p is not None and imp is not None) else None
                ev = ev_from_prob_and_odds(p, price) if (p is not None) else None
                kelly = kelly_fraction(p, price) if (p is not None) else None
                candidates.append({'type':f'total_{side}','team':None,'opponent':None,'line':g.total,'price':price,'p_model':p,'implied_prob':imp,'edge':edge,'ev':ev,'ev_per_100':(ev*100.0 if ev is not None else None),'kelly':kelly,'source_book':(side_best[1] if side_best else g.bookmaker)})

        # Rank: highest positive edge; if none positive, highest EV
        def edge_key(c):
            return c['edge'] if (c.get('edge') is not None) else float('-inf')
        def ev_key(c):
            return c['ev'] if (c.get('ev') is not None) else float('-inf')

        positives = [c for c in candidates if (c.get('edge') is not None and c['edge'] > 0)]
        if positives:
            top = sorted(positives, key=edge_key, reverse=True)[:2]
        else:
            top = sorted(candidates, key=ev_key, reverse=True)[:2]

        # Also return a ranked list for UI sorting needs
        ranked = sorted([c for c in candidates if c.get('ev') is not None], key=ev_key, reverse=True)
        return jsonify({'success': True, 'picks': top, 'ranked': ranked})
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

@app.route('/api/player_search', methods=['GET'])
def api_player_search():
    """Autosuggest players from current props (NBA only for now)."""
    try:
        from providers.odds_client import OddsClient
        q = (request.args.get('q') or '').strip().lower()
        if not q:
            return jsonify({'success': True, 'players': []})
        oc = OddsClient()
        props = []
        # Try NFL and MLB first given current seasons
        for sp in ['nfl','mlb','nba']:
            props.extend(oc.fetch_player_props_for_sport(sp))
        names = sorted({p['player_name'] for p in props if q in (p.get('player_name','').lower())})[:20]
        return jsonify({'success': True, 'players': names})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/player_props', methods=['GET'])
def api_player_props():
    """Return props for a player name (NBA points/rebounds/assists)."""
    try:
        from providers.odds_client import OddsClient
        name = (request.args.get('name') or '').strip().lower()
        if not name:
            return jsonify({'success': True, 'props': []})
        oc = OddsClient()
        props = []
        for sp in ['nfl','mlb','nba']:
            props.extend(oc.fetch_player_props_for_sport(sp))
        filtered = [p for p in props if name in (p.get('player_name','').lower())]
        return jsonify({'success': True, 'props': filtered})
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
        # Require login to save
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        data = request.get_json() or {}
        # Minimal required: bet type and sport (sport can be inferred from game if provided)
        if not data.get('type'):
            return jsonify({'success': False, 'error': 'Missing field: type'}), 400
        group_type = (data.get('group_type') or 'single').lower()  # 'single' or 'parlay'
        parlay_name = (data.get('parlay_name') or '').strip()

        # Resolve or create parlay
        active_parlays = Parlay.query.filter_by(status='active', user_id=(current_user.id if current_user.is_authenticated else None)).all()
        if group_type == 'parlay':
            if not parlay_name:
                return jsonify({'success': False, 'error': 'parlay_name required'}), 400
            parlay = Parlay.query.filter_by(name=parlay_name, status='active', user_id=(current_user.id if current_user.is_authenticated else None)).first()
            if not parlay:
                # Enforce up to 5 active setups
                if len(active_parlays) >= 5:
                    return jsonify({'success': False, 'error': 'Maximum 5 active setups reached'}), 400
                parlay = Parlay(name=parlay_name, user_id=(current_user.id if current_user.is_authenticated else None))
                db.session.add(parlay)
                db.session.flush()
        else:  # single -> create a dedicated setup
            # Reuse a single bucket named Single-# if under 5
            # Prefer a parlay named 'Singles' if exists and <5 legs
            parlay = Parlay.query.filter_by(name='Singles', status='active', user_id=(current_user.id if current_user.is_authenticated else None)).first()
            if not parlay:
                if len(active_parlays) >= 5:
                    return jsonify({'success': False, 'error': 'Maximum 5 active setups reached'}), 400
                parlay = Parlay(name='Singles', user_id=(current_user.id if current_user.is_authenticated else None))
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

        # Compute Ares metrics at save time (only for supported bet types)
        p_model = None
        implied = None
        edge = None
        ev = None
        ev_per_100 = None
        kelly = None
        try:
            from utils.pricing import implied_prob, ev_from_prob_and_odds, kelly_fraction
            from services.probabilities import ml_probability, spread_cover_probability, total_over_under_probability
            btype = (data.get('type') or '').lower()
            price = float(data.get('price')) if data.get('price') is not None else None
            if g and btype == 'moneyline' and price is not None:
                probs = ml_probability(g.home_team, g.away_team, g.sport, g.home_moneyline, g.away_moneyline)
                team_l = (data.get('team') or '').lower()
                p_model = probs.get('home') if g.home_team.lower() == team_l else probs.get('away')
            elif g and btype == 'spread' and data.get('line') is not None:
                probs = spread_cover_probability(g.spread, sport=g.sport)
                team_l = (data.get('team') or '').lower()
                p_model = probs.get('home') if g.home_team.lower() == team_l else probs.get('away')
            elif g and btype.startswith('total') and data.get('line') is not None:
                probs = total_over_under_probability(g.total, sport=g.sport)
                p_model = probs.get('over') if 'over' in btype else probs.get('under')
            if p_model is not None and price is not None:
                implied = implied_prob(price)
                edge = p_model - implied if implied is not None else None
                ev = ev_from_prob_and_odds(p_model, price)
                ev_per_100 = ev * 100.0
                kelly = kelly_fraction(p_model, price)
        except Exception:
            pass

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
            p_model=p_model,
            implied_prob=implied,
            edge=edge,
            ev=ev,
            ev_per_100=ev_per_100,
            kelly=kelly,
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
        # Active parlays for current user only; completed when all linked games are completed
        if not current_user.is_authenticated:
            return jsonify({'success': True, 'parlays': []})
        parlays = Parlay.query.filter_by(status='active', user_id=current_user.id).all()
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
                    'p_model': b.p_model,
                    'implied_prob': b.implied_prob,
                    'edge': b.edge,
                    'ev': b.ev,
                    'ev_per_100': b.ev_per_100,
                    'kelly': b.kelly,
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
        # Authorization: only owner can delete
        if parlay and current_user.is_authenticated and parlay.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
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
        _rollover_game_statuses()
        
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
            # Stale odds ratio (older than 12h)
            from datetime import datetime as _dt, timedelta as _td
            now = _dt.utcnow()
            stale_cut = now - _td(hours=12)
            stale_count = Game.query.filter(Game.odds_last_updated.isnot(None), Game.odds_last_updated < stale_cut).count()
            stale_ratio = (stale_count / max(1, total_games))
            
        return jsonify({
            'status': 'healthy',
            'total_games': total_games,
            'active_games': recent_games,
            'last_update': latest_collection.created_at.isoformat() if latest_collection else None,
            'stale_odds_ratio': round(stale_ratio, 3)
        })
    except Exception as e:
        # Always return 200 so platform healthchecks pass even if DB is cold
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 200

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

def fetch_espn_articles(sport: str, limit: int = 5):
    import requests
    import xml.etree.ElementTree as ET
    import re
    rss_map = {
        'nfl': 'https://www.espn.com/espn/rss/nfl/news',
        'nba': 'https://www.espn.com/espn/rss/nba/news',
        'mlb': 'https://www.espn.com/espn/rss/mlb/news',
        'nhl': 'https://www.espn.com/espn/rss/nhl/news',
        'cfb': 'https://www.espn.com/espn/rss/ncf/news',
        'soccer': 'https://www.espn.com/espn/rss/soccer/news',
        'golf': 'https://www.espn.com/espn/rss/golf/news',
    }
    url = rss_map.get((sport or '').lower())
    if not url:
        return []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (AresAI; +https://ares-alpha)'}
        resp = requests.get(url, timeout=8, headers=headers)
        resp.raise_for_status()
        content = resp.content
        # Parse XML with namespace tolerance
        root = ET.fromstring(content)
        items = []
        # ESPN uses standard RSS; try generic .//item
        for item in root.findall('.//item'):
            title = (item.findtext('title') or '').strip()
            link = (item.findtext('link') or '').strip()
            pub = (item.findtext('pubDate') or '').strip()
            # description or content:encoded
            desc = (item.findtext('description') or '').strip()
            if not desc:
                try:
                    desc = item.find('{http://purl.org/rss/1.0/modules/content/}encoded').text or ''
                except Exception:
                    desc = ''
            # Strip HTML from description and truncate to ~180 chars
            desc = re.sub('<[^<]+?>', '', desc)
            if len(desc) > 180:
                desc = desc[:177] + '...'
            if title and link:
                items.append({'title': title, 'link': link, 'published': pub, 'snippet': desc, 'source': 'ESPN'})
            if len(items) >= limit:
                break
        return items
    except Exception:
        # Fallback: try to extract <item> blocks via regex if XML parsing fails
        try:
            text = content.decode('utf-8', errors='ignore')
            blocks = re.findall(r'<item>([\s\S]*?)</item>', text)[:limit]
            out = []
            for b in blocks:
                t = re.search(r'<title>(.*?)</title>', b)
                l = re.search(r'<link>(.*?)</link>', b)
                d = re.search(r'<description>([\s\S]*?)</description>', b)
                title = re.sub('<[^<]+?>', '', t.group(1)).strip() if t else ''
                link = (l.group(1).strip() if l else '')
                desc = re.sub('<[^<]+?>', '', d.group(1)).strip() if d else ''
                if len(desc) > 180:
                    desc = desc[:177] + '...'
                if title and link:
                    out.append({'title': title, 'link': link, 'published': '', 'snippet': desc, 'source': 'ESPN'})
            return out
        except Exception:
            return []

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
            remember = True
            login_user(user, remember=remember, duration=app.config.get('REMEMBER_COOKIE_DURATION'))
            # Make session permanent for longer lifetime
            session.permanent = True
            # Force-set cookies for cross-route persistence
            session.modified = True
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
