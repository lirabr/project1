from __future__ import annotations

import re
import unittest
from unittest.mock import patch

import render_visual_pdf as render


class PdfContentTests(unittest.TestCase):
    def test_visual_includes_current_architecture(self):
        document, diagrams, titles = render.build_document()
        content = "\n".join(diagrams)
        self.assertIn("Implemented portfolio and simulator", " ".join(titles))
        for expected in ("Immutable PortfolioTarget", "Transactional ledger events",
                         "Graph checkpoints", "Offline units", "broker-paper sessions"):
            with self.subTest(expected=expected):
                self.assertIn(expected, content.replace("<br/>", " "))
        self.assertEqual(document.count('class="sheet'), len(titles))

    def test_overview_includes_current_capabilities(self):
        document, diagrams, titles = render.build_overview()
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", document))
        for expected in ("PortfolioTarget", "Model Signal", "Bull Analyst", "Bear Analyst",
                         "Portfolio Manager", "partial fills", "frozen models",
                         "read-only", "sentiment", "FinRL-X", "legacy", "UNKNOWN"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertEqual(diagrams, [])
        self.assertEqual(document.count('class="sheet'), len(titles))

    def test_overview_does_not_present_implemented_foundations_as_missing(self):
        document, _, _ = render.build_overview()
        self.assertNotIn("Accurate marked/session accounting and realistic trade exits.", document)
        self.assertNotIn("Approved inference artifacts and time-correct memory.", document)
        self.assertIn("No live broker adapter", document)

    def test_export_does_not_read_setup_folder(self):
        original = render.Path.read_text

        def read_text(path, *args, **kwargs):
            self.assertNotIn("SetUp", path.parts)
            return original(path, *args, **kwargs)

        with patch.object(render.Path, "read_text", read_text):
            for build in (render.build_document, render.build_overview):
                document, _, _ = build()
                self.assertNotIn("SetUp/", document)


if __name__ == "__main__":
    unittest.main()
