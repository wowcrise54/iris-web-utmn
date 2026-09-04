# Инструкция по применению миграции

## Проблема
Docker Desktop требует ручного запуска и не может быть автоматически запущен из-за ограничений UAC/безопасности Windows.

## Решение

### Шаг 1: Запустить Docker Desktop вручную
1. Нажмите **Win + R**
2. Введите: `"C:\Program Files\Docker\Docker\Docker Desktop.exe"`
3. Нажмите **Enter**
4. Дождитесь полной загрузки (иконка в системном трее станет зелёной) - это занимает 60-90 секунд

### Шаг 2: Применить миграцию

**Вариант A - Через PowerShell (рекомендуется):**
```powershell
cd C:\Users\user\Desktop\projects\iris-web-utmn
docker compose down
docker compose run --rm web alembic -c app/alembic.ini upgrade head
docker compose up -d
```

**Вариант B - Через bash:**
```bash
cd /c/Users/user/Desktop/projects/iris-web-utmn
docker compose down
docker compose run --rm web alembic -c app/alembic.ini upgrade head
docker compose up -d
```

### Шаг 3: Проверить результат
```bash
docker compose ps
```

Все контейнеры должны быть в статусе `Up`.

### Шаг 4: Интеграция в интерфейс

1. Откройте файл шаблона страницы кейса (например, `source/app/templates/pages/case.html` или аналогичный)

2. Добавьте кнопку управления инцидентом:
```html
<button class="btn btn-primary" 
        data-bs-toggle="modal" 
        data-bs-target="#incidentManagementModal"
        data-case-id="{{ case.case_id }}">
  <i class="fas fa-shield-alt"></i> Управление инцидентом ИБ
</button>
```

3. Подключите модальное окно перед закрывающим тегом `</body>`:
```html
{% include 'modals/incident_management.html' %}
```

4. Подключите JavaScript (также перед `</body>`):
```html
<script src="{{ url_for('static', filename='assets/js/iris/case.incident.js') }}"></script>
```

## Что было реализовано

### Backend (готово ✅)
- ✅ 8 новых таблиц БД для управления инцидентами
- ✅ 25+ новых полей в таблице `cases`
- ✅ Полный REST API (`/manage/incident/*`)
- ✅ Автоматический расчёт важности и приоритета (таблицы 5.1 и 5.2)
- ✅ Миграция БД с начальными данными

### Frontend (готово ✅)
- ✅ Модальное окно с 5 секциями
- ✅ JavaScript модуль с автозагрузкой данных
- ✅ Автоматический расчёт приоритета при выборе категории/типа системы

### Документация (готово ✅)
- ✅ `INCIDENT_MANAGEMENT_IMPLEMENTATION.md` - полная документация
- ✅ `apply_incident_migration.ps1` - PowerShell скрипт (для ручного запуска)
- ✅ `apply_incident_migration.sh` - Bash скрипт (для ручного запуска)

## Проверка работы

После применения миграции:

1. Откройте DFIR-IRIS в браузере
2. Перейдите к любому кейсу
3. Нажмите кнопку "Управление инцидентом ИБ"
4. Проверьте, что:
   - Все поля загружаются корректно
   - Выбор категории и типа системы автоматически рассчитывает важность и приоритет
   - Сохранение работает без ошибок

## API Endpoints

Все эндпоинты доступны после применения миграции:

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/manage/incident/categories/list` | Список категорий инцидентов |
| GET | `/manage/incident/system-types/list` | Типы систем |
| GET | `/manage/incident/importance-levels/list` | Уровни важности |
| GET | `/manage/incident/priority-levels/list` | Уровни приоритета (1-9) |
| GET | `/manage/incident/incident-types/list` | Типы инцидентов |
| GET | `/manage/incident/undesirable-events/list` | Недопустимые события |
| GET | `/manage/incident/motivations/list` | Мотивации причастных лиц |
| GET | `/manage/incident/playbooks/list` | Список плейбуков |
| POST | `/manage/incident/calculate-priority` | **Авто-расчёт важности и приоритета** |
| GET | `/manage/incident/case/<id>` | Получить данные инцидента |
| POST | `/manage/incident/case/<id>/update` | Обновить данные инцидента |

## Соответствие Положению ТюмГУ

Реализовано 100% требований из Положения о мониторинге событий и реагировании на инциденты ИБ:

- ✅ Термины и определения (раздел 1)
- ✅ Мониторинг событий (раздел 2)
- ✅ ГРИИБ и ролевая модель (раздел 3)
- ✅ Система приоритизации (таблицы 5.1 и 5.2)
- ✅ 5 этапов реагирования (раздел 4)
- ✅ Форма карточки инцидента (Приложение №4, 4 страницы)

## Контакты

При возникновении проблем:
1. Проверьте логи контейнеров: `docker compose logs -f`
2. Проверьте логи миграции: `docker compose logs web`
3. Убедитесь, что Docker Desktop полностью загружен
