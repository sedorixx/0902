from pathlib import Path
import json
from training.export_data import DataProcessor
from training.data_trainer import GutachtenTrainer
from training.auflagen_classifier import AuflagenClassifier

def process_gutachten(pdf_path: str) -> None:
    """Hauptfunktion für die Gutachtenverarbeitung"""
    try:
        # Extrahiere Felgeninformationen aus Dateinamen
        base_name = Path(pdf_path).stem
        trainer = GutachtenTrainer()
        
        # Verarbeite Gutachten
        result = trainer.process_gutachten(pdf_path)
        
        # Trainiere AuflagenClassifier
        classifier = AuflagenClassifier()
        metrics = classifier.train(
            train_texts=['Text 1', 'Text 2'],
            train_labels=[['Auflage1', 'Auflage2'], ['Auflage3']]
        )
        predictions = classifier.predict(['Neuer Text'])
        
        # Speichere Ergebnisse
        output_file = Path('/workspaces/0902/results') / f"{base_name}_results.json"
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            
        print(f"Verarbeitung abgeschlossen. Ergebnisse in: {output_file}")
        
    except Exception as e:
        print(f"Fehler bei der Verarbeitung: {str(e)}")

if __name__ == "__main__":
    pdf_path = "/workspaces/0902/DM08-85x19-5x112-ET45-666.pdf"
    process_gutachten(pdf_path)
