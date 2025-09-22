"""
Celery configuration for Ares AI background tasks
"""

from celery import Celery
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
    timezone='US/Eastern',
    enable_utc=True,
    # Schedule tasks
    beat_schedule={
        'collect-sports-data-every-hour': {
            'task': 'celery_app.collect_sports_data_task',
            'schedule': 3600.0,  # Every hour
        },
        'collect-sports-data-week-transition': {
            'task': 'celery_app.collect_sports_data_task',
            'schedule': 86400.0,  # Daily check for week transitions
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
