from transformers import AutoModelForSequenceClassification, AutoTokenizer, TrainingArguments, AutoModel
from datasets import Dataset
import torch
import torch.nn.functional as F
from typing import List, Dict, Optional
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
import logging

logger = logging.getLogger(__name__)

class GutachtenBERT:
    def __init__(self):
        self.model_name = "deepset/gbert-base"  # Speziell für deutsche Texte
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.max_length = 512
        
    def prepare_data(self, texts: List[str], labels: List[int]) -> Dataset:
        """Bereitet Daten für BERT vor"""
        encodings = self.tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors="pt"
        )
        
        return Dataset.from_dict({
            "input_ids": encodings["input_ids"],
            "attention_mask": encodings["attention_mask"],
            "labels": labels
        })

    def compute_metrics(self, pred):
        """Berechnet Metriken für das Training"""
        labels = pred.label_ids
        preds = pred.predictions.argmax(-1)
        
        precision, recall, f1, _ = precision_recall_fscore_support(
            labels, preds, average='weighted'
        )
        acc = accuracy_score(labels, preds)
        
        return {
            'accuracy': acc,
            'f1': f1,
            'precision': precision,
            'recall': recall
        }

class AuflagenClassifier(GutachtenBERT):
    def __init__(self, num_labels: int):
        super().__init__()
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=num_labels,
            problem_type="multi_label_classification"
        )
        
    def train(self, 
              train_texts: List[str],
              train_labels: List[int],
              eval_texts: Optional[List[str]] = None,
              eval_labels: Optional[List[int]] = None,
              **kwargs):
        """Trainiert den Klassifizierer"""
        training_args = TrainingArguments(
            output_dir="./results",
            learning_rate=2e-5,
            per_device_train_batch_size=16,
            per_device_eval_batch_size=16,
            num_train_epochs=3,
            weight_decay=0.01,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            push_to_hub=False,
        )
        
        train_dataset = self.prepare_data(train_texts, train_labels)
        eval_dataset = None
        if eval_texts and eval_labels:
            eval_dataset = self.prepare_data(eval_texts, eval_labels)

        trainer = Trainer( # type: ignore
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            compute_metrics=self.compute_metrics
        )
        
        trainer.train()
        return trainer.evaluate()

class GutachtenEmbedding(GutachtenBERT):
    def __init__(self):
        super().__init__()
        self.model_name = "deepset/gbert-base"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        logger.info(f"Modell geladen auf {self.device}")
        
    def encode(self, texts: List[str]) -> np.ndarray:
        """Erstellt Embeddings für Texte"""
        encodings = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt"
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**encodings)
            embeddings = self._mean_pooling(outputs, encodings['attention_mask'])
            
        return embeddings.cpu().numpy()

    def _mean_pooling(self, model_output, attention_mask):
        """Mittelt Token Embeddings mit Attention Mask"""
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def get_similarity(self, text1: str, text2: str) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Texten"""
        try:
            emb1 = self.encode([text1])[0]
            emb2 = self.encode([text2])[0]
            
            similarity = F.cosine_similarity(
                torch.tensor(emb1),
                torch.tensor(emb2)
            ).item()
            
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Fehler bei Ähnlichkeitsberechnung: {e}")
            return 0.0
