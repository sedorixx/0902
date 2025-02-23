from pathlib import Path
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from .config import MODELS_DIR, TRAINING_CONFIG
from app import db

class BaseClassifier:
    def __init__(self, model_name: str, num_labels: int):
        self.model_name = model_name
        self.num_labels = num_labels
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=num_labels
        )
        
    def save(self, name: str):
        save_dir = MODELS_DIR / name
        self.model.save_pretrained(save_dir)
        self.tokenizer.save_pretrained(save_dir)

class AuflagenClassifier(BaseClassifier):
    def __init__(self):
        super().__init__(str(TRAINING_CONFIG['model_name']), num_labels=len(self.get_auflagen_labels()))
        
    @staticmethod
    def get_auflagen_labels():
        return ["A01", "A02", "A03", "A14", "155"]  # Beispiel-Labels

class TableClassifier(BaseClassifier):
    def __init__(self):
        super().__init__(str(TRAINING_CONFIG['model_name']), num_labels=2)  # Binary classification

class AuflagenCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
