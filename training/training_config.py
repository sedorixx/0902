from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class TrainingConfig:
    model_name: str = "deepset/gbert-large"
    learning_rate: float = 2e-5
    batch_size: int = 16
    max_epochs: int = 10
    warmup_steps: int = 500
    weight_decay: float = 0.01
    max_length: int = 512
    gradient_accumulation_steps: int = 2
    early_stopping_patience: int = 3
    scheduler_type: str = "linear"
    fp16: bool = True  # Mixed precision training
    
    # Multi-Task Learning Gewichte
    task_weights: Optional[Dict[str, float]] = None
    
    # Modell-spezifische Parameter
    model_config: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.task_weights is None:
            self.task_weights = {
                "auflagen": 1.0,
                "fahrzeug": 0.8,
                "reifen": 0.8
            }
        
        if self.model_config is None:
            self.model_config = {
                "hidden_dropout_prob": 0.1,
                "attention_probs_dropout_prob": 0.1,
                "layer_norm_eps": 1e-7
            }
