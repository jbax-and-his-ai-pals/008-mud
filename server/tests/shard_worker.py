"""Runs one shard of the test suites for `run_tests.py --jobs N`.

    python -m tests.shard_worker --report out.json tests.singles.test_a tests.batch.test_b ...

It is a plain `unittest` run of the named modules, plus a report of how long each module took (the
runner balances the next run's shards by it) and which tests failed. Nothing here changes how a test runs;
a module run alone behaves as it does in a full run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unittest
from collections import defaultdict


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module_seconds = defaultdict(float)
        self._started = 0.0

    def startTest(self, test):
        self._started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        module = type(test).__module__
        self.module_seconds[module] += time.perf_counter() - self._started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("modules", nargs="+")
    args = parser.parse_args()

    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for name in args.modules:
        suite.addTests(loader.loadTestsFromName(name))

    runner = unittest.TextTestRunner(verbosity=0, resultclass=TimedResult, stream=sys.stderr)
    result = runner.run(suite)
    report = {
        "ran": result.testsRun,
        "failed": [str(test) for test, _ in result.failures + result.errors],
        "skipped": len(result.skipped),
        "seconds": dict(result.module_seconds),
    }
    with open(args.report, "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
