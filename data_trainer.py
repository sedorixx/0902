import pandas as pd
import json
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

class GutachtenTrainer:
    def __init__(self):
        self.training_dir = Path('/workspaces/0902/training_data')
        self.models_dir = Path('/workspaces/0902/models')
        self.models_dir.mkdir(exist_ok=True)

    def prepare_training_data(self) -> Tuple[pd.DataFrame, Dict]:
        """Bereitet Trainingsdaten aus CSV und JSON Dateien vor"""
        # Sammle alle Fahrzeug- und Reifendaten
        fahrzeug_dfs = []
        reifen_dfs = []
        auflagen_data = {}

        # Lade CSVs
        for csv_file in self.training_dir.glob('*_fahrzeuge_*.csv'):
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            fahrzeug_dfs.append(df)

        for csv_file in self.training_dir.glob('*_reifen_*.csv'):
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            reifen_dfs.append(df)

        # Lade JSONs (Auflagen)
        for json_file in self.training_dir.glob('*_auflagen_*.json'):
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                auflagen_data.update(data.get('auflagen', {}))

        # Kombiniere Daten
        combined_data = {
            'fahrzeuge': pd.concat(fahrzeug_dfs, ignore_index=True) if fahrzeug_dfs else pd.DataFrame(),
            'reifen': pd.concat(reifen_dfs, ignore_index=True) if reifen_dfs else pd.DataFrame(),
            'auflagen': auflagen_data
        }

        return combined_data

    def train_models(self) -> None:
        """Trainiert die ML-Modelle mit den vorbereiteten Daten"""
        training_data = self.prepare_training_data()
        
        # Speichere Trainings-Snapshot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshot_file = self.training_dir / f'training_snapshot_{timestamp}.json'
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': timestamp,
                'data_stats': {
                    'fahrzeuge': len(training_data['fahrzeuge']),
                    'reifen': len(training_data['reifen']),
                    'auflagen': len(training_data['auflagen'])
                },
                'training_config': {
                    'model_type': 'classification',
                    'epochs': 5,
                    'batch_size': 32
                }
            }, f, ensure_ascii=False, indent=2)
