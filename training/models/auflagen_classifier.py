from typing import List, Dict, Optional, Set
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.svm import LinearSVC
import numpy as np
from pathlib import Path
import joblib
import logging
from ..config import TRAINING_CONFIG, MODELS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuflagenClassifier:
    def __init__(self, model_dir: Optional[Path] = None):
        """Initialisiert den Classifier mit TF-IDF und SVM"""
        config = TRAINING_CONFIG['auflagen_classifier']
        self.model_dir = model_dir or MODELS_DIR
        
        self.vectorizer = TfidfVectorizer(
            max_features=config['max_features'],
            ngram_range=config['ngram_range'],
            strip_accents='unicode'
        )
        
        self.classifier = OneVsRestClassifier(LinearSVC(
            random_state=42,
            max_iter=config['max_iter']
        ))
        
        self.trained = False
        self.label_encoder = None
        
        # Versuche vorhandenes Modell zu laden
        if not self.load_model():
            logger.info("Kein vorhandenes Modell gefunden, initialisiere neues Modell")

    def _validate_training_data(self, texts: List[str], labels: List[List[str]]) -> bool:
        """Validiert die Trainingsdaten"""
        if not texts or not labels:
            return False
        if len(texts) != len(labels):
            return False
        if not all(isinstance(t, str) for t in texts):
            return False
        if not all(isinstance(l, list) for l in labels):
            return False
        return True

    def train(self, train_texts: List[str], train_labels: List[List[str]]) -> Dict:
        """Trainiert den Classifier mit Texten und zugehörigen Auflagen"""
        if not train_texts or not train_labels:
            return {'error': 'Keine Trainingsdaten vorhanden',
                   'samples': 0}

        try:
            if not self._validate_training_data(train_texts, train_labels):
                return {'error': 'Ungültige Trainingsdaten'}

            # Konvertiere Texte zu Feature-Matrix
            X = self.vectorizer.fit_transform(train_texts)
            
            # Trainiere den Classifier
            self.classifier.fit(X, train_labels)
            
            # Berechne Trainings-Metriken
            predictions = self.classifier.predict(X)
            accuracy = np.mean([
                set(pred) == set(true) 
                for pred, true in zip(predictions, train_labels)
            ])
            
            # Speichere Trainingsstatus
            self.trained = True
            
            metrics = {
                'samples': len(train_texts),
                'accuracy': float(accuracy),
                'labels': len(set([l for labels in train_labels for l in labels])),
                'trained': True
            }
            
            # Speichere das trainierte Modell
            self._save_model()
            
            return metrics
            
        except Exception as e:
            logger.error(f"Fehler beim Training: {str(e)}")
            return {
                'error': str(e),
                'samples': len(train_texts),
                'trained': False
            }

    def _calculate_metrics(self, predictions: np.ndarray, true_labels: List[List[str]]) -> Dict:
        """Berechnet detaillierte Metriken"""
        accuracy = np.mean([
            set(pred) == set(true) 
            for pred, true in zip(predictions, true_labels)
        ])
        
        # Sammle alle einzigartigen Labels
        all_labels: Set[str] = set()
        for labels in true_labels:
            all_labels.update(labels)
            
        return {
            'samples': len(true_labels),
            'accuracy': float(accuracy),
            'labels': len(all_labels),
            'unique_labels': sorted(list(all_labels))
        }

    def predict(self, texts: List[str]) -> List[List[str]]:
        """Sagt Auflagen für neue Texte vorher"""
        if not self.trained:
            return [[] for _ in texts]
            
        try:
            X = self.vectorizer.transform(texts)
            predictions = self.classifier.predict(X)
            return [[str(label) for label in pred] if isinstance(pred, (list, np.ndarray)) else [str(pred)] for pred in predictions]
        except Exception as e:
            logger.error(f"Vorhersagefehler: {e}")
            return [[] for _ in texts]

    def _save_model(self) -> None:
        """Speichert das trainierte Modell"""
        model_file = self.model_dir / 'auflagen_classifier.joblib'
        vectorizer_file = self.model_dir / 'vectorizer.joblib'
        
        joblib.dump(self.classifier, model_file)
        joblib.dump(self.vectorizer, vectorizer_file)

    def load_model(self) -> bool:
        """Lädt ein gespeichertes Modell"""
        try:
            model_file = self.model_dir / 'auflagen_classifier.joblib'
            vectorizer_file = self.model_dir / 'vectorizer.joblib'
            
            if model_file.exists() and vectorizer_file.exists():
                self.classifier = joblib.load(model_file)
                self.vectorizer = joblib.load(vectorizer_file)
                return True
            return False
        except Exception as e:
            print(f"Fehler beim Laden des Modells: {e}")
            return False
