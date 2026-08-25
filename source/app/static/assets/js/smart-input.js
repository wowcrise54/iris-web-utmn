/**
 * DFIR-IRIS Smart IOC Input
 * 
 * Automatically detects IOC types and provides validation
 * Supports: IPv4, IPv6, Domain, URL, MD5, SHA1, SHA256, Email, MAC
 */

class SmartIOCInput {
  constructor(selector) {
    this.input = document.querySelector(selector);
    if (!this.input) return;
    
    this.detectedType = null;
    this.init();
  }

  init() {
    // Create type indicator
    const indicator = document.createElement('div');
    indicator.className = 'detected-type';
    indicator.style.display = 'none';
    this.input.parentElement.appendChild(indicator);
    this.typeIndicator = indicator;

    // Create error message
    const error = document.createElement('div');
    error.className = 'input-error';
    error.style.display = 'none';
    this.input.parentElement.appendChild(error);
    this.errorIndicator = error;

    // Bind input events
    this.input.addEventListener('input', (e) => this.handleInput(e.target.value));
    this.input.addEventListener('focus', () => this.handleFocus());
    this.input.addEventListener('blur', () => this.handleBlur());
  }

  handleInput(value) {
    if (!value.trim()) {
      this.clear();
      return;
    }

    const type = this.detectType(value.trim());
    
    if (type) {
      this.detectedType = type;
      this.showType(type);
      this.errorIndicator.style.display = 'none';
    } else {
      this.detectedType = null;
      this.showError('Unrecognized IOC type. Supported: IP, Domain, URL, Hash, Email, MAC');
    }
  }

  detectType(value) {
    // MAC Address (check before IPv6 to avoid false positives)
    const macRegex = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/;
    if (macRegex.test(value)) {
      return { type: 'MAC Address', icon: '🔌', color: 'var(--color-info-600)' };
    }

    // IPv4
    const ipv4Regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    if (ipv4Regex.test(value)) {
      return { type: 'IPv4 Address', icon: '🌐', color: 'var(--color-success-600)' };
    }

    // IPv6 (supports full and compressed formats)
    const ipv6Regex = /^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$|^((([0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{0,4})|(::([0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4})|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:))$/;
    if (ipv6Regex.test(value)) {
      return { type: 'IPv6 Address', icon: '🌐', color: 'var(--color-success-600)' };
    }

    // Domain (must not contain http/https)
    const domainRegex = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}$/;
    if (domainRegex.test(value) && !value.includes('http')) {
      return { type: 'Domain', icon: '🌍', color: 'var(--color-primary-600)' };
    }

    // URL
    const urlRegex = /^https?:\/\/[^\s/$.?#].[^\s]*$/i;
    if (urlRegex.test(value)) {
      return { type: 'URL', icon: '🔗', color: 'var(--color-primary-600)' };
    }

    // SHA256 (64 hex chars)
    const sha256Regex = /^[a-fA-F0-9]{64}$/;
    if (sha256Regex.test(value)) {
      return { type: 'SHA256', icon: '🔐', color: 'var(--color-warning-600)' };
    }

    // SHA1 (40 hex chars)
    const sha1Regex = /^[a-fA-F0-9]{40}$/;
    if (sha1Regex.test(value)) {
      return { type: 'SHA1', icon: '🔐', color: 'var(--color-warning-600)' };
    }

    // MD5 (32 hex chars)
    const md5Regex = /^[a-fA-F0-9]{32}$/;
    if (md5Regex.test(value)) {
      return { type: 'MD5', icon: '🔐', color: 'var(--color-warning-600)' };
    }

    // Email
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (emailRegex.test(value)) {
      return { type: 'Email', icon: '📧', color: 'var(--color-info-600)' };
    }

    return null;
  }

  showType(type) {
    this.typeIndicator.innerHTML = `${type.icon} ${type.type}`;
    this.typeIndicator.style.color = type.color;
    this.typeIndicator.style.display = 'flex';
    this.typeIndicator.style.alignItems = 'center';
    this.typeIndicator.style.gap = '8px';
    this.typeIndicator.style.fontSize = '14px';
    this.typeIndicator.style.marginTop = '4px';
  }

  showError(message) {
    this.errorIndicator.textContent = message;
    this.errorIndicator.style.color = 'var(--color-danger-600)';
    this.errorIndicator.style.display = 'block';
    this.errorIndicator.style.fontSize = '12px';
    this.errorIndicator.style.marginTop = '4px';
  }

  clear() {
    this.detectedType = null;
    this.typeIndicator.style.display = 'none';
    this.errorIndicator.style.display = 'none';
  }

  handleFocus() {
    // Show hint
    this.typeIndicator.innerHTML = '🔍 Paste IOC (IP, domain, URL, hash...)';
    this.typeIndicator.style.color = 'var(--color-neutral-500)';
    this.typeIndicator.style.display = 'flex';
  }

  handleBlur() {
    if (!this.input.value.trim()) {
      this.clear();
    }
  }

  getDetectedType() {
    return this.detectedType;
  }
}

// Initialize all smart inputs
document.addEventListener('DOMContentLoaded', () => {
  const smartInputs = document.querySelectorAll('.smart-ioc-input');
  smartInputs.forEach(input => new SmartIOCInput(input));
});

// Export for window
window.SmartIOCInput = SmartIOCInput;
