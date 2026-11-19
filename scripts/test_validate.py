"""Tests for scripts/validate.py — each one proves CI rejects a bad file.

Run: python3 -m unittest discover -s scripts
"""

import copy
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.datetime.now(dt.timezone.utc).date()


class ValidatorTests(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for rel in ("v1", "schema"):
            shutil.copytree(ROOT / rel, self.tmp / rel)
        self.airports = json.loads((ROOT / "v1/airports.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_with(self, airports):
        (self.tmp / "v1/airports.json").write_text(json.dumps(airports))
        return validate.validate(self.tmp, None, TODAY)

    def lca_stamp(self, data):
        return data["airports"][0]["lounges"][0]["entry_window"]

    def first_scraped_stamp(self, node):
        """The first sourced scraped stamp anywhere in the file, so the test
        does not depend on which stamps today's data happens to scrape."""
        if isinstance(node, dict):
            if node.get("confidence") == "scraped" and "source" in node:
                return node
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            return None
        for child in children:
            found = self.first_scraped_stamp(child)
            if found is not None:
                return found
        return None

    def test_currentDataPasses(self):
        self.assertEqual(validate.validate(ROOT, None, TODAY), [])

    def test_undatedVerifiedStampFails(self):
        data = copy.deepcopy(self.airports)
        del self.lca_stamp(data)["verified_on"]
        errors = self.run_with(data)
        self.assertTrue(any("has no verified_on" in e for e in errors), errors)

    def test_unsourcedScrapedStampFails(self):
        data = copy.deepcopy(self.airports)
        stamp = self.first_scraped_stamp(data["airports"])
        self.assertIsNotNone(stamp, "data has no scraped stamp to strip")
        del stamp["source"]
        errors = self.run_with(data)
        self.assertTrue(any("scraped stamp has no source" in e for e in errors), errors)

    def test_futureDateFails(self):
        data = copy.deepcopy(self.airports)
        self.lca_stamp(data)["verified_on"] = (TODAY + dt.timedelta(days=1)).isoformat()
        self.assertTrue(any("in the future" in e for e in self.run_with(data)))

    def test_impossibleDateFails(self):
        data = copy.deepcopy(self.airports)
        self.lca_stamp(data)["verified_on"] = "2026-02-30"
        self.assertTrue(any("not a real date" in e for e in self.run_with(data)))

    def test_ruleStampNeedsNoDate(self):
        data = copy.deepcopy(self.airports)
        self.assertNotIn("verified_on", data["airports"][0]["border"])
        self.assertEqual(self.run_with(data), [])

    def test_schemaRejectsMissingUpdatedAt(self):
        data = copy.deepcopy(self.airports)
        del data["airports"][0]["updated_at"]
        self.assertTrue(any("updated_at" in e for e in self.run_with(data)))

    def test_schemaRejectsUnknownZone(self):
        data = copy.deepcopy(self.airports)
        data["airports"][0]["lounges"][0]["zone"] = "airside"
        self.assertTrue(any(".zone" in e for e in self.run_with(data)))

    def test_nonStringConfidenceIsAViolationNotACrash(self):
        data = copy.deepcopy(self.airports)
        self.lca_stamp(data)["confidence"] = ["verified"]
        self.assertTrue(any(".confidence" in e for e in self.run_with(data)))

    def test_baseRefThatDoesNotResolveIsAnErrorNotASkip(self):
        errors = validate.validate(ROOT, "refs/remotes/origin/no-such-branch", TODAY)
        self.assertTrue(any("does not resolve" in e for e in errors), errors)

    def test_dataVersionMustGrowWhenTheFileChanges(self):
        base = json.dumps(self.airports)
        changed = copy.deepcopy(self.airports)
        changed["airports"][0]["name"] += " "
        text = json.dumps(changed)
        self.assertTrue(validate.version_errors("v1/airports.json", changed, text, base))
        changed["data_version"] += 1
        self.assertEqual(validate.version_errors("v1/airports.json", changed, json.dumps(changed), base), [])

    def test_dataVersionCheckSkippedWithoutMainOrWhenUnchanged(self):
        text = json.dumps(self.airports)
        self.assertEqual(validate.version_errors("v1/airports.json", self.airports, text, None), [])
        self.assertEqual(validate.version_errors("v1/airports.json", self.airports, text, text), [])


if __name__ == "__main__":
    unittest.main()
