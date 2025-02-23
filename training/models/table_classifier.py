from typing import List, Dict, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
import numpy as np
from pathlib import Path
import joblib
import logging
from ..config import TRAINING_CONFIG
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"
logger = logging.getLogger(__name__)

class TableClassifier:
    def __init__(self, model_dir: Optional[Path] = None):
        """Initialisiert den Classifier für Tabellenerkennung"""
        config = TRAINING_CONFIG['table_classifier']
        self.model_dir = model_dir or MODELS_DIR
        
        self.vectorizer = TfidfVectorizer(
            max_features=config['max_features'],
            ngram_range=config['ngram_range']
        )
        self.classifier = LinearSVC(
            random_state=42,
            max_iter=config['max_iter']
        )
        self.labels = ['fahrzeug', 'reifen', 'auflagen']
        
        if not self.load_model():
            logger.info("Initialisiere neuen Table Classifier")

    def train(self, texts: List[str], labels: List[str]) -> Dict:
        """Trainiert den Classifier für Tabellenerkennung"""
        try:
            X = self.vectorizer.fit_transform(texts)
            self.classifier.fit(X, labels)
            
            predictions = self.classifier.predict(X)
            accuracy = np.mean(predictions == labels)
            
            self._save_model()
            
            return {
                'accuracy': float(accuracy),
                'samples': len(texts),
                'labels': self.labels
            }
            
        except Exception as e:
            logger.error(f"Trainingsfehler: {e}")
            return {'error': str(e)}

    def predict(self, texts: List[str]) -> List[str]:
        """Klassifiziert Tabellen nach Typ"""
        try:
            X = self.vectorizer.transform(texts)
            predictions = self.classifier.predict(X)
            return [str(pred) for pred in predictions]
        except Exception as e:
            logger.error(f"Vorhersagefehler: {e}")
            return ['unbekannt'] * len(texts)

    def _save_model(self) -> None:
        """Speichert das trainierte Modell"""
        try:
            model_path = self.model_dir / TRAINING_CONFIG['table_classifier']['model_filename']
            vectorizer_path = self.model_dir / TRAINING_CONFIG['table_classifier']['vectorizer_filename']
            
            joblib.dump(self.classifier, model_path)
            joblib.dump(self.vectorizer, vectorizer_path)
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")

    def load_model(self) -> bool:
        """Lädt ein gespeichertes Modell"""
        try:
            model_path = self.model_dir / TRAINING_CONFIG['table_classifier']['model_filename']
            vectorizer_path = self.model_dir / TRAINING_CONFIG['table_classifier']['vectorizer_filename']
            
            if model_path.exists() and vectorizer_path.exists():
                self.classifier = joblib.load(model_path)
                self.vectorizer = joblib.load(vectorizer_path)
                return True
            return False
        except Exception as e:
            logger.error(f"Fehler beim Laden: {e}")
            return False
