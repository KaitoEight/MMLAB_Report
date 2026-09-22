import json
import sqlite3
import unittest
import unicodedata
from email.message import EmailMessage

from pydantic import ValidationError

from mmlab_pipeline import parse_and_validate_email as parse, resolve_members
from mmlab_pipeline.members import DIRECTORY, sender_matches
from mmlab_pipeline.parser import parse_eml
from mmlab_pipeline.validator import WorkReport

STUDENT = "Phong <22520001@gm.uit.edu.vn>"
BASE = {"Type of Report": "Paper", "Title of Work": "A study of multimodal learning",
        "All authors": "Chế Quang Huy, Vinh-Tiep Nguyen", "Venue": "Example Conference 2026",
        "Role": "Co author", "Index": "Scopus", "Ranking": "C-Unranked"}


def body(**updates):
    fields = BASE | updates
    return "\n".join(f"{k}: {v}" for k, v in fields.items() if v is not None)


def work(**updates):
    return parse("Fwd: Research report", body(**updates), STUDENT)


class RequiredTests(unittest.TestCase):
    def test_01_student_two_members(self):
        result = work()
        self.assertTrue(result["is_valid"])
        self.assertTrue(result["ready_for_kpi"])
        self.assertEqual([m["id"] for m in result["credited_members"]], [1, 7])

    def test_02_missing_ranking_bad_role_together(self):
        result = work(**{"Ranking": None, "Role": "Principal investigator"})
        self.assertFalse(result["is_valid"])
        self.assertEqual(result["missing_fields"], ["Ranking"])
        self.assertEqual([e["field"] for e in result["invalid_fields"]], ["Role"])

    def test_03_project(self):
        result = work(**{"Type of Report": "de tai", "Index": "-", "Ranking": "NAFOSTED"})
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["category"], "Project")

    def test_04_external_authors(self):
        result = work(**{"All authors": "Alice Brown; Bob Smith"})
        self.assertTrue(result["is_valid"])
        self.assertFalse(result["kpi_eligible"])
        self.assertTrue(result["warnings"])

    def test_05_monthly(self):
        result = parse("FW: Báo cáo tháng 9/2026", "Đã:\n- 01/09/2026, Huấn luyện mô hình\n02/09, Viết báo cáo\nSẽ:\n- Nộp bài", "thindv@uit.edu.vn", received_at="2026-09-15T00:00:00+07:00")
        self.assertTrue(result["is_valid"], result)
        self.assertEqual(result["data"]["done"][1]["date"], "2026-09-02")
        self.assertTrue(result["ready_for_kpi"])


