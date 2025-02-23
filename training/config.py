from pathlib import Path

# Basis-Verzeichnis (der aktuelle Projektordner)
BASE_DIR = Path(__file__).parent.parent

# Trainings-Verzeichnisse
TRAINING_DATA_DIR = BASE_DIR / 'training_data'
MODELS_DIR = BASE_DIR / 'models'
REPROCESS_DIR = BASE_DIR / 'reprocess'
EXPORT_DIR = BASE_DIR / 'exported_data'

# Erstelle die Verzeichnisse
for dir_path in [TRAINING_DATA_DIR, MODELS_DIR, REPROCESS_DIR, EXPORT_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Trainings-Konfiguration
TRAINING_CONFIG = {
    'batch_size': 32,
    'epochs': 10,
    'validation_split': 0.2,
    'learning_rate': 3e-5,
    'max_seq_length': 512,
    'model_name': 'bert-base-german-cased'
}
