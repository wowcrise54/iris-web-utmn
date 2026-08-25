/**
 * DFIR-IRIS Minimalist Navigation
 * 
 * Features:
 * - Simplified navigation (6 main sections)
 * - Global search (Cmd+K)
 * - Keyboard shortcuts (j/k navigation, ESC, etc.)
 * - Zen mode toggle
 * - Shortcuts modal
 */

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
      // Cmd+K / Ctrl+K - Global search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.openSearch();
      }
      
      // ESC - Close modals
      if (e.key === 'Escape') {
        this.closeAllModals();
      }
      
      // / - Shortcuts modal (only when not in input)
      if (e.key === '/' && !this.isInputFocused()) {
        e.preventDefault();
        this.openShortcuts();
      }
      
      // j/k - Navigate list (when on alerts/cases page)
      if ((e.key === 'j' || e.key === 'k') && !this.isInputFocused()) {
        this.handleListNavigation(e.key);
      }
    });
  }

  initSearch() {
    // Create search modal HTML
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
    
    // Bind search input
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
    // Implement search logic
    // Search alerts, cases, IOC, etc.
    const resultsContainer = this.searchModal.querySelector('.search-results');
    
    if (query.length < 2) {
      resultsContainer.innerHTML = '';
      return;
    }
    
    // Placeholder for actual search implementation
    // This would query the backend for matching results
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
            <div class="shortcut-item">
              <kbd>Cmd+K</kbd>
              <span>Global search</span>
            </div>
            <div class="shortcut-item">
              <kbd>j/k</kbd>
              <span>Navigate list</span>
            </div>
            <div class="shortcut-item">
              <kbd>ESC</kbd>
              <span>Close modal</span>
            </div>
            <div class="shortcut-item">
              <kbd>/</kbd>
              <span>Show shortcuts</span>
            </div>
            <div class="shortcut-item">
              <kbd>Cmd+.</kbd>
              <span>Zen mode</span>
            </div>
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
    // Add zen mode toggle button to navigation
    const minimalNav = document.querySelector('.minimal-nav');
    if (minimalNav) {
      const zenButton = document.createElement('button');
      zenButton.className = 'zen-mode-toggle btn-icon';
      zenButton.innerHTML = '◐';
      zenButton.title = 'Toggle Zen Mode (Cmd+.)';
      zenButton.setAttribute('aria-label', 'Toggle Zen Mode');
      zenButton.onclick = () => this.toggleZenMode();
      
      minimalNav.appendChild(zenButton);
    }
    
    // Bind Cmd+. hotkey
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '.') {
        e.preventDefault();
        this.toggleZenMode();
      }
    });
    
    // Restore zen mode from localStorage
    if (localStorage.getItem('zen-mode') === 'true') {
      this.enableZenMode();
    }
  }

  toggleZenMode() {
    const isZenMode = document.body.classList.toggle('zen-mode');
    localStorage.setItem('zen-mode', isZenMode);
    
    if (isZenMode) {
      this.enableZenMode();
    } else {
      this.disableZenMode();
    }
  }

  enableZenMode() {
    document.body.classList.add('zen-mode');
    // Hide sidebars
    const sidebars = document.querySelectorAll('.sidebar');
    sidebars.forEach(sidebar => {
      sidebar.style.display = 'none';
    });
  }

  disableZenMode() {
    document.body.classList.remove('zen-mode');
    // Show sidebars
    const sidebars = document.querySelectorAll('.sidebar');
    sidebars.forEach(sidebar => {
      sidebar.style.display = '';
    });
  }

  handleListNavigation(key) {
    // Find all navigable rows (alerts, cases, etc.)
    const rows = document.querySelectorAll('.alert-row:not(.selected), .case-row:not(.selected)');
    if (rows.length === 0) return;
    
    if (key === 'j') {
      // Move down
      this.currentFocusIndex = Math.min(this.currentFocusIndex + 1, rows.length - 1);
    } else {
      // Move up
      this.currentFocusIndex = Math.max(this.currentFocusIndex - 1, 0);
    }
    
    // Update selection
    rows.forEach((row, index) => {
      row.classList.toggle('selected', index === this.currentFocusIndex);
      
      // Scroll selected item into view if needed
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

// Initialize on DOM ready
const minimalistNav = new MinimalistNavigation();

// Export for window
window.minimalistNav = minimalistNav;
