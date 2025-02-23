from typing import Dict, List
import re
import pandas as pd

class DataValidator:
    def validate_wheel_info(self, wheel_info: Dict) -> Dict:
        """Validiert Felgeninformationen"""
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'data': None
        }
        
        try:
            required_fields = {
                'felgenname': str,
                'felgengroesse': dict,
                'lochkreis': dict,
                'et': (int, float)
            }
            
            # Prüfe ob alle erforderlichen Felder vorhanden sind
            for field, field_type in required_fields.items():
                if field not in wheel_info:
                    result['errors'].append(f"Fehlendes Feld: {field}")
                    continue
                    
                if not isinstance(wheel_info[field], field_type):
                    result['errors'].append(f"Ungültiger Typ für {field}")
                    continue
                    
            # Spezielle Validierung für felgengroesse
            if 'felgengroesse' in wheel_info:
                size_info = wheel_info['felgengroesse']
                if not all(k in size_info for k in ['breite', 'durchmesser']):
                    result['errors'].append("Unvollständige Felgengröße")
                elif not isinstance(size_info['breite'], (int, float)):
                    result['errors'].append("Ungültige Felgenbreite")
                elif not isinstance(size_info['durchmesser'], int):
                    result['errors'].append("Ungültiger Felgendurchmesser")
                    
            # Spezielle Validierung für lochkreis
            if 'lochkreis' in wheel_info:
                pcd_info = wheel_info['lochkreis']
                if not all(k in pcd_info for k in ['anzahl', 'durchmesser']):
                    result['errors'].append("Unvollständiger Lochkreis")
                elif not isinstance(pcd_info['anzahl'], int):
                    result['errors'].append("Ungültige Lochanzahl")
                elif not isinstance(pcd_info['durchmesser'], int):
                    result['errors'].append("Ungültiger Lochkreisdurchmesser")
                    
            # Validierung bestanden wenn keine Fehler
            if not result['errors']:
                result['valid'] = True
                result['data'] = wheel_info
                
        except Exception as e:
            result['errors'].append(f"Validierungsfehler: {str(e)}")
            
        return result

    def validate_wheel_tire_combo(self, wheel_info: Dict, tire_info: Dict) -> Dict:
        """Validiert Felgen-Reifen-Kombinationen"""
        result = {
            'valid': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Extrahiere Reifendimensionen
            tire_pattern = r'(\d{3})/(\d{2})R(\d{2})'
            match = re.match(tire_pattern, tire_info['dimension'])
            
            if not match:
                result['errors'].append('Ungültiges Reifenformat')
                return result
                
            width, ratio, rim = match.groups()
            
            # Validiere Felgenbreite
            tire_width = int(width)
            wheel_width = float(wheel_info['felgengroesse']['breite']) * 25.4  # Konvertiere zu mm
            
            if not (wheel_width * 0.9 <= tire_width <= wheel_width * 1.1):
                result['warnings'].append('Felgenbreite möglicherweise nicht optimal')
                
            # Validiere Durchmesser
            if int(rim) != wheel_info['felgengroesse']['durchmesser']:
                result['errors'].append('Felgendurchmesser passt nicht zur Reifengröße')
                return result
                
            result['valid'] = len(result['errors']) == 0
            
        except Exception as e:
            result['errors'].append(f'Validierungsfehler: {str(e)}')
            
        return result

    def validate_vehicle_compatibility(self, vehicle_data: Dict, wheel_info: Dict) -> Dict:
        """Validiert Fahrzeug-Felgen Kompatibilität"""
        result = {
            'valid': False,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Validiere Lochkreis
            if 'lochkreis' in vehicle_data:
                vehicle_pcd = vehicle_data['lochkreis']
                wheel_pcd = f"{wheel_info['lochkreis']['anzahl']}x{wheel_info['lochkreis']['durchmesser']}"
                
                if vehicle_pcd != wheel_pcd:
                    result['errors'].append('Lochkreis nicht kompatibel')
                    
            # Validiere Einpresstiefe (ET)
            if 'et_bereich' in vehicle_data:
                min_et, max_et = map(int, vehicle_data['et_bereich'].split('-'))
                if not (min_et <= wheel_info['et'] <= max_et):
                    result['errors'].append('Einpresstiefe außerhalb des zulässigen Bereichs')
                    
            result['valid'] = len(result['errors']) == 0
            
        except Exception as e:
            result['errors'].append(f'Validierungsfehler: {str(e)}')
            
        return result
