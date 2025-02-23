from pathlib import Path
import os

# Basis-Verzeichnis (absoluter Pfad zum Projektordner)
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Trainings-Verzeichnisse mit absoluten Pfaden
TRAINING_DATA_DIR = BASE_DIR / 'training_data'
MODELS_DIR = BASE_DIR / 'models'
REPROCESS_DIR = BASE_DIR / 'reprocess'
EXPORT_DIR = BASE_DIR / 'exported_data'

# Erstelle die Verzeichnisse mit Fehlerbehandlung
def ensure_directories():
    dirs = [TRAINING_DATA_DIR, MODELS_DIR, REPROCESS_DIR, EXPORT_DIR]
    for dir_path in dirs:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"Verzeichnis existiert oder wurde erstellt: {dir_path}")
        except Exception as e:
            print(f"Fehler beim Erstellen von {dir_path}: {e}")
            raise

# Trainings-Konfiguration
TRAINING_CONFIG = {
    'batch_size': 32,
    'epochs': 10,
    'validation_split': 0.2,
    'learning_rate': 3e-5,
    'max_seq_length': 512,
    'model_name': 'bert-base-german-cased'
}

# Stelle sicher, dass die Verzeichnisse existieren
ensure_directories()
