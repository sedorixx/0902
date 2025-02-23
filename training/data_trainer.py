from pathlib import Path
import pandas as pd
import json
from typing import Dict, List, Tuple, Optional, Union
from datetime import datetime
from .config import TRAINING_DATA_DIR, MODELS_DIR, TRAINING_CONFIG, REPROCESS_DIR
from .models import AuflagenClassifier
from .pdf_extractor import PDFExtractor
from .data_validator import DataValidator
from .export_data import DataProcessor
import shutil

class GutachtenTrainer:
    def __init__(self, training_dir: Union[str, Path] = '/workspaces/0902/training_data'):
        self.training_dir = Path(training_dir)
        self.training_dir.mkdir(exist_ok=True)
        self.cached_data = self._init_cache()
        self.last_update = None
        self.data_validator = DataValidator()
        self.data_processor = DataProcessor()

    def _init_cache(self) -> Dict:
        """Initialisiert den Cache mit leeren Strukturen"""
        return {
            'kombinationen': [],
            'fahrzeuge': [],
            'reifen': [],
            'auflagen': []
        }

    def _is_cache_valid(self, max_age_minutes: int = 60) -> bool:
        """Prüft ob der Cache noch gültig ist"""
        if not self.last_update:
            return False
        age = (datetime.now() - self.last_update).total_seconds() / 60
        return age < max_age_minutes

    def load_training_data(self, max_age_minutes: int = 60) -> Dict:
        """Lädt alle Trainingsdaten aus dem Verzeichnis"""
        if self._is_cache_valid(max_age_minutes):
            return self.cached_data

        self.cached_data = self._init_cache()

        try:
            # Lade alle JSON-Dateien für Kombinationen
            for json_file in self.training_dir.glob('*_kombinationen_*.json'):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):  # Validiere JSON-Struktur
                            self.cached_data['kombinationen'].append(data)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"Fehler beim Lesen der JSON-Datei {json_file}: {e}")
                    continue

            # Lade CSV-Dateien mit Fehlerbehandlung
            self._load_csv_files('fahrzeuge')
            self._load_csv_files('reifen')

            # Lade Auflagen mit Validierung
            self._load_auflagen()

            self.last_update = datetime.now()
            return self.cached_data

        except Exception as e:
            print(f"Fehler beim Laden der Trainingsdaten: {str(e)}")
            return self.cached_data

    def _load_csv_files(self, data_type: str) -> None:
        """Lädt CSV-Dateien für den angegebenen Datentyp"""
        for csv_file in self.training_dir.glob(f'*_{data_type}_*.csv'):
            try:
                df = pd.read_csv(csv_file, encoding='utf-8-sig')
                if not df.empty:
                    self.cached_data[data_type].extend(df.to_dict('records'))
            except Exception as e:
                print(f"Fehler beim Lesen der CSV-Datei {csv_file}: {e}")

    def _load_auflagen(self) -> None:
        """Lädt und validiert Auflagen aus JSON-Dateien"""
        for json_file in self.training_dir.glob('*_auflagen_*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'auflagen' in data:
                        self.cached_data['auflagen'].extend(
                            [a for a in data['auflagen'] if isinstance(a, (str, dict))]
                        )
            except Exception as e:
                print(f"Fehler beim Laden der Auflagen aus {json_file}: {e}")

    def get_statistics(self) -> Dict:
        """Erstellt eine Statistik über die Trainingsdaten"""
        data = self.load_training_data()
        
        return {
            'datensätze': {
                'kombinationen': len(data['kombinationen']),
                'fahrzeuge': len(data['fahrzeuge']),
                'reifen': len(data['reifen']),
                'auflagen': len(data['auflagen'])
            },
            'reifen_statistik': self._analyze_tire_data(data['reifen']),
            'fahrzeug_statistik': self._analyze_vehicle_data(data['fahrzeuge']),
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    def _analyze_tire_data(self, tire_data: List[Dict]) -> Dict:
        """Analysiert die Reifendaten"""
        if not tire_data:
            return {}
            
        df = pd.DataFrame(tire_data)
        
        return {
            'durchschnitt_breite': df['breite'].mean() if 'breite' in df else None,
            'häufigste_dimension': df['dimension'].mode().iloc[0] if 'dimension' in df else None,
            'anzahl_validiert': df['validated'].sum() if 'validated' in df else 0,
            'anzahl_kompatibel': df['felge_kompatibel'].sum() if 'felge_kompatibel' in df else 0
        }

    def _analyze_vehicle_data(self, vehicle_data: List[Dict]) -> Dict:
        """Analysiert die Fahrzeugdaten"""
        if not vehicle_data:
            return {}
            
        df = pd.DataFrame(vehicle_data)
        
        return {
            'anzahl_hersteller': df['hersteller'].nunique() if 'hersteller' in df else 0,
            'anzahl_modelle': df['modell'].nunique() if 'modell' in df else 0
        }

    def export_training_summary(self, output_file: Optional[Path] = None) -> None:
        """Exportiert eine Zusammenfassung der Trainingsdaten"""
        try:
            stats = self.get_statistics()
            
            if output_file is None:
                output_file = self.training_dir / f'training_summary_{datetime.now():%Y%m%d_%H%M%S}.json'
            
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Fehler beim Exportieren der Zusammenfassung: {e}")

    def prepare_training_data(self) -> Dict[str, pd.DataFrame]:
        """Bereitet Trainingsdaten aus CSV und JSON Dateien vor"""
        training_data = {
            'fahrzeuge': pd.DataFrame(),
            'reifen': pd.DataFrame(),
            'auflagen': [],
            'kombinationen': []
        }
        
        # Lade alle Dateien
        for file_path in self.training_dir.glob('*_kombinationen_*.json'):
            with open(file_path, 'r', encoding='utf-8') as f:
                kombi_data = json.load(f)
                if 'validierte_kombinationen' in kombi_data:
                    training_data['kombinationen'].extend(kombi_data['validierte_kombinationen'])

        # Verarbeite Fahrzeugdaten
        fahrzeug_files = list(self.training_dir.glob('*_fahrzeuge_*.csv'))
        if fahrzeug_files:
            dfs = []
            for f in fahrzeug_files:
                try:
                    df = pd.read_csv(f, encoding='utf-8-sig')
                    dfs.append(df)
                except Exception as e:
                    print(f"Fehler beim Lesen von {f}: {e}")
            if dfs:
                training_data['fahrzeuge'] = pd.concat(dfs, ignore_index=True)

        # Verarbeite Reifendaten mit Felgeninformationen
        reifen_files = list(self.training_dir.glob('*_reifen_*.csv'))
        if reifen_files:
            dfs = []
            for f in reifen_files:
                try:
                    df = pd.read_csv(f, encoding='utf-8-sig')
                    # Extrahiere Felgenname aus Dateinamen
                    felge = f.stem.split('_')[0]
                    df['felge'] = felge
                    dfs.append(df)
                except Exception as e:
                    print(f"Fehler beim Lesen von {f}: {e}")
            if dfs:
                training_data['reifen'] = pd.concat(dfs, ignore_index=True)

        return training_data

    def analyze_combination(self, fahrzeug: str, felge: str, reifen: str) -> Dict:
        """Analysiert eine spezifische Kombination"""
        if not all([fahrzeug, felge, reifen]):
            return {'error': 'Alle Parameter müssen angegeben werden'}
            
        data = self.load_training_data()
        result = {
            'zulässig': False,
            'auflagen': [],
            'details': {},
            'felgen_info': {},
            'warnungen': []
        }
        
        try:
            # Suche in Kombinationen mit verbesserter Fehlerbehandlung
            for kombi in data['kombinationen']:
                if not isinstance(kombi, dict):
                    continue
                    
                if (kombi.get('felge_kompatibel', False) and
                    kombi.get('dimension', '') == reifen):
                    result['zulässig'] = True
                    result['auflagen'] = kombi.get('auflagen', [])
                    result['felgen_info'] = kombi.get('felgen_details', {})
                    break
            
            # Suche passende Fahrzeuge mit Fuzzy-Matching
            fahrzeuge_df = pd.DataFrame(data['fahrzeuge'])
            if not fahrzeuge_df.empty and 'handelsbezeichnung' in fahrzeuge_df:
                fahrzeug_filter = fahrzeuge_df['handelsbezeichnung'].str.contains(
                    fahrzeug, case=False, na=False, regex=True
                )
                matching_vehicles = fahrzeuge_df[fahrzeug_filter]
                if not matching_vehicles.empty:
                    result['details']['fahrzeug'] = matching_vehicles.iloc[0].to_dict()
                    
        except Exception as e:
            result['warnungen'].append(f"Fehler bei der Analyse: {str(e)}")
            
        return result

    def train_models(self) -> Dict:
        """Trainiert die ML-Modelle mit den vorbereiteten Daten"""
        training_data = self.prepare_training_data()
        
        training_results = {
            'status': 'success',
            'metrics': {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Trainiere Auflagen-Klassifizierer
            if len(training_data['kombinationen']) > 0:
                auflagen_texts = []
                auflagen_labels = []
                for kombi in training_data['kombinationen']:
                    if isinstance(kombi, dict) and kombi.get('auflagen'):
                        auflagen_texts.append(kombi.get('original_text', ''))
                        auflagen_labels.append(kombi['auflagen'])
                
                if auflagen_texts:
                    self.auflagen_classifier = AuflagenClassifier()
                    metrics = self.auflagen_classifier.train(
                        train_texts=auflagen_texts,
                        train_labels=auflagen_labels
                    )
                    training_results['metrics']['auflagen'] = metrics
            
            # Speichere Trainings-Snapshot
            self._save_training_snapshot(training_results)
            
        except Exception as e:
            training_results['status'] = 'error'
            training_results['error'] = str(e)
            
        return training_results

    def _save_training_snapshot(self, results: Dict) -> None:
        """Speichert einen Snapshot des Trainings"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshot_file = self.training_dir / f'training_snapshot_{timestamp}.json'
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': timestamp,
                'results': results,
                'config': TRAINING_CONFIG
            }, f, ensure_ascii=False, indent=2)

    def process_gutachten(self, pdf_path: str, wheel_info: Optional[Dict] = None) -> Dict:
        """Verarbeitet ein Gutachten vollständig"""
        try:
            # Suche PDF in reprocess-Verzeichnis falls nicht gefunden
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                reprocess_pdf = REPROCESS_DIR / pdf_file.name
                if reprocess_pdf.exists():
                    # Kopiere PDF in Workspace
                    shutil.copy2(str(reprocess_pdf), str(pdf_file))
                    print(f"PDF aus reprocess kopiert: {pdf_file.name}")
                else:
                    return {
                        'status': 'error',
                        'error': f'PDF-Datei nicht gefunden: Weder in {pdf_path} noch in {reprocess_pdf}',
                        'step': 'process_gutachten'
                    }

            # Lade Daten aus reprocess
            reprocess_data = self.load_reprocess_data()
            
            # Verarbeite PDF und extrahiere Daten
            processed_data = self.data_processor.process_pdf(
                pdf_path=str(pdf_file),  # Nutze den aktualisierten Pfad
                wheel_info=wheel_info
            )
            
            if processed_data['status'] != 'success':
                return processed_data
                
            # Bereite Trainingsdaten vor
            training_data = self.prepare_training_data()
            
            # Trainiere Modelle nur wenn neue Daten valide sind
            if processed_data['validation'].get('valid', False):
                training_results = self.train_models()
                processed_data['training'] = training_results
                
            # Exportiere verarbeitete Daten
            export_results = self.data_processor.export_data(
                data=processed_data['data'],
                export_dir=self.training_dir / 'processed_data'
            )
            processed_data['export'] = export_results
            
            return processed_data
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'step': 'process_gutachten'
            }

    def _validate_combinations(self, data: Dict) -> Dict:
        """Validiert alle Fahrzeug-Felgen-Reifen Kombinationen"""
        validated = {
            'valid_combinations': [],
            'invalid_combinations': [],
            'warnings': []
        }
        
        for wheel_info in data.get('felgen', []):
            for tire_info in data.get('reifen', []):
                # Validiere Felgen-Reifen Kombination
                tire_validation = self.data_validator.validate_wheel_tire_combo(
                    wheel_info, tire_info
                )
                
                if tire_validation['valid']:
                    combo = {
                        'felge': wheel_info,
                        'reifen': tire_info,
                        'validation': tire_validation
                    }
                    validated['valid_combinations'].append(combo)
                else:
                    validated['invalid_combinations'].append({
                        'felge': wheel_info,
                        'reifen': tire_info,
                        'errors': tire_validation['errors']
                    })
                    
                if tire_validation['warnings']:
                    validated['warnings'].extend(tire_validation['warnings'])
                    
        return validated

    def load_reprocess_data(self) -> Dict:
        """Lädt Daten aus dem reprocess-Verzeichnis"""
        reprocess_data = {
            'kombinationen': [],
            'fahrzeuge': [],
            'reifen': [],
            'auflagen': []
        }
        
        try:
            # Durchsuche reprocess-Verzeichnis nach JSON-Dateien
            for json_file in REPROCESS_DIR.glob('*.json'):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            # Verarbeite die Daten basierend auf dem Dateinamen
                            base_name = json_file.stem
                            if 'kombinationen' in base_name:
                                reprocess_data['kombinationen'].append(data)
                            elif 'auflagen' in base_name:
                                if 'auflagen' in data:
                                    reprocess_data['auflagen'].extend(data['auflagen'])
                except Exception as e:
                    print(f"Fehler beim Laden von {json_file}: {e}")
                    continue

            # Lade CSV-Dateien aus dem reprocess-Verzeichnis
            for csv_file in REPROCESS_DIR.glob('*.csv'):
                try:
                    df = pd.read_csv(csv_file, encoding='utf-8-sig')
                    if not df.empty:
                        if 'fahrzeuge' in csv_file.stem:
                            reprocess_data['fahrzeuge'].extend(df.to_dict('records'))
                        elif 'reifen' in csv_file.stem:
                            reprocess_data['reifen'].extend(df.to_dict('records'))
                except Exception as e:
                    print(f"Fehler beim Laden von {csv_file}: {e}")
                    continue

            # Kopiere Daten ins Training-Verzeichnis
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self._save_to_training_dir(reprocess_data, timestamp)
            
            return reprocess_data

        except Exception as e:
            print(f"Fehler beim Laden der Reprocess-Daten: {e}")
            return reprocess_data

    def _save_to_training_dir(self, data: Dict, timestamp: str) -> None:
        """Speichert verarbeitete Daten im Training-Verzeichnis"""
        try:
            # Speichere Kombinationen
            if data['kombinationen']:
                kombinationen_file = TRAINING_DATA_DIR / f'kombinationen_{timestamp}.json'
                with open(kombinationen_file, 'w', encoding='utf-8') as f:
                    json.dump(data['kombinationen'], f, ensure_ascii=False, indent=2)

            # Speichere Fahrzeugdaten
            if data['fahrzeuge']:
                fahrzeug_file = TRAINING_DATA_DIR / f'fahrzeuge_{timestamp}.csv'
                pd.DataFrame(data['fahrzeuge']).to_csv(fahrzeug_file, index=False, encoding='utf-8-sig')

            # Speichere Reifendaten
            if data['reifen']:
                reifen_file = TRAINING_DATA_DIR / f'reifen_{timestamp}.csv'
                pd.DataFrame(data['reifen']).to_csv(reifen_file, index=False, encoding='utf-8-sig')

            # Speichere Auflagen
            if data['auflagen']:
                auflagen_file = TRAINING_DATA_DIR / f'auflagen_{timestamp}.json'
                with open(auflagen_file, 'w', encoding='utf-8') as f:
                    json.dump({'auflagen': data['auflagen']}, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"Fehler beim Speichern in training_data: {e}")