/**
 * DFIR-IRIS Zen Mode
 * 
 * Full-screen focus mode for distraction-free work
 * - Toggle via button or Cmd+. hotkey
 * - Persists across pages via localStorage
 * - ESC to exit
 */

class ZenMode {
  constructor() {
    this.isActive = false;
    this.init();
  }

  init() {
    // Check localStorage for saved preference
    this.isActive = localStorage.getItem('zen-mode') === 'true';
    
    if (this.isActive) {
      this.enable();
    }

    // Bind hotkey
    document.addEventListener('keydown', (e) => {
      // Cmd+. or Ctrl+.
      if ((e.metaKey || e.ctrlKey) && e.key === '.') {
        e.preventDefault();
        this.toggle();
      }
      
      // ESC to exit
      if (e.key === 'Escape' && this.isActive) {
        this.disable();
      }
    });

    // Add exit hint
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
    
    // Show indicator
    this.showIndicator();
    
    // Dispatch custom event
    document.dispatchEvent(new CustomEvent('zenMode:enabled'));
  }

  disable() {
    this.isActive = false;
    document.body.classList.remove('zen-mode');
    localStorage.setItem('zen-mode', 'false');
    
    // Hide indicator
    this.hideIndicator();
    
    // Dispatch custom event
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

// Initialize on DOM ready
const zenMode = new ZenMode();

// Export for window
window.zenMode = zenMode;

// Integrate with minimalist-nav
if (typeof minimalistNav !== 'undefined') {
  minimalistNav.toggleZenMode = () => zenMode.toggle();
}
