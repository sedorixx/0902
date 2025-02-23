import nlpaug.augmenter.word as naw
import nlpaug.augmenter.char as nac
from typing import List, Dict
import numpy as np

class GutachtenAugmenter:
    def __init__(self):
        self.aug_substitute = naw.SynonymAug(
            aug_src='wordnet', 
            lang='deu'
        )
        self.aug_insert = naw.ContextualWordEmbsAug(
            model_path='bert-base-german-cased',
            action="insert"
        )
        
    def augment_text(self, text: str, num_samples: int = 2) -> List[str]:
        """Erweitert einen Text durch verschiedene Augmentierungstechniken"""
        augmented = []
        
        # Synonym-Ersetzung
        aug_syn = self.aug_substitute.augment(text, n=num_samples)
        augmented.extend(aug_syn)
        
        # Kontextbasierte Einfügung
        aug_ctx = self.aug_insert.augment(text, n=num_samples)
        augmented.extend(aug_ctx)
        
        return augmented

    def augment_dataset(self, texts: List[str], labels: List[int], 
                       samples_per_class: Dict[int, int]) -> tuple:
        """Erweitert den Datensatz mit klassenspezifischer Augmentierung"""
        augmented_texts = []
        augmented_labels = []
        
        for text, label in zip(texts, labels):
            if label in samples_per_class:
                num_samples = samples_per_class[label]
                aug_texts = self.augment_text(text, num_samples)
                augmented_texts.extend(aug_texts)
                augmented_labels.extend([label] * len(aug_texts))
        
        return (
            texts + augmented_texts,
            labels + augmented_labels
        )

    def generate_synthetic_data(self, text: str) -> List[str]:
        """Generiert synthetische Daten durch Regelbasierte Transformationen"""
        synthetic = []
        
        # Ziffern-Variation
        digit_variants = self._create_digit_variants(text)
        synthetic.extend(digit_variants)
        
        # Abkürzungsvariationen
        abbrev_variants = self._create_abbreviation_variants(text)
        synthetic.extend(abbrev_variants)
        
        return synthetic

    def _create_digit_variants(self, text: str) -> List[str]:
        """Erstellt Variationen von Zahlen und Maßeinheiten"""
        variants = []
        # Konvertiert z.B. "235/35R19" zu ["235/35 R19", "235-35 R19"]
        import re
        
        # Reifengrößen-Pattern
        tire_pattern = r'(\d+)/(\d+)R(\d+)'
        variants.append(re.sub(tire_pattern, r'\1/\2 R\3', text))
        variants.append(re.sub(tire_pattern, r'\1-\2 R\3', text))
        
        return variants

    def _create_abbreviation_variants(self, text: str) -> List[str]:
        """Erstellt Variationen von Abkürzungen"""
        variants = []
        replacements = {
            'ET': 'Einpresstiefe',
            'ABE': 'Allgemeine Betriebserlaubnis',
            'EG': 'Europäische Gemeinschaft',
            'KBA': 'Kraftfahrt-Bundesamt',
            # Weitere domänenspezifische Abkürzungen
        }
        
        for abbrev, full in replacements.items():
            variants.append(text.replace(abbrev, full))
            variants.append(text.replace(full, abbrev))
            
        return variants
