"""Documentation links have to work on somebody else's machine.

The repository moved out of `C:/python/old/restart/` and eleven documents kept
linking into it, so every one of those links was dead — 65 occurrences, and the
targets all existed here at the same relative path. Then the same check, widened,
found 32 *relative* links whose target existed but whose base directory was
wrong: written as if the linking file sat at the repository root or in `docs/`.
Nothing checked either, because a link is text.

Three rules, all checkable, all about the reader rather than the author's machine:

* a markdown link target is a relative path or an `http(s)` URL, never an
  absolute one — `C:/...`, `C:\\...` or `file:///...`;
* the old checkout's name does not appear in a link target at all;
* every relative link under `docs/` resolves to a file that exists, and every
  document is valid UTF-8 (one archive was written by a tool that emitted cp1252
  punctuation into a UTF-8 file, so it rendered as `�` for anyone who read it).

Prose that *quotes* the stale prefix (the plan documents that record this very
finding, and `server/data_fixtures/LATEST_REFRESH.json`, which is a log the
content gate reinterprets against this checkout) is deliberately out of scope:
`](C:/...` is the shape that breaks, and that is what this refuses.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKIP_DIRECTORIES = {".git", ".venv", "tmp", "node_modules", ".claude"}

# `[label](target)` and `![alt](target)`.
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
ABSOLUTE_TARGET = re.compile(r"^(?:[A-Za-z]:[\\/]|file://|\\\\)")
HTTPS_TARGET = re.compile(r"^https?://", re.IGNORECASE)
ANCHOR = re.compile(r"^#")


def markdown_files():
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        yield path


def documentation_files():
    for path in markdown_files():
        if "docs" in path.relative_to(REPO_ROOT).parts:
            yield path


class TestDocumentationLinksArePortable(unittest.TestCase):
    def test_no_markdown_link_points_at_an_absolute_path(self) -> None:
        offenders = []
        for path in markdown_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for target in LINK.findall(line):
                    if HTTPS_TARGET.match(target) or ANCHOR.match(target):
                        continue
                    if ABSOLUTE_TARGET.match(target):
                        offenders.append(
                            "%s:%d -> %s" % (path.relative_to(REPO_ROOT).as_posix(), line_number, target)
                        )

        self.assertEqual(
            [], offenders,
            "a link into an absolute path is dead for everyone else; make it relative:\n"
            + "\n".join(offenders),
        )

    def test_no_markdown_link_names_the_old_checkout(self) -> None:
        offenders = []
        for path in markdown_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for target in LINK.findall(line):
                    if "old/restart" in target.replace("\\", "/"):
                        offenders.append(
                            "%s:%d -> %s" % (path.relative_to(REPO_ROOT).as_posix(), line_number, target)
                        )

        self.assertEqual([], offenders, "\n".join(offenders))

    def test_every_relative_link_under_docs_resolves(self) -> None:
        """Every relative link, not only the ones a sweep has already touched.

        This is the rule that found 32 links pointing at files that exist but
        were written from the wrong directory — a link can be *absolute-correct*
        and still land nowhere.
        """
        missing = []
        for path in documentation_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for target in LINK.findall(line):
                    if HTTPS_TARGET.match(target) or ANCHOR.match(target):
                        continue
                    resolved = (path.parent / target.split("#", 1)[0]).resolve()
                    if not resolved.exists():
                        missing.append(
                            "%s:%d -> %s" % (path.relative_to(REPO_ROOT).as_posix(), line_number, target)
                        )

        self.assertEqual([], missing, "these links land nowhere:\n" + "\n".join(missing))

    def test_every_document_is_valid_utf8(self) -> None:
        """A cp1252 byte in a UTF-8 file renders as `�` for every reader."""
        broken = []
        for path in markdown_files():
            try:
                path.read_bytes().decode("utf-8")
            except UnicodeDecodeError as error:
                broken.append("%s (%s)" % (path.relative_to(REPO_ROOT).as_posix(), error.reason))

        self.assertEqual([], broken, "not UTF-8:\n" + "\n".join(broken))


if __name__ == "__main__":
    unittest.main()
