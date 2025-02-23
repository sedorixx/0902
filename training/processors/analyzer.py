from pathlib import Path
import pandas as pd
import json
from typing import Dict, List
from datetime import datetime
from ..config import TRAINING_DATA_DIR, MODELS_DIR
from ..data_trainer import GutachtenTrainer
from .gutachten_processor import GutachtenProcessor

# Verschiebe bestehenden GutachtenAnalyzer Code hierher
class GutachtenAnalyzer:
    def __init__(self):
        self.processor = GutachtenProcessor()
        self.trainer = GutachtenTrainer()
        self.training_dir = TRAINING_DATA_DIR
        self.models_dir = MODELS_DIR
