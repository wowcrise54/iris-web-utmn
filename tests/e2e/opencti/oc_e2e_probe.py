"""Headless E2E probe for the OpenCTI alert-enrichment plugin.

Logs in as e2e_test, creates an alert on an existing case with a real
IOC (a domain that is present in the local OpenCTI), then waits for the
Celery auto-enrichment task to store results, and prints the outcome.

Run from the host (uses the running stack at https://localhost).
"""
import json
import re
import sys
import time

import requests

BASE = "https://localhost"
USER = "e2e_test"
PASS = "E2eTestPassw0rd!"
CASE_ID = 49
CLIENT_ID = 1
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
    print(f"LOGIN status={r.status_code} (expect 302)")
    if r.status_code != 302:
        print("login failed; dumping head of page:")
        print(r.text[:400])
        sys.exit(2)

    # Reuse the session CSRF token (Flask-WTF tokens are per-session).
    print(f"CSRF token acquired (login page status={code})")

    payload = {
        "csrf_token": token,
        "alert_title": "OpenCTI E2E probe %d" % int(time.time()),
        "alert_description": "E2E: verify OpenCTI auto-enrichment of alert IOCs",
        "alert_source": "opencti-e2e-probe",
        "alert_customer_id": CLIENT_ID,
        "alert_severity_id": 4,
        "alert_status_id": 2,
        "alert_iocs": [
            {
                "ioc_value": IOC_VALUE,
                "ioc_type_id": IOC_TYPE_ID,
                "ioc_description": "probe domain",
            }
        ],
    }
    r = s.post(BASE + "/alerts/add", json=payload, timeout=30)
    print("ALERT_ADD status=%d" % r.status_code)
    try:
        data = r.json()
    except Exception:
        print(r.text[:500])
        sys.exit(3)
    if "status" in data and data.get("status") != "success":
        print("alert add error:", json.dumps(data)[:500])
        sys.exit(4)

    alert = data.get("data", {})
    alert_id = alert.get("alert_id")
    print("CREATED alert_id=%s" % alert_id)

    # Poll the alert until enrichment is stored.
    deadline = time.time() + 120
    last = None
    while time.time() < deadline:
        r = s.get(BASE + "/alerts/%d" % alert_id, timeout=30)
        a = r.json().get("data", {}) if r.status_code == 200 else {}
        ctx = (a.get("alert_context") or {}).get("opencti") or {}
        ioc = (a.get("iocs") or [{}])[0]
        enr = (ioc.get("ioc_enrichment") or {}).get("opencti") or {}
        state = {
            "progress_status": (ctx.get("progress") or {}).get("status"),
            "enr_status": enr.get("status"),
            "match_count": enr.get("match_count"),
            "has_verdict": bool(enr.get("verdict")),
        }
        if state != last:
            print("  polling:", json.dumps(state))
            last = state
        if enr.get("status") in ("match", "no_match", "error"):
            print("FINAL:", json.dumps(state))
            print("VERDICT:", json.dumps(enr.get("verdict"), ensure_ascii=False))
            print("MATCH0:", json.dumps((enr.get("matches") or [{}])[0].get("name") if enr.get("matches") else None, ensure_ascii=False))
            return
        time.sleep(5)

    print("TIMEOUT waiting for enrichment; last state:", json.dumps(last))


if __name__ == "__main__":
    main()
