from extensions import db
from datetime import datetime

class AuflagenCode(db.Model):
    __tablename__ = 'auflagen_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, code=None, description=None):
        self.code = code
        self.description = description

    def __repr__(self):
        return f'<AuflagenCode {self.code}>'
