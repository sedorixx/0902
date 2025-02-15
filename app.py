from __future__ import annotations
import sys
import subprocess
import threading # type: ignore
import tempfile
import re # type: ignore
import os
from typing import Any, Dict, List, Optional, Set, Union # type: ignore
from pathlib import Path
from urllib.parse import urlparse

# Try to import jpype and tabula with error handling
tabula_available = False

def cleanup_temp_files():
    """Clean up temporary files in the upload folder"""
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
    except Exception as e:
        print(f"Error cleaning temporary files: {e}")

try:
    import jpype # type: ignore
    from tabula.io import read_pdf # type: ignore
except ImportError:
    print("Warning: tabula-py not available, will use fallback methods")

# Import other required packages
import pandas as pd # type: ignore
import pdfplumber # type: ignore
from PyPDF2 import PdfReader # type: ignore
from flask import Flask, render_template, request, send_file, url_for, jsonify, redirect # type: ignore
from werkzeug.utils import secure_filename # type: ignore
from extensions import db
from models import AuflagenCode # type: ignore
from datetime import datetime

class TempStorage:
    def __init__(self):
        self.active_files = set()

    def add_file(self, filename):
        self.active_files.add(filename)

    def remove_file(self, filename):
        if filename in self.active_files:
            self.active_files.remove(filename)

# Initialize Flask app and temp storage
app = Flask(__name__)
temp_storage = TempStorage()
database_url = os.getenv('DATABASE_URL')

# Update database configuration
if database_url:
    # Convert postgres:// to postgresql:// in database URL
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
else:
    database_url = 'sqlite:///auflagen.db'

app.config.update(
    UPLOAD_FOLDER=tempfile.mkdtemp(),
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50MB max-limit
    TEMPLATES_AUTO_RELOAD=True,
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_EXTENSIONS=['.pdf']
)

# Initialize database
db.init_app(app)

# Print temporary directory location
print(f"Temporäres Verzeichnis erstellt: {app.config['UPLOAD_FOLDER']}")

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Ensure JVM is properly initialized if tabula is available
if tabula_available:
    try:
        if not jpype.isJVMStarted(): # type: ignore
            jpype.startJVM(convertStrings=False) # type: ignore
    except Exception as e:
        print(f"Warning: JVM initialization failed: {e}")
        print("Will use fallback methods for PDF processing")

required_packages = {
    'flask': 'Flask',
    'pandas': 'pandas',
    'tabula-py': 'tabula',
    'jpype1': 'jpype',
    'tabula-py': 'tabula',
    'jpype1': 'jpype',
    'openpyxl': 'openpyxl',
    'flask-sqlalchemy': 'flask_sqlalchemy'  # SQLAlchemy Abhängigkeit
}

def check_and_install_packages():
    """Überprüft und installiert fehlende Pakete"""
    for package, import_name in required_packages.items():
        try:
            __import__(import_name.lower())
        except ImportError:
            print(f"Installiere {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Überprüfe und installiere Abhängigkeiten
check_and_install_packages()

# Jetzt importiere die benötigten Module
import os
import pandas as pd # type: ignore
from werkzeug.utils import secure_filename # type: ignore
from tabula import read_pdf # type: ignore
import jpype # type: ignore
import threading
from flask_sqlalchemy import SQLAlchemy # type: ignore
from extensions import db
from models import AuflagenCode

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
print(f"Temporäres Verzeichnis erstellt: {app.config['UPLOAD_FOLDER']}")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
# Neue Konfigurationsoptionen für besseres Neuladen
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the db with the Flask app
db.init_app(app)

# Remove these lines:
# @app.before_first_request
# def create_tables():
#     db.create_all()

# Überprüfe Abhängigkeiten beim Start
try:
    import jpype # type: ignore
    import tabula # type: ignore
except ImportError as e:
    print("Fehler: Benötigte Pakete nicht gefunden.")
    print("Bitte installieren Sie die erforderlichen Pakete mit:")
    print("pip install jpype1 tabula-py")
    sys.exit(1)

# Stelle sicher, dass der Upload-Ordner existiert
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def check_java():
    """Überprüft die Java-Installation"""
    try:
        import subprocess
        subprocess.check_output(['java', '-version'], stderr=subprocess.STDOUT)
        return True
    except:
        return False

def is_valid_table(df: pd.DataFrame) -> bool:
    """Überprüft, ob ein DataFrame eine echte Tabelle ist"""
    if df.empty or len(df.columns) < 2 or len(df) < 2:
        return False
    
    # Reduziere die Mindestanforderung an gefüllte Zellen auf 50%
    non_empty_cells = df.count()
    total_rows = len(df)
    if (non_empty_cells / total_rows < 0.5).any():
        return False
    
    # Prüfe auf Struktur statt nur numerische Werte
    has_structure = False
    for col in df.columns:
        col_values = df[col].astype(str)
        # Prüfe auf Muster in den Werten
        mean_value = col_values.str.match(r'^[A-Za-z]').mean()
        if mean_value is not None and mean_value > 0.7:  # Text-Muster
            has_structure = True
            break
    
    return has_structure

def clean_vehicle_data(df: pd.DataFrame) -> pd.DataFrame:
    """Bereinigt und standardisiert Fahrzeugdaten"""
    try:
        # Konvertiere alle Spalten zu String
        df = df.astype(str)
        df.columns = [str(col).lower().strip() for col in df.columns]
        
        # Typische Fahrzeug-Spalten erkennen und umbenennen
        column_mapping = {
            'fahrzeug': 'fahrzeug',
            'fzg': 'fahrzeug',
            'kennzeichen': 'kennzeichen',
            'kfz': 'kennzeichen',
            'baujahr': 'baujahr',
            'jahr': 'baujahr',
            'typ': 'typ',
            'modell': 'modell'
        }
        
        # Sichere Spaltenumbenennung
        new_columns = []
        for col in df.columns:
            mapped = False
            for key, value in column_mapping.items():
                if key in str(col).lower():
                    new_columns.append(value)
                    mapped = True
                    break
            if not mapped:
                new_columns.append(col)
        
        df.columns = new_columns
        
        # Bereinige Kennzeichen (nur wenn Spalte existiert)
        if 'kennzeichen' in df.columns:
            df['kennzeichen'] = df['kennzeichen'].apply(lambda x: ''.join(c for c in str(x) if c.isalnum()))
        
        # Bereinige Baujahr
        if 'baujahr' in df.columns:
            def extract_year(x):
                try:
                    # Suche nach 4-stelliger Jahreszahl
                    import re
                    match = re.search(r'\b(19|20)\d{2}\b', str(x))
                    return match.group(0) if match else x
                except:
                    return x
            
            df['baujahr'] = df['baujahr'].apply(extract_year)
        
        return df
    except Exception as e:
        print(f"Fehler bei der Datenbereinigung: {str(e)}")
        # Gebe ursprüngliches DataFrame zurück, wenn Fehler auftreten
        return df

def initialize_jvm_with_fallback():
    """Initialisiert die JVM mit Fallback-Mechanismus"""
    try:
        if not jpype.isJVMStarted():
            jpype.getDefaultJVMPath()  # Prüfe zuerst den JVM-Pfad
            jpype.startJVM(
                jpype.getDefaultJVMPath(),
                "-Djava.class.path=/usr/share/java/tabula-java.jar",
                convertStrings=False,
                interrupt=True
            )
        return True
    except Exception as e:
        print(f"JVM Initialisierungsfehler: {str(e)}")
        print("Verwende Fallback-Methode...")
        return False

def process_pdf_with_encoding(filepath, output_format):
    """Verarbeitet PDF mit verbesserter Tabellenerkennung und extrahiert alle Tabellen"""
    try:
        # Erste Erkennung mit angepasstem Encoding
        try:
            tables_lattice = read_pdf(
                filepath,
                pages='all',
                multiple_tables=True,
                lattice=True,
                guess=True,
                silent=True,
                encoding='utf-8',
                pandas_options={'header': 0}
            )
        except UnicodeDecodeError:
            print("UnicodeDecodeError encountered. Retrying with encoding='latin1'")
            tables_lattice = read_pdf(
                filepath,
                pages='all',
                multiple_tables=True,
                lattice=True,
                guess=True,
                silent=True,
                encoding='latin1',
                pandas_options={'header': 0}
            )
        if tables_lattice:
            return tables_lattice
        
        # Zweite Erkennung mit Stream-Modus und Fallback
        try:
            tables_stream = read_pdf(
                filepath,
                pages='all',
                multiple_tables=True,
                guess=True,
                lattice=True,
                stream=True,
                encoding='utf-8',
                java_options=['-Dfile.encoding=UTF8']
            )
        except UnicodeDecodeError:
            print("UnicodeDecodeError encountered for stream mode. Retrying with encoding='latin1'")
            tables_stream = read_pdf(
                filepath,
                pages='all',
                multiple_tables=True,
                guess=True,
                lattice=True,
                stream=True,
                encoding='latin1',
                java_options=['-Dfile.encoding=latin1']
            )
        if tables_stream:
            return tables_stream
            
        print("No tables found in PDF")
        return []
        
    except Exception as e:
        print(f"Table extraction error: {e}")
        return []

def convert_table_to_html(df):
    """Konvertiert DataFrame in formatiertes HTML"""
    return df.to_html(
        classes='table table-striped table-hover',
        index=False,
        border=0,
    )

def extract_auflagen_codes(tables):
    """Extrahiert Auflagen-Codes ausschließlich aus bestimmten Spalten der Tabellen"""
    codes = set()
    target_columns = [
        'reifenbezogene auflagen und hinweise',
        'auflagen und hinweise'
    ]

    print("Starting Auflagen code extraction...")
    for i, df in enumerate(tables):
        if not isinstance(df, pd.DataFrame):
            continue

        print(f"\nProcessing table {i+1}")
        # Clean column names by removing \r and \n and normalizing whitespace
        df.columns = [str(col).lower().replace('\r', ' ').replace('\n', ' ').strip() for col in df.columns]
        print(f"Normalized columns: {df.columns.tolist()}")

        # Check each column
        for col in df.columns:
            cleaned_col = ' '.join(col.split())  # Normalize whitespace
            if any(target in cleaned_col for target in target_columns):
                print(f"Found matching column: {col}")
                cell_values = df[col].astype(str)

                # Process each cell
                for cell in cell_values:
                    cell = str(cell).strip()
                    if not cell:
                        continue
                        
                    print(f"Processing cell value: {cell}")
                    # First try to find codes with explicit spacing
                    matches = re.finditer(r'(?:^|\s)([A-Za-z]{1,2}\d{1,3}|[A-Z]+\d[a-z]?)(?:\s|$)', cell)
                    for match in matches:
                        code = match.group(1).strip()
                        print(f"Found code: {code}")
                        codes.add(code)

    result_codes = sorted(list(codes))
    print(f"Total codes found: {len(result_codes)}")
    print(f"Found codes: {result_codes}")
    return result_codes

def extract_auflagen_with_text(pdf_path):
    """Extrahiert Auflagen-Codes und zugehörige Texte aus dem PDF"""
    result = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print("Extracting text from PDF...")
            text = ''
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                text += page_text + '\n'
                print(f"Page {page_num + 1} text length: {len(page_text)}")

            # Look for patterns like:
            # A12, A 12, T89, T 89, NA1, K2b, etc. followed by text
            print("Searching for codes and descriptions...")
            
            # Multiple regex patterns for different code formats
            patterns = [
                r'([A-Za-z]{1,2}\s?\d{1,3}[a-z]?)[:\s]+([^\.]+\.)',  # Standard format like A12: text
                r'([A-Z]+\d[a-z])[:\s]+([^\.]+\.)',                   # Format like K2b: text
                r'(\d{2,3})[:\s]+([^\.]+\.)'                         # Just numbers like 123: text
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    code = match.group(1).replace(' ', '')  # Remove spaces in code
                    description = match.group(2).strip()
                    print(f"Found code: {code} with description: {description}")
                    result[code] = description

            print(f"Total descriptions found: {len(result)}")
            print("Found codes with descriptions:", result)
            
    except Exception as e:
        print(f"Error extracting Auflagen text: {e}")
        print(traceback.format_exc())
    return result

@app.route('/', methods=['GET'])
def index():
    if not check_java():
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen.", 500
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
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
        cleanup_temp_files()  # Bereinige alte temporäre Dateien
        if not file.filename:
            return 'Invalid filename', 400
        filename = secure_filename(file.filename or "default_filename.pdf")
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)
        temp_storage.add_file(filename)  # Markiere PDF als aktiv
        
        tables = process_pdf_with_encoding(pdf_path, output_format)
        results = []
        table_htmls = []
        
        # Speichere die Original-PDF-ID für die Suche
        pdf_id = os.path.splitext(filename)[0]
        
        for i, table in enumerate(tables):
            if isinstance(table, pd.DataFrame):
                table = table.fillna('')
                table = table.astype(str)
            else:
                table = pd.DataFrame() if table == '' else pd.DataFrame([table])
            
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
                    print("Installing openpyxl...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                    table.to_excel(output_path, index=False, engine='openpyxl')
            
            temp_storage.add_file(output_filename)  # Markiere Tabelle als aktiv
            results.append(output_filename)
        
        # Extrahiere Auflagen-Codes und deren Texte
        auflagen_codes = extract_auflagen_codes(tables)
        if auflagen_codes is None:
            auflagen_codes = []
        extracted_texts = extract_auflagen_with_text(pdf_path)
        
        # Erstelle Liste von AuflagenCode-Objekten mit den extrahierten Texten
        auflagen_codes = [
    AuflagenCode(
        code=str(code) if code is not None else None,
        description=extracted_texts.get(str(code), "Keine Beschreibung verfügbar")
    )
    for code in auflagen_codes
    if code is not None and not isinstance(code, int)
]
        
        if not results:
            return render_template('error.html', 
                message="Keine Tabellen gefunden", 
                details=[
                    "Die PDF-Datei enthält keine erkennbaren Tabellen.",
                    "Stellen Sie sicher, dass die PDF-Datei die erwarteten Tabellen enthält.",
                    "Versuchen Sie, eine andere PDF-Datei hochzuladen."
                ]
            ), 400
            
        # Automatische Bereinigung nach 1 Stunde
        def delayed_cleanup(file_list, pdf_filename):
            import time
            time.sleep(3600)  # 1 Stunde warten
            for fname in file_list + [pdf_filename]:
                temp_storage.remove_file(fname)
        
        threading.Thread(target=delayed_cleanup, args=(results, filename)).start()
        
        return render_template('results.html', 
                            files=results, 
                            tables=table_htmls,
                            auflagen_codes=auflagen_codes,
                            pdf_file=filename)
        
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
            if not isinstance(table, pd.DataFrame):
                table = pd.DataFrame() if table == '' else pd.DataFrame([table])
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
            return render_template('error.html', 
                message="Keine Tabellen gefunden", 
                details=[
                    "Die PDF-Datei enthält keine erkennbaren Tabellen.",
                    "Vergewissern Sie sich, dass die PDF-Datei Tabellen enthält.",
                    "Versuchen Sie es mit einer alternativen PDF-Datei."
                ]
            ), 400

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
            jpype.startJVM(convertStrings=False)  # Verhindert automatische String-Konvertierung
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

@app.route('/dashboard')
def dashboard():
    """Dashboard view with file management and code management"""
    try:
        files = os.listdir(app.config['UPLOAD_FOLDER'])
        codes = AuflagenCode.query.all()
        
        # Pass helper functions to template
        return render_template(
            'dashboard.html',
            files=files,
            codes=codes,
            get_file_size=get_file_size,
            get_file_date=get_file_date
        )
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template('error.html', 
            message="Fehler beim Laden des Dashboards",
            details=[str(e)]
        ), 500

def check_duplicate_codes():
    """Überprüft und entfernt doppelte Auflagen-Codes und Codes ohne Beschreibung"""
    try:
        # Get all codes
        all_codes = AuflagenCode.query.all()
        
        # Track duplicates and empty descriptions
        code_dict = {}
        duplicates = []
        empty_descriptions = []
        
        for code_obj in all_codes:
            # Stricter check for empty descriptions
            if (code_obj.description is None or 
                code_obj.description.strip() == "" or 
                code_obj.description.strip() == "Keine Beschreibung verfügbar"):
                print(f"Found code without description: {code_obj.code}")
                empty_descriptions.append(code_obj)
                continue
                
            # Check for duplicates
            if code_obj.code in code_dict:
                print(f"Found duplicate code: {code_obj.code}")
                # Keep the one with description if available
                existing_code = code_dict[code_obj.code]
                if (not existing_code.description or 
                    existing_code.description.strip() in ["", "Keine Beschreibung verfügbar"]):
                    duplicates.append(existing_code)
                    code_dict[code_obj.code] = code_obj
                else:
                    duplicates.append(code_obj)
            else:
                code_dict[code_obj.code] = code_obj
        
        # Remove duplicates and empty descriptions
        total_removed = 0
        
        print(f"Found {len(duplicates)} duplicates and {len(empty_descriptions)} codes without description")
        
        # Remove empty descriptions first
        for empty in empty_descriptions:
            print(f"Removing code without description: {empty.code}")
            db.session.delete(empty)
            total_removed += 1
            
        # Then remove duplicates
        for dup in duplicates:
            print(f"Removing duplicate code: {dup.code}")
            db.session.delete(dup)
            total_removed += 1
        
        if total_removed > 0:
            print(f"Committing changes, total removed: {total_removed}")
            db.session.commit()
            return {
                'duplicates': len(duplicates),
                'empty': len(empty_descriptions),
                'total': total_removed
            }
            
        print("No codes to remove")
        return {'duplicates': 0, 'empty': 0, 'total': 0}
        
    except Exception as e:
        print(f"Error checking codes: {e}")
        import traceback
        print(traceback.format_exc())
        db.session.rollback()
        return None

@app.route('/check_duplicates', methods=['POST'])
def check_duplicates():
    """API endpoint to check and remove duplicate codes"""
    try:
        result = check_duplicate_codes()
        if result is None:
            return jsonify({
                'status': 'error',
                'message': 'Fehler beim Überprüfen der Codes'
            }), 500
            
        if result['total'] > 0:
            message = []
            if result['duplicates'] > 0:
                message.append(f"{result['duplicates']} doppelte Codes")
            if result['empty'] > 0:
                message.append(f"{result['empty']} Codes ohne Beschreibung")
            
            return jsonify({
                'status': 'success',
                'message': f"{' und '.join(message)} wurden entfernt",
                'count': result['total']
            })
        else:
            return jsonify({
                'status': 'success',
                'message': 'Keine problematischen Codes gefunden',
                'count': 0
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/save_code', methods=['POST'])
def save_code():
    """Speichert einen neuen Auflagen-Code"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        description = data.get('description', '').strip()
        
        if not code or not description:
            return jsonify({
                'status': 'error',
                'message': 'Code und Beschreibung sind erforderlich'
            }), 400
            
        # Check if code already exists
        existing_code = AuflagenCode.query.filter_by(code=code).first()
        if existing_code:
            return jsonify({
                'status': 'error',
                'message': f'Code {code} existiert bereits'
            }), 400
            
        # Create new code
        new_code = AuflagenCode(code=code, description=description)
        db.session.add(new_code)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Code {code} wurde erfolgreich gespeichert'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error saving code: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Fehler beim Speichern des Codes'
        }), 500

@app.route('/update_code', methods=['POST'])
def update_code():
    """Aktualisiert einen bestehenden Auflagen-Code"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        description = data.get('description', '').strip()
        
        if not code or not description:
            return jsonify({
                'status': 'error',
                'message': 'Code und Beschreibung sind erforderlich'
            }), 400
            
        # Find and update code
        existing_code = AuflagenCode.query.filter_by(code=code).first()
        if not existing_code:
            return jsonify({
                'status': 'error',
                'message': f'Code {code} nicht gefunden'
            }), 404
            
        existing_code.description = description
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Code {code} wurde aktualisiert'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating code: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Fehler beim Aktualisieren des Codes'
        }), 500

@app.route('/delete_code', methods=['POST'])
def delete_code():
    """Löscht einen Auflagen-Code"""
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        
        if not code:
            return jsonify({
                'status': 'error',
                'message': 'Code ist erforderlich'
            }), 400
            
        # Find and delete code
        existing_code = AuflagenCode.query.filter_by(code=code).first()
        if not existing_code:
            return jsonify({
                'status': 'error',
                'message': f'Code {code} nicht gefunden'
            }), 404
            
        db.session.delete(existing_code)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f'Code {code} wurde gelöscht'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting code: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Fehler beim Löschen des Codes'
        }), 500

def get_file_size(filename):
    """Returns formatted file size"""
    try:
        size = os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
    except:
        return "N/A"

def get_file_date(filename):
    """Returns formatted file modification date"""
    try:
        timestamp = os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M')
    except:
        return "N/A"

@app.route('/upload_file', methods=['POST'])
def upload_file():
    """Handle file upload"""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Keine Datei ausgewählt'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Keine Datei ausgewählt'}), 400
    
    if file.filename and not file.filename.lower().endswith('.pdf'):
        return jsonify({'status': 'error', 'message': 'Nur PDF-Dateien sind erlaubt'}), 400
    
    try:
        filename = secure_filename(file.filename or "")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'status': 'success', 'message': 'Datei erfolgreich hochgeladen'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/rename_file', methods=['POST'])
def rename_file():
    """Handle file rename"""
    try:
        data = request.get_json()
        old_name = secure_filename(data['old_name'])
        new_name = secure_filename(data['new_name'])
        
        if not new_name.lower().endswith('.pdf'):
            new_name += '.pdf'
            
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_name)
        new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_name)
        
        if not os.path.exists(old_path):
            return jsonify({'status': 'error', 'message': 'Datei nicht gefunden'}), 404
            
        if os.path.exists(new_path) and old_path != new_path:
            return jsonify({'status': 'error', 'message': 'Zieldatei existiert bereits'}), 400
            
        os.rename(old_path, new_path)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/delete_file', methods=['POST'])
def delete_file():
    """Handle file deletion"""
    try:
        data = request.get_json()
        filename = secure_filename(data['filename'])
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({'status': 'error', 'message': 'Datei nicht gefunden'}), 404
            
        os.unlink(filepath)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/extract_tables/<filename>')
def extract_tables(filename):
    """Extract tables from existing PDF"""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return "Datei nicht gefunden", 404
        
    return redirect(url_for('extract', file=filename))

def init_db():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully")

if __name__ == '__main__':
    print("Starting application...")
    try:
        # Initialize database
        print("Initializing database...")
        init_db()
        print("Database initialized successfully")
        
        # Verbesserte Entwicklungsumgebung-Konfiguration
        debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
        port = int(os.environ.get('FLASK_PORT', 5000))
        print(f"Debug mode: {debug_mode}, Port: {port}")
        
        # Bereite die Liste der zu überwachenden Dateien vor
        print("Setting up file monitoring...")
        extra_files = []
        if os.path.exists('./templates'):
            extra_files.extend([os.path.join('./templates', f) for f in os.listdir('./templates')])
        if os.path.exists('./static'):
            extra_files.extend([os.path.join('./static', f) for f in os.listdir('./static')])
        print(f"Monitoring extra files: {extra_files}")
        
        # Initialisiere JVM vor dem Start des Servers
        print("Initializing JVM...")
        initialize_jvm()
        print("JVM initialized successfully")
        
        # Stelle sicher, dass der temporäre Ordner existiert und leer ist
        print("Cleaning temporary files...")
        cleanup_temp_files()
        print("Temporary files cleaned")
        
        print("Starting Flask server...")
        app.run(
            host='0.0.0.0',
            port=port,
            debug=debug_mode,
            use_reloader=True,
            reloader_type='stat',
            extra_files=extra_files
        )
    except Exception as e:
        print(f"Error starting application: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise
    finally:
        # Stelle sicher, dass die JVM beim Beenden heruntergefahren wird
        print("Shutting down JVM...")
        shutdown_jvm()