import tabula
import pandas as pd
import os

def extract_tables_from_pdf(pdf_path, output_format='csv'):
    """
    Extrahiert Tabellen aus einer PDF-Datei
    
    Args:
        pdf_path (str): Pfad zur PDF-Datei
        output_format (str): Format für den Export ('csv' oder 'excel')
    """
    # Extrahiere alle Tabellen aus der PDF
    tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)
    
    # Basis-Dateiname ohne Erweiterung
    base_name = os.path.splitext(pdf_path)[0]
    
    # Exportiere jede gefundene Tabelle
    for i, table in enumerate(tables):
        if output_format == 'csv':
            output_path = f"{base_name}_table_{i+1}.csv"
            table.to_csv(output_path, index=False)
        else:
            output_path = f"{base_name}_table_{i+1}.xlsx"
            table.to_excel(output_path, index=False)
            
        print(f"Tabelle {i+1} wurde exportiert nach: {output_path}")

if __name__ == "__main__":
    # Beispielaufruf
    pdf_path = "beispiel.pdf"
    extract_tables_from_pdf(pdf_path, output_format='csv')
