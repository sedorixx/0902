import sys
import subprocess
import threading
import re
import os
import pandas as pd
import numpy as np
import logging
from functools import lru_cache

# Constants - Auflagen codes and texts
AUFLAGEN_CODES = [
    "155", 
    "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10",
    "A11", "A12", "A13", "A14", "A14a", "A15", "A58"
]

AUFLAGEN_TEXTE = {
    "155": "Das Sonderrad (gepr. Radlast) ist in Verbindung mit dieser Reifengröße nur zulässig bis zu einer zul. Achslast von 1550 kg...",
    "A01": "Nach Durchführung der Technischen Änderung ist das Fahrzeug unter Vorlage der vorliegenden ABE unverzüglich einem amtlich anerkannten Sachverständigen einer Technischen Prüfstelle vorzuführen.",
    "A02": "Die Verwendung der Rad-/Reifenkombination ist nur zulässig an Fahrzeugen mit serienmäßiger Rad-/Reifenkombination in den Größen gemäß Fahrzeugpapieren.",
    "A03": "Die Verwendung der Rad-/Reifenkombination ist nur zulässig, sofern diese in den entsprechenden Fahrzeugpapieren eingetragen ist.",
    "A04": "Die Rad-/Reifenkombination ist nur zulässig für Fahrzeugausführungen mit Allradantrieb.",
    "A05": "Die Rad-/Reifenkombination ist nur zulässig für Fahrzeugausführungen mit Heckantrieb.",
    "A06": "Die Rad-/Reifenkombination ist nur zulässig für Fahrzeugausführungen mit Frontantrieb.",
    "A07": "Die mindestens erforderlichen Geschwindigkeitsbereiche (PR-Zahl) und Tragfähigkeiten der verwendeten Reifen sind den Fahrzeugpapieren zu entnehmen.",
    "A08": "Verwendung nur zulässig an Fahrzeugen mit serienmäßiger Rad-/Reifenkombination gemäß EG-Typgenehmigung.",
    "A09": "Die Rad-/Reifenkombination ist nur an der Vorderachse zulässig.",
    "A10": "Es dürfen nur feingliedrige Schneeketten an der Hinterachse verwendet werden.",
    "A11": "Es dürfen nur feingliedrige Schneeketten an der Antriebsachse verwendet werden.",
    "A12": "Die Verwendung von Schneeketten ist nicht zulässig.",
    "A13": "Nur zulässig für Fahrzeuge ohne Schneekettenbetrieb.",
    "A14": "Zum Auswuchten der Räder dürfen an der Felgenaußenseite nur Klebegewichte unterhalb der Felgenschulter angebracht werden.",
    "A14a": "Zum Auswuchten der Räder dürfen an der Felgenaußenseite keine Gewichte angebracht werden.",
    "A15": "Die Verwendung des Rades mit genannter Einpresstiefe ist nur zulässig, wenn das Fahrzeug serienmäßig mit Rädern dieser Einpresstiefe ausgerüstet ist.",
    "A58": "Rad-/Reifenkombination(en) nicht zulässig an Fahrzeugen mit Allradantrieb.",
    "Lim": "Nur zulässig für Limousinen-Ausführungen des Fahrzeugtyps.",
    "NoH": "Die Verwendung an Fahrzeugen mit Niveauregulierung ist nicht zulässig."
}

# Required packages definition
required_packages = {
    'flask': 'Flask',
    'pandas': 'pandas',
    'tabula-py': 'tabula',
    'jpype1': 'jpype',
    'openpyxl': 'openpyxl',
    'pdfplumber': 'pdfplumber',
    'flask-sqlalchemy': 'flask_sqlalchemy',
    'psutil': 'psutil'
}

# Utility Functions
def check_and_install_packages(logger=None):
    """Überprüft und installiert fehlende Pakete"""
    for package, import_name in required_packages.items():
        try:
            __import__(import_name.lower())
        except ImportError:
            if logger:
                logger.info(f"Installiere {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# File Management Class
class TemporaryStorage:
    """Verwaltet temporäre Dateien mit automatischer Bereinigung"""
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.active_files = set()
        self.lock = threading.Lock()
    
    def add_file(self, filename):
        """Markiert eine Datei als aktiv"""
        with self.lock:
            self.active_files.add(filename)
    
    def remove_file(self, filename):
        """Entfernt eine Datei aus dem aktiven Set und löscht sie"""
        with self.lock:
            if filename in self.active_files:
                self.active_files.remove(filename)
                filepath = os.path.join(self.base_dir, filename)
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"Fehler beim Löschen von {filepath}: {e}")
    
    def cleanup_inactive(self):
        """Löscht alle inaktiven Dateien"""
        try:
            with self.lock:
                for filename in os.listdir(self.base_dir):
                    if filename not in self.active_files:
                        filepath = os.path.join(self.base_dir, filename)
                        try:
                            if os.path.isfile(filepath):
                                os.remove(filepath)
                        except Exception as e:
                            print(f"Fehler beim Löschen von {filepath}: {e}")
        except Exception as e:
            print(f"Fehler bei der Bereinigung: {e}")

@lru_cache(maxsize=32)
def is_valid_table(df, logger=None):
    """Überprüft, ob ein DataFrame eine echte Tabelle ist (mit Caching)"""
    # Grundlegende Prüfung - Tabelle muss Inhalt haben
    if df.empty:
        if logger:
            logger.info("Tabelle wird abgelehnt: Leer")
        return False
    
    # Extrem lockere Validierung
    # Mindestens 1 Spalte und 1 Zeile
    if len(df.columns) == 0 or len(df) == 0:
        if logger:
            logger.info(f"Tabelle wird abgelehnt: Keine Spalten oder Zeilen ({len(df.columns)}x{len(df)})")
        return False
    
    # Mindestens ein nicht-leerer Wert in der Tabelle
    if df.astype(str).replace('', np.nan).count().sum() == 0:
        if logger:
            logger.info("Tabelle wird abgelehnt: Enthält keine Daten")
        return False
        
    if logger:
        logger.info(f"Tabelle akzeptiert: {len(df)} Zeilen, {len(df.columns)} Spalten")
    return True

def convert_table_to_html(df):
    """Konvertiert DataFrame in formatiertes HTML"""
    return df.to_html(
        classes='table table-striped table-hover',
        index=False,
        border=0,
        escape=False,
        na_rep=''
    )

def extract_vehicle_info(df):
    """Extrahiert Fahrzeuginformationen aus DataFrame"""
    vehicle_info = {}
    
    # Typische Spalten und ihre normalisierte Form
    key_columns = {
        'fahrzeug': ['fzg', 'fahrzeugtyp', 'typ', 'modell', 'vehicle'],
        'hersteller': ['manufacturer', 'marke', 'fabrikat'],
        'typ': ['type', 'fahrzeugtyp', 'typen', 'modell']
    }
    
    # Normalisiere Spaltennamen
    normalized_columns = {col.lower().strip(): col for col in df.columns}
    
    # Suche nach relevanten Spalten
    for target, alternatives in key_columns.items():
        for alt in [target] + alternatives:
            for col in normalized_columns:
                if alt in col:
                    # Versuche, einen sinnvollen Wert zu finden
                    values = df[normalized_columns[col]].unique()
                    for val in values:
                        if isinstance(val, str) and len(val) > 2 and val.lower() != 'nan':
                            vehicle_info[target.capitalize()] = val
                            break
    
    return vehicle_info

def extract_wheel_tire_info(df):
    """Extrahiert Rad/Reifen-Informationen aus DataFrame mit verbesserter Zuverlässigkeit"""
    wheel_tire_info = {}
    
    # Erweiterte Erkennungsmuster für relevante Spalten
    key_patterns = {
        'Reifengröße': ['reifen', 'tire', 'dimension', 'größe', 'size', 'reifentyp'],
        'Felgengröße': ['felge', 'rim', 'wheel', 'alufelge', 'räder', 'zoll'],
        'Einpresstiefe': ['et', 'offset', 'einpress', 'einpresstiefe'],
        'Hersteller': ['hersteller', 'manufacturer', 'producer', 'marke', 'brand'],
        'Tragfähigkeit': ['load', 'traglast', 'tragfähigkeit', 'last', 'gewicht', 'kg'],
        'Geschwindigkeitsindex': ['speed', 'geschwindigkeit', 'index', 'km/h', 'si']
    }
    
    # Verbesserte Normalisierung von Spaltennamen
    normalized_columns = {col.lower().strip().replace('-', '').replace('_', ''): col for col in df.columns}
    
    # Direkte Werterkennung durch Muster
    patterns = {
        'Reifengröße': r'(\d{3}/\d{2}[R]\d{2})', # z.B. 205/55R16
        'Felgengröße': r'(\d{1,2}[,.]\d{1}[Jx]?\d{2})', # z.B. 7J16 oder 7,5x16
        'Einpresstiefe': r'ET\s*(\d{1,2})', # z.B. ET35
    }
    
    # Zuerst direkte Suche in den Werten aller Spalten
    for key, pattern in patterns.items():
        if key not in wheel_tire_info:
            for col in df.columns:
                for value in df[col].astype(str):
                    match = re.search(pattern, value, re.IGNORECASE)
                    if match:
                        wheel_tire_info[key] = match.group(0)
                        break
                if key in wheel_tire_info:
                    break
    
    # Dann Suche nach relevanten Spalten
    for target, pats in key_patterns.items():
        if target not in wheel_tire_info:  # Nur suchen wenn noch nicht gefunden
            for pattern in pats:
                for col in normalized_columns:
                    if pattern in col:
                        # Werte prüfen
                        values = df[normalized_columns[col]].astype(str).unique()
                        for val in values:
                            if len(val) > 2 and val.lower() not in ['nan', '', 'none']:
                                wheel_tire_info[target] = val
                                break
                        if target in wheel_tire_info:
                            break
                if target in wheel_tire_info:
                    break
    
    # Nachbearbeitung: Formatierung standardisieren
    if 'Einpresstiefe' in wheel_tire_info:
        # Extrahiere nur die Zahl, wenn "ET" enthalten ist
        et_val = wheel_tire_info['Einpresstiefe']
        if 'et' in et_val.lower():
            et_match = re.search(r'(?:et)\s*(\d+)', et_val.lower())
            if et_match:
                wheel_tire_info['Einpresstiefe'] = f"ET {et_match.group(1)}"
    
    return wheel_tire_info

def find_condition_codes(df):
    """Findet Auflagen-Codes in einem DataFrame"""
    codes = set()
    code_pattern = re.compile(r"""
        (?:
            [A-Z][0-9]{1,3}[a-z]?|    # Bsp: A01, B123a
            [0-9]{2,3}[A-Z]?|          # Bsp: 155, 12A
            NoH|Lim                     # Spezielle Codes
        )
    """, re.VERBOSE)
    
    # Suche in allen String-Spalten
    for col in df.columns:
        for value in df[col]:
            if isinstance(value, str):
                matches = code_pattern.findall(value)
                codes.update(matches)
    
    return list(codes)

def analyze_freedom(codes, auflagen_db, vehicle_info, wheel_tire_info):
    """Analysiert, ob eine Rad/Reifenkombination eintragungsfrei ist"""
    # Definiere Codes die auf Eintragungsfreiheit hindeuten
    freedom_positive = ['A02', 'A08']  # Codes, die explizit Eintragungsfreiheit bestätigen
    
    # Codes die auf Eintragungspflicht hindeuten
    freedom_negative = ['A01', 'A03']  # Codes, die explizit Eintragung erfordern
    
    # Codes die neutral sind oder von Bedingungen abhängen
    freedom_conditional = ['A04', 'A05', 'A06', 'A07', 'A09', 'A10', 'A11', 'A14', 'A15']
    
    # Bewertungsmechanismus
    reasons = []
    rating = 0  # -100 bis 100, wobei >0 eintragungsfrei bedeutet
    
    # Analysiere gefundene Codes
    condition_codes = []
    
    for code in codes:
        impact = "neutral"
        description = auflagen_db.get(code, "Keine Beschreibung verfügbar")
        
        if code in freedom_positive:
            impact = "positive"
            rating += 40
            reasons.append({
                "type": "positive", 
                "text": f"Code {code} weist auf Eintragungsfreiheit hin: {description}"
            })
        elif code in freedom_negative:
            impact = "negative"
            rating -= 50
            reasons.append({
                "type": "negative", 
                "text": f"Code {code} weist auf Eintragungspflicht hin: {description}"
            })
        elif code in freedom_conditional:
            impact = "neutral"
            # Kein Rating-Änderung, aber Hinweis
            reasons.append({
                "type": "neutral", 
                "text": f"Code {code} benötigt weitere Bewertung: {description}"
            })
        else:
            # Unbekannter Code
            reasons.append({
                "type": "neutral", 
                "text": f"Code {code} konnte nicht bewertet werden: {description}"
            })
        
        condition_codes.append({
            "code": code,
            "description": description,
            "impact": impact
        })
    
    # Weitere Analysen basierend auf Fahrzeugdaten
    if not codes:
        reasons.append({
            "type": "neutral",
            "text": "Keine Auflagencodes gefunden - ohne Codes kann keine sichere Bewertung erfolgen"
        })
        rating -= 10
    
    if 'A02' in codes and 'A03' in codes:
        reasons.append({
            "type": "negative",
            "text": "Widersprüchliche Codes gefunden (A02 und A03) - im Zweifelsfall ist Eintragung erforderlich"
        })
        rating -= 30
    
    # Berechne Zuverlässigkeit
    base_confidence = 70  # Basiswert
    
    # Mehr Codes = höhere Zuverlässigkeit (bis zu einem gewissen Grad)
    codes_factor = min(len(codes) * 5, 20)
    
    confidence = base_confidence + codes_factor
    
    # Bei widersprüchlichen Codes sinkt die Zuverlässigkeit
    if 'A02' in codes and 'A03' in codes:
        confidence -= 20
    
    # Begrenze auf 0-100%
    confidence = max(0, min(confidence, 100))
    confidence = round(confidence)
    
    # Entscheidung treffen
    is_free = rating > 0
    
    # Erstelle Zusammenfassung
    if is_free:
        summary = ("Die Analyse deutet auf Eintragungsfreiheit hin. Es wurden Codes gefunden, die explizit "
                  "auf eine erlaubte Verwendung ohne Eintragung hinweisen.")
        if confidence < 80:
            summary += " Die Zuverlässigkeit dieser Analyse ist jedoch eingeschränkt."
    else:
        summary = ("Die Analyse deutet darauf hin, dass eine Eintragung notwendig ist. Es wurden Hinweise "
                  "gefunden, die eine Eintragungspflicht nahelegen.")
        
    # Gebe nur die 5 ursprünglich definierten Rückgabewerte zurück
    return is_free, confidence, reasons, condition_codes, summary

def extract_auflagen_with_text(pdf_path, app):
    """Extrahiert Auflagen-Codes und deren zugehörige Texte aus der PDF"""
    import pdfplumber
    
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
                        print("Extraktion beendet - 'Prüfort und Prüfdatum' gefunden")
                        # Speichere letzten Abschnitt vor dem Beenden
                        if current_section:
                            code_match = re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)](.+)', current_section)
                            if code_match:
                                code = code_match.group(1).strip()
                                description = code_match.group(2).strip()
                                if code in db_codes:
                                    codes_with_text[code] = description
                                    print(f"Letzter Code gespeichert: {code}")
                        return codes_with_text  # Beende die Funktion sofort
                    
                    # Prüfe auf "Technologiezentrum"
                    if "Technologiezentrum" in line:
                        print("Technologie gefunden - Pausiere Extraktion")
                        collect_text = False
                        current_section = ""  # Verwerfe aktuellen Abschnitt
                        continue

                    # Prüfe auf neuen Auflagen-Code
                    if re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)]', line):
                        print(f"Neuer Code gefunden: {line[:20]}...")
                        
                        # Speichere vorherigen Abschnitt wenn vorhanden
                        if collect_text and current_section:
                            code_match = re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)](.+)', current_section)
                            if code_match:
                                code = code_match.group(1).strip()
                                description = code_match.group(2).strip()
                                if code in db_codes:
                                    codes_with_text[code] = description
                                    print(f"Gespeichert: {code}")
                        
                        collect_text = True  # Setze Extraktion fort
                        current_section = line  # Starte neuen Abschnitt
                        continue

                    # Sammle Text wenn aktiv
                    if collect_text and current_section:
                        current_section += " " + line

    except Exception as e:
        print(f"Fehler beim Extrahieren der Auflagen-Texte: {str(e)}")
        import traceback
        print(traceback.format_exc())
    
    # Bereinige die gesammelten Texte
    for code, text in codes_with_text.items():
        text = re.sub(r'\s+', ' ', text)  # Entferne mehrfache Leerzeichen
        text = text.strip()
        codes_with_text[code] = text
        print(f"Finaler Code {code}: {text[:100]}...")

    return codes_with_text

def save_to_database(codes_with_text, app):
    """Speichert oder aktualisiert Auflagen-Codes und Texte in der Datenbank"""
    try:
        with app.app_context():
            from models import AuflagenCode
            for code, description in codes_with_text.items():
                # Prüfe, ob der Code bereits existiert
                existing_code = AuflagenCode.query.filter_by(code=code).first()
                
                if existing_code:
                    # Aktualisiere nur, wenn der Text sich geändert hat
                    if existing_code.description != description:
                        existing_code.description = description
                        print(f"Aktualisiere Code {code} in der Datenbank")
                else:
                    # Füge neuen Code hinzu
                    new_code = AuflagenCode(code=code, description=description)
                    from extensions import db
                    db.session.add(new_code)
                    print(f"Füge neuen Code {code} zur Datenbank hinzu")
            
            from extensions import db
            db.session.commit()
            print("Datenbank erfolgreich aktualisiert")
            
    except Exception as e:
        print(f"Fehler beim Speichern in der Datenbank: {str(e)}")
        from extensions import db
        db.session.rollback()

def extract_auflagen_codes(tables, app, request, logger):
    """Extrahiert Auflagen-Codes aus Tabellen und aktualisiert die Datenbank"""
    from flask import request
    import os
    
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
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], request.files['file'].filename)
    extracted_texts = extract_auflagen_with_text(pdf_path, app)
    logger.info(f"Gefundene Auflagen-Texte: {len(extracted_texts)}")  # Debug-Ausgabe
    for code, text in extracted_texts.items():
        logger.info(f"Code {code}: {text[:100]}...")  # Debug-Ausgabe
    
    # Modifizierte Logik für das Speichern der Codes mit Texten
    with app.app_context():
        from models import AuflagenCode
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
            from extensions import db
            db.session.add(new_code)
        
        from extensions import db
        db.session.commit()

    # Kombiniere gefundene Codes mit ihren Texten
    codes_with_text = {}
    for code in codes:
        description = extracted_texts.get(code, AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar"))
        codes_with_text[code] = description
    
    # Speichere in der Datenbank
    save_to_database(codes_with_text, app)
    
    return sorted(list(codes))
