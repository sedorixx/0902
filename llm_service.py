import os
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from functools import lru_cache
import gc
import psutil
import logging
from typing import Dict, List, Optional, Union
import threading
import bitsandbytes as bnb

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, model_path="TinyLlama/TinyLlama-1.1B-Chat-v1.0", cache_size=128):
        self.model_path = model_path
        self.tokenizer = None
        self.model = None
        self.device = None
        self.lock = threading.Lock()
        self.logger = self._setup_logging()
        self.device = self._get_optimal_device()
        self._initialize_model()

    def _setup_logging(self):
        """Konfiguriert das Logging für den Service"""
        logger = logging.getLogger(f"{__name__}.LLMService")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _get_optimal_device(self) -> str:
        """Wählt das optimale Gerät basierend auf Verfügbarkeit und Speicher"""
        if torch.cuda.is_available():
            try:
                # Prüfe verfügbaren GPU-Speicher
                gpu_memory = torch.cuda.get_device_properties(0).total_memory
                if gpu_memory > 4 * 1024 * 1024 * 1024:  # > 4GB
                    return "cuda"
            except:
                pass
        return "cpu"

    def _initialize_model(self):
        """Initialisiert das Modell mit CPU-optimierten Einstellungen"""
        try:
            self._clear_memory()
            
            # Optimierte Tokenizer-Konfiguration
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                use_fast=True
            )

            # Wichtig: Setze pad_token verschieden von eos_token
            self.tokenizer.pad_token = self.tokenizer.pad_token or '[PAD]'
            if self.tokenizer.pad_token == self.tokenizer.eos_token:
                self.tokenizer.pad_token = '[PAD]'
            
            # Basis Modell-Konfiguration
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                trust_remote_code=True,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            ).to("cpu")
            
            self._log_memory_usage()
            self.logger.info("Modell erfolgreich geladen")
            
        except Exception as e:
            self.logger.error(f"Modell-Initialisierung fehlgeschlagen: {e}")
            self.model = None

    def _clear_memory(self):
        """Bereinigt den Speicher"""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def _log_memory_usage(self):
        """Protokolliert den aktuellen Speicherverbrauch"""
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_usage_mb = memory_info.rss / 1024 / 1024
        self.logger.info(f"Aktueller Speicherverbrauch: {memory_usage_mb:.2f} MB")

    @lru_cache(maxsize=256)
    def generate_response(self, prompt: str) -> str:
        """Generiert eine Antwort mit verbesserter Token-Handhabung"""
        with self.lock:
            if not self.model or not self.tokenizer:
                return "Modell nicht verfügbar"
                
            try:
                self._clear_memory()
                
                # Verbesserte Tokenisierung mit expliziter attention_mask
                inputs = self.tokenizer(
                    prompt,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    add_special_tokens=True,
                    return_attention_mask=True
                )
                
                with torch.inference_mode():
                    outputs = self.model.generate(
                        input_ids=inputs["input_ids"],
                        attention_mask=inputs["attention_mask"],
                        max_new_tokens=512,
                        num_return_sequences=1,
                        temperature=0.7,
                        do_sample=True,
                        pad_token_id=self.tokenizer.pad_token_id,
                        eos_token_id=self.tokenizer.eos_token_id
                    )
                
                response = self.tokenizer.decode(
                    outputs[0], 
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=True
                )
                
                self._clear_memory()
                return response
                
            except Exception as e:
                self.logger.error(f"Generierungsfehler: {e}")
                return self._handle_generation_error(e)
    
    def _handle_generation_error(self, error: Exception) -> str:
        """Verbesserte Fehlerbehandlung"""
        if isinstance(error, RuntimeError) and "out of memory" in str(error):
            self._clear_memory()
            return "Speicherfehler - Bitte versuchen Sie einen kürzeren Text"
        return f"Fehler bei der Generierung: {str(error)}"

    def analyze_codes_and_info(self, codes, vehicle_info, wheel_tire_info):
        """Analysiert die Informationen mit optimierter Promptverarbeitung"""
        prompt = self._create_optimized_prompt(codes, vehicle_info, wheel_tire_info)
        return self.generate_response(prompt)
    
    def _create_optimized_prompt(self, codes, vehicle_info, wheel_tire_info):
        """Erstellt einen optimierten Prompt für bessere Antworten"""
        return f"""Analysiere folgende Rad/Reifenkombination:

Auflagencodes: {', '.join(codes) if codes else 'Keine'}

Fahrzeug:
{'; '.join(f'{k}: {v}' for k, v in vehicle_info.items()) if vehicle_info else 'Keine Fahrzeugdaten'}

Rad/Reifen:
{'; '.join(f'{k}: {v}' for k, v in wheel_tire_info.items()) if wheel_tire_info else 'Keine Rad/Reifendaten'}

Bitte gib eine kurze, präzise Einschätzung zur Eintragungspflicht und möglichen Besonderheiten."""
        
    def __del__(self):
        """Verbesserte Ressourcenfreigabe"""
        try:
            if hasattr(self, 'model') and self.model is not None:
                self.model.cpu()  # Verschiebe Modell zur CPU
                del self.model
            if hasattr(self, 'tokenizer') and self.tokenizer is not None:
                del self.tokenizer
            self._clear_memory()
        except:
            pass
