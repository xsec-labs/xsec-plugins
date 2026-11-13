from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_submodule_beta_pointers as check  # noqa: E402

BROWSER = "plugins/com.xsec.workspace.browser"
JWT = "plugins/com.xsec.jwt-analysis"
OLD = "a" * 40
NEW = "b" * 40


def write_gitmodules(directory: str, text: str) -> Path:
    root = Path(directory)
    (root / ".gitmodules").write_text(text, encoding="utf-8")
    return root


class SubmoduleBetaPointerTests(unittest.TestCase):
    def test_reads_every_submodule_and_its_beta_branch_from_gitmodules(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-submodule-pointers-") as directory:
            root = write_gitmodules(
                directory,
                "[submodule \"plugins/com.xsec.workspace.browser\"]\n"
                f"\tpath = {BROWSER}\n"
                "\turl = https://github.com/xsec-labs/xsec-plugin-browser.git\n"
                "\tbranch = beta\n"
                "[submodule \"plugins/com.xsec.jwt-analysis\"]\n"
                f"\tpath = {JWT}\n"
                "\turl = https://github.com/xsec-labs/xsec-plugin-jwt-analysis.git\n"
                "\tbranch = beta\n",
            )
            self.assertEqual(
                check.submodule_branches(root),
                [
                    (BROWSER, "https://github.com/xsec-labs/xsec-plugin-browser.git", "beta"),
                    (JWT, "https://github.com/xsec-labs/xsec-plugin-jwt-analysis.git", "beta"),
                ],
            )

    def test_submodule_without_a_beta_branch_fails_instead_of_being_skipped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-submodule-pointers-") as directory:
            root = write_gitmodules(
                directory,
                "[submodule \"plugins/com.xsec.workspace.browser\"]\n"
                f"\tpath = {BROWSER}\n"
                "\turl = https://github.com/xsec-labs/xsec-plugin-browser.git\n"
                "\tbranch = beta\n"
                "[submodule \"plugins/com.xsec.jwt-analysis\"]\n"
                f"\tpath = {JWT}\n"
                "\turl = https://github.com/xsec-labs/xsec-plugin-jwt-analysis.git\n",
            )
            with self.assertRaisesRegex(ValueError, "has no branch"):
                check.submodule_branches(root)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check.main(["--root", str(root)]), 1)

    def test_reports_each_pointer_that_is_not_the_beta_head(self) -> None:
        problems = check.mismatches(
            pointers={BROWSER: OLD, JWT: NEW},
            heads={BROWSER: NEW, JWT: NEW},
        )
        self.assertEqual(problems, [f"{BROWSER}: pointer {OLD} is not the Beta head {NEW}"])

    def test_missing_pointer_is_a_mismatch(self) -> None:
        self.assertEqual(
            check.mismatches(pointers={}, heads={BROWSER: NEW}),
            [f"{BROWSER}: pointer None is not the Beta head {NEW}"],
        )

    def test_matching_pointers_pass(self) -> None:
        self.assertEqual(check.mismatches(pointers={BROWSER: NEW}, heads={BROWSER: NEW}), [])


if __name__ == "__main__":
    unittest.main()
