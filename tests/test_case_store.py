"""Focused regression checks for case deletion without touching Supabase."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import case_store


class CaseDeletionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path_patch = patch.object(case_store, "LOCAL_CASES_PATH", Path(self.directory.name) / "cases.json")
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.store = object.__new__(case_store.CaseStore)
        self.store.remote = None
        self.store.local_fallback = True
        self.store.initialization_error = ""

    def test_deletes_only_requested_case(self):
        first = self.store.save_case({"title": "first", "status": "published"}, actor="admin")
        second = self.store.save_case({"title": "second", "status": "draft"}, actor="admin")
        self.assertTrue(self.store.delete_case(first["id"]))
        self.assertIsNone(self.store.get_case(first["id"]))
        self.assertEqual([case["id"] for case in self.store.list_cases()], [second["id"]])
        self.assertFalse(self.store.delete_case(first["id"]))

    def test_rejects_empty_id(self):
        with self.assertRaises(ValueError):
            self.store.delete_case("")

    def test_remote_deletion_is_filtered_by_id(self):
        class RemoteTable:
            def __init__(self):
                self.filters = []
                self.data = []

            def delete(self):
                return self

            def eq(self, key, value):
                self.filters.append((key, value))
                return self

            def select(self, key):
                self.selected = key
                return self

            def execute(self):
                return type("Response", (), {"data": self.data})()

        remote = RemoteTable()
        self.store.remote = type("Remote", (), {"table": lambda _, name: remote})()
        remote.data = [{"id": "selected"}]
        self.assertTrue(self.store.delete_case("selected"))
        self.assertEqual(remote.filters, [("id", "selected")])
        self.assertEqual(remote.selected, "id")


if __name__ == "__main__":
    unittest.main()
