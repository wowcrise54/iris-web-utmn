"""Public HTTP regression scenarios, with writes limited to an isolated test DB.

Records status/content contracts for comparison between preserved Flask and ASGI.
Socket.IO uses real Engine.IO polling packets, so no extra client dependency is
needed on the Windows test host.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import requests

API_KEY = "B8BA5D730210B50F41C06941582D7965D57319D5685440587F98DFDC45A01594"
PASSWORD = "MySuperAdminPassword!"


class PollingClient:
    def __init__(self, url, namespace="/server-updates", cookie=None):
        self.url = url.rstrip("/") + "/socket.io/"
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["Authorization"] = "Bearer " + API_KEY
        if cookie:
            self.session.headers["Cookie"] = "session=" + cookie
        self.namespace = namespace
        self.params = {"EIO": 4, "transport": "polling"}
        response = self.session.get(self.url, params=self.params, timeout=10)
        assert response.status_code == 200 and response.text.startswith("0"), response.text
        self.params["sid"] = json.loads(response.text[1:])["sid"]
        self.send("40" + (namespace + "," if namespace != "/" else ""))
        assert "40" in self.poll(), "Socket.IO namespace did not connect"

    def send(self, packet):
        response = self.session.post(self.url, params=self.params, data=packet,
                                     headers={"Content-Type": "text/plain;charset=UTF-8"}, timeout=10)
        assert response.status_code == 200, response.text

    def emit(self, event, data):
        self.send("42" + (self.namespace + "," if self.namespace != "/" else "") + json.dumps([event, data]))

    def poll(self):
        response = self.session.get(self.url, params=self.params, timeout=30)
        assert response.status_code == 200, response.text
        return response.text

    def close(self):
        self.send("1")


def probes(http, https, certificate):
    session = requests.Session()
    session.trust_env = False
    session.headers["Authorization"] = "Bearer " + API_KEY
    anonymous = requests.Session()
    anonymous.trust_env = False
    records = {}

    def record(name, response):
        records[name] = {"status": response.status_code, "content_type": response.headers.get("Content-Type", "").split(";")[0]}
        return response

    for route in ("/manage/customers/list", "/api/v2/cases"):
        for label, key in (("missing", None), ("invalid", "0" * 64)):
            headers = {} if key is None else {"Authorization": "Bearer " + key}
            response = anonymous.get(http + route, headers=headers, timeout=20)
            record("auth " + route + " " + label, response)
            assert response.status_code == 401, response.text
    record("v1 customers", session.get(http + "/manage/customers/list", timeout=20))
    record("v2 pagination", session.get(http + "/api/v2/cases", params={"page": 1, "per_page": 2}, timeout=20))
    head = record("HEAD v2 cases", session.head(http + "/api/v2/cases", timeout=20))
    assert head.status_code == 200 and not head.content
    record("OPTIONS v2 cases", session.options(http + "/api/v2/cases", timeout=20))
    record("strict slash", session.get(http + "/api/v2/cases/", allow_redirects=False, timeout=20))
    record("unknown route", session.get(http + "/migration-does-not-exist", timeout=20))
    invalid_graphql = anonymous.post(http + "/graphql", json={"query": "{ cases { edges { node { name } } } }"}, timeout=20)
    record("GraphQL unauthorized", invalid_graphql)
    assert invalid_graphql.status_code == 401
    graphql = record("GraphQL query", session.post(http + "/graphql", json={"query": "{ cases { edges { node { name } } } }"}, timeout=20))
    assert graphql.status_code == 200 and "errors" not in graphql.json(), graphql.text

    browser = requests.Session()
    browser.trust_env = False
    browser.verify = certificate
    login = record("login page", browser.get(https + "/login", timeout=20))
    assert login.status_code == 200
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login.text).group(1)
    signed_cookie = browser.cookies.get("session")
    cookie = next(c for c in browser.cookies if c.name == "session")
    assert cookie.secure and cookie.has_nonstandard_attr("HttpOnly")
    records["session cookie"] = {"secure": cookie.secure, "http_only": cookie.has_nonstandard_attr("HttpOnly"),
                                "same_site": cookie.get_nonstandard_attr("SameSite")}
    response = record("login form", browser.post(https + "/login", data={"username": "administrator", "password": PASSWORD,
                        "csrf_token": token}, allow_redirects=False, timeout=20))
    assert response.status_code == 302, response.text[:300]
    for path in ("/", "/dashboard", "/case?cid=1", "/case/tasks?cid=1", "/case/assets?cid=1", "/case/ioc?cid=1", "/alerts"):
        response = record("page " + path, browser.get(https + path, timeout=30))
        assert response.status_code == 200, (path, response.status_code, response.text[:300])
    without_csrf = record("authenticated API without CSRF", browser.post(https + "/manage/customers/add", json={}, timeout=20))
    assert without_csrf.status_code == 400, without_csrf.text
    # Use the CSRF token already rendered before login: the token is session-bound.
    valid_csrf = record("authenticated API valid CSRF", browser.post(https + "/api/v2/cases", json={"csrf_token": token}, timeout=20))
    assert valid_csrf.status_code == 400 and "CSRF" not in valid_csrf.text, valid_csrf.text
    tampered = requests.Session()
    tampered.trust_env = False
    tampered.verify = certificate
    tampered.cookies.set("session", signed_cookie + "x", domain="localhost.local", secure=True)
    denied = record("tampered session", tampered.get(https + "/case?cid=1", allow_redirects=False, timeout=20))
    assert denied.status_code in {302, 401}, denied.text[:300]
    static = record("compiled UI asset", browser.get(https + "/static/assets/js/iris/login.js", timeout=20))
    assert static.status_code == 200
    records["compiled UI asset"]["sha256"] = hashlib.sha256(static.content).hexdigest()

    alert_client = PollingClient(http, namespace="/alerts", cookie=browser.cookies.get("session"))
    alert_id = None
    try:
        response = record("alert create", session.post(http + "/alerts/add", json={"alert_title": "Migration notification",
                           "alert_severity_id": 4, "alert_status_id": 3, "alert_customer_id": 1}, timeout=20))
        assert response.status_code == 200, response.text
        alert_id = response.json()["data"]["alert_id"]
        packet = alert_client.poll()
        assert "new_alert" in packet and str(alert_id) in packet, packet
        records["Socket.IO alerts broadcast"] = {"handshake": 200, "namespace": "/alerts", "new_alert": True}
    finally:
        alert_client.close()
        if alert_id is not None:
            deleted = session.post(http + f"/alerts/delete/{alert_id}", json={}, timeout=20)
            assert deleted.status_code == 200, deleted.text

    case = session.post(http + "/api/v2/cases", json={"case_name": "Migration binary probe", "case_description": "Isolated test",
                          "case_customer": 1, "case_soc_id": ""}, timeout=20)
    assert case.status_code == 201, case.text
    cid = case.json()["case_id"]
    try:
        tree = session.get(http + "/datastore/list/tree", params={"cid": cid}, timeout=20).json()["data"]
        node = int(next(iter(tree)).removeprefix("d-"))
        binary = bytes(range(256)) * 8192 + b"\x00\r\nIRIS migration\xff"
        upload = record("multipart binary upload", session.post(http + f"/datastore/file/add/{node}", params={"cid": cid},
                        data={"file_original_name": "migration.bin", "file_description": "Binary contract"},
                        files={"file_content": ("migration.bin", binary, "application/octet-stream")}, timeout=30))
        assert upload.status_code == 200, upload.text
        file_id = upload.json()["data"]["file_id"]
        download = record("binary download", session.get(http + f"/datastore/file/view/{file_id}", params={"cid": cid}, timeout=20))
        assert download.status_code == 200 and download.content == binary, download.text[:300]
        records["binary download"]["sha256"] = hashlib.sha256(download.content).hexdigest()
        records["binary download"]["disposition"] = download.headers.get("Content-Disposition")
        first, second = PollingClient(http, cookie=browser.cookies.get("session")), PollingClient(http, cookie=browser.cookies.get("session"))
        try:
            channel = "iris_update_status"
            first.emit("join-update", {"channel": channel})
            assert "join" in first.poll()
            second.emit("join-update", {"channel": channel})
            assert "join" in second.poll()
            assert "join" in first.poll()
            first.emit("update_get_current_version", {})
            data = second.poll()
            assert "update_current_version" in data and "2.5.0-beta.1" in data, data
            assert "update_current_version" in first.poll()
            first.emit("update_ping", {})
            assert "Server connected" in first.poll()
            records["Socket.IO room notification"] = {"handshake": 200, "two_clients": True, "namespace": "/server-updates",
                                                       "join": True, "version_broadcast": True, "ping": True}
        finally:
            first.close()
            second.close()
    finally:
        response = session.delete(http + f"/api/v2/cases/{cid}", timeout=20)
        assert response.status_code == 204, response.text
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", required=True)
    parser.add_argument("--https", required=True)
    parser.add_argument("--certificate", default=str(Path(__file__).parent / "runtime/certs/migration-cert.pem"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.http).hostname not in {"localhost", "127.0.0.1"} or urlparse(args.http).port not in {18080, 18081}:
        parser.error("Writes are permitted only on isolated localhost validation ports")
    results = probes(args.http, args.https, args.certificate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"{len(results)} HTTP, page, binary and Socket.IO contracts passed")
