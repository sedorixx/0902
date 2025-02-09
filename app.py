import sys
import subprocess
import threading
import tempfile
# import pkg_resources # removed

required_packages = {
    'flask': 'Flask',
    'pandas': 'pandas',
    'tabula-py': 'tabula',
    'jpype1': 'jpype',
    'openpyxl': 'openpyxl'
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

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
print(f"Temporäres Verzeichnis erstellt: {app.config['UPLOAD_FOLDER']}")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
# Neue Konfigurationsoptionen für besseres Neuladen
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

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
    except:
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
        return False

def process_pdf_with_encoding(filepath, output_format):
    """Verarbeitet PDF mit verbesserter Tabellenerkennung und extrahiert alle Tabellen"""
    try:
        all_tables = []
        
        # Erste Erkennung mit angepassten Parametern für Fahrzeugtabellen
        tables_lattice = tabula.read_pdf(
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
        tables_stream = tabula.read_pdf(
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
        all_detected_tables = tables_lattice + tables_stream
        
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
        return "Fehler: Java muss installiert sein, um diese Anwendung zu nutzen.", 500
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
        
        if not results:
            return "Keine Tabellen in der PDF-Datei gefunden.", 400
            
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

# Ersetze die alte cleanup_temp_files Funktion
def cleanup_temp_files():
    """Bereinigt alle inaktiven temporären Dateien"""
    temp_storage.cleanup_inactive()

if __name__ == '__main__':
    try:
        # Verbesserte Entwicklungsumgebung-Konfiguration
        debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
        port = int(os.environ.get('FLASK_PORT', 5000))
        
        # Bereite die Liste der zu überwachenden Dateien vor
        extra_files = []
        if os.path.exists('./templates'):
            extra_files.extend([os.path.join('./templates', f) for f in os.listdir('./templates')])
        if os.path.exists('./static'):
            extra_files.extend([os.path.join('./static', f) for f in os.listdir('./static')])
        
        # Initialisiere JVM vor dem Start des Servers
        initialize_jvm()
        
        # Stelle sicher, dass der temporäre Ordner existiert und leer ist
        cleanup_temp_files()
        
        app.run(
            host='127.0.0.1',
            port=port,
            debug=debug_mode,
            use_reloader=True,
            reloader_type='stat',
            extra_files=extra_files
        )
    except Exception as e:
        print(f"Server-Fehler: {e}")
        # Fahre JVM nur beim Beenden herunter
        shutdown_jvm()
        sys.exit(1)
    finally:
        # Stelle sicher, dass die JVM beim Beenden heruntergefahren wird
        shutdown_jvm()
