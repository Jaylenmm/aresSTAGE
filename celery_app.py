"""
Celery configuration for Ares AI background tasks
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready
import threading
import os

# Initialize Celery
celery_app = Celery('ares_ai')

# Configure Celery
celery_app.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=os.getenv('APP_TIMEZONE', 'US/Pacific'),
    enable_utc=True,
    # Schedule tasks
    beat_schedule={
        'collect-schedules-every-30min': {
            'task': 'celery_app.collect_sports_data_task',
            'schedule': 1800.0,
        },
        'refresh-odds-every-5min': {
            'task': 'celery_app.refresh_odds_task',
            'schedule': 300.0,
        },
        'collect-sports-data-midnight-pst': {
            'task': 'celery_app.collect_sports_data_task',
            'schedule': crontab(minute=0, hour=0),
        },
    },
)

@celery_app.task
def collect_sports_data_task():
    """Background task to collect sports data"""
    try:
        from sports_collector import SportsDataCollector
        
        print("🔄 Auto-collecting sports data...")
        collector = SportsDataCollector()
        games = collector.collect_all_games()
        
        print(f"✅ Auto-collection complete: {len(games)} games")
        return {
            'success': True,
            'games_count': len(games),
            'message': f'Successfully collected {len(games)} games'
        }
    except Exception as e:
        print(f"❌ Auto-collection failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f'Error collecting data: {str(e)}'
        }

@celery_app.task
def check_week_transition():
    """Check if we need to transition to a new NFL week"""
    try:
        from sports_collector import SportsDataCollector
        
        collector = SportsDataCollector()
        current_week = collector.get_nfl_week()
        
        # Force data collection for new week
        games = collector.collect_all_games()
        
        return {
            'success': True,
            'current_week': current_week,
            'games_count': len(games),
            'message': f'Week transition check complete - Week {current_week}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Week transition check failed: {str(e)}'
        }

@celery_app.task
def refresh_odds_task():
    """Background task to refresh odds more frequently"""
    try:
        from sports_collector import SportsDataCollector
        collector = SportsDataCollector()
        collector._update_odds_for_upcoming()
        return {'success': True, 'message': 'Odds refreshed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Run one full collection shortly after the worker starts
@worker_ready.connect
def run_collect_on_boot(sender, **kwargs):
    def _trigger():
        try:
            collect_sports_data_task.delay()
        except Exception:
            pass
    # small delay to allow app boot and DB ready
    threading.Timer(5.0, _trigger).start()
