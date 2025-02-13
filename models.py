from extensions import db
from datetime import datetime

class AuflagenCode(db.Model):
    """Modell für Auflagen-Codes und deren Beschreibungen"""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, code, description):
        self.code = code.strip()
        self.description = description.strip() if description else "Keine Beschreibung verfügbar"

    def to_dict(self):
        """Convert object to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'code': self.code,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<AuflagenCode {self.code}>'
