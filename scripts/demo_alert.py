"""Create a demo alert 'привет hello hello' on a running IRIS stack.

Run from the host against https://localhost. Logs in as e2e_test,
creates an alert with a real IOC domain, prints the new alert id.
"""
import re
import sys
import time

import requests

BASE = "https://localhost"
USER = "e2e_test"
PASS = "E2eTestPassw0rd!"
CLIENT_ID = 1
TITLE = "привет hello hello"
IOC_VALUE = "mehrstimmen.de"
IOC_TYPE_ID = 20  # domain


def get_csrf(s, url):
    r = s.get(url, timeout=30)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
    if not m:
        m = re.search(r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)', r.text)
    return (m.group(1) if m else None), r.status_code


def main():
    s = requests.Session()
    s.verify = False
    requests.packages.urllib3.disable_warnings()

    token, code = get_csrf(s, BASE + "/login")
    r = s.post(BASE + "/login",
               data={"csrf_token": token, "username": USER, "password": PASS},
               timeout=30, allow_redirects=False)
    print("LOGIN status=%d (expect 302)" % r.status_code)
    if r.status_code != 302:
        print("login failed; head of page:")
        print(r.text[:400])
        sys.exit(2)

    payload = {
        "csrf_token": token,
        "alert_title": TITLE,
        "alert_description": "Демонстрационный алёрт: новый минималистичный интерфейс и исправления багов.",
        "alert_source": "demo-minimal-ui",
        "alert_customer_id": CLIENT_ID,
        "alert_severity_id": 4,
        "alert_status_id": 2,
        "alert_iocs": [
            {
                "ioc_value": IOC_VALUE,
                "ioc_type_id": IOC_TYPE_ID,
                "ioc_description": "демо-домен для OpenCTI",
            }
        ],
    }
    r = s.post(BASE + "/alerts/add", json=payload, timeout=30)
    print("ALERT_ADD status=%d" % r.status_code)
    try:
        data = r.json()
    except Exception:
        print(r.text[:800])
        sys.exit(3)
    if "status" in data and data.get("status") != "success":
        print("alert add error:", str(data)[:500])
        sys.exit(4)
    alert = data.get("data", {})
    print("CREATED alert_id=%s title=%r" % (alert.get("alert_id"), TITLE))


if __name__ == "__main__":
    main()
