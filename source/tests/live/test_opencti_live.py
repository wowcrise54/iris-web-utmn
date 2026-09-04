"""LIVE end-to-end OpenCTI enrichment test.

This test drives the REAL OpenCTIHandler._enrich_ioc() against a real,
running OpenCTI instance (no Postgres required). It is the runtime
verification that the Docker/Postgres environment was blocking.

It is OFF by default (it talks to a network endpoint and a real data
store). Run it explicitly:

    OPENCTI_LIVE=1  IRIS_WORKER=1  POSTGRES_*=dummy  \
        python -m pytest tests/live/test_opencti_live.py -v

Credentials are read at runtime from the project-root .env (OPENCTI_URL,
OPENCTI_TOKEN). They are never hard-coded in this file.

Why IRIS_WORKER=1: app import triggers run_post_init(), which exits(1)
when it cannot reach Postgres. Setting IRIS_WORKER makes run_post_init
skip all DB bootstrap (the Celery-worker path), so we can import the
real handler and exercise the real enrichment pipeline without a DB.
"""
import os

# MUST be set before `app` is imported (transitively via opencti_handler -> app).
os.environ.setdefault("IRIS_WORKER", "1")
# App config reads these at import time; dummy values are fine because
# IRIS_WORKER=1 prevents run_post_init from actually opening a DB.
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "dumb")
os.environ.setdefault("POSTGRES_ADMIN_USER", "irisadmin")
os.environ.setdefault("POSTGRES_ADMIN_PASSWORD", "dumb")
os.environ.setdefault("POSTGRES_SERVER", "127.0.0.1")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "irisdb")

import logging
import re
import unittest
from pathlib import Path
from unittest.mock import patch

# Live guard: skip the whole module unless OPENCTI_LIVE is truthy.
LIVE = os.getenv("OPENCTI_LIVE", "").lower() in ("1", "true", "yes", "on")

if LIVE:
    from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler
    from iris_opencti_module.opencti_handler.opencti_client import OpenCTIClient
    from iris_opencti_module.opencti_handler.opencti_mapping import (
        normalize_search_results,
        extract_value_from_pattern,
    )
    from iris_opencti_module.opencti_handler.history import reset_enrichment_history


def _load_env() -> dict:
    """Read project-root .env without printing any values."""
    env = {}
    for cand in (
        Path(__file__).resolve().parents[3] / ".env",
        Path.cwd() / ".env",
    ):
        if cand.exists():
            for line in open(cand, encoding="utf-8", errors="replace"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
            break
    return env


class _FakeIoc:
    """Minimal stand-in for an Ioc ORM row - just the attributes the
    enrichment pipeline reads/writes. Not attached to a DB session."""

    def __init__(self, value):
        self.ioc_value = value
        self.ioc_type = None          # _ioc_type_name -> None -> "unknown"
        self.ioc_tags = ""
        self.ioc_enrichment = {}
        self.custom_attributes = {}


@unittest.skipUnless(LIVE, "Set OPENCTI_LIVE=1 to run the live OpenCTI enrichment test")
class TestOpenCTILiveEnrichment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = _load_env()
        cls.url = (env.get("OPENCTI_URL") or "").rstrip("/")
        cls.token = env.get("OPENCTI_TOKEN") or ""
        if not cls.url or not cls.token:
            raise unittest.SkipTest("OPENCTI_URL/OPENCTI_TOKEN not present in .env")
        cls.client = OpenCTIClient(url=cls.url, token=cls.token,
                                   verify_ssl=True, timeout=20)
        cls.match_ioc = cls._discover_live_ioc()

    @classmethod
    def _discover_live_ioc(cls):
        """Find an IOC value that actually returns >=1 match in the live
        dataset, using the real client + real mapping code. Auto-discovers
        so the test is not fragile to a particular feed's contents."""
        # Enumerate real indicators and collect candidate values.
        try:
            raw = cls.client.query(
                "{ indicators(first:40){ edges{ node{ name pattern } } } }", {}
            )
            nodes = (raw.get("indicators") or {}).get("edges") or []
        except Exception as e:  # noqa: BLE001
            raise unittest.SkipTest(f"could not enumerate live indicators: {e}")
        candidates = []
        for node in nodes:
            node = node.get("node") or {}
            pat = node.get("pattern") or ""
            val, _t = extract_value_from_pattern(pat)
            if val:
                candidates.append(val)
            else:
                # fall back to a bare domain/ip-looking name
                name = (node.get("name") or "").strip()
                if re.fullmatch(r"[A-Za-z0-9.:/-]+", name) and not name.startswith(("MISP", "MP ")):
                    candidates.append(name)
        for cand in dict.fromkeys(candidates):
            try:
                payload = cls.client.search_ioc(value=cand, first=10)
                matches = normalize_search_results(
                    payload, min_score=0, query_value=cand, base_url=cls.url
                )
            except Exception:
                continue
            if matches:
                return cand
        return None

    def setUp(self):
        # Fresh shared-history singleton per test so the dedup window doesn't
        # leak between cases.
        reset_enrichment_history()
        self._fm = patch(
            "iris_opencti_module.opencti_handler.opencti_handler.flag_modified",
            lambda *a, **k: None,
        )
        self._fm.start()

    def tearDown(self):
        self._fm.stop()

    def _make_handler(self, **over):
        mod_config = {
            "opencti_url": self.url,
            "opencti_token": self.token,
            "opencti_public_url": self.url,
            "opencti_verify_ssl": True,
            "opencti_timeout": 20,
            "opencti_max_results": 20,
            "opencti_min_score": 0,
            "opencti_store_raw_enrichment": True,
            "opencti_report_as_attribute": False,   # keep the live test focused
            "opencti_add_tags": True,
        }
        mod_config.update(over)
        return OpenCTIHandler(mod_config, {}, logging.getLogger("live"))

    def test_live_search_returns_real_data(self):
        self.assertIsNotNone(
            self.match_ioc, "no live IOC returned a match - live dataset empty?"
        )
        payload = self.client.search_ioc(value=self.match_ioc, first=10)
        self.assertIn("indicators", payload)
        self.assertIn("stixCyberObservables", payload)
        matches = normalize_search_results(
            payload, min_score=0, query_value=self.match_ioc, base_url=self.url
        )
        self.assertGreaterEqual(len(matches), 1)

    def test_live_enrich_ioc_full_path(self):
        if not self.match_ioc:
            self.skipTest("no live matching IOC to enrich")
        handler = self._make_handler()
        ioc = _FakeIoc(self.match_ioc)
        status, matches = handler._enrich_ioc(ioc)
        self.assertTrue(status.is_success(), msg=status.get_message())
        self.assertGreaterEqual(len(matches), 1)

        stored = ioc.ioc_enrichment["opencti"]
        # The full path must produce a complete payload (the cached-skip
        # regression was exactly these keys being missing).
        for key in ("provider", "query_value", "status", "match_count",
                    "last_lookup_utc", "last_success_utc", "verdict"):
            self.assertIn(key, stored, f"missing {key} in live enrichment")
        self.assertEqual(stored["status"], "match")
        self.assertEqual(stored["match_count"], len(matches))
        self.assertEqual(stored["provider"], "OpenCTI")
        self.assertIsNotNone(stored["verdict"])
        self.assertIn("opencti:match", ioc.ioc_tags.split(","))

    def test_live_enrich_ioc_cached_skip(self):
        """Enrich the same IOC twice; the second run must take the
        cached-skip branch and STILL return verdict + last_success_utc
        (this is the live proof of the cached-skip bug fix)."""
        if not self.match_ioc:
            self.skipTest("no live matching IOC to enrich")
        handler = self._make_handler()
        ioc = _FakeIoc(self.match_ioc)
        status1, _ = handler._enrich_ioc(ioc)
        self.assertTrue(status1.is_success())

        # Second run -> history dedup should skip the OpenCTI query.
        ioc2 = _FakeIoc(self.match_ioc)
        status2, _ = handler._enrich_ioc(ioc2)
        self.assertTrue(status2.is_success(), msg=status2.get_message())
        self.assertIn("cached", status2.get_message().lower())

        stored = ioc2.ioc_enrichment["opencti"]
        for key in ("verdict", "last_success_utc", "match_count"):
            self.assertIn(key, stored, f"cached-skip dropped {key}")
        self.assertEqual(stored["match_count"],
                         ioc.ioc_enrichment["opencti"]["match_count"])

    def test_live_enrich_ioc_no_match(self):
        handler = self._make_handler()
        ioc = _FakeIoc("definitely-not-a-real-ioc-0.0.0.invalid")
        status, matches = handler._enrich_ioc(ioc)
        self.assertTrue(status.is_success(), msg=status.get_message())
        stored = ioc.ioc_enrichment["opencti"]
        self.assertEqual(stored["status"], "no_match")
        self.assertEqual(stored["match_count"], 0)


if __name__ == "__main__":
    unittest.main()
