"""Run the repository's unchanged REST and GraphQL suite on an isolated stack."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
import unittest
from urllib.parse import urlparse


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--tests", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = urlparse(args.url)
    if url.hostname not in {"localhost", "127.0.0.1", "app"} or url.port not in {18080, 18081, 8000}:
        parser.error("Refusing destructive legacy test cleanup outside isolated local test ports")
    sys.path.insert(0, str(args.tests.resolve()))
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,app"
    import iris
    iris.API_URL = args.url.rstrip("/")
    suite = unittest.defaultTestLoader.discover(str(args.tests), pattern="tests_*.py")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix(".log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    summary = {"url": args.url, "tests_run": result.testsRun,
               "failures": [{"test": str(test), "traceback": trace} for test, trace in result.failures],
               "errors": [{"test": str(test), "traceback": trace} for test, trace in result.errors],
               "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped]}
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{result.testsRun} tests: {len(result.failures)} failures, {len(result.errors)} errors, {len(result.skipped)} skipped")
    sys.exit(not result.wasSuccessful())
