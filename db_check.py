from app import app, db
from app.models import AuflagenCode

def check_database_connection():
    try:
        with app.app_context():
            # Try to make a simple query
            AuflagenCode.query.first()
            print("Database connection successful!")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

if __name__ == '__main__':
    check_database_connection()
