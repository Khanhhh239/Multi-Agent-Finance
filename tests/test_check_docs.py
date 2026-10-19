"""Behavior checks for the offline documentation gate."""

from pathlib import Path
import tempfile
import unittest

from scripts.checks.check_docs import check_repository, local_links


class DocumentationChecks(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)

    def write(self, name, text=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self, required=()):
        return check_repository(self.root, required)

    def test_relative_root_fragment_and_directory_targets(self):
        self.write("docs/README.md", "[relative](../README.md#section)\n"
                   "[root](/README.md)\n[folder](../docs/)\n")
        self.write("README.md")
        self.assertEqual(self.check(), (2, []))

    def test_missing_required_document_fails(self):
        self.assertEqual(self.check(("AGENTS.md",))[1],
                         ["Missing required document: AGENTS.md"])

    def test_broken_link_reports_file_and_line(self):
        self.write("README.md", "# Heading\n\n[missing](gone.md)\n")
        errors = self.check()[1]
        self.assertEqual(errors, ["README.md:3: missing local target: gone.md"])

    def test_examples_comments_and_remote_links_are_not_files(self):
        self.write("README.md", "```md\n[example](absent.md)\n```\n"
                   "~~~md\n[example](absent.md)\n~~~\n"
                   "`[example](absent.md)`\n<!-- [example](absent.md) -->\n"
                   "[web](https://example.com) [mail](mailto:x@example.com)\n"
                   "[anchor](#unknown) [remote](//example.com/path)\n")
        self.assertEqual(self.check()[1], [])

    def test_code_masking_preserves_error_line_number(self):
        text = "```md\n[fake](a.md)\n```\n[real](b.md)\n"
        self.assertEqual(list(local_links(text)), [(4, "b.md")])

    def test_reference_images_spaces_unicode_and_parentheses(self):
        self.write("tài liệu (T1).md")
        self.write("README.md", '[read](<tài liệu (T1).md> "Title")\n'
                   "![image](t%C3%A0i%20li%E1%BB%87u%20%28T1%29.md)\n"
                   "[ref]: <tài liệu (T1).md>\n[missing]: gone.md\n")
        self.assertEqual(self.check()[1],
                         ["README.md:4: missing local target: gone.md"])
        self.assertEqual(list(local_links("[x](report(T1).md)")),
                         [(1, "report(T1).md")])

    def test_repository_escape_is_rejected_even_if_file_exists(self):
        self.write("README.md", "[outside](../outside.md)")
        self.assertIn("link escapes repository", self.check()[1][0])

    def test_generated_data_and_environment_are_not_scanned(self):
        for name in ["data/T1/raw/README.md", "data/T1/interim/README.md",
                     "data/processed/README.md", ".venv/README.md",
                     "node_modules/pkg/README.md", ".git/README.md"]:
            self.write(name, "[missing](not-present.md)")
        self.write("data/T1/README.md")
        self.write("docs/archive/old.md", "[missing](not-present.md)")
        count, errors = self.check()
        self.assertEqual(count, 2)
        self.assertEqual(len(errors), 1)  # Archive links still participate.

    def test_missing_data_link_is_not_silently_exempted(self):
        self.write("README.md", "[raw](data/T1/raw/local-only.csv)")
        self.assertIn("missing local target", self.check()[1][0])

    def test_invalid_utf8_fails_with_document_name(self):
        path = self.write("bad.md")
        path.write_bytes(b"\xff\xfe")
        self.assertIn("bad.md: cannot read UTF-8", self.check()[1][0])


if __name__ == "__main__":
    unittest.main()
