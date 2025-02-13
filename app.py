import sys
import subprocess
import threading
import tempfile
import re  # Add this import
import jpype
import pdfplumber  # Am Anfang der Datei bei den anderen Imports
from flask import Flask, render_template, request, send_file, url_for, jsonify, send_from_directory, make_response
from flask_cors import CORS

def install_package(package):
    """Installiert ein Python-Paket über pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"Paket {package} erfolgreich installiert")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei der Installation von {package}: {e}")
        return False

# Stelle sicher, dass pdfplumber installiert ist
try:
    import pdfplumber
except ImportError:
    if install_package('pdfplumber'):
        import pdfplumber
    else:
        print("Fehler: Konnte pdfplumber nicht installieren")
        sys.exit(1)

required_packages = {
    'flask': 'Flask',
    'pandas': 'pandas',
    'tabula-py': 'tabula',
    'jpype1': 'jpype',
    'tabula-py': 'tabula',
    'jpype1': 'jpype',
    'openpyxl': 'openpyxl',
    'pdfplumber': 'pdfplumber'  # Neue Abhängigkeit
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
import tabula
import jpype
import threading
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import AuflagenCode

# Aktualisiere die CORS-Konfiguration
app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://musical-guacamole-jj7g69vxrx4jhprjp-5000.app.github.dev",
            "http://127.0.0.1:5000"
        ],
        "methods": ["GET", "HEAD", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in [
        'https://musical-guacamole-jj7g69vxrx4jhprjp-5000.app.github.dev',
        'http://127.0.0.1:5000'
    ]:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Zentrale Route für alle statischen Dateien"""
    try:
        response = send_from_directory('static', filename)
        
        # Set cache headers based on file type
        if any(filename.endswith(ext) for ext in ['.js', '.css', '.woff2', '.png', '.jpg', '.jpeg', '.gif']):
            # Cache static assets for 1 year
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        else:
            # No cache for other files
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            
        # Set content type headers
        if filename.endswith('.js'):
            response.headers['Content-Type'] = 'application/javascript'
        elif filename.endswith('.css'):
            response.headers['Content-Type'] = 'text/css'
        elif filename.endswith('.json'):
            response.headers['Content-Type'] = 'application/json'
            
        return response
    except Exception as e:
        print(f"Fehler beim Bereitstellen von {filename}: {str(e)}")
        return f"Datei {filename} nicht verfügbar", 404

@app.route('/sw.js')
@app.route('/static/sw.js')  # Alternative Route für Abwärtskompatibilität
def serve_sw():
    """Serve Service Worker with correct headers"""
    try:
        response = send_from_directory('static', 'sw.js')
        response.headers.update({
            'Content-Type': 'application/javascript',
            'Service-Worker-Allowed': '/',
            'Cache-Control': 'no-cache',
        })
        
        origin = request.headers.get('Origin')
        if origin:
            response.headers['Access-Control-Allow-Origin'] = origin
            
        return response
    except Exception as e:
        print(f"Fehler beim Bereitstellen von sw.js: {str(e)}")
        return "Service Worker nicht verfügbar", 404

@app.route('/')
@app.route('/upload', methods=['GET'])
def index():
    """Hauptseite und Upload-Route"""
    if not check_java():
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen.", 500
        
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

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
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei der Überprüfung der Java-Installation: {e.output.decode()}")
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

def process_pdf_with_encoding(filepath, output_format):
    """Verarbeitet PDF mit verbesserter Tabellenerkennung"""
    try:
        all_tables = []
        tables_lattice = tabula.read_pdf(
            filepath,
            pages='all',
            multiple_tables=True,
            lattice=True,
            guess=False,
            stream=False,
            silent=True,
            encoding='utf-8',
            pandas_options={'header': None, 'dtype': str}
        )
        
        for table in tables_lattice:
            if isinstance(table, pd.DataFrame) and len(table) > 0:
                # Bereinige die Tabelle
                table = table.fillna('')
                table = table.loc[:, ~table.apply(lambda x: x.str.strip().eq('').all())]
                table = table.loc[~table.apply(lambda x: x.str.strip().eq('').all(), axis=1)]
                
                if len(table) > 0:
                    # Versuche Kopfzeile zu identifizieren
                    if table.columns.dtype == 'int64':
                        table.columns = table.iloc[0]
                        table = table.iloc[1:]
                    all_tables.append(table)

        return all_tables

    except Exception as e:
        print(f"Fehler bei der Tabellenextraktion: {str(e)}")
        return []

def create_condition_code_link(match):
    """Creates HTML for condition code with tooltip"""
    code = match.group(0)
    description = AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar")
    return f'<span class="condition-code" data-code="{code}" data-description="{description}">{code}</span>'

@app.template_filter('replace_condition_codes')
def replace_condition_codes(html):
    """Template filter to replace condition codes with linked versions"""
    import re
    # Pattern für Auflagen-Codes
    pattern = r'(?:(?:[A-Z][0-9]{1,3}[a-z]?)|(?:[0-9]{2,3}[A-Z]?)|(?:NoH|Lim))'
    return re.sub(pattern, create_condition_code_link, html)

def convert_table_to_html(df):
    """Konvertiert DataFrame zu HTML mit Tooltips für Auflagencodes"""
    # Füge Tooltips zu Auflagencodes hinzu
    def add_tooltips_to_codes(text):
        if pd.isna(text):
            return ''
        text = str(text)
        # Pattern für Auflagen-Codes
        pattern = r'([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3}[A-Z]?|NoH|Lim)'
        
        def replace_with_tooltip(match):
            code = match.group(1)
            description = AUFLAGEN_TEXTE.get(code, "Keine Beschreibung verfügbar")
            return f'<span class="auflage-code" data-bs-toggle="tooltip" data-bs-title="{description}">{code}</span>'
        
        return re.sub(pattern, replace_with_tooltip, text)

    # Identifiziere Auflagen-Spalten
    auflagen_columns = [col for col in df.columns 
                       if any(x in str(col).lower() for x in ['auflagen', 'hinweise'])]
    
    # Konvertiere Auflagen-Spalten
    df_copy = df.copy()
    for col in auflagen_columns:
        df_copy[col] = df_copy[col].apply(add_tooltips_to_codes)

    # Konvertiere zu HTML
    html = df_copy.to_html(
        index=False,
        header=True,
        classes='table table-striped table-bordered pdf-table',
        escape=False,
        na_rep='',
        justify='left',
        border=1,
        table_id='dataTable'
    )
    
    # Entferne zusätzliche Formatierungen
    html = html.replace('style="text-align: left;"', '')
    html = html.replace('\n', ' ')
    
    return html

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
    current_code = None
    current_text = []
    extraction_finished = False
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                if extraction_finished:
                    break
                    
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    # Beende sofort wenn "Prüfort und Prüfdatum" gefunden wird
                    if "Prüfort und Prüfdatum" in line:
                        if current_code and current_text:
                            codes_with_text[current_code] = ' '.join(current_text).strip()
                            print(f"Letzter Code gespeichert: {current_code}")
                        extraction_finished = True
                        break
                    
                    # Überspringe irrelevante Zeilen
                    if not line or any(x in line for x in [
                        "Technologiezentrum", 
                        "Prüfstelle", 
                        "Königsberger",
                        "Tel.:",
                        "Fax:"
                    ]):
                        continue

                    # Pattern für Auflagen-Code mit Beschreibung
                    code_match = re.match(
                        r'^([A-Z][0-9]{1,3}[a-z]?|[0-9]{2,3}[A-Z]?|[XY][0-9]{2}|[A-Z]{1,2}[0-9]{2}[a-z]?)\s*[:.-]?\s*(.+)', 
                        line
                    )
                    
                    if code_match:
                        # Speichere vorherigen Code
                        if current_code and current_text:
                            codes_with_text[current_code] = ' '.join(current_text).strip()
                            print(f"Gespeicherter Code {current_code}: {codes_with_text[current_code][:100]}")
                        
                        # Starte neuen Code
                        current_code = code_match.group(1)
                        current_text = [code_match.group(2)]
                        print(f"Neuer Code gefunden: {current_code}")
                    elif current_code:
                        # Füge Folgezeilen zur aktuellen Beschreibung hinzu
                        current_text.append(line)

        # Bereinige die Texte
        for code, text in codes_with_text.items():
            # Entferne mehrfache Leerzeichen und Zeilenumbrüche
            text = re.sub(r'\s+', ' ', text)
            # Entferne Sonderzeichen am Anfang und Ende
            text = re.sub(r'^[^a-zA-Z0-9äöüÄÖÜß]+', '', text)
            text = re.sub(r'[^a-zA-Z0-9äöüÄÖÜß.]+$', '', text)
            codes_with_text[code] = text.strip()

    except Exception as e:
        print(f"Fehler beim Extrahieren der Auflagen-Texte: {str(e)}")
        import traceback
        print(traceback.format_exc())
    
    print(f"\nGefundene Auflagen-Texte: {len(codes_with_text)}")
    return codes_with_text

def extract_auflagen_codes(tables):
    """Extrahiert und speichert Auflagencodes"""
    codes = set()
    codes_in_tables = {}  # Speichert Codes und deren Kontext aus den Tabellen
    
    code_pattern = re.compile(r"""
        (?:
            # Standardcodes wie A01, B123a, T99, etc.
            [A-Z][0-9]{1,3}[a-z]?|
            # Numerische Codes wie 155, 12A
            [0-9]{2,3}[A-Z]?|
            # Spezielle zweibuchstabige Codes wie Kg, KG
            K[a-z1-9]|
            # Spezielle Codes mit Buchstaben und Zahlen
            [A-Z][0-9][a-z0-9]|
            # Codes mit Buchstaben am Ende wie 123a
            [0-9]{2,3}[a-z]|
            # Spezielle Wörter
            NoH|Lim|
            # Codes wie V00, V19, etc.
            V[0-9]{2}|
            # Codes wie X77, Y16, Y18, Y63, Y85
            [XY][0-9]{2}|
            # S-Codes wie S01, S02, etc.
            S[0-9]{2}|
            # K-Codes wie K14, K1a, K1b, etc.
            K[0-9][a-z0-9]|
            # Spezielle K-Codes wie K41, K42, etc.
            K[0-9]{2}|
            # T-Codes wie T84-T99
            T[0-8][0-9]|T9[0-9]|
            # R-Codes wie R21, R35
            R[0-9]{2}|
            # G-Codes wie G01, G03
            G[0-9]{2}|
            # B-Codes wie B03, B90
            B[0-9]{2}|
            # F-Codes wie F24, F38, F39
            F[0-9]{2}
        )
        (?=[^a-zA-Z0-9]|$)  # Verhindert teilweise Matches in längeren Wörtern
    """, re.VERBOSE)

    # Erst alle Codes aus den Tabellen extrahieren und Kontext speichern
    for table in tables:
        normalized_columns = {
            str(col).strip().lower(): col 
            for col in table.columns
        }
        
        relevant_columns = []
        for norm_name, original_name in normalized_columns.items():
            if ('reifenbezogene' in norm_name and 'auflagen' in norm_name) or \
               ('auflagen' in norm_name and 'hinweise' in norm_name):
                relevant_columns.append(original_name)
                print(f"Gefundene relevante Spalte: {original_name}")

        if not relevant_columns:
            continue

        for col in relevant_columns:
            values = table[col].astype(str)
            for value in values:
                # Teile den Text an Kommas und anderen Trennzeichen
                parts = re.split(r'[,;/\s]+', value)
                for part in parts:
                    matches = code_pattern.findall(part.strip())
                    if matches:
                        for code in matches:
                            codes.add(code)
                            # Speichere den originalen Kontext
                            if code not in codes_in_tables:
                                codes_in_tables[code] = value.strip()
                        print(f"Gefundene Codes in '{value}': {matches}")

    try:
        # Hole die Beschreibungen aus der PDF
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], request.files['file'].filename)
        extracted_texts = extract_auflagen_with_text(pdf_path)
        
        with app.app_context():
            existing_codes = {code.code: code for code in AuflagenCode.query.all()}
            code_objects = []
            
            for code in codes:
                # Priorität der Beschreibungen:
                # 1. Aus der PDF extrahierter Text
                # 2. Standard-Text aus AUFLAGEN_TEXTE
                # 3. Kontext aus der Tabelle
                # 4. Fallback-Text
                if code in extracted_texts:
                    description = extracted_texts[code]
                elif code in AUFLAGEN_TEXTE:
                    description = AUFLAGEN_TEXTE[code]
                elif code in codes_in_tables:
                    description = f"Aus Tabelle: {codes_in_tables[code]}"
                else:
                    description = "Keine Beschreibung verfügbar"

                if code in existing_codes:
                    existing_codes[code].description = description
                    code_objects.append(existing_codes[code])
                else:
                    new_code = AuflagenCode(code=code, description=description)
                    db.session.add(new_code)
                    code_objects.append(new_code)
            
            db.session.commit()
            print(f"Erfolgreich {len(code_objects)} Codes gespeichert")
            
            # Hole aktualisierte Codes
            return AuflagenCode.query.filter(AuflagenCode.code.in_(codes)).all()

    except Exception as e:
        print(f"Fehler beim Speichern in der DB: {str(e)}")
        db.session.rollback()
        return []

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
            
            # Verbesserte Tabellenverarbeitung
            if isinstance(table, pd.DataFrame):
                # Konvertiere erste Zeile zu Spaltenüberschriften wenn keine vorhanden
                if table.columns.dtype == 'int64':
                    table.columns = table.iloc[0]
                    table = table.iloc[1:]
                
                # Bereinige die Tabelle
                table = clean_table_data(table)
                
                # Generiere HTML
                table_html = convert_table_to_html(table)
                table_htmls.append(table_html)
            
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
        
        # Extrahiere und speichere Auflagencodes
        condition_codes = extract_auflagen_codes(tables)
        print(f"Gefundene Auflagencodes: {len(condition_codes)}")
        
        # Verwende die Attribute innerhalb der Route-Funktion
        for code in condition_codes:
            with app.app_context():
                print(f"Code: {code.code}, Beschreibung: {code.description[:50]}...")
            
        return render_template(
            'results.html',
            files=results,
            tables=table_htmls,
            condition_codes=condition_codes,  # Übergebe die Code-Objekte
            pdf_file=filename
        )
        
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

def clean_table_data(df):
    """Bereinigt Tabellendaten und markiert Auflagen-Codes"""
    df = df.astype(str)  # Konvertiere alle Daten zu Strings
    
    # Konvertiere Spaltennamen zu Strings
    df.columns = df.columns.astype(str)
    
    # Identifiziere Spalten mit Auflagen
    auflagen_columns = [col for col in df.columns 
                       if any(x in str(col).lower() for x in ['auflagen', 'hinweise'])]
    
    # Bereinige die Auflagen-Spalten
    for col in auflagen_columns:
        if col in df.columns:
            # Standardisiere Trennzeichen
            df[col] = df[col].str.replace(';', ',').str.replace('/', ',')
            # Entferne überflüssige Leerzeichen
            df[col] = df[col].str.strip()
    
    return df

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

@app.route('/condition_codes', methods=['GET'])
def get_condition_codes():
    """Zeigt alle verfügbaren Auflagencodes an"""
    try:
        codes = AuflagenCode.query.all()
        return render_template('condition_codes.html', condition_codes=codes)
    except Exception as e:
        print(f"Fehler beim Abrufen der Auflagencodes: {str(e)}")
        return "Fehler beim Laden der Auflagencodes", 500

def init_db():
    with app.app_context():
        db.create_all()

def init_app():
    """Initialisiert die Anwendung"""
    init_db()
    initialize_jvm()
    cleanup_temp_files()
    atexit.register(cleanup_on_shutdown)

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
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    init_app()
    
    try:
        # Starte Flask-Server
        app.run(
            host='127.0.0.1',
            port=port,
            debug=debug,
            use_reloader=False
        )
    except Exception as e:
        print(f"Fehler beim Starten der Anwendung: {e}")
    finally:
        # Stelle sicher, dass die JVM beim Beenden heruntergefahren wird
        shutdown_jvm()
