import sys
import subprocess
import threading
import tempfile
import re
import jpype
import os
import pandas as pd
import numpy as np
import logging
from werkzeug.utils import secure_filename
import traceback
from functools import lru_cache

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define required packages
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

def check_and_install_packages():
    """Überprüft und installiert fehlende Pakete"""
    for package, import_name in required_packages.items():
        try:
            __import__(import_name.lower())
        except ImportError:
            logger.info(f"Installiere {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Überprüfe und installiere Abhängigkeiten
check_and_install_packages()

# Jetzt importiere die benötigten Module
from flask import Flask, render_template, request, send_file, url_for, jsonify
import tabula
import pdfplumber
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import AuflagenCode

# Initialize Flask app
app = Flask(__name__)

# App configuration
app.config.update({
    'UPLOAD_FOLDER': tempfile.mkdtemp(),
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB max-limit
    'TEMPLATES_AUTO_RELOAD': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///auflagen.db',
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
})
app.jinja_env.auto_reload = True

# Log the temp directory
logger.info(f"Temporäres Verzeichnis erstellt: {app.config['UPLOAD_FOLDER']}")

# Initialize the db with the Flask app
db.init_app(app)

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

# File and JVM Management Classes
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
                    logger.error(f"Fehler beim Löschen von {filepath}: {e}")
    
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
                            logger.error(f"Fehler beim Löschen von {filepath}: {e}")
        except Exception as e:
            logger.error(f"Fehler bei der Bereinigung: {e}")

class JVMManager:
    """Manages JVM initialization and shutdown"""
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = JVMManager()
        return cls._instance
    
    def __init__(self):
        self.initialized = False
    
    def initialize(self):
        """Initialize the JVM if not already started"""
        if not self.initialized and not jpype.isJVMStarted():
            try:
                jvm_path = jpype.getDefaultJVMPath()
                if not os.path.exists(jvm_path):
                    raise FileNotFoundError(f"JVM shared library file not found: {jvm_path}")
                jpype.startJVM(jvm_path, convertStrings=False)
                self.initialized = True
                logger.info("JVM successfully initialized")
            except Exception as e:
                logger.error(f"JVM Initialisierungsfehler: {str(e)}")
                logger.info("Verwende Fallback-Methode...")
                return False
        return True
    
    def shutdown(self):
        """Shutdown the JVM if running"""
        if self.initialized and jpype.isJVMStarted() and threading.current_thread() is threading.main_thread():
            try:
                jpype.shutdownJVM()
                self.initialized = False
                logger.info("JVM shut down")
            except Exception as e:
                logger.error(f"Error shutting down JVM: {e}")

# Initialize managers
temp_storage = TemporaryStorage(app.config['UPLOAD_FOLDER'])
jvm_manager = JVMManager.get_instance()

# Utility Functions
def check_java():
    """Überprüft die Java-Installation und gibt den Status zurück"""
    try:
        subprocess.check_output(['java', '-version'], stderr=subprocess.STDOUT)
        logger.info("Java ist installiert und funktioniert")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error("Java ist nicht installiert oder der 'java' Befehl ist nicht im PATH.")
        return False

def install_java():
    """Versucht, Java automatisch zu installieren"""
    try:
        # Betriebssystem erkennen
        import platform
        system = platform.system().lower()
        
        if system == 'linux':
            logger.info("Versuche Java auf Linux zu installieren...")
            # Überprüfen, ob apt, yum oder dnf verfügbar ist
            if subprocess.call("which apt", shell=True, stdout=subprocess.PIPE) == 0:
                subprocess.check_call(["sudo", "apt", "update"])
                subprocess.check_call(["sudo", "apt", "install", "-y", "default-jre"])
                return True
            elif subprocess.call("which yum", shell=True, stdout=subprocess.PIPE) == 0:
                subprocess.check_call(["sudo", "yum", "install", "-y", "java-11-openjdk"])
                return True
            elif subprocess.call("which dnf", shell=True, stdout=subprocess.PIPE) == 0:
                subprocess.check_call(["sudo", "dnf", "install", "-y", "java-11-openjdk"])
                return True
        elif system == 'darwin':  # macOS
            logger.info("Versuche Java auf macOS zu installieren...")
            if subprocess.call("which brew", shell=True, stdout=subprocess.PIPE) == 0:
                subprocess.check_call(["brew", "tap", "adoptopenjdk/openjdk"])
                subprocess.check_call(["brew", "install", "--cask", "adoptopenjdk11"])
                return True
        elif system == 'windows':
            logger.info("Automatische Java-Installation auf Windows wird nicht unterstützt")
            # Windows-Installation ist komplexer und erfordert Administratorrechte
        
        logger.error("Automatische Java-Installation nicht möglich")
        return False
    except Exception as e:
        logger.error(f"Fehler bei der Java-Installation: {str(e)}")
        return False

def process_pdf_with_encoding(pdf_path, output_format='csv'):
    """Verarbeitet PDF-Datei mit Berücksichtigung der Kodierung für 1:1-Extraktion"""
    # Prüfe, ob Java verfügbar ist
    if not check_java():
        logger.warning("Java nicht gefunden. Verwende Fallback-Methode.")
        return process_pdf_without_java(pdf_path, output_format)
        
    all_tables = []
    try:
        # JVM initialisieren
        jvm_manager.initialize()
        
        # Fokus auf Lattice-Modus (für Tabellen mit sichtbaren Linien)
        # Dies ist am besten für strukturerhaltende 1:1-Extraktion
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
        
        logger.info(f"Tabula hat insgesamt {len(tables)} potenzielle Tabellen gefunden")
        
        # Verarbeite alle gefundenen Tabellen mit minimaler Manipulation
        for i, table in enumerate(tables):
            logger.info(f"Prüfe Tabelle {i+1}: {table.shape[0]} Zeilen, {table.shape[1]} Spalten")
            
            # MINIMALE Nachbearbeitung - nur NaN durch leere Strings ersetzen
            clean_table = table.fillna('')
            
            # Keine Validierung oder Filterung mehr - alle gefundenen Tabellen akzeptieren
            all_tables.append(clean_table)
            logger.info(f"Tabelle {i+1} hinzugefügt (1:1 Extraktion)")

        if not all_tables:
            logger.warning("Keine Tabellen mit tabula gefunden. Versuche Fallback-Methode.")
            return process_pdf_without_java(pdf_path, output_format)
            
        return all_tables

    except Exception as e:
        logger.error(f"Fehler bei der Tabellenextraktion mit tabula: {str(e)}")
        logger.info("Versuche Fallback-Methode.")
        return process_pdf_without_java(pdf_path, output_format)

def process_pdf_without_java(pdf_path, output_format='csv'):
    """Verarbeitet PDF-Datei ohne Java mit pdfplumber für 1:1-Extraktion"""
    logger.info("Verwende pdfplumber für 1:1 PDF-Tabellenextraktion")
    all_tables = []
    
    try:
        import numpy as np
        import pdfplumber
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                logger.info(f"Verarbeite Seite {page_num+1} mit pdfplumber")
                
                # Standard-Tabelleneinstellungen - am besten für strukturerhaltende Extraktion
                tables = page.extract_tables()
                
                # Nur wenn keine Tabellen gefunden wurden, verwenden wir alternative Einstellungen
                if not tables:
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
                
                logger.info(f"pdfplumber hat {len(tables)} Tabellen auf Seite {page_num+1} gefunden")
                
                for i, table_data in enumerate(tables):
                    if not table_data:
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
                    logger.info(f"Tabelle {i+1} auf Seite {page_num+1} hinzugefügt (1:1 Extraktion)")
        
        if not all_tables:
            logger.warning("Keine Tabellen mit pdfplumber gefunden. Extrahiere Text als letzte Option.")
            # Versuche als letzten Ausweg den gesamten Text zu extrahieren
            return extract_text_as_structured_table(pdf_path)
            
        return all_tables

    except Exception as e:
        logger.error(f"Fehler bei der pdfplumber Extraktion: {str(e)}")
        return extract_text_as_structured_table(pdf_path)

def extract_text_as_structured_table(pdf_path):
    """Extrahiert Text und versucht, eine Tabellenstruktur zu erkennen"""
    logger.info("Versuche Text mit Strukturerkennung zu extrahieren")
    try:
        import pdfplumber
        
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
                    logger.info(f"Strukturierte Texttabelle von Seite {page_num+1} extrahiert: {len(df)} Zeilen, {len(df.columns)} Spalten")
        
        if not all_tables:
            # Als letzte Option, erstelle eine einfache Texttabelle
            return extract_text_as_simple_table(pdf_path)
            
        return all_tables
        
    except Exception as e:
        logger.error(f"Fehler bei der strukturierten Textextraktion: {str(e)}")
        return extract_text_as_simple_table(pdf_path)

def extract_text_as_simple_table(pdf_path):
    """Letzte Fallback-Methode: Extrahiert Text als einfache Tabelle"""
    logger.info("Extrahiere Text als einfache Tabelle (letzte Option)")
    try:
        import pdfplumber
        
        all_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)
        
        if not all_text:
            logger.error("Kein Text in der PDF gefunden")
            # Erstelle leere DataFrame mit Hinweis
            return [pd.DataFrame([["Keine Tabellen oder Text in der PDF erkannt"]], columns=["Hinweis"])]
            
        # Kombiniere allen Text und teile nach Zeilen
        combined_text = '\n'.join(all_text)
        lines = [line for line in combined_text.split('\n') if line.strip()]
        
        if not lines:
            logger.error("Keine Textzeilen gefunden")
            return [pd.DataFrame([["Keine strukturierten Zeilen in der PDF gefunden"]], columns=["Hinweis"])]
        
        # Erstelle ein einfaches DataFrame mit dem Text
        df = pd.DataFrame(lines, columns=["PDF-Textinhalt"])
        
        logger.info(f"Einfache Texttabelle mit {len(df)} Zeilen erstellt")
        return [df]
        
    except Exception as e:
        logger.error(f"Fehler beim finalen Fallback: {str(e)}")
        # Erstelle generische Fehlertabelle
        return [pd.DataFrame([["Fehler bei der Textextraktion: " + str(e)]], columns=["Fehler"])]

@app.route('/', methods=['GET'])
def index():
    java_installed = check_java()
    return render_template('index.html', java_installed=java_installed)

@app.route('/', methods=['POST'], endpoint='index_post')
def index_post():
    """Endpunkt zum Versuch der Java-Installation"""
    if install_java():
        return jsonify({
            'success': True,
            'message': 'Java wurde erfolgreich installiert. Sie können die Anwendung jetzt nutzen.'
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Automatische Installation fehlgeschlagen. Bitte installieren Sie Java manuell.'
        }), 500

@app.route('/home', methods=['GET'])
def home():
    if not check_java():
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen. Bitte installieren Sie Java und stellen Sie sicher, dass der 'java' Befehl im PATH ist.", 500
    return render_template('index.html')

@lru_cache(maxsize=32)
def is_valid_table(df):
    """Überprüft, ob ein DataFrame eine echte Tabelle ist (mit Caching)"""
    # Grundlegende Prüfung - Tabelle muss Inhalt haben
    if df.empty:
        logger.info("Tabelle wird abgelehnt: Leer")
        return False
    
    # Extrem lockere Validierung
    # Mindestens 1 Spalte und 1 Zeile
    if len(df.columns) == 0 or len(df) == 0:
        logger.info(f"Tabelle wird abgelehnt: Keine Spalten oder Zeilen ({len(df.columns)}x{len(df)})")
        return False
    
    # Mindestens ein nicht-leerer Wert in der Tabelle
    if df.astype(str).replace('', np.nan).count().sum() == 0:
        logger.info("Tabelle wird abgelehnt: Enthält keine Daten")
        return False
        
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

# Füge temporären Storage-Handler hinzu
class TemporaryStorage:
    """Verwaltet temporäre Dateien mit automatischer Bereinigung"""
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.active_files = set()
    
    def add_file(self, filename):
        """Markiert eine Datei als aktiv"""
        self.active_files.add(filename)
    
    def remove_file(self, filename):
        """Entfernt eine Datei aus dem aktiven Set und löscht sie"""
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

# Initialisiere Storage-Handler nach app-Definition
temp_storage = TemporaryStorage(app.config['UPLOAD_FOLDER'])

def cleanup_temp_files():
    """Bereinigt alle inaktiven temporären Dateien"""
    temp_storage.cleanup_inactive()

# Registriere cleanup NACH der Funktionsdefinition
import atexit
atexit.register(cleanup_temp_files)

# Definiere Auflagen-Codes und Texte getrennt
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

def extract_auflagen_with_text(pdf_path):
    """Extrahiert Auflagen-Codes und deren zugehörige Texte aus der PDF"""
    codes_with_text = {}
    excluded_texts = [
        "Technologiezentrum Typprüfstelle Lambsheim - Königsberger Straße 20d - D-67245 Lambsheim",
    ]
    collect_text = True  # Flag für die Textsammlung
    current_section = ""  # Buffer für den aktuellen Textabschnitt

    try:
        with app.app_context():
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

def save_to_database(codes_with_text):
    """Speichert oder aktualisiert Auflagen-Codes und Texte in der Datenbank"""
    try:
        with app.app_context():
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
                    db.session.add(new_code)
                    print(f"Füge neuen Code {code} zur Datenbank hinzu")
            
            db.session.commit()
            print("Datenbank erfolgreich aktualisiert")
            
    except Exception as e:
        print(f"Fehler beim Speichern in der Datenbank: {str(e)}")
        db.session.rollback()

def extract_auflagen_codes(tables):
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
    extracted_texts = extract_auflagen_with_text(pdf_path)
    print(f"Gefundene Auflagen-Texte: {len(extracted_texts)}")  # Debug-Ausgabe
    for code, text in extracted_texts.items():
        print(f"Code {code}: {text[:100]}...")  # Debug-Ausgabe
    
    # Modifizierte Logik für das Speichern der Codes mit Texten
    with app.app_context():
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
        description = extracted_texts.get(code, AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar"))
        codes_with_text[code] = description
    
    # Speichere in der Datenbank
    save_to_database(codes_with_text)
    
    return sorted(list(codes))

@app.route('/extract', methods=['POST', 'GET'])  # GET-Methode hinzugefügt
def extract():
    if not check_java():
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen.", 500
    
    if 'file' not in request.files:
        return 'Keine Datei ausgewählt', 400
    
    file = request.files['file']
    if file.filename == '':
        return 'Keine Datei ausgewählt', 400
    
    output_format = request.form.get('format', 'csv')
    
    try:
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)
        temp_storage.add_file(filename)  # Markiere PDF als aktiv
        
        cleanup_temp_files()  # Bereinige alte temporäre Dateien
        
        # Speichere die Original-PDF-ID für die Suche
        pdf_id = os.path.splitext(filename)[0]
        
        logger.info(f"Starte Extraktion aus PDF: {pdf_path}")
        
        # Erhöhe die Wahrscheinlichkeit, dass Tabellen gefunden werden
        tables = process_pdf_with_encoding(pdf_path, output_format)
        
        # Sicherstellen, dass immer ein Ergebnis zurückgegeben wird
        if not tables:
            logger.warning("Keine Tabellen gefunden. Erstelle Notfalltabelle mit PDF-Text.")
            
            # Extrahiere den vollständigen Text aus der PDF als Notfalllösung
            try:
                import pdfplumber
                text_content = []
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_content.extend(page_text.split('\n'))
                
                # Erstelle ein einfaches DataFrame mit dem Textinhalt
                if text_content:
                    text_df = pd.DataFrame(text_content, columns=["PDF-Textinhalt"])
                    tables = [text_df]
                    logger.info("Textinhalt als Notfalltabelle erstellt")
                else:
                    # Absolute Notfalllösung: Leere Tabelle mit Hinweistext
                    tables = [pd.DataFrame([["Keine Tabellen in der PDF erkannt. Bitte andere PDF probieren oder manuell Daten eingeben."]], 
                                columns=["Hinweis"])]
                    logger.warning("Erstelle leere Tabelle mit Hinweis")
            except Exception as text_error:
                logger.error(f"Fehler bei der Textextraktion: {str(text_error)}")
                tables = [pd.DataFrame([["Keine Tabellen in der PDF erkannt. Bitte andere PDF probieren oder manuell Daten eingeben."]], 
                            columns=["Hinweis"])]
        
        results = []
        table_htmls = []
        
        for i, table in enumerate(tables):
            table = table.fillna('')
            table = table.astype(str)
            
            # Generiere HTML-Vorschau
            table_htmls.append(convert_table_to_html(table))
            
            # Verwende PDF-ID im Dateinamen
            output_filename = f"{pdf_id}_table_{i+1}.{output_format}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            if output_format == 'csv':
                table.to_csv(output_path, index=False, encoding='utf-8-sig', sep=';')
            else:
                try:
                    table.to_excel(output_path, index=False, engine='openpyxl')
                except ImportError:
                    logger.info("Installing openpyxl...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                    table.to_excel(output_path, index=False, engine='openpyxl')
                    
            temp_storage.add_file(output_filename)  # Markiere Tabelle als aktiv
            results.append(output_filename)
        
        # Extrahiere Auflagen-Codes und deren Texte 
        # Auch wenn keine Tabellen gefunden wurden, versuchen wir, Codes direkt aus der PDF zu extrahieren
        auflagen_codes = []
        try:
            auflagen_codes = extract_auflagen_codes(tables) 
            extracted_texts = extract_auflagen_with_text(pdf_path)
        except Exception as e:
            logger.error(f"Fehler bei der Auflagen-Extraktion: {str(e)}")
            extracted_texts = {}
            
        # Erstelle Liste von AuflagenCode-Objekten mit den extrahierten Texten
        condition_codes = [
            AuflagenCode(
                code=code,
                description=extracted_texts.get(code, AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar"))
            )
            for code in auflagen_codes
        ]
            
        # Automatische Bereinigung nach 1 Stunde
        def delayed_cleanup():
            import time
            time.sleep(3600)  # 1 Stunde warten
            for filename in results + [filename]:
                temp_storage.remove_file(filename)
                
        threading.Thread(target=delayed_cleanup).start()
        
        return render_template('results.html', 
            files=results, 
            tables=table_htmls,
            condition_codes=condition_codes,
            pdf_file=filename
        )
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Fehler bei der PDF-Verarbeitung: {str(e)}\n{error_details}")
        error_msg = (
            f"Fehler bei der PDF-Verarbeitung:\n"
            f"1. PDF-Datei könnte beschädigt sein\n"
            f"2. Format möglicherweise nicht unterstützt\n"
            f"Details: {str(e)}\n{error_details}"
        )
        return error_msg, 500

@app.route('/download/<filename>')
def download_file(filename):
    """Datei herunterladen und danach als inaktiv markieren"""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        if not os.path.exists(filepath):
            return "Datei nicht mehr verfügbar", 404
            
        return send_file(filepath, as_attachment=True, download_name=filename)
    finally:
        def delayed_delete():
            import time
            time.sleep(5)  # Kurz warten nach Download
            temp_storage.remove_file(filename)
        threading.Thread(target=delayed_delete).start()

@app.route('/list_files')
def list_files():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('list_files.html', files=files)

@app.route('/reprocess/<filename>')
def reprocess_file(filename):
    if not check_java():
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen.", 500

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(filepath):
        return 'Datei nicht gefunden', 404

    output_format = 'csv'  # Standardformat
    try:
        tables = process_pdf_with_encoding(filepath, output_format)
        results = []
        table_htmls = []

        for i, table in enumerate(tables):
            table = table.fillna('')
            table = table.astype(str)
            
            # Generiere HTML-Vorschau
            table_htmls.append(convert_table_to_html(table))
            
            output_filename = f"{os.path.splitext(filename)[0]}_table_{i + 1}.{output_format}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            if output_format == 'csv':
                table.to_csv(output_path, index=False, encoding='utf-8-sig', sep=';')
            else:
                # Füge Fehlerbehandlung für Excel-Export hinzu
                try:
                    table.to_excel(output_path, index=False, engine='openpyxl')
                except ImportError:
                    # Falls openpyxl nicht installiert ist
                    print("Installing openpyxl...")
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                    table.to_excel(output_path, index=False, engine='openpyxl')

            results.append(output_filename)

        if not results:
            return "Keine Tabellen in der PDF-Datei gefunden.", 400

        return render_template('results.html', files=results, tables=table_htmls)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        error_msg = (
            f"Fehler bei der PDF-Verarbeitung:\n"
            f"1. PDF-Datei könnte beschädigt sein\n"
            f"2. Format möglicherweise nicht unterstützt\n"
            f"Details: {str(e)}\n{error_details}"
        )
        return error_msg, 500

@app.route('/search', methods=['POST'])
def search_vehicles():
    """Verbesserte Fahrzeugsuche mit PDF-ID"""
    try:
        data = request.get_json()
        print("Received search request")
        print("Request data:", data)
        
        search_term = data.get('search', '').strip().lower()
        pdf_id = data.get('file_id', '')
        
        if not search_term or not pdf_id:
            return jsonify({
                'html': '<div class="alert alert-warning">Bitte geben Sie einen Suchbegriff ein.</div>',
                'status': 'error'
            })

        # Suche nach CSV-Dateien mit der PDF-ID
        csv_pattern = f"{pdf_id}_table_*.csv"
        table_files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if filename.startswith(f"{pdf_id}_table_") and filename.endswith('.csv'):
                table_files.append(filename)
        
        print(f"Found table files: {table_files}")

        # Rest der Suchlogik bleibt gleich
        all_results = []
        for table_file in table_files:
            try:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], table_file)
                if not os.path.exists(filepath):
                    print(f"File not found: {filepath}")
                    continue
                
                print(f"Reading file: {filepath}")
                df = pd.read_csv(filepath, sep=';', encoding='utf-8-sig')
                df = df.fillna('').astype(str)  # Konvertiere zu String
                
                # Suche in allen Spalten
                mask = pd.Series(False, index=df.index)
                for col in df.columns:
                    col_values = df[col].str.lower().str.strip()
                    mask |= col_values.str.contains(search_term, case=False, na=False, regex=False)
                
                if mask.any():
                    results = df[mask].copy()
                    print(f"Found {len(results)} matches in {table_file}")
                    
                    # Markiere Treffer
                    for col in results.columns:
                        results[col] = results[col].apply(
                            lambda x: f'<mark>{x}</mark>' if search_term in str(x).lower() else x
                        )
                    all_results.append((table_file, results))
            
            except Exception as e:
                print(f"Error processing {table_file}: {str(e)}")
                continue

        if all_results:
            result_htmls = []
            total_count = 0
            for table_file, result_df in all_results:
                total_count += len(result_df)
                result_htmls.append(f"""
                    <div class="card mb-3">
                        <div class="card-header">
                            <h6 class="mb-0">Ergebnisse aus {table_file}</h6>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                {convert_table_to_html(result_df)}
                            </div>
                        </div>
                    </div>
                """)
            
            return jsonify({
                'html': f"""
                    <div class="alert alert-success">
                        {total_count} Treffer gefunden für "{search_term}"
                    </div>
                    {''.join(result_htmls)}
                """,
                'count': total_count,
                'status': 'success'
            })
        else:
            return jsonify({
                'html': f'<div class="alert alert-info">Keine Fahrzeuge gefunden für "{search_term}".</div>',
                'count': 0,
                'status': 'no_results'
            })
            
    except Exception as e:
        print(f"Search error: {str(e)}")
        return jsonify({
            'error': str(e),
            'html': '<div class="alert alert-danger">Fehler bei der Suche.</div>',
            'status': 'error'
        }), 500

# JVM-Handhabung verbessern
def initialize_jvm():
    """Initialisiert die JVM mit Fehlerbehandlung"""
    try:
        if not jpype.isJVMStarted():
            jvm_path = jpype.getDefaultJVMPath()
            if not os.path.exists(jvm_path):
                raise FileNotFoundError(f"JVM shared library file not found: {jvm_path}")
            jpype.startJVM(jvm_path, convertStrings=False)  # Verhindert automatische String-Konvertierung
    except Exception as e:
        print(f"JVM Initialisierungsfehler: {str(e)}")
        print("Verwende Fallback-Methode...")
        # Hier könnte eine alternative Implementierung erfolgen

def shutdown_jvm():
    if jpype.isJVMStarted():
        try:
            # Nur ausführen, wenn wir im Hauptthread sind
            if threading.current_thread() is threading.main_thread():
                jpype.shutdownJVM()
        except:
            pass

# Kontext-Handler anpassen
@app.before_request
def before_request():
    if not jpype.isJVMStarted():
        initialize_jvm()

@app.teardown_appcontext
def teardown_appcontext(exception=None):
    # JVM nicht bei jedem Request herunterfahren
    pass

# Bereinigung beim Herunterfahren
import atexit
atexit.register(cleanup_temp_files)

# Ersetze die alte cleanup_temp_files Funktion
def cleanup_temp_files():
    """Bereinigt alle inaktiven temporären Dateien"""
    temp_storage.cleanup_inactive()

def init_db():
    with app.app_context():
        db.create_all()

# Verbesserte Thread-Handhabung
def cleanup_on_shutdown():
    """Führt sauberes Herunterfahren durch"""
    try:
        # Beende alle aktiven Threads
        for thread in threading.enumerate():
            if thread is not threading.current_thread():
                try:
                    thread.join(timeout=1.0)
                except Exception as e:
                    print(f"Fehler beim Beenden des Threads {thread.name}: {e}")
        
        # Bereinige Dateien
        cleanup_temp_files()
        
        # Fahre JVM herunter
        shutdown_jvm()
        
    except Exception as e:
        print(f"Fehler beim Herunterfahren: {e}")
    finally:
        print("Shutdown-Prozess abgeschlossen.")

# Neue Route für KI-Analyse
@app.route('/analyze/<filename>')
def analyze_registration_freedom(filename):
    """Führt eine KI-Analyse der Eintragungsfreiheit für eine extrahierte PDF durch"""
    try:
        print(f"Analyse gestartet für: {filename}")
        pdf_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(pdf_filepath):
            print(f"PDF nicht gefunden: {pdf_filepath}")
            return 'PDF Datei nicht gefunden', 404
        
        # Sammle verfügbare Tabellendateien für diese PDF
        pdf_id = os.path.splitext(filename)[0]
        table_files = []
        for file in os.listdir(app.config['UPLOAD_FOLDER']):
            if file.startswith(f"{pdf_id}_table_") and (file.endswith('.csv') or file.endswith('.xlsx')):
                table_files.append(file)
                
        if not table_files:
            print(f"Keine Tabellen für PDF {filename} gefunden")
            return 'Keine extrahierten Tabellen gefunden', 404
            
        # Analysiere Tabellendaten
        vehicle_info = {}
        wheel_tire_info = {}
        
        # Auflagencodes aus Datenbank laden
        with app.app_context():
            auflagen_db = {code.code: code.description for code in AuflagenCode.query.all()}
        
        auflagencodes_found = []
        
        # Analysiere alle Tabellendateien
        for table_file in table_files:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], table_file)
            if not os.path.exists(filepath):
                continue
                
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath, sep=';', encoding='utf-8-sig')
            else:  # Excel-Datei
                df = pd.read_excel(filepath)
                
            df = df.fillna('')
            df = df.astype(str)
            
            # Fahrzeugdaten extrahieren
            if vehicle_info == {}:
                vehicle_info = extract_vehicle_info(df)
                print(f"Extrahierte Fahrzeugdaten: {vehicle_info}")
            
            # Rad/Reifen-Informationen extrahieren
            if wheel_tire_info == {}:
                wheel_tire_info = extract_wheel_tire_info(df)
                print(f"Extrahierte Rad/Reifen-Informationen: {wheel_tire_info}")
            
            # Auflagencodes finden
            codes = find_condition_codes(df)
            auflagencodes_found.extend(codes)
        
        # Aus PDF erneut Codes extrahieren für maximale Sicherheit
        try:
            with pdfplumber.open(pdf_filepath) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
                
                # Suche nach Auflagen-Codes im Text
                code_pattern = re.compile(r"""
                    (?:
                        [A-Z][0-9]{1,3}[a-z]?|  # Bsp: A01, B123a
                        [0-9]{2,3}[A-Z]?|        # Bsp: 155, 12A
                        NoH|Lim                  # Spezielle Codes
                    )
                """, re.VERBOSE)
                text_codes = code_pattern.findall(text)
                auflagencodes_found.extend(text_codes)
        except Exception as e:
            print(f"Fehler beim PDF-Text extrahieren: {e}")
        
        # Deduplizieren und sortieren
        auflagencodes_found = sorted(list(set(auflagencodes_found)))
        print(f"Gefundene Auflagencodes: {auflagencodes_found}")
        
        # Analysiere die Eintragungsfreiheit
        is_free, confidence, reasons, condition_codes, analysis_summary = analyze_freedom(
            auflagencodes_found, auflagen_db, vehicle_info, wheel_tire_info)
        
        print(f"Analyse-Ergebnis: Eintragungsfrei={is_free}, Zuverlässigkeit={confidence}%")
        
        return render_template(
            'ai_analysis.html',
            is_free=is_free,
            confidence=confidence,
            vehicle_info=vehicle_info,
            wheel_tire_info=wheel_tire_info,
            condition_codes=condition_codes,
            analysis_reasons=reasons,
            analysis_summary=analysis_summary,
            pdf_file=filename
        )
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Fehler bei KI-Analyse: {error_details}")
        return f"Fehler bei der KI-Analyse: {str(e)}<br/><pre>{error_details}</pre>", 500

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

# Korrigierte Version der export_analysis Funktion
@app.route('/export_analysis/<filename>', methods=['GET'])
def export_analysis(filename):
    """Exportiert die KI-Analyse als PDF oder CSV"""
    format_type = request.args.get('format', 'pdf')
    
    # Hier die gleiche Analyse wie in analyze_registration_freedom durchführen
    try:
        pdf_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(pdf_filepath):
            return 'PDF Datei nicht gefunden', 404
        
        # Sammle verfügbare Tabellendateien für diese PDF
        pdf_id = os.path.splitext(filename)[0]
        table_files = []
        for file in os.listdir(app.config['UPLOAD_FOLDER']):
            if file.startswith(f"{pdf_id}_table_") and (file.endswith('.csv') or file.endswith('.xlsx')):
                table_files.append(file)
                
        if not table_files:
            return 'Keine extrahierten Tabellen gefunden', 404
            
        # Analysiere Tabellendaten
        vehicle_info = {}
        wheel_tire_info = {}
        
        # Auflagencodes aus Datenbank laden
        with app.app_context():
            auflagen_db = {code.code: code.description for code in AuflagenCode.query.all()}
        
        auflagencodes_found = []
        
        # Analysiere alle Tabellendateien
        for table_file in table_files:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], table_file)
            if not os.path.exists(filepath):
                continue
                
            if filepath.endswith('.csv'):
                df = pd.read_csv(filepath, sep=';', encoding='utf-8-sig')
            else:  # Excel-Datei
                df = pd.read_excel(filepath)
                
            df = df.fillna('')
            df = df.astype(str)
            
            # Extrahiere Daten
            if vehicle_info == {}:
                vehicle_info = extract_vehicle_info(df)
            
            if wheel_tire_info == {}:
                wheel_tire_info = extract_wheel_tire_info(df)
            
            codes = find_condition_codes(df)
            auflagencodes_found.extend(codes)
        
        # Dedupliziere und sortiere Codes
        auflagencodes_found = sorted(list(set(auflagencodes_found)))
        
        # Analyse durchführen
        is_free, confidence, reasons, condition_codes, analysis_summary = analyze_freedom(
            auflagencodes_found, auflagen_db, vehicle_info, wheel_tire_info)
        
        # PDF-Exportlogik hier, gekürzt um Platz zu sparen
        if format_type == 'pdf':
            # PDF-Export erstellen
            try:
                from fpdf import FPDF
                # ... PDF-Erstellungscode ...
                return "PDF Export wird implementiert", 200
                
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                return f"Fehler beim Exportieren der Analyse: {str(e)}<br/><pre>{error_details}</pre>", 500
        
        return "Format nicht unterstützt", 400
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"Fehler bei der Analyse: {str(e)}<br/><pre>{error_details}</pre>", 500

# Route für die Ergebnisseite hinzufügen
@app.route('/results/<filename>')
def results(filename):
    """Rendert die Ergebnis-Seite für bereits extrahierte PDF-Dateien"""
    try:
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(pdf_path):
            return 'PDF Datei nicht gefunden', 404
        
        # Sammle verfügbare Tabellendateien für diese PDF
        pdf_id = os.path.splitext(filename)[0]
        results = []
        table_htmls = []
        
        # Finde alle generierten CSV/Excel-Dateien
        for file in os.listdir(app.config['UPLOAD_FOLDER']):
            if file.startswith(f"{pdf_id}_table_") and (file.endswith('.csv') or file.endswith('.xlsx')):
                results.append(file)
                
                # Lade den Inhalt für die Vorschau
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file)
                if filepath.endswith('.csv'):
                    df = pd.read_csv(filepath, sep=';', encoding='utf-8-sig')
                else:  # Excel-Datei
                    df = pd.read_excel(filepath)
                    
                df = df.fillna('')
                df = df.astype(str)
                table_htmls.append(convert_table_to_html(df))
        
        # Lade zugehörige Auflagencodes
        condition_codes = []
        with app.app_context():
            # Suche nach Codes in den Tabellen
            auflagencodes_found = []
            for file in results:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file)
                if filepath.endswith('.csv'):
                    df = pd.read_csv(filepath, sep=';', encoding='utf-8-sig')
                else:  # Excel-Datei
                    df = pd.read_excel(filepath)
                df = df.fillna('')
                df = df.astype(str)
                codes = find_condition_codes(df)
                auflagencodes_found.extend(codes)
            
            # Deduplizieren
            auflagencodes_found = sorted(list(set(auflagencodes_found)))
            
            # Hole Beschreibungen
            for code in auflagencodes_found:
                db_code = AuflagenCode.query.filter_by(code=code).first()
                if db_code:
                    condition_codes.append(db_code)
        
        return render_template('results.html', 
                            files=results, 
                            tables=table_htmls,
                            condition_codes=condition_codes,
                            pdf_file=filename)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"Fehler beim Anzeigen der Ergebnisse: {str(e)}<br/><pre>{error_details}</pre>", 500

# Flask-App starten
if __name__ == "__main__":
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
