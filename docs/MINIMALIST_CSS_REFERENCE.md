# Minimalist CSS Reference

## Design Tokens

### Colors

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary-600` | #2563eb | Primary actions |
| `--color-primary-700` | #1d4ed8 | Hover states |
| `--color-success-600` | #16a34a | Success states |
| `--color-warning-600` | #d97706 | Warnings |
| `--color-danger-600` | #dc2626 | Errors |
| `--color-neutral-50` | #fafafa | Backgrounds |
| `--color-neutral-900` | #171417 | Text |

### Typography

| Token | Value | Usage |
|-------|-------|-------|
| `--font-family` | Inter | Body text |
| `--text-sm` | 14px | Small text |
| `--text-base` | 16px | Body text |
| `--text-lg` | 18px | Large text |
| `--text-xl` | 20px | H4 |
| `--text-2xl` | 24px | H3 |
| `--text-3xl` | 30px | H2 |
| `--text-4xl` | 36px | H1 |

### Spacing

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Tight spacing |
| `--space-2` | 8px | Small spacing |
| `--space-3` | 12px | Medium spacing |
| `--space-4` | 16px | Base spacing |
| `--space-6` | 24px | Large spacing |
| `--space-8` | 32px | XL spacing |

### Components

#### Buttons
```css
.btn-primary {
  background-color: var(--color-primary-600);
  color: white;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
}
```

#### Cards
```css
.card {
  background-color: var(--card-background);
  border-radius: var(--card-border-radius);
  box-shadow: var(--card-shadow);
  padding: var(--card-padding);
}
```

#### Inputs
```css
.smart-input {
  width: 100%;
  padding: var(--input-padding-y) var(--input-padding-x);
  border: 1px solid var(--color-border);
  border-radius: var(--input-border-radius);
}
```

## Responsive Breakpoints

| Breakpoint | Width | Usage |
|------------|-------|-------|
| Mobile | 320px - 767px | Default |
| Tablet | 768px+ | `@media (min-width: 768px)` |
| Desktop | 1024px+ | `@media (min-width: 1024px)` |
| Large | 1280px+ | `@media (min-width: 1280px)` |

## Utility Classes

### Spacing
- `m-1` to `m-12` - Margin
- `p-1` to `p-12` - Padding
- `mt-*`, `mb-*`, `ml-*`, `mr-*` - Directional

### Display
- `block`, `inline`, `inline-block`
- `flex`, `grid`
- `hidden`

### Text
- `text-center`, `text-left`, `text-right`
- `font-bold`, `font-medium`, `font-normal`
- `text-sm`, `text-base`, `text-lg`

### Colors
- `text-primary`, `text-success`, `text-warning`, `text-danger`
- `bg-primary`, `bg-success`, `bg-warning`, `bg-danger`

## Files

| File | Size | Purpose |
|------|------|---------|
| `design-tokens.css` | ~10KB | Design tokens |
| `minimalist-base.css` | ~21KB | Base styles |
| `minimalist-components.css` | ~11KB | Components |
| `zen-mode.css` | ~5KB | Zen mode |
| **Total** | **~47KB** | Full minimalist UI |
