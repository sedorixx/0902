class LoadingManager {
    constructor() {
        this.count = 0;
        this._timeout = null;
        this.overlayElement = $('.loading-overlay');
    }

    show() {
        this.count++;
        if (this.count === 1) {
            this.overlayElement.fadeIn();
            document.body.style.overflow = 'hidden';
        }
    }

    hide() {
        this.count = Math.max(0, this.count - 1);
        if (this.count === 0) {
            this.overlayElement.fadeOut();
            document.body.style.overflow = '';
        }
    }

    showWithDelay(delay = 300) {
        this.clearDelay();
        this._timeout = setTimeout(() => this.show(), delay);
    }

    clearDelay() {
        if (this._timeout) {
            clearTimeout(this._timeout);
            this._timeout = null;
        }
    }
}

// Add version number for cache busting
const version = '1.0.0';

window.loadingManager = new LoadingManager();
