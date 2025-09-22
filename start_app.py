#!/usr/bin/env python3
"""
Startup script for Ares AI with automatic data collection
"""

import os
import sys
from app import app, data_scheduler

def main():
    """Start the Ares AI application with background services"""
    
    # Create database tables
    with app.app_context():
        from app import db
        db.create_all()
    
    # Start background scheduler
    data_scheduler.start()
    
    # Get configuration
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    try:
        # Run the Flask app
        app.run(debug=debug, host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        data_scheduler.stop()
    except Exception as e:
        data_scheduler.stop()
        sys.exit(1)

if __name__ == '__main__':
    main()
