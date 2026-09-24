"""The admin list and counters must reflect draft/publish immediately."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import admin_pages
import case_store


def _app():
    import admin_pages

    admin_pages.render_admin_page({})


class AdminRefreshTests(unittest.TestCase):
    def test_draft_and_publish_refresh_without_manual_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            def store_factory():
                store = object.__new__(case_store.CaseStore)
                store.remote = None
                store.local_fallback = True
                store.initialization_error = ""
                return store

            with (
                patch.object(case_store, "LOCAL_CASES_PATH", Path(directory) / "cases.json"),
                patch.object(admin_pages, "CaseStore", store_factory),
                patch.object(admin_pages, "_login", return_value=True),
                patch.object(admin_pages, "_nav"),
                patch.object(admin_pages, "_strategies", return_value=["测试策略案例"]),
            ):
                app = AppTest.from_function(_app).run()
                app.button(key="case-add").click().run()
                app.text_input[0].set_value("验证刷新")
                app.text_input[1].set_value("测试经理")
                app.text_area[1].set_value("测试判断")
                next(button for button in app.button if button.key and button.key.endswith("-保存草稿")).click().run()

                self.assertFalse(app.exception)
                self.assertEqual(store_factory().list_cases()[0]["status"], "draft")
                self.assertEqual(len(app.success), 1)
                self.assertTrue(any("<strong>1</strong>全部案例" in item.value for item in app.markdown))

                next(button for button in app.button if button.key and button.key.endswith("-发布")).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(store_factory().list_cases()[0]["status"], "published")
                self.assertEqual(len(app.success), 1)
                self.assertTrue(any("<strong>1</strong>已发布" in item.value for item in app.markdown))


if __name__ == "__main__":
    unittest.main()
