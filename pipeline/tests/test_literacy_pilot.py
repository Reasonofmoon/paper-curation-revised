"""Literacy pilot: education template, Gemini flag, folder classification, BM25 fallback."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))

import config_loader  # noqa: E402
from answer_deep_research import format_retrieval_markdown, number_papers  # noqa: E402
from build_search_index import build_parser, select_text_windows  # noqa: E402
from classify_bib_subtopic import assign_categories, label_for  # noqa: E402
from lib.gemini_llm import GeminiKeyMissing, require_google_key  # noqa: E402
from lib.review_education import (  # noqa: E402
    NOT_IN_TEXT,
    excerpt_for_review,
    placeholder_fields,
    render_education_markdown,
    scrub_guarantees,
)


class EducationTemplateTests(unittest.TestCase):
    def test_placeholder_has_sections_and_no_guarantee(self):
        meta = {
            "title": "Extensive Reading Meta-analysis",
            "authors": ["Ada Lovelace"],
            "year": "2025",
            "doi": "10.1000/example",
            "license": "CC BY",
            "subtopic": "extensive-reading",
            "venue": "Educational Psychology Review",
        }
        fields = placeholder_fields(meta, "Children read graded readers for twelve weeks.")
        text = render_education_markdown(meta, fields, status="placeholder")
        for heading in (
            "## Essence", "## 연구 질문과 배경", "## 참여자", "## 연구 설계",
            "## 주요 결과와 효과크기", "## 한계", "## 학부모 시사점", "## 근거 인용",
        ):
            self.assertIn(heading, text)
        self.assertIn(NOT_IN_TEXT, text)
        self.assertIn("근거 강도", text)
        self.assertNotIn("합격을 보장", text)
        self.assertIn("review_status: \"placeholder\"", text)

    def test_excerpt_keeps_a_late_effect_size(self):
        late = ("intro " * 4000) + "The pooled Cohen's d = 0.41, 95% CI [0.20, 0.62]."
        excerpt = excerpt_for_review(late, head=2000, window=200, extra=1)
        self.assertIn("Cohen's d = 0.41", excerpt)

    def test_scrub_removes_score_guarantee(self):
        cleaned = scrub_guarantees("이 방법은 점수를 보장한다. 가정 독서는 상관연구이다.")
        self.assertNotIn("보장", cleaned)
        self.assertIn("상관연구", cleaned)


class LlmFlagTests(unittest.TestCase):
    def tearDown(self):
        config_loader._config_cache = None

    def test_default_provider_is_anthropic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{}", encoding="utf-8")
            config_loader._config_cache = None
            with patch.object(config_loader, "CONFIG_PATH", path):
                settings = config_loader.get_llm_settings()
                profile = config_loader.get_review_profile("literacy")
        self.assertEqual(settings["provider"], "anthropic")
        self.assertEqual(profile, "education")

    def test_gemini_flag_and_missing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "llm": {"provider": "gemini", "review_model": "gemini-2.5-flash"},
            }), encoding="utf-8")
            config_loader._config_cache = None
            with patch.object(config_loader, "CONFIG_PATH", path):
                with patch.dict("os.environ", {}, clear=False):
                    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                        if name in __import__("os").environ:
                            del __import__("os").environ[name]
                    settings = config_loader.get_llm_settings()
                    with self.assertRaises(GeminiKeyMissing):
                        require_google_key()
        self.assertEqual(settings["provider"], "gemini")
        self.assertEqual(settings["review_model"], "gemini-2.5-flash")


class ClassificationTests(unittest.TestCase):
    def test_primary_follows_subtopic_and_secondary_is_selective(self):
        records = [
            {"slug": "a", "subtopic": "extensive-reading",
             "text": "extensive reading graded readers vocabulary gains fluency"},
            {"slug": "b", "subtopic": "extensive-reading",
             "text": "extensive reading graded readers vocabulary gains fluency practice"},
            {"slug": "c", "subtopic": "phonics-decoding",
             "text": "phonological awareness phonics decoding intervention grapheme"},
            {"slug": "d", "subtopic": "parent-home-literacy",
             "text": "home literacy environment shared book reading parents"},
        ]
        assigned = {row["slug"]: row for row in assign_categories(records)}
        self.assertEqual(assigned["a"]["primary_category"], "Extensive Reading")
        self.assertEqual(label_for("phonics-decoding"), "Phonics and Decoding")
        self.assertEqual(assigned["c"]["all_categories"][0], "Phonics and Decoding")
        self.assertNotIn("Phonics and Decoding", assigned["d"]["all_categories"])


class RetrievalHelperTests(unittest.TestCase):
    def test_opening_windows_when_ml_lexicon_is_absent(self):
        text = (
            "Shared book reading at home and English vocabulary in elementary school. "
            "Parents and children read picture books together. " * 40
        )
        windows = select_text_windows(text)
        self.assertTrue(windows)
        self.assertIn("Shared book reading", windows[0])

    def test_bm25_only_flag(self):
        args = build_parser().parse_args(["--topic", "literacy", "--bm25-only"])
        self.assertTrue(args.bm25_only)

    def test_retrieval_markdown_numbers_papers_once(self):
        result = {
            "topic": "literacy",
            "mode": "bm25",
            "model": "bm25-only",
            "results": [
                {"slug": "001_a", "title": "Alpha", "year": 2024, "section": "Detail (1)",
                 "text": "extensive reading", "url": "https://doi.org/10.1/a"},
                {"slug": "001_a", "title": "Alpha", "year": 2024, "section": "Detail (2)",
                 "text": "more", "url": "https://doi.org/10.1/a"},
                {"slug": "011_b", "title": "Beta", "year": 2021, "section": "Detail (1)",
                 "text": "elementary", "url": ""},
            ],
        }
        papers = number_papers(result)
        self.assertEqual([p["n"] for p in papers], [1, 2])
        text = format_retrieval_markdown("Q?", result, papers, None, "BLOCKED")
        self.assertIn("### [1] Alpha", text)
        self.assertIn("### [2] Beta", text)
        self.assertIn("BLOCKED", text)
        self.assertNotIn("합격을 보장", text)


if __name__ == "__main__":
    unittest.main()
