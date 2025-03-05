from extensions import db

class AuflagenCode(db.Model):
    __tablename__ = 'auflagen_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    def __repr__(self):
        return f'<AuflagenCode {self.code}>'
