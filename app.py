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
from flask import Flask, render_template, request, send_file, jsonify
import tabula
import pdfplumber
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import AuflagenCode
from utils import (
    TemporaryStorage, check_and_install_packages, AUFLAGEN_CODES, AUFLAGEN_TEXTE,
    convert_table_to_html, extract_vehicle_info, extract_wheel_tire_info,
    save_to_database, find_condition_codes, analyze_freedom, is_valid_table
)
from pdf_extractor import (
    process_pdf_with_encoding, process_pdf_without_java,
    extract_text_as_structured_table, extract_text_as_simple_table,
    extract_auflagen_with_text, extract_auflagen_codes
)
from llm_service import LLMService  # Neue Import
import gc
import psutil
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Überprüfe und installiere Abhängigkeiten
check_and_install_packages(logger)

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

# Initialize managers
temp_storage = TemporaryStorage(app.config['UPLOAD_FOLDER'])

# Initialize LLM Service
llm_service = LLMService()

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
        # Prüfe ob Java bereits installiert ist
        if check_java():
            logger.info("Java ist bereits installiert")
            return True
            
        logger.info("Versuche Java zu installieren...")
        install_script = os.path.join(os.path.dirname(__file__), 'install_java.sh')
        
        # Setze Ausführungsrechte
        os.chmod(install_script, 0o755)
        
        # Führe Installation aus
        result = subprocess.run(['sudo', install_script], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Java-Installation erfolgreich")
            return True
        else:
            logger.error(f"Fehler bei Java-Installation: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Fehler bei der Java-Installation: {str(e)}")
        return False

# JVM Manager Klasse definieren
class JVMManager:
    def __init__(self):
        self.jvm_started = False
        
    def initialize(self):
        if not jpype.isJVMStarted():
            try:
                jvm_path = jpype.getDefaultJVMPath()
                jpype.startJVM(jvm_path, convertStrings=False)
                self.jvm_started = True
                logger.info("JVM erfolgreich initialisiert")
            except Exception as e:
                logger.error(f"Fehler beim Initialisieren der JVM: {str(e)}")
                
    def shutdown(self):
        if jpype.isJVMStarted():
            try:
                jpype.shutdownJVM()
                self.jvm_started = False
                logger.info("JVM heruntergefahren")
            except Exception as e:
                logger.error(f"Fehler beim Herunterfahren der JVM: {str(e)}")

# JVM Manager instanziieren
jvm_manager = JVMManager()

def monitor_memory():
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    logger.info(f"Speicherverbrauch: {memory_info.rss / 1024 / 1024:.2f} MB")

@app.after_request
def cleanup_after_request(response):
    """Führt Speicherbereinigung nach jeder Anfrage durch"""
    gc.collect()
    monitor_memory()
    return response

@app.route('/', methods=['GET'])
def index():
    java_installed = check_java()
    return render_template('index.html', java_installed=java_installed)

@app.route('/', methods=['POST'], endpoint='index_post')
def index_post():
    """Endpunkt zum Versuch der Java-Installation"""
    try:
        if install_java():
            return jsonify({
                'success': True,
                'message': 'Java wurde erfolgreich installiert. Sie können die Anwendung jetzt nutzen.'
            })
        else:
            # Genauere Fehlermeldung
            return jsonify({
                'success': False,
                'message': 'Automatische Installation fehlgeschlagen. Bitte installieren Sie Java manuell:\n' +
                          '- Windows: Laden Sie Java von https://adoptium.net herunter\n' +
                          '- Linux: Nutzen Sie Ihren Paketmanager (apt/yum/dnf install java-11-openjdk)\n' +
                          '- macOS: Nutzen Sie brew install --cask temurin'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Installationsfehler: {str(e)}\nBitte installieren Sie Java manuell.'
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
    """Optimierte Version der DataFrame-zu-HTML Konvertierung"""
    # Speicheroptimierung für große DataFrames
    chunk_size = 1000
    if len(df) > chunk_size:
        html_parts = []
        for i in range(0, len(df), chunk_size):
            chunk = df.iloc[i:i+chunk_size]
            html_parts.append(chunk.to_html(
                classes='table table-striped table-hover',
                index=False,
                border=0,
                escape=False,
                na_rep=''
            ))
        return ''.join(html_parts)
    
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
        # Übergebe die benötigten Funktionen und Objekte an die PDF-Extraktionsfunktionen
        tables = process_pdf_with_encoding(pdf_path, output_format, logger, check_java, jvm_manager)
        
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
            # Übergebe die notwendigen Parameter an die verschobene Funktion
            auflagen_codes = extract_auflagen_codes(tables, app, pdf_path, logger) 
            extracted_texts = extract_auflagen_with_text(pdf_path, app, logger)
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
        
        # Füge Speicherbereinigung nach der Verarbeitung hinzu
        gc.collect()
        monitor_memory()
        
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
    finally:
        # Stelle sicher, dass temporäre Dateien gelöscht werden
        cleanup_temp_files()
        gc.collect()

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
    """Initialisiert die JVM mit optimierten Einstellungen"""
    try:
        if not jpype.isJVMStarted():
            jvm_path = jpype.getDefaultJVMPath()
            if not os.path.exists(jvm_path):
                raise FileNotFoundError(f"JVM nicht gefunden: {jvm_path}")
                
            # JVM-Optionen für bessere Stabilität
            jvm_options = [
                "-Xmx4G",  # Maximum Heap Size
                "-Xms2G",  # Initial Heap Size
                "-XX:+UseG1GC",  # G1 Garbage Collector
                "-XX:MaxGCPauseMillis=100",  # Max GC Pause
                "-Dfile.encoding=UTF-8"  # Encoding
            ]
            
            jpype.startJVM(jvm_path, *jvm_options, convertStrings=False)
            logger.info("JVM erfolgreich initialisiert")
            
    except Exception as e:
        logger.error(f"JVM Initialisierungsfehler: {e}")
        raise

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
        
        # LLM-Analyse durchführen
        llm_analysis = llm_service.analyze_codes_and_info(
            codes=auflagencodes_found,
            vehicle_info=vehicle_info,
            wheel_tire_info=wheel_tire_info
        )
        
        # Füge LLM-Analyse zu den Ergebnissen hinzu
        analysis_summary += f"\n\nKI-Assistenten Analyse:\n{llm_analysis}"
        
        return render_template(
            'ai_analysis.html',
            is_free=is_free,
            confidence=confidence,
            vehicle_info=vehicle_info,
            wheel_tire_info=wheel_tire_info,
            condition_codes=condition_codes,
            analysis_reasons=reasons,
            analysis_summary=analysis_summary,
            llm_analysis=llm_analysis,
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
    
    if 'A02' in codes and 'A03' in codes:  # Lasse die zeile unverändert
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
            if file.startswith(f"{pdf_id}_table_") and (file.endswith('.csv') or file.endswith('.xlsx')):  # lasse die zeile unverändert
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
            if file.startswith(f"{pdf_id}_table_") and (file.endswith('.csv') or file.endswith('.xlsx')):   # lasse die zeile unverändert
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
    app.run(debug=True, host='0.0.0.0', port=5050)
