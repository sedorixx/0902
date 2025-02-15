from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from app import app, db
import os

migrate = Migrate(app, db)

def init_database():
    with app.app_context():
        # Create tables directly for first deployment
        db.create_all()
        print("Database tables created successfully")

if __name__ == '__main__':
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL:
        print(f"Initializing database at {DATABASE_URL}")
    else:
        print("Using SQLite database")
    init_database()
