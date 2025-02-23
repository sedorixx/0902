import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer
from typing import List, Dict, Tuple
import numpy as np

class GutachtenTransformer(nn.Module):
    def __init__(self, num_labels: int):
        super().__init__()
        self.bert = AutoModel.from_pretrained("deepset/gbert-large")
        self.dropout = nn.Dropout(0.3)
        self.classifier = nn.Linear(1024, num_labels)  # gbert-large hat 1024 hidden size
        
        # Mehrschichtiger Classifier für bessere Feature-Extraktion
        self.classifier_layers = nn.Sequential(
            nn.Linear(1024, 512),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_labels)
        )
        
    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        pooled_output = outputs[0][:, 0]  # CLS token
        pooled_output = self.dropout(pooled_output)
        return self.classifier_layers(pooled_output)

class HierarchicalAttention(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1, bias=False)
        )
        
    def forward(self, hidden_states, attention_mask):
        attention_weights = self.attention(hidden_states).squeeze(-1)
        attention_weights = attention_weights.masked_fill(~attention_mask, float('-inf'))
        attention_weights = torch.softmax(attention_weights, dim=1)
        return torch.bmm(attention_weights.unsqueeze(1), hidden_states).squeeze(1)
