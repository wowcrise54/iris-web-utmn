# DFIR-IRIS Minimalist UI/UX Enhancement Plan

> **Version:** 1.0  
> **Date:** 2026-08-25  
> **Status:** Planning Phase  
> **Estimated Duration:** 4-6 weeks

---

## 📋 Executive Summary

### Цель
Создать минималистичный, современный и интуитивно понятный интерфейс DFIR-IRIS, который:
- Уменьшает визуальный шум на 60%
- Ускоряет выполнение типовых задач на 40%
- Улучшает пользовательский опыт для новых и опытных аналитиков

### Ключевые принципы
1. **Less is More** - показывать только то, что нужно
2. **Context-Aware** - интерфейс адаптируется под задачу
3. **Fast & Responsive** - мгновенная реакция на действия
4. **Consistent** - единый стиль во всех модулях
5. **Accessible** - доступность для всех пользователей

---

## 📊 Анализ текущего состояния

### Проблемы текущего дизайна

| Проблема | Влияние | Приоритет |
|----------|---------|-----------|
| Перегруженный дашборд | Пользователи теряются в виджетах | 🔥 Высокий |
| Сложная навигация | 5+ кликов до нужной функции | 🔥 Высокий |
| Непоследовательные стили | Путаница между модулями | 🟡 Средний |
| Маленькие кнопки/текст | Усталость глаз, ошибки | 🟡 Средний |
| Медленная загрузка | 3-5 секунд до готовности | 🟢 Низкий |
| Нет адаптивности | Не работает на планшетах | 🟢 Низкий |

### Метрики успеха

| Метрика | Текущее значение | Целевое значение |
|---------|------------------|------------------|
| Время до первого действия | 8 сек | < 3 сек |
| Кликов до создания алерта | 12 | < 6 |
| Время на обогащение IOC | 45 сек | < 20 сек |
| Скорость загрузки страниц | 3-5 сек | < 1 сек |
| Удовлетворённость (NPS) | ~30 | > 70 |

---

## 🎯 Фазы реализации

### Фаза 1: Foundation (Недели 1-2)

#### 1.1 Дизайн-система
- [ ] Создать token-based дизайн-систему
- [ ] Определить цветовую палитру (минималистичная, 6 основных цветов)
- [ ] Определить типографику (1 шрифт, 3 размера)
- [ ] Определить spacing scale (4px base unit)
- [ ] Создать библиотеку компонентов (buttons, cards, inputs)

**Deliverables:**
- `docs/design-system.md`
- `source/app/static/assets/css/design-tokens.css`
- Figma/Sketch библиотека компонентов

#### 1.2 Базовая CSS-архитектура
```css
/* Пример структуры */
:root {
  /* Colors */
  --color-primary: #2563eb;
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  --color-surface: #ffffff;
  --color-background: #f8fafc;
  
  /* Typography */
  --font-family: 'Inter', system-ui, sans-serif;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  
  /* Spacing */
  --space-xs: 0.25rem;  /* 4px */
  --space-sm: 0.5rem;   /* 8px */
  --space-md: 1rem;     /* 16px */
  --space-lg: 1.5rem;   /* 24px */
  --space-xl: 2rem;     /* 32px */
  
  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
  
  /* Border Radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
}
```

**Deliverables:**
- `source/app/static/assets/css/design-tokens.css`
- `source/app/static/assets/css/minimalist-base.css`

#### 1.3 Typography & Layout
- [ ] Установить Inter как основной шрифт
- [ ] Определить hierarchy заголовков (H1-H6)
- [ ] Создать grid system (12-col, max-width 1440px)
- [ ] Определить контейнеры для контента

**Deliverables:**
- Обновлённые шаблоны с новой типографикой
- Responsive breakpoints (mobile: 320px, tablet: 768px, desktop: 1024px)

---

### Фаза 2: Core Components (Недели 2-3)

#### 2.1 Navigation
**Текущее состояние:**
- 3 sidebar'а (основной, quick, datastore)
- 15+ пунктов меню
- Многоуровневая вложенность

**Новый дизайн:**
```
┌─────────────────────────────────────────────────┐
│  🔍 Search  │  📁 Cases  │  ⚠️ Alerts  │  👤 User  │
├─────────────────────────────────────────────────┤
│                                                 │
│           Main Content Area                     │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Изменения:**
- [ ] Упростить навигацию до 6 основных разделов
- [ ] Добавить глобальный поиск (Cmd+K)
- [ ] Скрыть второстепенное меню (открывается по требованию)
- [ ] Добавить breadcrumbs для глубокой навигации

**Deliverables:**
- `source/app/templates/includes/navigation-minimal.html`
- `source/app/static/assets/js/navigation.js`
- Hotkey support (Cmd+K, Cmd+E, Cmd+N)

#### 2.2 Cards & Containers
**Текущее состояние:**
- Тени, границы, фоны - слишком много визуального шума
- Непоследовательные отступы

**Новый дизайн:**
```html
<!-- Minimal Card -->
<div class="card">
  <div class="card-header">
    <h3>Alert Title</h3>
    <span class="badge">High Severity</span>
  </div>
  <div class="card-body">
    <p>Concise description...</p>
  </div>
  <div class="card-actions">
    <button class="btn-primary">Open</button>
    <button class="btn-secondary">Enrich</button>
  </div>
</div>
```

**Изменения:**
- [ ] Убрать границы (только тени)
- [ ] Уменьшить padding на 30%
- [ ] Использовать whitespace вместо разделителей
- [ ] Контекстные действия (appear on hover)

**Deliverables:**
- `source/app/static/assets/css/cards.css`
- Обновлённые компоненты: AlertCard, CaseCard, IOCCard

#### 2.3 Tables & Lists
**Текущее состояние:**
- Много колонок по умолчанию
- Маленький текст
- Нет группировки

**Новый дизайн:**
```
┌──────────────────────────────────────────────────────┐
│  ⚠️ Alerts                           [+ New Alert]   │
├──────────────────────────────────────────────────────┤
│  Status │ Title           │ IOC    │ Age    │ Actions│
├──────────────────────────────────────────────────────┤
│  🟢 New │ Malicious IP    │ 2      │ 5 min  │ [Open] │
│  🟡 In  │ Suspicious File │ 5      │ 1 hour │ [Open] │
│  🔵 Done│ Phishing Email  │ 3      │ 2 days │ [View] │
└──────────────────────────────────────────────────────┘
```

**Изменения:**
- [ ] Показывать только 5 ключевых колонок
- [ ] Кнопка "Customize columns" для остальных
- [ ] Group by status (expandable)
- [ ] Bulk actions checkbox
- [ ] Infinite scroll вместо pagination

**Deliverables:**
- `source/app/static/assets/css/tables.css`
- `source/app/static/assets/js/table-enhancements.js`
- Column customization modal

#### 2.4 Forms & Inputs
**Текущее состояние:**
- Большие отступы
- Много полей сразу
- Нет умных подсказок

**Новый дизайн:**
```html
<!-- Smart IOC Input -->
<div class="input-group">
  <input type="text" 
         class="smart-input"
         placeholder="Paste IOC (IP, domain, hash...)"
         data-auto-detect="true">
  <span class="detected-type">🔍 Detected: IPv4 Address</span>
</div>
```

**Изменения:**
- [ ] Умный ввод с автоопределением типа
- [ ] Progressive disclosure (показывать поля по мере необходимости)
- [ ] Inline validation
- [ ] Автозаполнение из истории

**Deliverables:**
- `source/app/static/assets/css/forms.css`
- `source/app/static/assets/js/smart-input.js`
- IOC type detector

---

### Фаза 3: Key Pages Redesign (Недели 3-4)

#### 3.1 Dashboard
**Текущее состояние:**
- 10+ виджетов
- Много графиков
- Перегружено информацией

**Новый дизайн:**
```
┌─────────────────────────────────────────────────────┐
│  Good morning, [User]                    [🌙 Zen]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   🔴 12     │  │   🟡 8      │  │   🟢 45     │  │
│  │   New       │  │   In Prog   │  │   Closed    │  │
│  │   Alerts    │  │   Cases     │  │   Today     │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │  Recent Alerts                               │  │
│  │  ┌──────────────────────────────────────┐   │  │
│  │  │ ⚠️ Malicious IP • 5 min ago    [→]   │   │  │
│  │  │ ⚠️ Suspicious File • 12 min ago [→]  │   │  │
│  │  └──────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  [+ Create New Investigation]                       │
└─────────────────────────────────────────────────────┘
```

**Изменения:**
- [ ] Максимум 3 KPI на дашборде
- [ ] Один скроллящийся список recent items
- [ ] Одна primary action button
- [ ] Zen mode toggle

**Deliverables:**
- `source/app/templates/dashboard-minimal.html`
- `source/app/static/assets/js/dashboard-widgets.js`

#### 3.2 Alerts List
**Текущее состояние:**
- 20+ колонок таблицы
- Сложные фильтры
- Медленная загрузка

**Новый дизайн:**
```
┌─────────────────────────────────────────────────────┐
│  Alerts                              [+ New Alert]  │
│  ┌─────────────────────────────────────────────┐   │
│  │ 🔍 Search alerts...          [Filters ▼]   │   │
│  └─────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  ☐ [New] Malicious IP detected • 185.220.101.1    → │
│  ☐ [New] Suspicious file hash • xyz123...       → │
│  ☐ [In Progress] Phishing campaign • 3 IOC      → │
│  ☐ [Closed] False positive • resolved           → │
└─────────────────────────────────────────────────────┘
```

**Изменения:**
- [ ] Single-column layout (только главное)
- [ ] Expandable rows для деталей
- [ ] Quick actions при наведении
- [ ] Keyboard navigation (j/k для навигации)

**Deliverables:**
- `source/app/templates/alerts-minimal.html`
- `source/app/static/assets/js/alerts-list.js`

#### 3.3 Alert Detail
**Текущее состояние:**
- 10+ секций
- Много табов
- Сложная навигация

**Новый дизайн:**
```
┌─────────────────────────────────────────────────────┐
│  ← Back  │  Alert #123  │  [Enrich]  [Close]  [⋮]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Malicious IP Detected              🔴 High        │
│  Created 5 min ago by system                       │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ IOC: 185.220.101.1                         │   │
│  │ Type: IPv4 Address    Risk: Malicious     │   │
│  │ OpenCTI: ⚠️ Found 3 related indicators    │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  Timeline:                                         │
│  • 10:00 - Alert created                          │
│  • 10:05 - IOC enriched (OpenCTI)                 │
│  • 10:10 - Added to case #456                     │
│                                                     │
│  [Add Note] [Add IOC] [Create Case]               │
└─────────────────────────────────────────────────────┘
```

**Изменения:**
- [ ] Single-page layout (без табов)
- [ ] Sticky header с основными действиями
- [ ] Timeline вместо истории
- [ ] Contextual actions

**Deliverables:**
- `source/app/templates/alert-detail-minimal.html`
- `source/app/static/assets/js/alert-detail.js`

#### 3.4 Cases
**Текущее состояние:**
- Сложная структура
- Много информации сразу

**Новый дизайн:**
```
┌─────────────────────────────────────────────────────┐
│  Cases                               [+ New Case]   │
├─────────────────────────────────────────────────────┤
│  Active                    Archived                 │
│  ┌────────────┐  ┌────────────┐                    │
│  │ Case #456  │  │ Case #445  │                    │
│  │ Phishing   │  │ Malware    │                    │
│  │ 3 alerts   │  │ 8 alerts   │                    │
│  │ In Progress│  │ Closed     │                    │
│  └────────────┘  └────────────┘                    │
└─────────────────────────────────────────────────────┘
```

**Изменения:**
- [ ] Card-based layout вместо таблицы
- [ ] Tabs для Active/Archived
- [ ] Quick stats на карточке
- [ ] Drag & drop для сортировки

**Deliverables:**
- `source/app/templates/cases-minimal.html`
- `source/app/static/assets/js/cases-grid.js`

---

### Фаза 4: Advanced Features (Недели 4-5)

#### 4.1 Zen Mode
**Описание:** Максимально упрощённый интерфейс для фокусной работы

**Функции:**
- [ ] Скрыть все панели (sidebar, footer, header)
- [ ] Только рабочая область
- [ ] Минимальная навигация (ESC для выхода)
- [ ] Тёмная тема по умолчанию
- [ ] Увеличенный текст

**Hotkey:** `Cmd + .` (точка)

**Deliverables:**
- `source/app/static/assets/css/zen-mode.css`
- `source/app/static/assets/js/zen-mode.js`

#### 4.2 Smart Search
**Описание:** Глобальный поиск с естественным языком

**Примеры:**
```
"alerts with high severity from last week"
"cases with malicious IPs"
"IOC 185.220.101.1"
```

**Функции:**
- [ ] Cmd+K для открытия
- [ ] Natural language parsing
- [ ] Recent searches
- [ ] Search history

**Deliverables:**
- `source/app/static/assets/js/smart-search.js`
- `source/app/blueprints/search_routes.py`

#### 4.3 Keyboard Shortcuts
**Описание:** Полная поддержка keyboard-only workflow

**Основные hotkeys:**
```
Cmd + K    Global search
Cmd + N    New alert
Cmd + E    Enrich IOC
Cmd + C    New case
Cmd + /    Show shortcuts
j/k        Navigate list
Enter      Open selected
Esc        Close modal / Zen mode
```

**Deliverables:**
- `source/app/static/assets/js/keyboard-nav.js`
- `source/app/templates/shortcuts-modal.html`

#### 4.4 Performance Optimizations
**Описания:** Ускорение загрузки и взаимодействия

**Меры:**
- [ ] Lazy loading для изображений и таблиц
- [ ] Code splitting для JS
- [ ] CSS minification
- [ ] Service worker для caching
- [ ] WebP изображения

**Целевые метрики:**
- First Contentful Paint: < 1s
- Time to Interactive: < 2s
- Total Bundle Size: < 500KB

**Deliverables:**
- webpack.config.js с code splitting
- Service worker для PWA
- Lighthouse score > 90

---

### Фаза 5: Testing & Iteration (Недели 5-6)

#### 5.1 User Testing
**Методы:**
- [ ] A/B тестирование (старый vs новый дизайн)
- [ ] Usability testing с 5-10 пользователями
- [ ] Heatmaps (Hotjar или аналоги)
- [ ] Session recordings

**Метрики:**
- Task completion rate
- Time on task
- Error rate
- Satisfaction score (SUS)

#### 5.2 Automated Testing
**Test Coverage:**
- [ ] Visual regression testing (Percy/Chromatic)
- [ ] E2E тесты для ключевых workflows
- [ ] Accessibility testing (axe-core)
- [ ] Performance testing (Lighthouse CI)

**Deliverables:**
- `tests/e2e/minimal-ui.spec.js`
- `tests/visual/minimal-ui.spec.js`
- Accessibility audit report

#### 5.3 Feedback Loop
**Механизмы:**
- [ ] In-app feedback widget
- [ ] NPS surveys после ключевых действий
- [ ] Feature usage analytics
- [ ] Bug report form

**Deliverables:**
- `source/app/static/assets/js/feedback-widget.js`
- Dashboard для анализа фидбека

---

## 📅 Timeline & Milestones

| Фаза | Недели | Основные вехи | Критерии готовности |
|------|--------|---------------|---------------------|
| **Foundation** | 1-2 | Дизайн-система, базовый CSS | Все токены определены |
| **Components** | 2-3 | Navigation, Cards, Tables, Forms | 10+ компонентов готовы |
| **Pages** | 3-4 | Dashboard, Alerts, Cases | 4 ключевые страницы |
| **Advanced** | 4-5 | Zen Mode, Search, Shortcuts | Все features работают |
| **Testing** | 5-6 | Testing, оптимизация | 90%+ тестов пройдено |

---

## 🎯 Критерии успеха

### Функциональные
- [ ] Все существующие функции работают в новом дизайне
- [ ] Нет регрессий в функциональности
- [ ] Backward compatible с кастомными темами

### Производительность
- [ ] Lighthouse score > 90 (Performance, Accessibility, Best Practices, SEO)
- [ ] First Contentful Paint < 1s
- [ ] Time to Interactive < 2s
- [ ] Bundle size < 500KB (gzipped)

### Пользовательский опыт
- [ ] SUS score > 80
- [ ] Task completion rate > 95%
- [ ] Time on task уменьшился на 30%+
- [ ] NPS > 70

### Технические
- [ ] 100% покрытие тестами ключевых компонентов
- [ ] 0 critical/accessibility issues
- [ ] Полная документация
- [ ] CI/CD pipeline настроен

---

## 📁 Структура файлов

```
source/app/static/assets/
├── css/
│   ├── design-tokens.css          # CSS переменные
│   ├── minimalist-base.css        # Базовые стили
│   ├── minimalist-components.css  # Компоненты
│   ├── minimalist-pages.css       # Страницы
│   ├── zen-mode.css               # Zen mode
│   └── modern-ui-enhancements.css # (существующий, обновить)
├── js/
│   ├── navigation.js              # Упрощённая навигация
│   ├── smart-search.js            # Глобальный поиск
│   ├── keyboard-nav.js            # Hotkeys
│   ├── zen-mode.js                # Zen mode logic
│   ├── smart-input.js             # Умный ввод
│   └── feedback-widget.js         # Фидбек
└── img/
    └── (оптимизированные изображения)

source/app/templates/
├── includes/
│   ├── navigation-minimal.html    # Новая навигация
│   └── footer-minimal.html        # Упрощённый footer
├── dashboard-minimal.html         # Новый дашборд
├── alerts-minimal.html            # Новый список алертов
├── alert-detail-minimal.html      # Детали алерта
└── cases-minimal.html             # Cases grid

docs/
├── DESIGN_SYSTEM.md               # Полная документация
├── MINIMALIST_GUIDE.md            # Руководство по стилю
└── ACCESSIBILITY_REPORT.md        # Accessibility audit
```

---

## 🚀 План внедрения

### Week 1: Setup & Foundation
- Day 1-2: Создать дизайн-систему и токены
- Day 3-4: Базовая CSS архитектура
- Day 5: Typography и layout

### Week 2: Core Components
- Day 1-2: Navigation redesign
- Day 3-4: Cards & containers
- Day 5: Tables & lists

### Week 3: Forms & Key Pages
- Day 1-2: Forms & inputs
- Day 3-4: Dashboard redesign
- Day 5: Alerts list redesign

### Week 4: Advanced Pages
- Day 1-2: Alert detail page
- Day 3-4: Cases redesign
- Day 5: Integration & testing

### Week 5: Advanced Features
- Day 1-2: Zen mode
- Day 3-4: Smart search & hotkeys
- Day 5: Performance optimizations

### Week 6: Testing & Polish
- Day 1-2: User testing
- Day 3-4: Bug fixes & refinements
- Day 5: Documentation & deployment

---

## 📊 Ресурсы & Команда

### Необходимые роли
- **UI/UX Designer** - дизайн-система, прототипы
- **Frontend Developer** - HTML/CSS/JS реализация
- **QA Engineer** - тестирование, accessibility
- **Product Owner** - приоритизация, фидбек

### Инструменты
- **Design:** Figma/Sketch
- **Development:** VS Code, Git
- **Testing:** Playwright, Lighthouse, axe-core
- **Analytics:** Plausible/Google Analytics
- **Feedback:** Hotjar, Typeform

---

## ⚠️ Риски & Митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Сопротивление пользователей | Средняя | Высокое | A/B тестирование, фидбек |
| Регрессия функциональности | Низкая | Высокое | Полное тестирование |
| Превышение сроков | Средняя | Средняя | Приоритизация MVP |
| Проблемы с производительностью | Низкая | Средняя | Performance budget |
| Accessibility issues | Средняя | Высокое | Раннее тестирование |

---

## 📝 Следующие шаги

1. **Утвердить план** - обсудить с командой
2. **Создать прототип** - Figma для валидации
3. **Начать Фаза 1** - дизайн-система
4. **Еженедельные демо** - показывать прогресс
5. **Собирать фидбек** - итеративное улучшение

---

## 🎨 Визуальные примеры

### Текущий vs Минималистичный

**Current Dashboard:**
```
[Too many widgets] [Complex charts] [Multiple panels]
```

**Minimal Dashboard:**
```
[3 KPIs] [Recent items] [One primary action]
```

**Current Alert Card:**
```
┌────────────────────────────────────┐
│ Title | Status | Severity | Tags   │
│ Description (3 lines)              │
│ IOC Count | Created | Owner        │
│ [View] [Edit] [Delete] [Share]     │
│ [More Actions ▼]                   │
└────────────────────────────────────┘
```

**Minimal Alert Card:**
```
┌────────────────────────────────────┐
│ ⚠️ Malicious IP        🔴 High    │
│ 185.220.101.1 • 5 min ago         │
│ [Open] [Enrich]                    │
└────────────────────────────────────┘
```

---

**Plan approved by:** _________________  
**Date:** _________________  
**Next review:** _________________
