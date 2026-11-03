from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.schemas import ReadinessReport
from app.security import create_session_token, hash_token
from app.services.assessment import evaluate_readiness
from app.services.report_pdf import render_readiness_report


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "applicant_name": "Asha Rao",
            "education_level": "Undergraduate",
            "course": "Computer Science",
            "academic_year": "2026",
        }

    def test_missing_supporting_documents_are_reported(self):
        report = evaluate_readiness("session-1", "demo-scholarship", self.profile, [])

        statuses = {item.id: item.status for item in report.requirements}
        self.assertEqual(statuses["applicant_name"], "UNCERTAIN")
        self.assertEqual(statuses["transcript"], "MISSING")
        self.assertEqual(report.overall_status, "NEEDS_ATTENTION")

    def test_name_text_match_is_not_described_as_identity_verification(self):
        document = SimpleNamespace(filename="marksheet.pdf", extracted_text="Student: Asha Rao")
        report = evaluate_readiness("session-1", "demo-scholarship", self.profile, [document])

        name_requirement = next(item for item in report.requirements if item.id == "applicant_name")
        self.assertEqual(name_requirement.status, "VERIFIED")
        self.assertIn("does not authenticate", name_requirement.explanation)


class SecurityTests(unittest.TestCase):
    def test_session_token_is_random_and_only_hash_is_used_for_storage(self):
        token = create_session_token()

        self.assertNotEqual(token, create_session_token())
        self.assertEqual(len(hash_token(token)), 64)
        self.assertNotEqual(token, hash_token(token))


class ReportPdfTests(unittest.TestCase):
    def test_report_renders_to_a_pdf(self):
        report = ReadinessReport(
            session_id="session-1",
            scheme_id="demo-scholarship",
            overall_status="NEEDS_ATTENTION",
            disclaimer="Synthetic demo assessment only.",
            requirements=[],
            next_steps=["Review the missing items."],
            generated_at=datetime.now(timezone.utc),
        )

        pdf = render_readiness_report(report, {"applicant_name": "Asha Rao"})

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))


if __name__ == "__main__":
    unittest.main()
