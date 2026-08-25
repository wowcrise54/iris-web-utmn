/**
 * DFIR-IRIS Keyboard Navigation
 * 
 * Global keyboard shortcuts for efficient workflow
 * - j/k: Navigate lists
 * - Enter: Open selected item
 * - ESC: Close modals
 * - /: Show shortcuts
 * - Cmd+B: Toggle sidebar
 * - Cmd+Shift+N: New alert
 */

class KeyboardNavigation {
  constructor() {
    this.currentFocusIndex = -1;
    this.currentList = null;
    this.init();
  }

  init() {
    this.bindGlobalShortcuts();
    this.initListNavigation();
    // Enhance existing shortcuts modal or create new one
    setTimeout(() => this.enhanceShortcutsModal(), 100);
  }

  bindGlobalShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ignore if typing in input/textarea
      if (this.isInputFocused() && e.key !== 'Escape') return;

      // ESC - Close all modals
      if (e.key === 'Escape') {
        this.closeAllModals();
        return;
      }

      // / - Show shortcuts (not in input)
      if (e.key === '/') {
        e.preventDefault();
        this.toggleShortcutsModal();
        return;
      }

      // Cmd+B / Ctrl+B - Toggle sidebar
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        this.toggleSidebar();
        return;
      }

      // Cmd+Shift+N / Ctrl+Shift+N - New alert
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'N') {
        e.preventDefault();
        window.location.href = '/alerts/new';
        return;
      }
    });
  }

  initListNavigation() {
    // Bind j/k navigation for alert/case lists
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

    // Remove previous selection
    if (this.currentFocusIndex >= 0 && this.currentFocusIndex < rows.length) {
      rows[this.currentFocusIndex].classList.remove('selected');
    }

    // Calculate new index
    this.currentFocusIndex += direction;
    this.currentFocusIndex = Math.max(0, Math.min(this.currentFocusIndex, rows.length - 1));

    // Add new selection
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
    // Close search modal
    const searchModal = document.querySelector('.search-modal');
    if (searchModal) searchModal.style.display = 'none';

    // Close shortcuts modal
    const shortcutsModal = document.querySelector('.shortcuts-modal');
    if (shortcutsModal) shortcutsModal.style.display = 'none';

    // Close any other modals
    document.querySelectorAll('.modal[style*="display: block"]').forEach(modal => {
      modal.style.display = 'none';
    });
  }

  toggleShortcutsModal() {
    let modal = document.querySelector('.shortcuts-modal');
    
    if (!modal) {
      modal = this.createShortcutsModal();
    } else {
      // Modal already exists (created by minimalist-nav.js), just toggle it
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
    // If modal exists (from minimalist-nav.js), add our additional shortcuts
    const modal = document.querySelector('.shortcuts-modal');
    if (!modal) return;
    
    const shortcutsList = modal.querySelector('.shortcuts-list');
    if (!shortcutsList) return;
    
    // Add keyboard-nav specific shortcuts
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

// Initialize on DOM ready
const keyboardNav = new KeyboardNavigation();

// Export for window
window.keyboardNav = keyboardNav;
