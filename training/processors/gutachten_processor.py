import pandas as pd
import json
from pathlib import Path
from typing import Dict, List
import re
from ...training.config import TRAINING_DATA_DIR

class GutachtenProcessor:
    def __init__(self):
        self.training_dir = TRAINING_DATA_DIR
