from flask_migrate import Migrate
from app import app, db

migrate = Migrate(app, db)

if __name__ == '__main__':
    with app.app_context():
        if not db.engine.dialect.has_table(db.engine, 'auflagen_codes'):
            db.create_all()
