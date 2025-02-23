from sklearn.model_selection import train_test_split, cross_val_score
from typing import Dict, List, Optional, Tuple
import numpy as np
from pathlib import Path
import joblib
import logging
from .config import TRAINING_CONFIG, VALIDATION_CONFIG
from .models import AuflagenClassifier, TableClassifier

logger = logging.getLogger(__name__)

class ModelTrainer:
    def __init__(self, model_dir: Optional[Path] = None):
        self.auflagen_classifier = AuflagenClassifier(model_dir)
        self.table_classifier = TableClassifier(model_dir)
        self.config = TRAINING_CONFIG
        
    def train_all_models(self, training_data: Dict) -> Dict:
        """Trainiert alle Modelle mit den gegebenen Daten"""
        results = {
            'status': 'success',
            'metrics': {},
            'validation': {}
        }
        
        try:
            # Trainiere Auflagen-Klassifizierer
            if training_data.get('auflagen'):
                auflagen_metrics = self._train_auflagen_classifier(
                    training_data['auflagen']
                )
                results['metrics']['auflagen'] = auflagen_metrics
            
            # Trainiere Tabellen-Klassifizierer
            if training_data.get('tables'):
                table_metrics = self._train_table_classifier(
                    training_data['tables']
                )
                results['metrics']['tables'] = table_metrics
            
            # Validiere Trainingsergebnisse
            results['validation'] = self._validate_training_results(
                results['metrics']
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Trainingsfehler: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }

    def _train_auflagen_classifier(self, auflagen_data: List[Dict]) -> Dict:
        """Trainiert den Auflagen-Klassifizierer mit Cross-Validation"""
        texts = [item['text'] for item in auflagen_data]
        labels = [item['labels'] for item in auflagen_data]
        
        # Split Daten
        X_train, X_val, y_train, y_val = train_test_split(
            texts, 
            labels,
            test_size=self.config['auflagen_classifier']['validation_split'],
            random_state=42
        )
        
        # Trainiere Model
        metrics = self.auflagen_classifier.train(X_train, y_train)
        
        # Berechne Validierungs-Metriken
        val_predictions = self.auflagen_classifier.predict(X_val)
        val_accuracy = np.mean([
            set(pred) == set(true) 
            for pred, true in zip(val_predictions, y_val)
        ])
        
        metrics['validation_accuracy'] = float(val_accuracy)
        
        # Führe Cross-Validation durch
        cv_scores = cross_val_score(
            self.auflagen_classifier.classifier,
            self.auflagen_classifier.vectorizer.transform(texts),
            labels,
            cv=VALIDATION_CONFIG['cross_validation_folds']
        )
        
        metrics['cv_scores'] = cv_scores.tolist()
        metrics['cv_mean'] = float(cv_scores.mean())
        metrics['cv_std'] = float(cv_scores.std())
        
        return metrics

    def _train_table_classifier(self, table_data: List[Dict]) -> Dict:
        """Trainiert den Tabellen-Klassifizierer"""
        texts = [item['content'] for item in table_data]
        labels = [item['type'] for item in table_data]
        
        return self.table_classifier.train(texts, labels)

    def _validate_training_results(self, metrics: Dict) -> Dict:
        """Validiert die Trainingsergebnisse"""
        validation = {
            'passed': True,
            'warnings': [],
            'checks': {}
        }
        
        # Prüfe Auflagen-Klassifizierer
        if 'auflagen' in metrics:
            auflagen_checks = {
                'accuracy': metrics['auflagen']['accuracy'] >= VALIDATION_CONFIG['min_accuracy'],
                'samples': metrics['auflagen']['samples'] >= VALIDATION_CONFIG['min_samples'],
                'cv_stability': metrics['auflagen']['cv_std'] < 0.1
            }
            validation['checks']['auflagen'] = auflagen_checks
            
            if not all(auflagen_checks.values()):
                validation['passed'] = False
                validation['warnings'].append(
                    "Auflagen-Klassifizierer erfüllt nicht alle Qualitätskriterien"
                )
        
        # Prüfe Tabellen-Klassifizierer
        if 'tables' in metrics:
            table_checks = {
                'accuracy': metrics['tables']['accuracy'] >= VALIDATION_CONFIG['min_accuracy'],
                'samples': metrics['tables']['samples'] >= VALIDATION_CONFIG['min_samples']
            }
            validation['checks']['tables'] = table_checks
            
            if not all(table_checks.values()):
                validation['passed'] = False
                validation['warnings'].append(
                    "Tabellen-Klassifizierer erfüllt nicht alle Qualitätskriterien"
                )
        
        return validation
