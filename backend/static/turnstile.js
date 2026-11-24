/**
 * Cloudflare Turnstile Authentication Handler
 * Manages widget initialization, verification, and token submission
 */

function meshmapPublicPathPrefix() {
  const body = document.body;
  if (!body || !body.dataset) return '';
  return String(body.dataset.appBasePath || '').trim();
}

function meshmapApiPath(p) {
  const prefix = meshmapPublicPathPrefix();
  const path = p.startsWith('/') ? p : `/${p}`;
  if (!prefix) return path;
  return `${prefix}${path}`;
}

const TurnstileAuth = {
  config: {
    siteKey: new URLSearchParams(window.location.search).get('siteKey') || 
             document.querySelector('code')?.textContent?.trim() || 
             '{{TURNSTILE_SITE_KEY}}',
    containerSelector: '#turnstile-container',
    errorMessageSelector: '#error-message',
    successMessageSelector: '#success-message',
  },

  state: {
    widgetLoaded: false,
    widgetRendered: false,
    token: null,
    verifying: false,
  },

  log(stepNumber, message) {
    const timestamp = new Date().toLocaleTimeString();
    const fullMessage = `[${timestamp}] Step ${stepNumber}: ${message}`;
    console.log(fullMessage);
    this.updateStepUI(stepNumber, message);
  },

  updateStepUI(stepNumber, message) {
    const statusEl = document.getElementById(`step-${stepNumber}-status`);
    const textEl = document.getElementById(`step-${stepNumber}-text`);
    
    if (!statusEl || !textEl) return;

    if (message.toLowerCase().includes('error') || 
        message.toLowerCase().includes('failed')) {
      statusEl.textContent = '✗';
      statusEl.className = 'step-status';
      textEl.textContent = message;
      textEl.style.color = '#fca5a5';
    } else if (message.toLowerCase().includes('done') || 
               message.toLowerCase().includes('success') ||
               message.toLowerCase().includes('verified')) {
      statusEl.textContent = '✓';
      statusEl.className = 'step-status done';
      textEl.textContent = message;
      textEl.style.color = '#a7f3d0';
    } else {
      statusEl.className = 'step-status active';
      textEl.textContent = message;
      textEl.style.color = '#cbd5e1';
    }
  },

  showError(message) {
    const errorEl = document.querySelector(this.config.errorMessageSelector);
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.classList.add('visible');
      console.error('Turnstile Error:', message);
    }
  },

  hideError() {
    const errorEl = document.querySelector(this.config.errorMessageSelector);
    if (errorEl) {
      errorEl.classList.remove('visible');
    }
  },

  showSuccess() {
    const successEl = document.querySelector(this.config.successMessageSelector);
    if (successEl) {
      successEl.classList.add('visible');
    }
  },

  async waitForTurnstile() {
    this.log(1, 'Waiting for Turnstile API...');
    
    return new Promise((resolve) => {
      const checkInterval = setInterval(() => {
        if (typeof window.turnstile !== 'undefined') {
          clearInterval(checkInterval);
          this.state.widgetLoaded = true;
          this.log(1, 'Turnstile API loaded');
          resolve();
        }
      }, 100);

      // Timeout after 30 seconds
      setTimeout(() => {
        if (!this.state.widgetLoaded) {
          clearInterval(checkInterval);
          this.showError('Turnstile widget took too long to load');
          this.log(1, 'Error: Widget load timeout');
          resolve();
        }
      }, 30000);
    });
  },

  async renderWidget() {
    this.log(2, 'Rendering Turnstile widget...');

    if (!window.turnstile) {
      this.showError('Turnstile API is not available');
      this.log(2, 'Error: Turnstile API unavailable');
      return false;
    }

    try {
      const container = document.querySelector(this.config.containerSelector);
      if (!container) {
        this.showError('Widget container not found');
        this.log(2, 'Error: Container not found');
        return false;
      }

      // Clear loading state
      container.innerHTML = '';

      window.turnstile.render(`#turnstile-container`, {
        sitekey: this.config.siteKey,
        theme: 'dark',
        callback: this.onTurnstileSuccess.bind(this),
        'error-callback': this.onTurnstileError.bind(this),
        'expired-callback': this.onTurnstileExpired.bind(this),
      });

      this.state.widgetRendered = true;
      this.log(2, 'Widget rendered successfully');
      return true;

    } catch (error) {
      this.showError(`Widget render error: ${error.message}`);
      this.log(2, `Error: ${error.message}`);
      return false;
    }
  },

  onTurnstileSuccess(token) {
    this.state.token = token;
    this.log(3, 'Verification received from Cloudflare');
    this.submitToken();
  },

  onTurnstileError(error) {
    this.showError(`Verification error: ${error}`);
    this.log(3, `Error: ${error}`);
  },

  onTurnstileExpired() {
    this.showError('Verification expired, please try again');
    this.log(3, 'Error: Token expired');
    this.state.token = null;
  },

  async submitToken() {
    if (!this.state.token || this.state.verifying) {
      return;
    }

    this.state.verifying = true;
    this.log(4, 'Submitting token to server...');

    try {
      const response = await fetch(meshmapApiPath('/api/verify-turnstile'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: this.state.token,
        }),
      });

      const data = await response.json();

      if (data.success) {
        this.log(4, 'Token verified successfully');
        this.showSuccess();
        
        // Store the auth token in cookie (sent with every request)
        // Set with expires in 24 hours (86400 seconds)
        const expiresIn = 86400;
        const d = new Date();
        d.setTime(d.getTime() + (expiresIn * 1000));
        const expires = d.toUTCString();
        const cookiePath = meshmapPublicPathPrefix()
          ? `${meshmapPublicPathPrefix()}/`
          : '/';
        document.cookie = (
          `meshmap_auth=${data.auth_token}; expires=${expires}; path=${cookiePath}; SameSite=Lax`
        );
        
        this.log(4, `Cookie set: meshmap_auth`);
        
        // Redirect to map after a short delay
        setTimeout(() => {
          window.location.href = meshmapApiPath('/map');
        }, 1500);

      } else {
        this.showError(data.error || 'Server verification failed');
        this.log(4, `Error: ${data.error}`);
        this.state.verifying = false;

        // Reset widget for retry
        if (window.turnstile) {
          window.turnstile.reset();
        }
      }

    } catch (error) {
      this.showError(`Submission error: ${error.message}`);
      this.log(4, `Error: ${error.message}`);
      this.state.verifying = false;

      // Reset widget for retry
      if (window.turnstile) {
        window.turnstile.reset();
      }
    }
  },

  async init() {
    // Retire unused copies; cookie authentication does not require Web Storage.
    for (const storageName of ['sessionStorage', 'localStorage']) {
      try {
        window[storageName].removeItem('meshmap_auth_token');
      } catch (_error) {
        // Storage may be blocked; still attempt cleanup of the other store.
      }
    }
    try {
      this.log(1, 'Initializing Turnstile authentication...');

      // Wait for Turnstile API to load
      await this.waitForTurnstile();

      if (!this.state.widgetLoaded) {
        this.showError('Failed to load Turnstile widget');
        return;
      }

      // Render the widget
      const rendered = await this.renderWidget();
      if (!rendered) {
        return;
      }

      this.hideError();
      this.log(3, 'Waiting for user verification...');

    } catch (error) {
      console.error('Turnstile initialization error:', error);
      this.showError(`Initialization error: ${error.message}`);
    }
  },
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    TurnstileAuth.init();
  });
} else {
  TurnstileAuth.init();
}
