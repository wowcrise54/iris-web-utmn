# DFIR-IRIS Modern UI Enhancements - Testing Guide

## Overview
This guide describes how to test the modern UI enhancements for DFIR-IRIS, including:
- Enhanced alert status badges with gradients
- Glassmorphism card effects
- Improved severity indicators
- Modern IOC badges and tags
- Updated button styling

## Prerequisites

### Option 1: Playwright (Recommended for automated testing)
```bash
# Install Playwright
pip install playwright
playwright install

# Run tests
python test_modern_ui.py
```

### Option 2: Manual verification
```bash
# Run visual verification guide
python verify_modern_ui.py
```

## Features to Test

### 1. Status Badges
**Location:** Alerts page, Case page
**Expected:**
- New alerts: Blue gradient (#3B82F6 → #2563EB)
- Open alerts: Orange gradient (#F59E0B → #D97706)
- Closed alerts: Green gradient (#10B981 → #059669)
- Critical alerts: Red gradient with pulsing animation

**Test steps:**
1. Navigate to `/alerts`
2. Check status badges on alert cards
3. Verify gradient backgrounds
4. Check for pulsing animation on critical alerts

### 2. Glassmorphism Cards
**Location:** Dashboard, Alerts, Cases
**Expected:**
- Backdrop blur effect (12px)
- Rounded corners (16px)
- Subtle white border (rgba(255,255,255,0.08))
- Hover effect with translateY(-2px)

**Test steps:**
1. Navigate to `/dashboard`
2. Inspect card elements
3. Check `backdrop-filter` CSS property
4. Hover over cards to verify animation

### 3. Severity Indicators
**Location:** Alert cards, IOCs table
**Expected:**
- Low: Green gradient
- Medium: Yellow gradient
- High: Orange gradient
- Critical: Red gradient with pulse

**Test steps:**
1. Navigate to `/alerts`
2. Check severity badges on alert cards
3. Verify distinct colors for each level

### 4. IOC Badges
**Location:** Alert details page
**Expected:**
- IP badges: Blue tint
- Domain badges: Green tint
- Hash badges: Purple tint
- URL badges: Orange tint

**Test steps:**
1. Open an alert with IOCs (e.g., `/alerts/2`)
2. Check IOC badge styling
3. Verify color coding by type

### 5. Tags
**Location:** Alert cards, Alert details
**Expected:**
- Subtle background (rgba(255,255,255,0.08))
- Hover effect with background change
- OpenCTI tags: Pink gradient

**Test steps:**
1. Navigate to `/alerts`
2. Check tag styling on alert cards
3. Hover over tags to verify hover effect
4. Check OpenCTI tags for special styling

### 6. Buttons
**Location:** Throughout the application
**Expected:**
- Primary buttons: Blue gradient with shadow
- Secondary buttons: Semi-transparent background
- Hover effects with translateY animation

**Test steps:**
1. Navigate to any page with action buttons
2. Check button styling
3. Hover over buttons to verify animations

## Automated Tests (Playwright)

### Test File: `test_modern_ui.py`

The Playwright test suite includes:
- `test_status_badges()` - Verifies status badge styling
- `test_glassmorphism_cards()` - Checks card effects
- `test_severity_indicators()` - Tests severity colors
- `test_ioc_badges()` - Validates IOC badge styling
- `test_tags()` - Checks tag styling
- `test_buttons()` - Verifies button effects

### Running Tests

```bash
# Install dependencies
pip install playwright
playwright install chromium

# Run tests
python test_modern_ui.py
```

### Test Output Example
```
============================================================
DFIR-IRIS Modern UI Enhancements - Playwright Tests
============================================================
[*] Navigating to login page...
[+] Login successful!

[*] Testing status badges...
[+] Found 5 status badges
    Badge 1: linear-gradient(135deg, rgb(59, 130, 246)...
    Badge 2: linear-gradient(135deg, rgb(245, 158, 11)...
    Badge 3: linear-gradient(135deg, rgb(16, 185, 129)...

[*] Testing glassmorphism cards...
[+] Found 8 cards
    Backdrop filter: blur(12px) saturate(180%)
    Border radius: 16px
[+] Glassmorphism effects detected!

...

============================================================
All tests completed!
============================================================
```

## Manual Verification

### Quick Checklist
- [ ] Status badges have gradient backgrounds
- [ ] Cards have blur effect on background
- [ ] Cards have 16px rounded corners
- [ ] Severity badges have distinct colors
- [ ] Critical alerts pulse
- [ ] IOC badges are color-coded
- [ ] Tags have subtle background
- [ ] OpenCTI tags have pink gradient
- [ ] Buttons have gradient and shadow
- [ ] Hover effects work smoothly

### CSS Inspection
Use browser DevTools to verify:
```css
/* Card should have */
background: rgba(32, 41, 64, 0.7);
backdrop-filter: blur(12px) saturate(180%);
border-radius: 16px;
border: 1px solid rgba(255, 255, 255, 0.08);

/* Status badge should have */
background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);
box-shadow: 0 2px 8px rgba(59, 130, 246, 0.35);
```

## Troubleshooting

### Styles not applying
1. Clear browser cache (Ctrl+Shift+R)
2. Verify dark theme is enabled in user settings
3. Check browser console for CSS errors
4. Verify `modern-ui-enhancements.css` is loaded

### Glassmorphism not working
- Requires browser support for `backdrop-filter`
- Modern browsers: Chrome 76+, Firefox 103+, Safari 9+
- Fallback: Solid background without blur

### Animations not smooth
- Check browser hardware acceleration
- Reduce CSS complexity if needed
- Test on different devices

## Adding New Tests

For each new feature, create a test function in `test_modern_ui.py`:

```python
async def test_new_feature(page: Page):
    """Test new feature description"""
    print("\n[*] Testing new feature...")
    
    # Navigate to relevant page
    await page.goto(f"{BASE_URL}/page", wait_until="networkidle")
    
    # Check for elements
    elements = page.locator('.your-css-selector')
    count = await elements.count()
    
    if count > 0:
        print(f"[+] Found {count} elements")
        # Add specific checks
        style = await elements.first.evaluate("el => window.getComputedStyle(el).background")
        print(f"    Style: {style}")
    else:
        print("[!] Elements not found")
```

Then add the test to `run_tests()`:
```python
async def run_tests():
    # ... existing tests ...
    await test_new_feature(page)
```

## Maintenance

### Updating Colors
Edit `modern-ui-enhancements.css` and update:
- Gradient colors in status badges
- Shadow values
- Border radius

### Adding New Status Types
1. Add CSS class in `modern-ui-enhancements.css`
2. Add test in `test_modern_ui.py`
3. Update this README

## Contributing

When adding new UI features:
1. Create CSS in `modern-ui-enhancements.css`
2. Create test in `test_modern_ui.py`
3. Update this README
4. Run tests to verify

---

**Last updated:** 2026-08-25
**Version:** 1.0
**Author:** DFIR-IRIS Team
