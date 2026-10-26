# Standalone: Yuki Socket.IO и 502 после обновления контейнеров

Инструкция для **существующего удалённого standalone-стека**, запущенного с
`docker-compose.standalone.yml`. Локальный стек с четырьмя Compose-файлами из
`AGENTS.md` этой командой не обновлять.

## Настройка внешнего адреса

В `.env` рядом с Compose-файлом задайте точный origin из адресной строки браузера:

```dotenv
IRIS_PUBLIC_URL=https://10.252.205.127:18545
IRIS_HTTPS_PORT=18545
```

IP выше — адрес, принятый в обсуждении; если фактический адрес отличается,
замените его. Не добавляйте путь `/chat` или `/socket.io/`. Сохраните остальные
существующие настройки `.env`. Не публикуйте файл: в нём могут быть секреты.
Переменная `IRIS_PUBLIC_URL` в оболочке имеет приоритет над `.env`.

Standalone передаёт `IRIS_PUBLIC_URL` как `IRIS_ALLOW_ORIGIN` в app/worker и
frontend. Не используйте `*`: точный origin нужен для защиты Socket.IO.
Обычный `restart` не применяет новое окружение — контейнеры нужно пересоздать.

## Что исправлено в nginx

`v3/backend/docker/nginx/nginx-newui.conf` использует Docker DNS `127.0.0.11`
с кешем 5 секунд и переменные в `proxy_pass`. Это позволяет заново находить
`app` и `frontend` после смены их IP. Путь и query string сохраняются,
включая `/socket.io/?EIO=4&transport=...`; внешний Host/Proto передаются дальше.
Директива `resolver` без изменения `proxy_pass` проблему не устраняет.

nginx, app и frontend должны находиться в сети своего Compose-проекта.
В общей сети с чужими сервисами под alias `app`/`frontend` адрес может быть
неоднозначным — проверьте состав сети, прежде чем менять подключения.
Существующий стандартный standalone создаёт отдельную сеть автоматически.

## Применение на Linux-сервере

Сначала перенесите изменённый шаблон nginx из этого checkout на сервер.
Все команды выполняйте из каталога **существующего** standalone-проекта.
Найдите его фактическое имя и конфигурацию:

```bash
docker ps --format 'table {{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Ports}}'
docker inspect ИМЯ_КОНТЕЙНЕРА_NGINX --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
```

Далее `PROJECT` должен совпадать с найденным именем; `iris-standalone` —
стандартное имя из файла, но установка могла использовать другое.
Если labels содержат дополнительные Compose-файлы, сохраните их в командах.
Проверьте mounts выбранной БД и ID/количество кейсов и алёртов в интерфейсе
перед обновлением; после обновления повторите проверку.

```bash
PROJECT='ФАКТИЧЕСКОЕ_ИМЯ_ПРОЕКТА'
docker compose -p "$PROJECT" -f docker-compose.standalone.yml ps
docker inspect "$(docker compose -p "$PROJECT" -f docker-compose.standalone.yml ps -q db)" --format '{{json .Mounts}}'

# Сначала резервная копия БД. Не продолжайте при ошибке pg_dump.
umask 077
BACKUP="iris-before-network-fix-$(date +%Y%m%d-%H%M%S).dump"
docker compose -p "$PROJECT" -f docker-compose.standalone.yml exec -T db pg_dump -U postgres -Fc iris_db > "$BACKUP" || exit 1
test -s "$BACKUP" || exit 1
docker compose -p "$PROJECT" -f docker-compose.standalone.yml exec -T db pg_restore --list < "$BACKUP" >/dev/null || exit 1

# После настройки IRIS_PUBLIC_URL в .env:
docker compose -p "$PROJECT" -f docker-compose.standalone.yml build nginx || exit 1
docker compose -p "$PROJECT" -f docker-compose.standalone.yml up -d --no-deps --no-build --pull never --force-recreate app worker frontend nginx || exit 1
docker compose -p "$PROJECT" -f docker-compose.standalone.yml exec -T nginx nginx -t
docker compose -p "$PROJECT" -f docker-compose.standalone.yml ps
```

Эти команды сохраняют имя проекта и тома; db, rabbitmq и init не пересоздаются.
Дамп БД не содержит вложений и других файловых томов. Сохраните также их
существующие резервные копии. Будет короткий перерыв в работе приложения.
Если изменился hostname, TLS-сертификат должен соответствовать новому имени
и быть доверенным браузеру; смена `IRIS_PUBLIC_URL` сама по себе его не обновит.

## Проверка на сервере

1. Дождитесь готовности app/frontend/nginx, проверьте логи worker.
2. С компьютера пользователя проверьте транспортный handshake, подставив
   фактический URL. Здесь `-k` допустим только для диагностики локального
   самоподписанного сертификата; браузеру требуется доверенный сертификат:

   ```bash
   curl -ksS --max-time 10 -H 'Origin: https://10.252.205.127:18545' 'https://10.252.205.127:18545/socket.io/?EIO=4&transport=polling'
   ```

   Ожидается ответ, начинающийся с `0{"sid":...`, а не HTML, 400 или 502.
   Это проверяет Engine.IO, но ещё не аутентификацию namespace `/chat`.
3. Войдите в IRIS и отправьте сообщение Yuki. В Network браузера найдите
   WebSocket `/socket.io/` со статусом 101 и успешное подключение `/chat`.
4. Проверьте прежние записи/ID. При согласованном тестовом обновлении app или
   frontend убедитесь, что новые HTTP-запросы восстанавливаются после готовности
   сервиса и обновления DNS без ручного рестарта nginx. Активные сокеты во время
   перезапуска app оборвутся; повторное подключение Yuki нужно проверить отдельно.

Если есть внешний nginx/ingress, он также должен пропускать WebSocket Upgrade,
сохранять внешний Host/Proto и направлять запросы в этот standalone-стек.

## Локальный регрессионный тест

```bash
IRIS_NGINX_DOCKER_TEST=1 python v3/backend/tests/test_nginx_discovery.py
```

Нужны уже существующие образы `iris-standalone-nginx:local` и `python:3.12`.
Тест монтирует изменённый шаблон и entrypoint, проверяет `nginx -t`, HTTP-пути,
query string, заголовки и восстановление маршрутизации после смены IP сервиса.
Создаёт отдельную сеть и временные контейнеры без внешних портов и томов данных,
удаляет только свои ресурсы. Это проверка прокси, не полноценный запуск Yuki.
