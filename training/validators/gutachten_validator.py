from typing import Dict, List
import re

class GutachtenValidator:
    def __init__(self):
        self.required_fields = {
            'fahrzeug': ['fin', 'marke', 'modell'],
            'felgen': ['groesse', 'typ', 'hersteller'],
            'reifen': ['groesse', 'typ', 'hersteller'],
            'technische_daten': ['einpresstiefe', 'lochkreis']
        }
        
    def validate_gutachten(self, extracted_data: Dict) -> Dict[str, bool]:
        """Validiert die extrahierten Daten gemäß ar.txt Anleitung"""
        validation_results = {}
        
        # Prüfe Vollständigkeit
        validation_results['vollstaendigkeit'] = self._check_completeness(extracted_data)
        
        # Prüfe Fahrzeugdaten
        validation_results['fahrzeug'] = self._validate_vehicle_data(
            extracted_data.get('fahrzeug', {})
        )
        
        # Prüfe technische Daten
        validation_results['technisch'] = self._validate_technical_data(
            extracted_data.get('technische_daten', {})
        )
        
        # Prüfe Zulassungsstatus
        validation_results['zulassung'] = self._validate_approval_status(
            extracted_data.get('zulassung', {})
        )
        
        return validation_results
        
    def _check_completeness(self, data: Dict) -> bool: # type: ignore
        """Prüft die Vollständigkeit aller erforderlichen Felder"""
        for section, fields in self.required_fields.items():
            if section not in data:
                return False
            for field in fields:
                if field not in data[section]:
                    return False
            return True
    
    def _validate_technical_data(self, technical_data: Dict) -> bool:
        """Validiert technische Daten des Gutachtens"""
        if not technical_data:
            return False
            
        # Prüfe erforderliche technische Werte
        if not all(key in technical_data for key in ['einpresstiefe', 'lochkreis']):
            return False
            
        return True

    def _validate_vehicle_data(self, vehicle_data: Dict) -> bool:
        """Validiert Fahrzeugdaten gemäß Herstellervorgaben"""
        if not vehicle_data.get('fin'):
            return False
            
        fin = vehicle_data['fin']
        # Prüfe FIN-Format (17 Zeichen, gültige Struktur)
        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', fin):
            return False
            
        return True

    def _validate_approval_status(self, approval_data: Dict) -> bool:
        """Validiert den Zulassungsstatus"""
        if not approval_data:
            return False
        return True
