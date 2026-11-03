"""End-to-end API checks using a temporary SQLite database."""

import os
import atexit
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

_test_directory = tempfile.TemporaryDirectory(prefix="dastaways-api-test-")
_test_root = Path(_test_directory.name)
os.environ["DATABASE_URL"] = f"sqlite:///{(_test_root / 'workflow.db').as_posix()}"
os.environ["CHROMA_PATH"] = str(_test_root / "chroma")

# Import only after pointing app settings at the disposable test database.
from app.main import app  # noqa: E402
from app.database import engine  # noqa: E402

atexit.register(_test_directory.cleanup)
atexit.register(engine.dispose)


class ApiWorkflowTests(unittest.TestCase):
    def test_workspace_profile_assessment_and_report_download(self):
        with TestClient(app) as client:
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)

            created = client.post("/api/sessions")
            self.assertEqual(created.status_code, 201)
            session = created.json()
            base = f"/api/sessions/{session['session_id']}"

            unauthorized = client.get(base)
            self.assertEqual(unauthorized.status_code, 401)

            headers = {"Authorization": f"Bearer {session['access_token']}"}
            profile = {
                "applicant_name": "Asha Rao",
                "education_level": "Undergraduate",
                "course": "Computer Science",
                "academic_year": "2026",
            }
            saved = client.put(f"{base}/profile", json=profile, headers=headers)
            self.assertEqual(saved.status_code, 200, saved.text)

            assessed = client.post(f"{base}/assess", headers=headers)
            self.assertEqual(assessed.status_code, 200, assessed.text)
            self.assertEqual(assessed.json()["session_id"], session["session_id"])

            report = client.get(f"{base}/report", headers=headers)
            self.assertEqual(report.status_code, 200, report.text)

            download = client.get(f"{base}/report/download", headers=headers)
            self.assertEqual(download.status_code, 200, download.content[:200])
            self.assertEqual(download.headers["content-type"], "application/pdf")
            self.assertIn("attachment; filename=", download.headers["content-disposition"])
            self.assertTrue(download.content.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
