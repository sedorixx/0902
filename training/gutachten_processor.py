from pathlib import Path
from typing import Dict, Optional, Union, List
import logging
from .pdf_processor import PDFProcessor
from .data_validator import DataValidator
from .models.neural import GutachtenEmbedding
from .model_trainer import ModelTrainer

logger = logging.getLogger(__name__)

class GutachtenProcessor:
    def __init__(self):
        self.pdf_processor = PDFProcessor()
        self.validator = DataValidator()
        self.embedder = GutachtenEmbedding()
        self.trainer = ModelTrainer()
        self.last_result = None

    async def process_gutachten(self, 
                              pdf_path: Union[str, Path], 
                              wheel_info: Optional[Dict] = None,
                              retrain: bool = True) -> Dict:
        """Verarbeitet ein Gutachten vollständig und asynchron"""
        try:
            # Extrahiere Daten aus PDF
            content = await self._extract_pdf_content(pdf_path)
            if content['status'] != 'success':
                return content

            # Strukturiere und validiere Daten
            structured_data = self._structure_data(content['content'], wheel_info)
            validation = self._validate_data(structured_data)

            if not validation['valid']:
                return {
                    'status': 'error',
                    'validation': validation,
                    'step': 'validation'
                }

            # Trainiere Modelle wenn gewünscht
            training_results = None
            if retrain:
                training_results = await self._train_models(structured_data)

            result = {
                'status': 'success',
                'data': structured_data,
                'validation': validation,
                'training': training_results,
                'embeddings': self._generate_embeddings(structured_data)
            }

            self.last_result = result
            return result

        except Exception as e:
            logger.error(f"Fehler bei der Gutachtenverarbeitung: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'step': 'process_gutachten'
            }

    async def _extract_pdf_content(self, pdf_path: Union[str, Path]) -> Dict:
        """Extrahiert Inhalt aus PDF"""
        return await self.pdf_processor.process_pdf(pdf_path)

    async def process_pdf(self, pdf_path: Union[str, Path]) -> Dict:
        """Verarbeitet ein PDF und gibt den Inhalt zurück"""
        return await self.pdf_processor.process_pdf(pdf_path)

    def _structure_data(self, content: Dict, wheel_info: Optional[Dict]) -> Dict:
        """Strukturiert extrahierte Daten"""
        structured = {
            'fahrzeuge': self._process_vehicle_data(content),
            'reifen': self._process_tire_data(content),
            'auflagen': self._process_condition_data(content)
        }

        if wheel_info:
            structured['felgen'] = [self.validator.validate_wheel_info(wheel_info)]

        return structured

    def _validate_data(self, data: Dict) -> Dict:
        """Validiert die strukturierten Daten"""
        validation = {
            'valid': True,
            'warnings': [],
            'errors': []
        }

        # Validiere Felgen-Reifen Kombinationen
        if 'felgen' in data and 'reifen' in data:
            for wheel in data['felgen']:
                for tire in data['reifen']:
                    result = self.validator.validate_wheel_tire_combo(wheel, tire)
                    if not result['valid']:
                        validation['valid'] = False
                        validation['errors'].extend(result['errors'])
                    validation['warnings'].extend(result['warnings'])

        # Validiere Fahrzeug-Felgen Kompatibilität
        if 'fahrzeuge' in data and 'felgen' in data:
            for vehicle in data['fahrzeuge']:
                for wheel in data['felgen']:
                    result = self.validator.validate_vehicle_compatibility(vehicle, wheel)
                    if not result['valid']:
                        validation['valid'] = False
                        validation['errors'].extend(result['errors'])
                    validation['warnings'].extend(result['warnings'])

        return validation

    async def _train_models(self, data: Dict) -> Dict:
        """Trainiert die Modelle mit den neuen Daten"""
        return await self.trainer.train_all_models(data)

    def _generate_embeddings(self, data: Dict) -> Dict:
        """Generiert Embeddings für relevante Textinhalte"""
        embeddings = {}
        
        # Generiere Embeddings für Auflagen
        if 'auflagen' in data:
            texts = [item.get('text', '') for item in data['auflagen']]
            if texts:
                embeddings['auflagen'] = self.embedder.encode(texts).tolist()

        return embeddings

    def _process_vehicle_data(self, content: Dict) -> List[Dict]:
        """Verarbeitet Fahrzeugdaten"""
        vehicles = []
        for block in content.get('classified', {}).get('fahrzeug', []):
            if isinstance(block, dict):
                if 'data' in block:  # Tabellendaten
                    vehicles.extend(block['data'])
                elif 'text' in block:  # Textblock
                    extracted = self._extract_vehicle_info(block['text'])
                    if extracted:
                        vehicles.append(extracted)
        return vehicles

    def _process_tire_data(self, content: Dict) -> List[Dict]:
        """Verarbeitet Reifendaten"""
        tires = []
        for block in content.get('classified', {}).get('reifen', []):
            if isinstance(block, dict):
                if 'data' in block:  # Tabellendaten
                    tires.extend(block['data'])
                elif 'text' in block:  # Textblock
                    extracted = self._extract_tire_info(block['text'])
                    if extracted:
                        tires.append(extracted)
        return tires

    def _process_condition_data(self, content: Dict) -> List[Dict]:
        """Verarbeitet Auflagen"""
        conditions = []
        for block in content.get('classified', {}).get('auflagen', []):
            if isinstance(block, dict):
                if 'data' in block:  # Tabellendaten
                    conditions.extend(block['data'])
                elif 'text' in block:  # Textblock
                    extracted = self._extract_conditions(block['text'])
                    conditions.extend(extracted)
        return conditions

    def _extract_vehicle_info(self, text: str) -> Optional[Dict]:
        """Extrahiert Fahrzeuginformationen aus Text"""
        try:
            info = {}
            
            # Suche nach Hersteller/Typ Pattern
            hersteller_pattern = r'(?:Hersteller|Fabrikat):\s*([^\n]+)'
            typ_pattern = r'(?:Typ|Modell):\s*([^\n]+)'
            
            hersteller_match = re.search(hersteller_pattern, text)
            typ_match = re.search(typ_pattern, text)
            
            if hersteller_match:
                info['hersteller'] = hersteller_match.group(1).strip()
            if typ_match:
                info['typ'] = typ_match.group(1).strip()
                
            # Nur zurückgeben wenn mindestens ein Feld gefunden wurde
            return info if info else None
            
        except Exception as e:
            logger.error(f"Fehler bei Fahrzeuginfo-Extraktion: {e}")
            return None

    def _extract_tire_info(self, text: str) -> Optional[Dict]:
        """Extrahiert Reifendaten aus Text"""
        try:
            # Suche nach Reifendimensionen
            dimension_pattern = r'(\d{3}/\d{2}\s*R\d{2})'
            dimensions = re.findall(dimension_pattern, text)
            
            if not dimensions:
                return None
                
            return {
                'dimension': dimensions[0],
                'original_text': text
            }
            
        except Exception as e:
            logger.error(f"Fehler bei Reifeninfo-Extraktion: {e}")
            return None

    def _extract_conditions(self, text: str) -> List[Dict]:
        """Extrahiert Auflagen aus Text"""
        conditions = []
        try:
            # Suche nach Auflagen-Codes und deren Beschreibungen
            pattern = r'([A-Z][0-9]{1,2}[a-z]?)[:\s]+([^\n]+)'
            matches = re.finditer(pattern, text)
            
            for match in matches:
                code = match.group(1)
                description = match.group(2).strip()
                
                if code and description:
                    conditions.append({
                        'code': code,
                        'text': description,
                        'original_text': match.group(0)
                    })
                    
        except Exception as e:
            logger.error(f"Fehler bei Auflagen-Extraktion: {e}")
            
        return conditions
