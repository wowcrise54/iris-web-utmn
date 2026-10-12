# Проверка миграции Flask → FastAPI

**Текущая база сравнения — официальный IRIS v2.4.29**, коммит
`340ce04080806a83837b713d01ea70632ee2b3f7`: 411 потенциальных маршрутов,
815 файлов UI/static и 213 Python-файлов бизнес-логики. Сам набор тестов
адаптеров продолжает проверять сессии, формы, ORM и ASGI независимо от релиза.

Команды приёмки текущей версии находятся в
[../upgrade_2_4_29/README.md](../upgrade_2_4_29/README.md).
Описанные ниже 181 тест и старый `probe_http.py` относятся к завершённой
первой миграции beta 2.5.0, включавшей API v2 и GraphQL. Их результаты являются
историей проверки; для 2.4.29 используйте новый набор приёмки, а не эти сценарии.

Backend работает на FastAPI/Uvicorn и native ASGI Socket.IO. Flask и WSGI-приложение
не используются. Слой `app.web` сохраняет API существующих синхронных обработчиков:
контексты запроса, Jinja, подписанные сессии, формы, URL и HTTP-ответы. Бизнес-код,
ORM-модели, схема GraphQL и исходные файлы интерфейса сохранены.

## Запуск отдельного Docker-окружения

Команды PowerShell выполняются из корня репозитория. Нужны Python и Docker Desktop
с запущенным Linux engine.

```powershell
python -m pip install -r tests/migration/requirements.txt
python tests/migration/prepare_stack.py
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml up -d
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml ps
```

Интерфейс: https://localhost:18443. Тестовый вход: `administrator` /
`MySuperAdminPassword!`. API: http://127.0.0.1:18080.
Тестовые учётные данные заданы в `tests/data/basic.env`. Сертификат localhost
генерируется в `runtime/certs`; HTTPS-проверки доверяют именно этому сертификату.
Браузер требует отдельного доверия к локальному сертификату.

Compose создаёт отдельные PostgreSQL, RabbitMQ, worker, Nginx, сеть и тома с
префиксом `iris-migration-fastapi`. Данные других экземпляров не используются.
Для `app`, `worker`, `db` и `nginx` задано `pull_policy: build`: обычный `up -d`
автоматически собирает их из локальных исходников и Dockerfile с использованием
кеша. RabbitMQ и базовые образы Dockerfile загружаются из официальных репозиториев.

## Повторение проверок

Существующие 181 REST/GraphQL тест используют тестовую базу и удаляют созданные
ими записи. Выполняйте проверки последовательно в этом отдельном окружении:

```powershell
python tests/migration/run_legacy_suite.py --url http://127.0.0.1:18080 --output tests/migration/runtime/native-suite.json
python tests/migration/probe_http.py --http http://127.0.0.1:18080 --https https://localhost:18443 --output tests/migration/runtime/native-probes.json
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml exec -T -e IRIS_WORKER=1 app python /migration/check_app.py
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml exec -T -e IRIS_WORKER=1 -e PYTHONPATH=/iriswebapp app python /migration/check_worker.py
```

Полная проверка адаптеров, исходных файлов и зарегистрированных маршрутов
в одноразовом контейнере с теми же зависимостями:

```powershell
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml run --rm --no-deps -e IRIS_WORKER=1 -e IRIS_MIGRATION_RUNTIME=1 -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}:/workspace:ro" --entrypoint sh app -c 'pip install -r /migration/requirements.txt && python -m pytest /workspace/tests/migration -q --basetemp /tmp/iris-migration-pytest'
```

`test_entrypoint.sh` проверяет сохранение контейнера при замене процесса сервером
обновлений и передачу SIGTERM дочернему процессу:

```powershell
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml run --rm --no-deps --entrypoint sh app -c 'sed "s/\r$//" /migration/test_entrypoint.sh | bash -s -- ./iris-entrypoint.sh'
```

Результаты находятся в `runtime/*.json` и `runtime/*.log`; сертификаты и результаты
не входят в Git. Неизменные контракты исходного Flask checkout сохранены в
`contracts.json` и `business_contracts.json`. Не перегенерируйте baseline из
мигрированного исходного кода.

Для сохранённого исходного Flask image используются `MIGRATION_APP_IMAGE`,
`MIGRATION_HTTP_PORT=18081`, `MIGRATION_HTTPS_PORT=18444` и отдельный Compose-проект
`iris-migration-baseline`; инспектор маршрутов принимает `--flask`. Legacy runner
принимает `--tests D:/Diplom/iris-flask-baseline/tests` для неизменных исходных тестов.
Сам baseline image собирается из сохранённого исходного checkout.

## Результаты 9 октября 2026

Исходный Flask checkout (`d35edc2e0536e07630d40989294c6cfb666cba19`) и FastAPI
проверены в отдельных Docker-проектах с PostgreSQL и RabbitMQ.

| Проверка | Результат |
| --- | --- |
| Существующие REST/GraphQL тесты | Flask: 181/181; FastAPI: 181/181 |
| Регрессионные тесты внутри финального Docker-образа | 52/52, без пропусков, включая проверку настоящего FastAPI-приложения |
| Маршруты, имена endpoint и HTTP-методы | Совпадают: 424 активных маршрута |
| Условные OIDC/demo маршруты | Сохранены в контракте из 427 маршрутов |
| Бизнес-код | 266 исходных Python-файлов: AST совпадает с baseline после замены импортов и имени класса формы |
| Интерфейс, шаблоны и статические файлы | 308 файлов: SHA-256 совпадает с baseline |
| HTTPS, вход, cookie, CSRF, API, страницы | 31 публичная проверка проходит; снимки контрактов Flask/FastAPI совпадают полностью |
| Multipart и скачивание | Файл более 2 МБ совпадает побайтно |
| Socket.IO | Два клиента, комнаты, сообщения версии/состояния и уведомления alerts проходят |
| Celery | Worker отвечает `pong`; задача через RabbitMQ возвращает `[1, 2, 3]` |
| Нативный backend | FastAPI APIRoute; Flask отсутствует в импортированных модулях; WSGI отсутствует |

Отдельные регрессии проверяют polling и WebSocket, прежние Flask-Login сессии,
подписанные CSRF-токены, загрузки во временный файл, ORM-контексты и передачу
управления внешнему обновлению. Независимое ревью не выявило оставшихся
подтверждённых функциональных регрессий.

В браузере проверено отображение формы входа и совпадение её структуры с Flask,
без ошибок JavaScript. Авторизованные страницы проверены по HTTPS с проверкой
сертификата; полный существующий Playwright-набор не заявляется как пройденный.
LDAP/OIDC требуют внешнего провайдера и не проверялись с реальным провайдером.
Исходный `source/tests/unit` не запускается и на Flask baseline: устаревший импорт
`from app.models import Client` вызывает `ImportError`. Реальный архив обновления
не применялся; проверены transport handoff и жизненный цикл процессов.

Остановка с сохранением тестовой базы:

```powershell
docker compose -p iris-migration-fastapi -f docker-compose.migration.yml down
```
