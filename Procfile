web: gunicorn app:app --workers=3 --timeout=120 --bind 0.0.0.0:$PORT
worker: python -m celery -A celery_app.celery_app worker --loglevel=INFO
beat: python -m celery -A celery_app.celery_app beat --loglevel=INFO
web: python app.py
