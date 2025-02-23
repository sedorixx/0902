from pathlib import Path

BASE_DIR = Path('/workspaces/0902')
TRAINING_DATA_DIR = Path("/workspaces/0902/training_data")
MODELS_DIR = Path("/workspaces/0902/models")
REPROCESS_DIR = Path("/workspaces/0902/reprocess")
EXPORT_DIR = BASE_DIR / 'exported_data'

# Stellen Sie sicher, dass alle notwendigen Verzeichnisse existieren
TRAINING_DATA_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)
REPROCESS_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

# Training Konfiguration
TRAINING_CONFIG = {
    'batch_size': 32,
    'epochs': 5,
    'learning_rate': 3e-5,
    'max_seq_length': 512,
    'model_name': 'bert-base-german-cased'
}
