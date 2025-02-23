import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import re

class GutachtenDataExtractor:
    def __init__(self):
        self.training_dir = Path('/workspaces/0902/training_data')
        self.training_dir.mkdir(exist_ok=True)

    def extract_wheel_info_from_filename(self, filename: str) -> Dict:
        """Extrahiert Felgeninformationen aus dem Dateinamen
        Format: DM08-85x19-5x112-ET45-666
        """
        if not isinstance(filename, str) or not filename:
            raise ValueError("Dateiname muss ein nicht-leerer String sein")

        # Entferne eventuelle Dateiendungen
        base_name = Path(filename).stem
        
        try:
            parts = base_name.split('-')
            if len(parts) != 5:
                raise ValueError(f"Ungültiges Dateinamenformat: {base_name}")

            # Extrahiere die einzelnen Komponenten
            wheel_info = {
                'felgenname': parts[0],                    # DM08
                'felgengroesse': self._parse_size(parts[1]), # 85x19 -> {'breite': 8.5, 'durchmesser': 19}
                'lochkreis': self._parse_pcd(parts[2]),    # 5x112 -> {'anzahl': 5, 'durchmesser': 112}
                'et': self._parse_et(parts[3]),           # ET45 -> 45
                'mittelloch': int(parts[4].split('.')[0]) # 666
            }
            
            return wheel_info
        except Exception as e:
            print(f"Fehler beim Parsen des Dateinamens {filename}: {str(e)}")
            return {}

    def _parse_size(self, size_str: str) -> Dict:
        """Konvertiert '85x19' zu {'breite': 8.5, 'durchmesser': 19}"""
        try:
            breite_str, durchmesser = size_str.lower().split('x')
            # Konvertiere 85 zu 8.5 für die Breite
            breite = float(breite_str) / 10
            return {
                'breite': breite,
                'durchmesser': int(durchmesser)
            }
        except Exception:
            raise ValueError(f"Ungültiges Größenformat: {size_str}")

    def _parse_pcd(self, pcd_str: str) -> Dict:
        """Konvertiert '5x112' zu {'anzahl': 5, 'durchmesser': 112}"""
        try:
            anzahl, durchmesser = pcd_str.lower().split('x')
            return {
                'anzahl': int(anzahl),
                'durchmesser': int(durchmesser)
            }
        except Exception:
            raise ValueError(f"Ungültiges Lochkreisformat: {pcd_str}")

    def _parse_et(self, et_str: str) -> int:
        """Extrahiert ET-Wert aus 'ET45' -> 45"""
        try:
            return int(et_str.lower().replace('et', ''))
        except Exception:
            raise ValueError(f"Ungültiges ET-Format: {et_str}")

    def _combine_wheel_data(self, data: Dict, wheel_info: Dict) -> Dict:
        """Kombiniert Fahrzeug- und Reifendaten mit Felgeninformationen"""
        for table in data.get('fahrzeuge', []):
            # Füge Felgeninformationen zu jedem Fahrzeugeintrag hinzu
            if isinstance(table, dict):
                table.update({
                    'felge_name': wheel_info['felgenname'],
                    'felge_breite': wheel_info['felgengroesse']['breite'],
                    'felge_durchmesser': wheel_info['felgengroesse']['durchmesser'],
                    'felge_lochkreis': f"{wheel_info['lochkreis']['anzahl']}x{wheel_info['lochkreis']['durchmesser']}",
                    'felge_et': wheel_info['et'],
                    'felge_mittelloch': wheel_info['mittelloch']
                })

        for table in data.get('reifen', []):
            # Füge Felgeninformationen zu jedem Reifeneintrag hinzu
            if isinstance(table, dict):
                table.update({
                    'passende_felge': wheel_info['felgenname'],
                    'felge_spezifikation': (
                        f"{wheel_info['felgengroesse']['breite']}J"
                        f"x{wheel_info['felgengroesse']['durchmesser']} "
                        f"ET{wheel_info['et']}"
                    )
                })
        
        return data

    def _process_tire_data(self, tire_data: List[str]) -> List[Dict]:
        """Verarbeitet Reifendaten in strukturiertes Format"""
        from training.tire_processor import TireProcessor
        processor = TireProcessor()
        processed_tires = []
        
        for entry in tire_data:
            tire_spec = processor.parse_tire_string(str(entry))
            if tire_spec:
                processed_tires.append({
                    'dimension': f"{tire_spec.width}/{tire_spec.aspect_ratio}R{tire_spec.diameter}",
                    'breite': tire_spec.width,
                    'querschnitt': tire_spec.aspect_ratio,
                    'durchmesser': tire_spec.diameter,
                    'auflagen': tire_spec.codes,
                    'original_text': tire_spec.original
                })
        
        return processed_tires

    def _validate_wheel_tire_combination(self, wheel_info: Dict, tire_data: List[Dict]) -> List[Dict]:
        """Validiert Felgen-Reifen-Kombinationen"""
        from training.tire_processor import TireProcessor
        processor = TireProcessor()
        validated_combinations = []
        
        for tire in tire_data:
            try:
                tire_spec = processor.parse_tire_string(tire['original_text'])
                if not tire_spec:
                    continue
                    
                validation = processor.validate_tire_wheel_combo(
                    tire=tire_spec,
                    wheel_width=wheel_info['felgengroesse']['breite'],
                    wheel_diameter=wheel_info['felgengroesse']['durchmesser']
                )
                
                tire.update({
                    'validated': True,
                    'felge_kompatibel': validation['valid'],
                    'warnungen': validation['warnings'],
                    'fehler': validation['errors'],
                    'felgen_details': {
                        'name': wheel_info['felgenname'],
                        'breite': wheel_info['felgengroesse']['breite'],
                        'et': wheel_info['et'],
                        'lochkreis': f"{wheel_info['lochkreis']['anzahl']}x{wheel_info['lochkreis']['durchmesser']}"
                    }
                })
                validated_combinations.append(tire)
                
            except Exception as e:
                print(f"Fehler bei der Validierung: {str(e)}")
                continue
                
        return validated_combinations

    def save_extracted_data(self, data: Dict, source_pdf: str) -> None:
        """Speichert extrahierte Daten im Training-Verzeichnis"""
        if not isinstance(data, dict):
            raise ValueError("data muss ein Dictionary sein")
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = Path(source_pdf).stem
        validated_combinations = []
        
        try:
            # Extrahiere Felgeninformationen aus dem Dateinamen
            wheel_info = self.extract_wheel_info_from_filename(base_name)
            
            if not wheel_info:
                raise ValueError(f"Konnte keine Felgeninformationen aus {base_name} extrahieren")
            
            # Verarbeite und validiere Reifendaten
            if 'reifen' in data:
                processed_tires = self._process_tire_data(data['reifen'])
                validated_combinations = self._validate_wheel_tire_combination(wheel_info, processed_tires)
                data['reifen'] = validated_combinations
            
            # Kombiniere Felgen- und Fahrzeugdaten
            if 'fahrzeuge' in data:
                data = self._combine_wheel_data(data, wheel_info)
            
            # Speichere kombinierte Daten
            combined_file = self.training_dir / f'{base_name}_kombinationen_{timestamp}.json'
            with open(combined_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'source': source_pdf,
                    'timestamp': timestamp,
                    'felgen_info': wheel_info,
                    'validierte_kombinationen': validated_combinations,
                    'statistik': {
                        'gesamt_kombinationen': len(validated_combinations),
                        'kompatibel': sum(1 for t in validated_combinations if t.get('felge_kompatibel', False))
                    }
                }, f, ensure_ascii=False, indent=2)

            # Speichere Fahrzeugdaten
            if 'fahrzeuge' in data:
                fahrzeug_file = self.training_dir / f'{base_name}_fahrzeuge_{timestamp}.csv'
                pd.DataFrame(data['fahrzeuge']).to_csv(fahrzeug_file, index=False, encoding='utf-8-sig')
                
            # Speichere Reifendaten
            if 'reifen' in data:
                reifen_file = self.training_dir / f'{base_name}_reifen_{timestamp}.csv'
                pd.DataFrame(data['reifen']).to_csv(reifen_file, index=False, encoding='utf-8-sig')
                
            # Speichere Auflagen und Hinweise
            if 'auflagen' in data:
                auflagen_file = self.training_dir / f'{base_name}_auflagen_{timestamp}.json'
                with open(auflagen_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'source': source_pdf,
                        'timestamp': timestamp,
                        'auflagen': data['auflagen']
                    }, f, ensure_ascii=False, indent=2)
            
            # Speichere Metadaten
            meta_file = self.training_dir / f'{base_name}_meta_{timestamp}.json'
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'source': source_pdf,
                    'timestamp': timestamp,
                    'file_count': {
                        'fahrzeuge': len(data.get('fahrzeuge', [])),
                        'reifen': len(data.get('reifen', [])),
                        'auflagen': len(data.get('auflagen', []))
                    }
                }, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Fehler beim Speichern der Daten: {str(e)}")
            raise
