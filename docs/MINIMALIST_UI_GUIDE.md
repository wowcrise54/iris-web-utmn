# DFIR-IRIS Minimalist UI User Guide

## Overview

The Minimalist UI mode provides a clean, distraction-free interface for DFIR-IRIS analysts. Designed for focused incident response work, it removes visual clutter while maintaining full functionality.

## Enabling Minimalist UI

1. Go to User Settings
2. Check "Enable Minimalist UI"
3. Refresh the page

## Features

### 1. Simplified Navigation
- 6 main sections: Dashboard, Alerts, Cases, Customers, Modules, Admin
- Clean icons and labels
- No visual clutter

### 2. Global Search (Cmd+K)
- Press `Cmd+K` (Mac) or `Ctrl+K` (Windows)
- Type to search alerts, cases, IOC
- Use `j/k` to navigate results
- Press `Enter` to open

### 3. Keyboard Shortcuts

| Hotkey | Action |
|--------|--------|
| Cmd+K / Ctrl+K | Global search |
| j / k | Navigate list |
| Enter | Open selected |
| ESC | Close modal |
| / | Show shortcuts |
| Cmd+B / Ctrl+B | Toggle sidebar |
| Cmd+Shift+N | New alert |
| Cmd+. | Zen mode |

### 4. Smart IOC Input
- Paste any IOC (IP, domain, URL, hash)
- Auto-detection shows type instantly
- Supports: IPv4, IPv6, Domain, URL, MD5, SHA1, SHA256, Email, MAC

### 5. Zen Mode
- Press `Cmd+.` to toggle
- Hides all sidebars
- Maximizes content area
- Dark mode for focus
- Press `ESC` to exit

### 6. Dashboard
- 3 KPI cards: New Alerts, In Progress Cases, Closed Today
- Recent alerts list
- Quick "Create Investigation" button

## Customization

### CSS Custom Properties

All minimalist styles use CSS variables:

```css
--color-primary-600: #2563eb;
--color-success-600: #16a34a;
--color-warning-600: #d97706;
--color-danger-600: #dc2626;
--font-family: 'Inter', sans-serif;
--space-4: 16px;
--radius-md: 8px;
```

### Disabling Minimalist UI
1. Go to User Settings
2. Uncheck "Enable Minimalist UI"
3. Refresh the page

## Troubleshooting

### Issue: Minimalist UI not loading
**Solution:** Clear browser cache and reload

### Issue: Keyboard shortcuts not working
**Solution:** Make sure focus is not in an input field

### Issue: Zen mode stuck
**Solution:** Press `ESC` or refresh page

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Accessibility

- WCAG 2.1 AA compliant
- Full keyboard navigation
- Screen reader compatible
- Skip links for navigation
- ARIA labels on all interactive elements

## Feedback

Report issues or suggestions to: [project email/issue tracker]
