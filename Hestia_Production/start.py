# Hestia_Production/start.py
"""
Startup script for Render deployment.
This ensures the database is initialized before starting the app.
"""
import os
import sys

def main():
    # Add the current directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Initialize database if it doesn't exist
    try:
        from init_db import init_database
        init_database()
        print("Database initialization completed")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        # Continue anyway - the app should handle missing DB gracefully
    
    # Import and create the app
    from hestia_app import create_app
    app = create_app()
    
    return app

if __name__ == "__main__":
    app = main()
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
