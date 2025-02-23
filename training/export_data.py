from typing import Dict, Optional, List
from pathlib import Path
import json
import pandas as pd
from datetime import datetime
import re
from .pdf_extractor import PDFExtractor

class DataProcessor:
    def __init__(self):
        self.pdf_extractor = PDFExtractor()
        self.validation_rules = {
            'fahrzeuge': ['hersteller', 'handelsbezeichnung'],
            'reifen': ['dimension'],
            'auflagen': ['code', 'text']
        }

    def process_pdf(self, pdf_path: str, wheel_info: Optional[Dict] = None) -> Dict:
        """Verarbeitet PDF und extrahiert strukturierte Daten"""
        try:
            # Extrahiere Rohdaten
            raw_data = self.pdf_extractor.extract_pdf(pdf_path)
            if raw_data['status'] != 'success':
                return raw_data

            # Verarbeite und validiere Daten
            processed_data = {
                'status': 'success',
                'data': {},
                'validation': self._validate_data(raw_data['data'])
            }

            # Verarbeite einzelne Datentypen
            for data_type in ['fahrzeuge', 'reifen', 'auflagen']:
                processed = self._process_data_type(
                    raw_data['data'].get(data_type, []),
                    data_type
                )
                if processed:
                    processed_data['data'][data_type] = processed

            # Füge Felgeninformationen hinzu
            if wheel_info:
                processed_data['data']['felgen'] = [
                    self._validate_wheel_info(wheel_info)
                ]

            return processed_data

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _process_data_type(self, data: List[Dict], data_type: str) -> List[Dict]:
        """Verarbeitet einen spezifischen Datentyp"""
        processors = {
            'fahrzeuge': self._process_vehicle_data,
            'reifen': self._process_tire_data,
            'auflagen': self._process_conditions
        }
        
        processor = processors.get(data_type)
        if processor:
            return processor(data)
        return []

    def _process_vehicle_data(self, vehicles: List[Dict]) -> List[Dict]:
        """Verarbeitet Fahrzeugdaten"""
        processed = []
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
                
            # Normalisiere Fahrzeugdaten
            processed_vehicle = {
                'hersteller': vehicle.get('hersteller', '').strip().upper(),
                'handelsbezeichnung': vehicle.get('handelsbezeichnung', '').strip(),
                'typ': vehicle.get('typ', '').strip(),
                'lochkreis': self._extract_pcd(vehicle.get('lochkreis', '')),
                'et_bereich': self._extract_et_range(vehicle.get('et_bereich', ''))
            }
            
            if processed_vehicle['hersteller'] and processed_vehicle['handelsbezeichnung']:
                processed.append(processed_vehicle)
                
        return processed

    def _process_tire_data(self, tires: List[Dict]) -> List[Dict]:
        """Verarbeitet Reifendaten"""
        processed = []
        for tire in tires:
            if not isinstance(tire, dict):
                continue
                
            # Extrahiere und validiere Reifendimensionen
            dimension = tire.get('dimension', '')
            if dimension:
                tire_info = self._parse_tire_dimension(dimension)
                if tire_info:
                    processed.append({
                        **tire_info,
                        'original': dimension,
                        'hersteller': tire.get('hersteller', '').strip(),
                        'typ': tire.get('typ', '').strip()
                    })
                    
        return processed

    def _process_conditions(self, conditions: List[Dict]) -> List[Dict]:
        """Verarbeitet Auflagen"""
        processed = []
        seen_codes = set()
        
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
                
            code = condition.get('code', '').strip()
            text = condition.get('text', '').strip()
            
            if code and text and code not in seen_codes:
                processed.append({
                    'code': code,
                    'text': text,
                    'kategorie': self._categorize_condition(text)
                })
                seen_codes.add(code)
                
        return processed

    def _parse_tire_dimension(self, dimension: str) -> Optional[Dict]:
        """Parst Reifendimensionen"""
        pattern = r'(\d{3})/(\d{2})R(\d{2})'
        match = re.match(pattern, dimension)
        
        if match:
            width, aspect_ratio, rim = match.groups()
            return {
                'breite': int(width),
                'querschnitt': int(aspect_ratio),
                'durchmesser': int(rim),
                'dimension': dimension
            }
        return None

    def _extract_pcd(self, pcd: str) -> str:
        """Extrahiert Lochkreis-Informationen"""
        pattern = r'(\d+)x(\d+)'
        match = re.match(pattern, pcd)
        
        if match:
            count, diameter = match.groups()
            return f"{count}x{diameter}"
        return pcd

    def _extract_et_range(self, et_range: str) -> str:
        """Extrahiert ET-Bereich"""
        pattern = r'ET\s*(-?\d+)\s*-\s*(-?\d+)'
        match = re.match(pattern, et_range)
        
        if match:
            min_et, max_et = match.groups()
            return f"{min_et}-{max_et}"
        return et_range

    def _validate_wheel_info(self, wheel_info: Dict) -> Dict:
        """Validiert Felgeninformationen"""
        required_fields = ['felgenname', 'felgengroesse', 'lochkreis', 'et']
        
        if not all(field in wheel_info for field in required_fields):
            raise ValueError("Unvollständige Felgeninformationen")
            
        return wheel_info

    def _validate_data(self, data: Dict) -> Dict:
        """Validiert die extrahierten Daten"""
        validation = {
            'valid': True,
            'warnings': [],
            'errors': []
        }
        
        for data_type, required_fields in self.validation_rules.items():
            items = data.get(data_type, [])
            if not items:
                validation['warnings'].append(f"Keine {data_type} gefunden")
                continue
                
            for item in items:
                missing_fields = [
                    field for field in required_fields 
                    if not item.get(field)
                ]
                if missing_fields:
                    validation['warnings'].append(
                        f"Fehlende Felder in {data_type}: {', '.join(missing_fields)}"
                    )
                    
        return validation

    def _categorize_condition(self, text: str) -> str:
        """Kategorisiert Auflagen nach Inhalt"""
        text_lower = text.lower()
        
        categories = {
            'montage': ['montage', 'einbau', 'anbau'],
            'sicherheit': ['sicherheit', 'warnung', 'achtung'],
            'dokumente': ['dokument', 'unterlag', 'nachweis'],
            'technisch': ['technisch', 'abnahme', 'prüfung']
        }
        
        for category, keywords in categories.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
                
        return 'sonstige'

    def export_data(self, data: dict, export_dir: Path) -> dict:
        """
        Exports processed data to the specified directory
        
        Args:
            data: Dictionary containing the data to export
            export_dir: Path to the export directory
            
        Returns:
            Dictionary with export results
        """
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
            
            result = {
                'status': 'success',
                'exported_files': []
            }
            
            for key, value in data.items():
                if value:
                    file_path = export_dir / f"{key}.json"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(value, f, ensure_ascii=False, indent=2)
                    result['exported_files'].append(str(file_path))
                    
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
