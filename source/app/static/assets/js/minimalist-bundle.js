/**
 * DFIR-IRIS Minimalist Bundle
 * 
 * Concatenated and optimized JS for minimalist UI
 * Auto-generated from individual modules
 * 
 * Classes included:
 * - MinimalistNavigation
 * - ZenMode
 * - KeyboardNavigation
 * - SmartIOCInput
 */

(function() {
  'use strict';

  // MinimalistNavigation class
  class MinimalistNavigation {
    constructor() {
      this.searchModal = null;
      this.shortcutsModal = null;
      this.currentFocusIndex = -1;
      this.init();
    }

    init() {
      this.bindKeyboardShortcuts();
      this.initSearch();
      this.initShortcutsModal();
      this.initZenMode();
    }

    bindKeyboardShortcuts() {
      document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
          e.preventDefault();
          this.openSearch();
        }
        if (e.key === 'Escape') {
          this.closeAllModals();
        }
        if (e.key === '/' && !this.isInputFocused()) {
          e.preventDefault();
          this.openShortcuts();
        }
        if ((e.key === 'j' || e.key === 'k') && !this.isInputFocused()) {
          this.handleListNavigation(e.key);
        }
      });
    }

    initSearch() {
      const searchModalHTML = `
        <div class="search-modal" style="display: none;">
          <div class="search-overlay" onclick="minimalistNav.closeSearch()"></div>
          <div class="search-container">
            <input type="text" class="search-input" placeholder="Search alerts, cases, IOC..." autofocus>
            <div class="search-results"></div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', searchModalHTML);
      this.searchModal = document.querySelector('.search-modal');
      
      const searchInput = this.searchModal.querySelector('.search-input');
      searchInput.addEventListener('input', (e) => this.performSearch(e.target.value));
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          this.closeSearch();
        }
      });
    }

    openSearch() {
      this.searchModal.style.display = 'block';
      const searchInput = this.searchModal.querySelector('.search-input');
      searchInput.focus();
      searchInput.value = '';
    }

    closeSearch() {
      this.searchModal.style.display = 'none';
    }

    performSearch(query) {
      const resultsContainer = this.searchModal.querySelector('.search-results');
      if (query.length < 2) {
        resultsContainer.innerHTML = '';
        return;
      }
      resultsContainer.innerHTML = `<div class="search-placeholder">Search for "${query}"...</div>`;
    }

    initShortcutsModal() {
      const shortcutsHTML = `
        <div class="shortcuts-modal" style="display: none;">
          <div class="shortcuts-overlay" onclick="minimalistNav.closeShortcuts()"></div>
          <div class="shortcuts-container">
            <div class="shortcuts-header">
              <h3>Keyboard Shortcuts</h3>
              <button class="btn-icon close-shortcuts" onclick="minimalistNav.closeShortcuts()">✕</button>
            </div>
            <div class="shortcut-list">
              <div class="shortcut-item"><kbd>Cmd+K</kbd><span>Global search</span></div>
              <div class="shortcut-item"><kbd>j/k</kbd><span>Navigate list</span></div>
              <div class="shortcut-item"><kbd>ESC</kbd><span>Close modal</span></div>
              <div class="shortcut-item"><kbd>/</kbd><span>Show shortcuts</span></div>
              <div class="shortcut-item"><kbd>Cmd+.</kbd><span>Zen mode</span></div>
            </div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', shortcutsHTML);
      this.shortcutsModal = document.querySelector('.shortcuts-modal');
    }

    openShortcuts() {
      this.shortcutsModal.style.display = 'block';
    }

    closeShortcuts() {
      this.shortcutsModal.style.display = 'none';
    }

    initZenMode() {
      const minimalNav = document.querySelector('.minimal-nav');
      if (minimalNav) {
        const zenButton = document.createElement('button');
        zenButton.className = 'zen-mode-toggle btn-icon';
        zenButton.innerHTML = '◐';
        zenButton.title = 'Toggle Zen Mode (Cmd+.)';
        zenButton.setAttribute('aria-label', 'Toggle Zen Mode');
        zenButton.onclick = () => {
          if (typeof zenMode !== 'undefined') {
            zenMode.toggle();
          }
        };
        minimalNav.appendChild(zenButton);
      }
    }

    handleListNavigation(key) {
      const rows = document.querySelectorAll('.alert-row:not(.selected), .case-row:not(.selected)');
      if (rows.length === 0) return;
      
      if (key === 'j') {
        this.currentFocusIndex = Math.min(this.currentFocusIndex + 1, rows.length - 1);
      } else {
        this.currentFocusIndex = Math.max(this.currentFocusIndex - 1, 0);
      }
      
      rows.forEach((row, index) => {
        row.classList.toggle('selected', index === this.currentFocusIndex);
        if (index === this.currentFocusIndex) {
          row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    }

    isInputFocused() {
      const activeElement = document.activeElement;
      return activeElement.tagName === 'INPUT' || 
             activeElement.tagName === 'TEXTAREA' ||
             activeElement.isContentEditable;
    }

    closeAllModals() {
      this.closeSearch();
      this.closeShortcuts();
    }
  }

  // ZenMode class
  class ZenMode {
    constructor() {
      this.isActive = false;
      this.init();
    }

    init() {
      this.isActive = localStorage.getItem('zen-mode') === 'true';
      if (this.isActive) {
        this.enable();
      }
      document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === '.') {
          e.preventDefault();
          this.toggle();
        }
        if (e.key === 'Escape' && this.isActive) {
          this.disable();
        }
      });
      this.addExitHint();
    }

    toggle() {
      if (this.isActive) {
        this.disable();
      } else {
        this.enable();
      }
    }

    enable() {
      this.isActive = true;
      document.body.classList.add('zen-mode');
      localStorage.setItem('zen-mode', 'true');
      this.showIndicator();
      document.dispatchEvent(new CustomEvent('zenMode:enabled'));
    }

    disable() {
      this.isActive = false;
      document.body.classList.remove('zen-mode');
      localStorage.setItem('zen-mode', 'false');
      this.hideIndicator();
      document.dispatchEvent(new CustomEvent('zenMode:disabled'));
    }

    showIndicator() {
      const indicator = document.createElement('div');
      indicator.className = 'zen-mode-indicator';
      indicator.innerHTML = '◐ Zen Mode Active';
      document.body.appendChild(indicator);
    }

    hideIndicator() {
      const indicator = document.querySelector('.zen-mode-indicator');
      if (indicator) {
        indicator.remove();
      }
    }

    addExitHint() {
      const hint = document.createElement('div');
      hint.className = 'zen-mode-exit-hint';
      hint.innerHTML = 'Press ESC to exit Zen Mode';
      document.body.appendChild(hint);
    }
  }

  // KeyboardNavigation class
  class KeyboardNavigation {
    constructor() {
      this.currentFocusIndex = -1;
      this.currentList = null;
      this.init();
    }

    init() {
      this.bindGlobalShortcuts();
      this.initListNavigation();
      setTimeout(() => this.enhanceShortcutsModal(), 100);
    }

    bindGlobalShortcuts() {
      document.addEventListener('keydown', (e) => {
        if (this.isInputFocused() && e.key !== 'Escape') return;
        if (e.key === 'Escape') {
          this.closeAllModals();
          return;
        }
        if (e.key === '/') {
          e.preventDefault();
          this.toggleShortcutsModal();
          return;
        }
        if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
          e.preventDefault();
          this.toggleSidebar();
          return;
        }
        if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'N') {
          e.preventDefault();
          window.location.href = '/alerts/new';
          return;
        }
      });
    }

    initListNavigation() {
      document.addEventListener('keydown', (e) => {
        if (!this.isInputFocused()) {
          const list = document.querySelector('.alert-row, .case-row');
          if (list) {
            if (e.key === 'j') {
              e.preventDefault();
              this.moveFocus(1);
            } else if (e.key === 'k') {
              e.preventDefault();
              this.moveFocus(-1);
            } else if (e.key === 'Enter') {
              e.preventDefault();
              this.openSelected();
            }
          }
        }
      });
    }

    moveFocus(direction) {
      const rows = document.querySelectorAll('.alert-row, .case-row');
      if (rows.length === 0) return;
      if (this.currentFocusIndex >= 0 && this.currentFocusIndex < rows.length) {
        rows[this.currentFocusIndex].classList.remove('selected');
      }
      this.currentFocusIndex += direction;
      this.currentFocusIndex = Math.max(0, Math.min(this.currentFocusIndex, rows.length - 1));
      rows[this.currentFocusIndex].classList.add('selected');
      rows[this.currentFocusIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    openSelected() {
      const selected = document.querySelector('.alert-row.selected, .case-row.selected');
      if (selected) {
        const link = selected.querySelector('a');
        if (link) {
          link.click();
        }
      }
    }

    closeAllModals() {
      const searchModal = document.querySelector('.search-modal');
      if (searchModal) searchModal.style.display = 'none';
      const shortcutsModal = document.querySelector('.shortcuts-modal');
      if (shortcutsModal) shortcutsModal.style.display = 'none';
      document.querySelectorAll('.modal[style*="display: block"]').forEach(modal => {
        modal.style.display = 'none';
      });
    }

    toggleShortcutsModal() {
      let modal = document.querySelector('.shortcuts-modal');
      if (!modal) {
        modal = this.createShortcutsModal();
      } else {
        if (modal.style.display === 'block') {
          modal.style.display = 'none';
        } else {
          modal.style.display = 'block';
        }
        return;
      }
      if (modal.style.display === 'block') {
        modal.style.display = 'none';
      } else {
        modal.style.display = 'block';
      }
    }

    createShortcutsModal() {
      const shortcuts = [
        { key: 'Cmd+K / Ctrl+K', action: 'Global search' },
        { key: 'j / k', action: 'Navigate list' },
        { key: 'Enter', action: 'Open selected' },
        { key: 'ESC', action: 'Close modal' },
        { key: '/', action: 'Show shortcuts' },
        { key: 'Cmd+B / Ctrl+B', action: 'Toggle sidebar' },
        { key: 'Cmd+Shift+N', action: 'New alert' },
        { key: 'Cmd+.', action: 'Zen mode' }
      ];
      const modalHTML = `
        <div class="shortcuts-modal">
          <div class="shortcuts-overlay" onclick="keyboardNav.closeAllModals()"></div>
          <div class="shortcuts-container">
            <div class="shortcuts-header">
              <h2>Keyboard Shortcuts</h2>
              <button class="btn-close" onclick="keyboardNav.closeAllModals()">×</button>
            </div>
            <div class="shortcuts-list">
              ${shortcuts.map(s => `
                <div class="shortcut-item">
                  <kbd>${s.key}</kbd>
                  <span>${s.action}</span>
                </div>
              `).join('')}
            </div>
            <div class="shortcuts-footer">
              <small>Press ESC or / to close</small>
            </div>
          </div>
        </div>
      `;
      document.body.insertAdjacentHTML('beforeend', modalHTML);
      return document.querySelector('.shortcuts-modal');
    }

    enhanceShortcutsModal() {
      const modal = document.querySelector('.shortcuts-modal');
      if (!modal) return;
      const shortcutsList = modal.querySelector('.shortcuts-list');
      if (!shortcutsList) return;
      const additionalShortcuts = [
        { key: 'Enter', action: 'Open selected' },
        { key: 'Cmd+B / Ctrl+B', action: 'Toggle sidebar' },
        { key: 'Cmd+Shift+N', action: 'New alert' }
      ];
      additionalShortcuts.forEach(s => {
        const item = document.createElement('div');
        item.className = 'shortcut-item';
        item.innerHTML = `<kbd>${s.key}</kbd><span>${s.action}</span>`;
        shortcutsList.appendChild(item);
      });
    }

    toggleSidebar() {
      document.body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('sidebar-collapsed', document.body.classList.contains('sidebar-collapsed'));
    }

    isInputFocused() {
      const activeElement = document.activeElement;
      return activeElement.tagName === 'INPUT' || 
             activeElement.tagName === 'TEXTAREA' ||
             activeElement.isContentEditable;
    }
  }

  // SmartIOCInput class
  class SmartIOCInput {
    constructor(selector) {
      this.input = document.querySelector(selector);
      if (!this.input) return;
      this.detectedType = null;
      this.init();
    }

    init() {
      const indicator = document.createElement('div');
      indicator.className = 'detected-type';
      indicator.style.display = 'none';
      this.input.parentElement.appendChild(indicator);
      this.typeIndicator = indicator;

      const error = document.createElement('div');
      error.className = 'input-error';
      error.style.display = 'none';
      this.input.parentElement.appendChild(error);
      this.errorIndicator = error;

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
      const macRegex = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/;
      if (macRegex.test(value)) {
        return { type: 'MAC Address', icon: '🔌', color: 'var(--color-info-600)' };
      }
      const ipv4Regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
      if (ipv4Regex.test(value)) {
        return { type: 'IPv4 Address', icon: '🌐', color: 'var(--color-success-600)' };
      }
      const ipv6Regex = /^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$|^((([0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{0,4})|(::([0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4})|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:))$/;
      if (ipv6Regex.test(value)) {
        return { type: 'IPv6 Address', icon: '🌐', color: 'var(--color-success-600)' };
      }
      const domainRegex = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}$/;
      if (domainRegex.test(value) && !value.includes('http')) {
        return { type: 'Domain', icon: '🌍', color: 'var(--color-primary-600)' };
      }
      const urlRegex = /^https?:\/\/[^\s/$.?#].[^\s]*$/i;
      if (urlRegex.test(value)) {
        return { type: 'URL', icon: '🔗', color: 'var(--color-primary-600)' };
      }
      const sha256Regex = /^[a-fA-F0-9]{64}$/;
      if (sha256Regex.test(value)) {
        return { type: 'SHA256', icon: '🔐', color: 'var(--color-warning-600)' };
      }
      const sha1Regex = /^[a-fA-F0-9]{40}$/;
      if (sha1Regex.test(value)) {
        return { type: 'SHA1', icon: '🔐', color: 'var(--color-warning-600)' };
      }
      const md5Regex = /^[a-fA-F0-9]{32}$/;
      if (md5Regex.test(value)) {
        return { type: 'MD5', icon: '🔐', color: 'var(--color-warning-600)' };
      }
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

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    window.minimalistNav = new MinimalistNavigation();
    window.zenMode = new ZenMode();
    window.keyboardNav = new KeyboardNavigation();
    
    // Initialize all smart inputs
    const smartInputs = document.querySelectorAll('.smart-ioc-input');
    smartInputs.forEach(input => new SmartIOCInput(input));
  });

})();
