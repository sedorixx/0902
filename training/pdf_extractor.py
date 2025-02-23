import pdfplumber
import PyPDF2
from pathlib import Path
from typing import Dict, List, Optional
import re
import pandas as pd
import logging
from .models.neural import GutachtenEmbedding

logger = logging.getLogger(__name__)

class PDFExtractor:
    def __init__(self):
        self.current_pdf = None
        self.embedder = GutachtenEmbedding()
        self.table_patterns = {
            'fahrzeug': r'(hersteller|typ|handelsbezeichnung|fahrzeug)',
            'reifen': r'(dimension|reifengröße|reifentyp)',
            'auflagen': r'(auflagen|hinweise|bedingungen)'
        }

    def extract_pdf(self, pdf_path: str) -> Dict:
        """Extrahiert strukturierte Daten aus dem PDF"""
        result = {
            'fahrzeuge': [],
            'reifen': [],
            'auflagen': [],
            'meta': {},
            'tables': []
        }
        
        try:
            # Primäre Extraktion mit pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                # Extrahiere Metadaten
                result['meta'] = self._extract_metadata(pdf)
                
                for page in pdf.pages:
                    # Extrahiere und klassifiziere Tabellen
                    tables = self._extract_tables(page)
                    for table_type, table_data in tables.items():
                        if table_type in result:
                            result[table_type].extend(table_data)
                    
                    # Extrahiere und analysiere Text
                    text_blocks = self._extract_text_blocks(page)
                    for block in text_blocks:
                        block_type = self._classify_text_block(block)
                        if block_type in result:
                            processed_data = self._process_text_block(block, block_type)
                            result[block_type].extend(processed_data)

            return {
                'status': 'success',
                'data': result
            }
            
        except Exception as e:
            logger.error(f"Fehler bei PDF-Extraktion: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }

    def _extract_tables(self, page) -> Dict[str, List[Dict]]:
        """Extrahiert und klassifiziert Tabellen"""
        tables_by_type = {
            'fahrzeuge': [],
            'reifen': [],
            'auflagen': []
        }
        
        tables = page.extract_tables()
        for table in tables:
            if not table:
                continue
                
            df = pd.DataFrame(table[1:], columns=table[0])
            table_type = self._detect_table_type(df)
            if table_type:
                processed_data = self._process_table(df, table_type)
                tables_by_type[table_type].extend(processed_data)
        
        return tables_by_type

    def _detect_table_type(self, df: pd.DataFrame) -> Optional[str]:
        """Erkennt den Tabellentyp anhand der Spalten"""
        columns = ' '.join(str(col).lower() for col in df.columns)
        
        for table_type, pattern in self.table_patterns.items():
            if re.search(pattern, columns):
                return table_type
        return None

    def _process_table(self, df: pd.DataFrame, table_type: str) -> List[Dict]:
        """Verarbeitet Tabellendaten basierend auf dem Typ"""
        processed = []
        
        # Normalisiere Spaltennamen
        df.columns = [str(col).lower().strip() for col in df.columns]
        
        if table_type == 'fahrzeuge':
            required_cols = ['hersteller', 'handelsbezeichnung']
            if all(col in df.columns for col in required_cols):
                processed = df.to_dict('records')
                
        elif table_type == 'reifen':
            required_cols = ['dimension']
            if any(col in df.columns for col in required_cols):
                processed = df.to_dict('records')
                
        elif table_type == 'auflagen':
            processed = [
                {'code': row.get('code', ''), 'text': row.get('text', '')}
                for _, row in df.iterrows() if row.get('code') or row.get('text')
            ]
            
        return processed

    def _extract_text_blocks(self, page) -> List[str]:
        """Extrahiert Textblöcke mit Kontext"""
        text_blocks = []
        
        # Extrahiere Text mit Layout-Informationen
        text = page.extract_text(x_tolerance=3, y_tolerance=3)
        if text:
            # Teile in logische Blöcke
            blocks = text.split('\n\n')
            text_blocks.extend(blocks)
            
        return text_blocks

    def _classify_text_block(self, text: str) -> Optional[str]:
        """Klassifiziert Textblöcke nach Typ"""
        text_lower = text.lower()
        
        for block_type, pattern in self.table_patterns.items():
            if re.search(pattern, text_lower):
                return block_type
        return None

    def _process_text_block(self, text: str, block_type: str) -> List[Dict]:
        """Verarbeitet Textblöcke basierend auf Typ"""
        processed = []
        
        if block_type == 'auflagen':
            # Suche nach Auflagen-Codes und Text
            matches = re.finditer(r'([A-Z][0-9]{1,2}[a-z]?|[0-9]{3})[:\s]+([^\n]+)', text)
            processed.extend([
                {
                    'code': match.group(1),
                    'text': match.group(2).strip(),
                    'context': text
                }
                for match in matches
            ])
            
        return processed

    def _extract_metadata(self, pdf) -> Dict:
        """Extrahiert erweiterte Metadaten"""
        meta = pdf.metadata or {}
        meta.update({
            'page_count': len(pdf.pages),
            'timestamp': pd.Timestamp.now().isoformat()
        })
        return meta

class PDFExtractionError(Exception):
    pass
