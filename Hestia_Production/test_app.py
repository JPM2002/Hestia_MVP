# Hestia_Production/test_app.py
"""
Simple test script to verify the app can start without errors.
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_app_creation():
    """Test that the app can be created without errors."""
    try:
        from hestia_app import create_app
        app = create_app()
        print("✅ App created successfully")
        return True
    except Exception as e:
        print(f"❌ App creation failed: {e}")
        return False

def test_database_connection():
    """Test database connection."""
    try:
        from hestia_app.services.db import db
        conn = db()
        conn.close()
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_blueprint_registration():
    """Test that blueprints are registered correctly."""
    try:
        from hestia_app import create_app
        app = create_app()
        
        # Check if blueprints are registered
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        expected_blueprints = ['admin', 'auth', 'dashboard', 'tickets', 'tecnico']
        
        for bp_name in expected_blueprints:
            if bp_name in blueprint_names:
                print(f"✅ Blueprint '{bp_name}' registered")
            else:
                print(f"❌ Blueprint '{bp_name}' not found")
                return False
        
        return True
    except Exception as e:
        print(f"❌ Blueprint registration test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Hestia app...")
    print("=" * 50)
    
    tests = [
        test_app_creation,
        test_database_connection,
        test_blueprint_registration,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! App is ready for deployment.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please fix the issues before deploying.")
        sys.exit(1)
