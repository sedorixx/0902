from models.gutachten_extractor import GutachtenExtractor # type: ignore
from validators.gutachten_validator import GutachtenValidator
from data_augmentation import GutachtenAugmenter
from typing import Dict, List
import torch

class GutachtenTrainer:
    def __init__(self, extractor):
        self.extractor = extractor
        self.augmenter = GutachtenAugmenter()
        self.validator = GutachtenValidator()

    def train(self, training_data: List[Dict]) -> None:
        """Trainiert das Modell mit Gutachtendaten"""
        # Bereite Daten vor
        augmented_data = self._prepare_training_data(training_data)
        
        # Trainiere für jede Informationsart separat
        for info_type in ['fahrzeug', 'felgen', 'reifen', 'auflagen']:
            self._train_specific_extractor(
                info_type, 
                augmented_data
            )
            
    def _prepare_training_data(self, data: List[Dict]) -> List[Dict]:
        """Bereitet Trainingsdaten mit Augmentierung vor"""
        augmented = []
        for gutachten in data:
            # Original-Daten
            augmented.append(gutachten)
            
            # Augmentierte Varianten
            variants = self._augment_gutachten(gutachten)
            augmented.extend(variants)
            
        return augmented
        
    def _augment_gutachten(self, gutachten: Dict) -> List[Dict]:
        """Erstellt Varianten eines Gutachtens"""
        variants = []
        
        # Textuelle Variationen
        text_variants = self.augmenter.generate_synthetic_data(
            str(gutachten)
        )
        
        # Konvertiere zurück zu strukturierten Daten
        for variant in text_variants:
            parsed = self.extractor.extract_info(variant)
            if self.validator.validate_gutachten(parsed):
                variants.append(parsed)
        
        return variants
        
    def _train_specific_extractor(self, info_type: str, training_data: List[Dict]) -> None:
        """Trainiert den Extraktor für einen spezifischen Informationstyp"""
        model = self.extractor.get_model(info_type)
        if model is not None:
            # Extrahiere relevante Daten für den Informationstyp
            training_samples = [data[info_type] for data in training_data if info_type in data]
            
            # Trainiere das Modell
            model.train(training_samples)
            self.extractor.save_model(info_type, model)

# Beispiel für die Verwendung der Methode
extractor = GutachtenExtractor()  # Initialisiere den GutachtenExtractor
trainer = GutachtenTrainer(extractor)
example_data = [{"info_type_beispiel": "some_data"}]  # Beispieldaten
trainer._train_specific_extractor("info_type_beispiel", example_data)
