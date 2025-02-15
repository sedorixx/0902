import sys
import subprocess
from subprocess import CalledProcessError, check_call, STDOUT
import threading
import tempfile
import re  # Add this import
import jpype
import PyPDF2  # Ersetze pdfplumber import mit PyPDF2

def install_package(package):
    """Installiert ein Python-Paket über pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"Paket {package} erfolgreich installiert")
        return True
    except CalledProcessError as e:
        print(f"Fehler beim Installieren von {package}: {e}")
        return False

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
from flask import Flask, render_template, request, send_file, url_for, jsonify
import os
import pandas as pd
from werkzeug.utils import secure_filename
from tabula.io import read_pdf as tabula_read_pdf
import jpype
import threading
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import AuflagenCode

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
print(f"Temporäres Verzeichnis erstellt: {app.config['UPLOAD_FOLDER']}")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
# Neue Konfigurationsoptionen für besseres Neuladen
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///auflagen.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the db with the Flask app
db.init_app(app)

# Remove these lines:
# @app.before_first_request
# def create_tables():
#     db.create_all()

# Überprüfe Abhängigkeiten beim Start
try:
    import jpype
    import tabula
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
    except CalledProcessError as e:
        return False
    except FileNotFoundError:
        print("Java ist nicht installiert oder der 'java' Befehl ist nicht im PATH.")
        return False

def is_valid_table(df):
    """Überprüft, ob ein DataFrame eine echte Tabelle ist"""
    if df.empty or len(df.columns) < 2 or len(df) < 2:
        return False
    
    # Reduziere die Mindestanforderung an gefüllte Zellen auf 50%
    non_empty_cells = df.count()
    total_rows = len(df)
    if (non_empty_cells / total_rows < 0.5).any():
        return False
    
    # Erlaube längere Texte in einzelnen Zellen
    text_lengths = df.astype(str).apply(lambda x: x.str.len().mean())
    if (text_lengths > 200).all():  # Erhöhe den Schwellenwert
        return False
    
    # Prüfe auf Struktur statt nur numerische Werte
    has_structure = False
    for col in df.columns:
        col_values = df[col].astype(str)
        # Prüfe auf Muster in den Werten
        if (col_values.str.match(r'^[\d.,/-]+$').mean() > 0.3 or  # Numerische Muster
            col_values.str.match(r'^[A-Za-z]').mean() > 0.7):     # Text-Muster
            has_structure = True
            break
    
    return has_structure

def clean_vehicle_data(df):
    """Bereinigt und standardisiert Fahrzeugdaten"""
    try:
        # Konvertiere alle Spalten zu String
        df = df.astype(str)
        
        # Standardisiere Spaltennamen (nur für String-Spalten)
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

def setup_jvm():
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

def process_pdf_with_encoding(filepath, output_format):
    """Verarbeitet PDF mit verbesserter Tabellenerkennung und extrahiert alle Tabellen"""
    try:
        all_tables = []
        
        # Erste Erkennung mit angepassten Parametern für Fahrzeugtabellen
        tables_lattice = tabula_read_pdf(
            filepath,
            pages='all',
            multiple_tables=True,
            lattice=True,
            guess=True,
            silent=True,
            encoding='utf-8',
            pandas_options={'header': 0}  # Erste Zeile als Header
        )
        
        # Zweite Erkennung: Stream-Modus für Tabellen ohne Linien
        tables_stream = tabula_read_pdf(
            filepath,
            pages='all',
            multiple_tables=True,
            lattice=False,
            stream=True,
            guess=True,
            silent=True,
            encoding='utf-8'
        )
        
        # Kombiniere alle Erkennungsmethoden
        all_detected_tables = (tables_lattice if isinstance(tables_lattice, list) else []) + \
                            (tables_stream if isinstance(tables_stream, list) else [])
        
        # Verarbeite die gefundenen Tabellen
        for table in all_detected_tables:
            if isinstance(table, pd.DataFrame) and len(table) > 0:
                # Grundlegende Bereinigung
                table = table.dropna(how='all')
                table = table.dropna(how='all', axis=1)
                table = table.fillna('')
                
                # Konvertiere zu String für einheitliche Verarbeitung
                table = table.astype(str)
                
                if not table.empty and is_valid_table(table):
                    all_tables.append(table)
                    print(f"Gültige Tabelle gefunden mit {len(table)} Zeilen und {len(table.columns)} Spalten")

        return all_tables

    except Exception as e:
        print(f"Fehler bei der Tabellenextraktion: {str(e)}")
        return []

@app.route('/', methods=['GET'])
def index():
    if not check_java():
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen. Bitte installieren Sie Java und stellen Sie sicher, dass der 'java' Befehl im PATH ist.", 500
    return render_template('index.html')

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
        "Technologiezentrum Typprüfstelle Lambsheim"
    ]
    
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            
            # Durchsuche jede Seite
            for page in reader.pages:
                text = page.extract_text()
                if not text:
                    continue
                
                # Teile Text in Zeilen
                lines = text.split('\n')
                current_code = None
                current_text = []
                
                for line in lines:
                    line = line.strip()
                    
                    # Überspringe ausgeschlossene Texte
                    if any(excl in line for excl in excluded_texts):
                        continue
                    
                    # Suche nach Auflagen-Codes
                    code_match = re.match(r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3})[\s\.:)](.+)', line)
                    if code_match:
                        # Speichere vorherigen Code wenn vorhanden
                        if current_code and current_text:
                            codes_with_text[current_code] = ' '.join(current_text)
                        
                        # Starte neuen Code
                        current_code = code_match.group(1)
                        current_text = [code_match.group(2).strip()]
                    elif current_code and line:
                        current_text.append(line)
                
                # Speichere letzten Code
                if current_code and current_text:
                    codes_with_text[current_code] = ' '.join(current_text)
        
        return codes_with_text
        
    except Exception as e:
        print(f"Fehler beim Extrahieren der Auflagen-Texte: {str(e)}")
        return {}

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
    if request.files['file'].filename is None:
        return 'Invalid filename', 400
    pdf_path = os.path.join(str(app.config['UPLOAD_FOLDER']), str(request.files['file'].filename))
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
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(pdf_path)
        temp_storage.add_file(filename)  # Markiere PDF als aktiv
        
        tables = process_pdf_with_encoding(pdf_path, output_format)
        results = []
        table_htmls = []
        
        # Speichere die Original-PDF-ID für die Suche
        pdf_id = os.path.splitext(filename)[0]
        
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
                    print("Installing openpyxl...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
                    table.to_excel(output_path, index=False, engine='openpyxl')
            
            temp_storage.add_file(output_filename)  # Markiere Tabelle als aktiv
            results.append(output_filename)
        
        # Extrahiere Auflagen-Codes und deren Texte
        auflagen_codes = extract_auflagen_codes(tables)
        extracted_texts = extract_auflagen_with_text(pdf_path)
        
        # Erstelle Liste von AuflagenCode-Objekten mit den extrahierten Texten
        condition_codes = [
            AuflagenCode(
                code=code, 
                description=str(extracted_texts.get(str(code))) if str(code) in extracted_texts else AUFLAGEN_TEXTE.get(str(code), "Keine Beschreibung verfügbar")
            )
            for code in auflagen_codes
        ]
        
        if not results:
            return "Keine Tabellen in der PDF-Datei gefunden.", 400
            
        # Automatische Bereinigung nach 1 Stunde
        def delayed_cleanup():
            import time
            time.sleep(3600)  # 1 Stunde warten
            pdf_filename = pdf_path.split('/')[-1]  # Extract filename from path
            for f in results + [pdf_filename]:
                temp_storage.remove_file(f)
        
        threading.Thread(target=delayed_cleanup).start()
        
        return render_template('results.html', 
                            files=results, 
                            tables=table_htmls,
                            condition_codes=condition_codes,
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
        setup_jvm()

@app.teardown_appcontext
def teardown_appcontext(exception=None):
    # JVM nicht bei jedem Request herunterfahren
    pass

# Bereinigung beim Herunterfahren
import atexit
atexit.register(cleanup_temp_files)

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

if __name__ == '__main__':
    try:
        # Initialize database
        init_db()
        
        # Verbesserte Entwicklungsumgebung-Konfiguration
        debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
        port = int(os.environ.get('FLASK_PORT', '5000'))  # Füge Standard-Port 5000 hinzu
        
        # Initialisiere JVM vor dem Start des Servers
        setup_jvm()
        
        # Stelle sicher, dass der temporäre Ordner existiert und leer ist
        cleanup_temp_files()
        
        # Registriere Cleanup-Funktion
        atexit.register(cleanup_on_shutdown)
        
        # Starte Flask-Server
        app.run(
            host='0.0.0.0',
            port=port,
            debug=not debug_mode,
            use_reloader=False
        )
    except Exception as e:
        print(f"Fehler beim Starten der Anwendung: {e}")
    finally:
        cleanup_on_shutdown()

