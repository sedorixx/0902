import os
import re
import pandas as pd
import numpy as np
import logging

# Diese Imports werden für die PDF-Verarbeitung benötigt
import tabula
import pdfplumber

def process_pdf_with_encoding(pdf_path, output_format='csv', logger=None, check_java_func=None, jvm_manager=None):
    """Verarbeitet PDF-Datei mit Berücksichtigung der Kodierung für 1:1-Extraktion"""
    # Prüfe, ob Java verfügbar ist
    if check_java_func and not check_java_func():
        if logger:
            logger.warning("Java nicht gefunden. Verwende Fallback-Methode.")
        return process_pdf_without_java(pdf_path, output_format, logger)
        
    all_tables = []
    try:
        # JVM initialisieren
        if jvm_manager:
            jvm_manager.initialize()
        
        # Fokus auf Lattice-Modus (für Tabellen mit sichtbaren Linien)
        # Dies ist am besten für strukturerhaltende 1:1-Extraktion
        if logger:
            logger.info("Lattice-Modus für präzise Tabellenextraktion")
        tables = tabula.read_pdf(
            pdf_path, 
            pages='all', 
            multiple_tables=True,
            lattice=True,
            guess=False,
            silent=True
        )
        
        # Wenn keine Tabellen gefunden wurden oder sie unvollständig erscheinen, 
        # versuchen wir den Stream-Modus als nächstes
        if not tables or len(tables) == 0:
            if logger:
                logger.info("Keine Tabellen im Lattice-Modus gefunden. Versuche Stream-Modus.")
            tables = tabula.read_pdf(
                pdf_path, 
                pages='all', 
                multiple_tables=True,
                stream=True,
                guess=False,
                silent=True
            )
        
        # Letzte Option: Kombination aus beiden mit Guess-Parameter
        if not tables or len(tables) == 0:
            if logger:
                logger.info("Versuche kombinierte Methode mit Guess-Parameter")
            tables = tabula.read_pdf(
                pdf_path,
                pages='all',
                multiple_tables=True,
                stream=True,
                lattice=True,
                guess=True,
                silent=True
            )
        
        if logger:
            logger.info(f"Tabula hat insgesamt {len(tables)} potenzielle Tabellen gefunden")
        
        # Verarbeite alle gefundenen Tabellen mit minimaler Manipulation
        for i, table in enumerate(tables):
            if logger:
                logger.info(f"Prüfe Tabelle {i+1}: {table.shape[0]} Zeilen, {table.shape[1]} Spalten")
            
            # MINIMALE Nachbearbeitung - nur NaN durch leere Strings ersetzen
            clean_table = table.fillna('')
            
            # Keine Validierung oder Filterung mehr - alle gefundenen Tabellen akzeptieren
            all_tables.append(clean_table)
            if logger:
                logger.info(f"Tabelle {i+1} hinzugefügt (1:1 Extraktion)")

        if not all_tables:
            if logger:
                logger.warning("Keine Tabellen mit tabula gefunden. Versuche Fallback-Methode.")
            return process_pdf_without_java(pdf_path, output_format, logger)
            
        return all_tables

    except Exception as e:
        if logger:
            logger.error(f"Fehler bei der Tabellenextraktion mit tabula: {str(e)}")
            logger.info("Versuche Fallback-Methode.")
        return process_pdf_without_java(pdf_path, output_format, logger)

def process_pdf_without_java(pdf_path, output_format='csv', logger=None):
    """Verarbeitet PDF-Datei ohne Java mit pdfplumber für 1:1-Extraktion"""
    if logger:
        logger.info("Verwende pdfplumber für 1:1 PDF-Tabellenextraktion")
    all_tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if logger:
                    logger.info(f"Verarbeite Seite {page_num+1} mit pdfplumber")
                
                # Standard-Tabelleneinstellungen - am besten für strukturerhaltende Extraktion
                tables = page.extract_tables()
                
                # Nur wenn keine Tabellen gefunden wurden, verwenden wir alternative Einstellungen
                if not tables:
                    if logger:
                        logger.info(f"Keine Standard-Tabellen auf Seite {page_num+1} gefunden. Versuche erweiterte Erkennung.")
                    tables = page.extract_tables(table_settings={
                        "vertical_strategy": "text", 
                        "horizontal_strategy": "text",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "edge_min_length": 3,
                        "min_words_vertical": 1,
                        "min_words_horizontal": 1
                    })
                
                if logger:
                    logger.info(f"pdfplumber hat {len(tables)} Tabellen auf Seite {page_num+1} gefunden")
                
                for i, table_data in enumerate(tables):
                    if not table_data:
                        if logger:
                            logger.info(f"Tabelle {i+1} auf Seite {page_num+1} ist leer")
                        continue
                    
                    # Erstellen eines DataFrame mit EXAKT derselben Struktur wie die gefundene Tabelle
                    headers = [f"Spalte_{j+1}" for j in range(len(table_data[0]))] if table_data[0] else []
                    
                    # Wenn die erste Zeile gute Überschriften enthält, nutze diese
                    if all(str(h).strip() for h in table_data[0]):
                        df = pd.DataFrame(table_data[1:], columns=table_data[0])
                    else:
                        df = pd.DataFrame(table_data, columns=headers)
                    
                    # Minimale Nachbearbeitung
                    df = df.fillna('')
                    
                    all_tables.append(df)
                    if logger:
                        logger.info(f"Tabelle {i+1} auf Seite {page_num+1} hinzugefügt (1:1 Extraktion)")
        
        if not all_tables:
            if logger:
                logger.warning("Keine Tabellen mit pdfplumber gefunden. Extrahiere Text als letzte Option.")
            # Versuche als letzten Ausweg den gesamten Text zu extrahieren
            return extract_text_as_structured_table(pdf_path, logger)
            
        return all_tables

    except Exception as e:
        if logger:
            logger.error(f"Fehler bei der pdfplumber Extraktion: {str(e)}")
        return extract_text_as_structured_table(pdf_path, logger)

def extract_text_as_structured_table(pdf_path, logger=None):
    """Extrahiert Text und versucht, eine Tabellenstruktur zu erkennen"""
    if logger:
        logger.info("Versuche Text mit Strukturerkennung zu extrahieren")
    try:
        all_tables = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue
                
                # Zeilen nach Zeilenumbrüchen trennen
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                
                # Versuchen wir, die Tabellenstruktur zu erkennen (suche nach Tabulatoren oder mehreren Leerzeichen)
                rows = []
                for line in lines:
                    # Zuerst nach Tabs suchen
                    if '\t' in line:
                        cells = [cell.strip() for cell in line.split('\t')]
                        rows.append(cells)
                    else:
                        # Nach mehreren Leerzeichen suchen (wahrscheinliche Zellentrennungen)
                        split_pattern = re.compile(r'\s{2,}')
                        cells = [cell.strip() for cell in split_pattern.split(line) if cell.strip()]
                        if len(cells) > 1:  # Nur hinzufügen, wenn es wie eine Tabelle aussieht
                            rows.append(cells)
                
                if rows:
                    # Finde die maximale Anzahl von Spalten
                    max_cols = max(len(row) for row in rows)
                    
                    # Fülle Zeilen mit weniger Spalten auf
                    padded_rows = [row + [''] * (max_cols - len(row)) for row in rows]
                    
                    # Versuche zu erkennen, ob die erste Zeile eine Überschriftenzeile ist
                    has_header = False
                    if len(padded_rows) > 1:
                        first_row = padded_rows[0]
                        # Wenn die erste Zeile kürzer ist oder sich deutlich von den anderen unterscheidet
                        # (z.B. enthält keine Zahlen, enthält nur Text), dann ist es wahrscheinlich eine Überschrift
                        if all(not re.search(r'\d', cell) for cell in first_row) and \
                           any(re.search(r'\d', cell) for row in padded_rows[1:] for cell in row):
                            has_header = True
                    
                    if has_header:
                        df = pd.DataFrame(padded_rows[1:], columns=padded_rows[0])
                    else:
                        df = pd.DataFrame(padded_rows, columns=[f"Spalte_{i+1}" for i in range(max_cols)])
                    
                    all_tables.append(df)
                    if logger:
                        logger.info(f"Strukturierte Texttabelle von Seite {page_num+1} extrahiert: {len(df)} Zeilen, {len(df.columns)} Spalten")
        
        if not all_tables:
            # Als letzte Option, erstelle eine einfache Texttabelle
            return extract_text_as_simple_table(pdf_path, logger)
            
        return all_tables
        
    except Exception as e:
        if logger:
            logger.error(f"Fehler bei der strukturierten Textextraktion: {str(e)}")
        return extract_text_as_simple_table(pdf_path, logger)

def extract_text_as_simple_table(pdf_path, logger=None):
    """Letzte Fallback-Methode: Extrahiert Text als einfache Tabelle"""
    if logger:
        logger.info("Extrahiere Text als einfache Tabelle (letzte Option)")
    try:
        all_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        
        if not all_text:
            if logger:
                logger.error("Kein Text in der PDF gefunden")
            # Erstelle leere DataFrame mit Hinweis
            return [pd.DataFrame([["Keine Tabellen oder Text in der PDF erkannt"]], columns=["Hinweis"])]
            
        # Kombiniere allen Text und teile nach Zeilen
        combined_text = '\n'.join(all_text)
        lines = [line for line in combined_text.split('\n') if line.strip()]
        
        if not lines:
            if logger:
                logger.error("Keine Textzeilen gefunden")
            return [pd.DataFrame([["Keine strukturierten Zeilen in der PDF gefunden"]], columns=["Hinweis"])]
        
        # Erstelle ein einfaches DataFrame mit dem Text
        df = pd.DataFrame(lines, columns=["PDF-Textinhalt"])
        
        if logger:
            logger.info(f"Einfache Texttabelle mit {len(df)} Zeilen erstellt")
        return [df]
        
    except Exception as e:
        if logger:
            logger.error(f"Fehler beim finalen Fallback: {str(e)}")
        # Erstelle generische Fehlertabelle
        return [pd.DataFrame([["Fehler bei der Textextraktion: " + str(e)]], columns=["Fehler"])]

def extract_auflagen_with_text(pdf_path, app, logger=None):
    """Extrahiert Auflagen-Codes und deren zugehörige Texte aus der PDF"""
    codes_with_text = {}
    excluded_texts = [
        "Technologiezentrum Typprüfstelle Lambsheim - Königsberger Straße 20d - D-67245 Lambsheim",
    ]
    collect_text = True  # Flag für die Textsammlung
    current_section = ""  # Buffer für den aktuellen Textabschnitt

    try:
        with app.app_context():
            from models import AuflagenCode
            db_codes = {code.code: code.description for code in AuflagenCode.query.all()}
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    # Prüfe auf Ende der Auflagen
                    if "Prüfort und Prüfdatum" in line:
                        if logger:
                            logger.info("Extraktion beendet - 'Prüfort und Prüfdatum' gefunden")
                        # Speichere letzten Abschnitt vor dem Beenden
                        if current_section:
                            code_match = re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)](.+)', current_section)
                            if code_match:
                                code = code_match.group(1).strip()
                                description = code_match.group(2).strip()
                                if code in db_codes:
                                    codes_with_text[code] = description
                                    if logger:
                                        logger.info(f"Letzter Code gespeichert: {code}")
                        return codes_with_text  # Beende die Funktion sofort
                    
                    # Prüfe auf "Technologiezentrum"
                    if "Technologiezentrum" in line:
                        if logger:
                            logger.info("Technologie gefunden - Pausiere Extraktion")
                        collect_text = False
                        current_section = ""  # Verwerfe aktuellen Abschnitt
                        continue

                    # Prüfe auf neuen Auflagen-Code
                    if re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)]', line):
                        if logger:
                            logger.info(f"Neuer Code gefunden: {line[:20]}...")
                        
                        # Speichere vorherigen Abschnitt wenn vorhanden
                        if collect_text and current_section:
                            code_match = re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)](.+)', current_section)
                            if code_match:
                                code = code_match.group(1).strip()
                                description = code_match.group(2).strip()
                                if code in db_codes:
                                    codes_with_text[code] = description
                                    if logger:
                                        logger.info(f"Gespeichert: {code}")
                        
                        collect_text = True  # Setze Extraktion fort
                        current_section = line  # Starte neuen Abschnitt
                        continue

                    # Sammle Text wenn aktiv
                    if collect_text and current_section:
                        current_section += " " + line

    except Exception as e:
        if logger:
            logger.error(f"Fehler beim Extrahieren der Auflagen-Texte: {str(e)}")
    
    # Bereinige die gesammelten Texte
    for code, text in codes_with_text.items():
        text = re.sub(r'\s+', ' ', text)  # Entferne mehrfache Leerzeichen
        text = text.strip()
        codes_with_text[code] = text
        if logger:
            logger.info(f"Finaler Code {code}: {text[:100]}...")

    return codes_with_text

def extract_auflagen_codes(tables, app, pdf_path, logger=None):
    """Extrahiert Auflagen-Codes aus Tabellen und aktualisiert die Datenbank"""
    codes = set()
    code_pattern = re.compile(r"""
        (?:
            [A-Z][0-9]{1,3}[a-z]?|    # Bsp: A01, B123a
            [0-9]{2,3}[A-Z]?|          # Bsp: 155, 12A
            NoH|Lim                     # Spezielle Codes
        )
    """, re.VERBOSE)
    
    # Explizit erlaubte Spalten
    allowed_columns = {
        'reifenbezogene auflagen und hinweise',
        'auflagen und hinweise',
        'auflagen'
    }

    # Explizit ausgeschlossene Spalten
    excluded_columns = {
        'handelsbezeichnung',
        'fahrzeug-typ',
        'abe/ewg-nr',
        'fahrzeugtyp',
        'typ',
        'abe',
        'ewg-nr'
    }

    for table in tables:
        # Konvertiere alle Werte zu Strings und normalisiere Spaltennamen
        table_str = table.astype(str)
        
        # Normalisiere Spaltennamen (zu Kleinbuchstaben und ohne Sonderzeichen)
        normalized_columns = {
            col: col.strip().lower().replace('/', '').replace('-', '').replace(' ', '')
            for col in table_str.columns
        }

        for original_col, normalized_col in normalized_columns.items():
            # Überspringe explizit ausgeschlossene Spalten
            if any(excl in normalized_col for excl in excluded_columns):
                continue
                
            # Prüfe nur erlaubte Spalten
            if any(allowed in normalized_col for allowed in allowed_columns):
                for value in table_str[original_col]:
                    matches = code_pattern.findall(str(value))
                    codes.update(matches)
    
    # Extrahiere auch die Auflagen-Texte aus der PDF
    extracted_texts = extract_auflagen_with_text(pdf_path, app, logger)
    if logger:
        logger.info(f"Gefundene Auflagen-Texte: {len(extracted_texts)}")
        for code, text in extracted_texts.items():
            logger.info(f"Code {code}: {text[:100]}...")
    
    # Modifizierte Logik für das Speichern der Codes mit Texten
    with app.app_context():
        from models import AuflagenCode
        from extensions import db
        
        # Lade AUFLAGEN_TEXTE für Fallback
        from utils import AUFLAGEN_TEXTE
        
        existing_codes = set(code.code for code in AuflagenCode.query.all())
        new_codes = codes - existing_codes
        
        for code in new_codes:
            description = extracted_texts.get(code)  # Versuche zuerst den extrahierten Text
            if not description:  # Falls nicht gefunden, verwende Standard-Text
                description = AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar")
            
            new_code = AuflagenCode(
                code=code,
                description=description
            )
            db.session.add(new_code)
        
        db.session.commit()

    # Kombiniere gefundene Codes mit ihren Texten
    codes_with_text = {}
    for code in codes:
        # Stelle sicher, dass AUFLAGEN_TEXTE auch hier verfügbar ist
        from utils import AUFLAGEN_TEXTE
        description = extracted_texts.get(code, AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar"))
        codes_with_text[code] = description
    
    # Speichere in der Datenbank
    try:
        with app.app_context():
            from models import AuflagenCode
            from extensions import db
            
            for code, description in codes_with_text.items():
                # Prüfe, ob der Code bereits existiert
                existing_code = AuflagenCode.query.filter_by(code=code).first()
                
                if existing_code:
                    # Aktualisiere nur, wenn der Text sich geändert hat
                    if existing_code.description != description:
                        existing_code.description = description
                        if logger:
                            logger.info(f"Aktualisiere Code {code} in der Datenbank")
                else:
                    # Füge neuen Code hinzu
                    new_code = AuflagenCode(code=code, description=description)
                    db.session.add(new_code)
                    if logger:
                        logger.info(f"Füge neuen Code {code} zur Datenbank hinzu")
            
            db.session.commit()
            if logger:
                logger.info("Datenbank erfolgreich aktualisiert")
            
    except Exception as e:
        if logger:
            logger.error(f"Fehler beim Speichern in der Datenbank: {str(e)}")
        with app.app_context():
            from extensions import db
            db.session.rollback()
    
    return sorted(list(codes))
