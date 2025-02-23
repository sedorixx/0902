from sqlalchemy import Column, Integer, String, Text, Float
from extensions import db

class AuflagenCode(db.Model):
    __tablename__ = 'auflagen_codes'
    
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    description = Column(Text)
    category = Column(String(50))  # Neue Kategorie für Auflagentyp
    required_checks = Column(Text)  # JSON-String mit erforderlichen Prüfungen
    estimated_time = Column(Float)  # Geschätzte Zeit für Prüfung in Minuten
    required_equipment = Column(Text)  # JSON-String mit benötigtem Equipment

    def __repr__(self):
        return f'<AuflagenCode {self.code}>'
