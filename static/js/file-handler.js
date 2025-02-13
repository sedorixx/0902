class FileHandler {
    constructor(inputElement, options = {}) {
        this.input = inputElement;
        this.options = {
            maxSize: options.maxSize || 16 * 1024 * 1024, // 16MB default
            acceptedTypes: options.acceptedTypes || ['application/pdf'],
            ...options
        };
        
        this.setupListeners();
    }

    setupListeners() {
        this.input.addEventListener('change', (e) => this.handleFileSelect(e));
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Clear input for back-forward cache compatibility
        event.target.value = '';

        if (!this.validateFile(file)) {
            return;
        }

        if (typeof this.options.onFileSelected === 'function') {
            this.options.onFileSelected(file);
        }
    }

    validateFile(file) {
        if (file.size > this.options.maxSize) {
            toastr.error('Die Datei ist zu groß. Maximale Größe: ' + 
                        (this.options.maxSize / (1024 * 1024)) + 'MB');
            return false;
        }

        if (!this.options.acceptedTypes.includes(file.type)) {
            toastr.error('Dieser Dateityp wird nicht unterstützt.');
            return false;
        }

        return true;
    }
}
