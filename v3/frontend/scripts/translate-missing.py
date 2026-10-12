"""Translate only the public upstream UI inventory; never application records."""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/lib/i18n'
catalog = json.loads((ROOT / 'ru.json').read_text(encoding='utf-8'))
inventory = json.loads((ROOT / 'inventory.json').read_text(encoding='utf-8'))
normalize = lambda value: re.sub(r'\s+', ' ', value).strip().lower().rstrip('.:')
lookup = {normalize(key): value for key, value in catalog.items()}

def save():
    (ROOT / 'ru.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

pending = []
for key in inventory:
    if key in catalog:
        continue
    if normalize(key) in lookup:
        catalog[key] = lookup[normalize(key)]
    elif not re.search('[a-zA-Z]{3}', key) or key in {'API', 'IOC', 'IOCs', 'UUID', '#UUID', '#ID', 'TLP', 'JSON', 'MCP', 'OIDC', 'LDAP', 'SQL', 'Yjs', 'IRIS'}:
        catalog[key] = key
    else:
        pending.append(key)

def translate_batch(keys):
    # Newlines separate strings; internal formatting whitespace is not translated.
    texts = [re.sub(r'\s+', ' ', key).strip() for key in keys]
    query = urllib.parse.urlencode({'client': 'gtx', 'sl': 'en', 'tl': 'ru', 'dt': 't', 'q': '\n'.join(texts)})
    request = urllib.request.Request('https://translate.googleapis.com/translate_a/single?' + query,
                                     headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                result = json.load(response)
            translated = ''.join(part[0] for part in result[0] if part[0]).split('\n')
            if len(translated) != len(keys):
                if len(keys) == 1:
                    return ['\n'.join(translated)]
                middle = len(keys) // 2
                return translate_batch(keys[:middle]) + translate_batch(keys[middle:])
            return translated
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

batch = []
size = 0
done = 0
for key in pending + [None]:
    length = len(urllib.parse.quote(key or ''))
    if batch and (key is None or size + length > 6500):
        for original, translated in zip(batch, translate_batch(batch), strict=True):
            catalog[original] = translated.strip() or original
        done += len(batch)
        save()
        print(f'Translated {done}/{len(pending)} public strings', flush=True)
        batch, size = [], 0
        time.sleep(0.3)
    if key is not None:
        batch.append(key)
        size += length

# Product terminology takes precedence over automatic translations.
terms = {
    'war rooms': 'штабы реагирования', 'war room': 'штаб реагирования',
    'investigation flows': 'сценарии расследования', 'investigation flow': 'сценарий расследования',
    'alert clusters': 'кластеры оповещений', 'alert cluster': 'кластер оповещений',
    'cases': 'инциденты', 'case': 'инцидент', 'alerts': 'оповещения', 'assets': 'активы',
    'evidence': 'доказательства', 'evidences': 'доказательства', 'notes': 'заметки',
    'tasks': 'задачи', 'timeline': 'временная шкала', 'timelines': 'временные шкалы',
    'sitrep': 'оперативная сводка', 'sitreps': 'оперативные сводки',
    'sign in': 'войти', 'sign out': 'выйти', 'logout': 'выйти', 'login': 'вход',
    'notifications': 'уведомления', 'mail': 'почта', 'settings': 'настройки',
    'create case': 'создать инцидент', 'dashboard': 'панель управления',
    'dashboards': 'панели управления', 'custom dashboards': 'пользовательские панели',
    'home': 'главная', 'overview': 'обзор', 'datastore': 'хранилище',
    'users': 'пользователи', 'customers': 'заказчики', 'groups': 'группы',
    'save': 'сохранить', 'cancel': 'отмена', 'delete': 'удалить', 'close': 'закрыть',
    'add': 'добавить', 'edit': 'изменить', 'search': 'поиск', 'filter': 'фильтр',
    'filters': 'фильтры', 'username': 'имя пользователя', 'password': 'пароль',
    'api docs': 'документация API', 'investigate': 'расследовать',
}
for key in inventory:
    term = terms.get(normalize(key))
    if term:
        catalog[key] = term[0].upper() + term[1:] if key[0].isupper() else term
    for bad, good in [('военные комнаты', 'штабы реагирования'), ('Военные комнаты', 'Штабы реагирования'),
                      ('военная комната', 'штаб реагирования'), ('Военная комната', 'Штаб реагирования'),
                      ('ходы расследования', 'сценарии расследования'), ('потоки расследования', 'сценарии расследования')]:
        catalog[key] = catalog[key].replace(bad, good)
save()
missing = [key for key in inventory if not catalog.get(key)]
(ROOT / 'missing.json').write_text(json.dumps(missing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Catalog complete: {len(inventory) - len(missing)}/{len(inventory)} extracted UI strings', flush=True)
