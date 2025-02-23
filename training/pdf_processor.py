import pdfplumber
from typing import Dict, List, Optional, Union
import pandas as pd
import logging
from pathlib import Path
from .models.neural import GutachtenEmbedding

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self):
        self.embedder = GutachtenEmbedding()
        self.current_pdf = None
        self.cache = {}

    def process_pdf(self, pdf_path: Union[str, Path], extract_tables: bool = True) -> Dict:
        """Verarbeitet PDF mit verbesserter Extraktion"""
        try:
            pdf_path = Path(pdf_path)
            cache_key = f"{pdf_path.stem}_{pdf_path.stat().st_mtime}"
            
            # Prüfe Cache
            if cache_key in self.cache:
                logger.info(f"Nutze Cache für {pdf_path.name}")
                return self.cache[cache_key]

            with pdfplumber.open(pdf_path) as pdf:
                result = {
                    'status': 'success',
                    'content': {
                        'text_blocks': [],
                        'tables': [],
                        'metadata': self._extract_metadata(pdf)
                    }
                }

                for page in pdf.pages:
                    # Extrahiere Text mit Layout-Analyse
                    text_blocks = self._extract_text_blocks(page)
                    result['content']['text_blocks'].extend(text_blocks)
                    
                    if extract_tables:
                        tables = self._extract_tables(page)
                        result['content']['tables'].extend(tables)

                # Klassifiziere Inhalte
                result['content']['classified'] = self._classify_content(result['content'])
                
                # Cache Ergebnis
                self.cache[cache_key] = result
                return result

        except Exception as e:
            logger.error(f"Fehler bei PDF-Verarbeitung: {str(e)}")
            return {'status': 'error', 'error': str(e)}

    def _extract_text_blocks(self, page) -> List[Dict]:
        """Extrahiert Textblöcke mit Layout-Informationen"""
        blocks = []
        
        text = page.extract_text(x_tolerance=3, y_tolerance=3)
        if not text:
            return blocks

        # Teile Text in semantische Blöcke
        raw_blocks = text.split('\n\n')
        
        for block in raw_blocks:
            if not block.strip():
                continue
                
            # Erstelle Embedding für den Block
            embedding = self.embedder.encode([block])[0]
            
            blocks.append({
                'text': block.strip(),
                'embedding': embedding.tolist(),
                'page': page.page_number,
                'type': self._detect_block_type(block)
            })
            
        return blocks

    def _extract_tables(self, page) -> List[Dict]:
        """Extrahiert und verarbeitet Tabellen"""
        tables = []
        
        for table in page.extract_tables():
            if not table:
                continue
                
            df = pd.DataFrame(table[1:], columns=table[0])
            if df.empty:
                continue
                
            # Normalisiere Spaltennamen
            df.columns = [str(col).lower().strip() for col in df.columns]
            
            tables.append({
                'data': df.to_dict('records'),
                'page': page.page_number,
                'columns': df.columns.tolist(),
                'type': self._detect_table_type(df)
            })
            
        return tables

    def _detect_block_type(self, text: str) -> str:
        """Erkennt den Typ eines Textblocks"""
        text_lower = text.lower()
        
        if any(keyword in text_lower for keyword in ['auflagen', 'hinweise', 'bedingungen']):
            return 'auflagen'
        elif any(keyword in text_lower for keyword in ['reifen', 'felgen', 'räder']):
            return 'reifen'
        elif any(keyword in text_lower for keyword in ['fahrzeug', 'typ', 'hersteller']):
            return 'fahrzeug'
        
        return 'sonstiges'

    def _detect_table_type(self, df: pd.DataFrame) -> str:
        """Erkennt den Typ einer Tabelle anhand der Spalten"""
        columns = set(df.columns)
        
        if {'hersteller', 'typ', 'handelsbezeichnung'}.intersection(columns):
            return 'fahrzeug'
        elif {'dimension', 'reifengröße', 'reifentyp'}.intersection(columns):
            return 'reifen'
        elif {'code', 'auflage', 'text'}.intersection(columns):
            return 'auflagen'
            
        return 'unbekannt'

    def _classify_content(self, content: Dict) -> Dict:
        """Klassifiziert und gruppiert Inhalte"""
        classified = {
            'fahrzeug': [],
            'reifen': [],
            'auflagen': [],
            'sonstiges': []
        }
        
        # Klassifiziere Textblöcke
        for block in content['text_blocks']:
            block_type = block['type']
            if block_type in classified:
                classified[block_type].append(block)
                
        # Klassifiziere Tabellen
        for table in content['tables']:
            table_type = table['type']
            if table_type in classified:
                classified[table_type].append(table)
                
        return classified

    def _extract_metadata(self, pdf) -> Dict:
        """Extrahiert erweiterte Metadaten"""
        meta = pdf.metadata or {}
        meta.update({
            'page_count': len(pdf.pages),
            'has_text': any(page.extract_text() for page in pdf.pages),
            'has_tables': any(page.extract_tables() for page in pdf.pages)
        })
        return meta
