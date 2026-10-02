"""Release changelog generated from commit messages (.github/scripts/changelog.py)."""

import importlib.util
import os

_path = os.path.join(os.path.dirname(__file__), "..", ".github", "scripts", "changelog.py")
_spec = importlib.util.spec_from_file_location("changelog", _path)
changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog)


def test_features_with_their_bullets():
    text = changelog.build([
        ("Mod icons in the list #minor", "- Icons from Modrinth\n- Cached on disk\n\nSome paragraph.\n"),
        ("Fix crash", ""),
    ])
    assert text.splitlines()[2:] == [
        "- Mod icons in the list",
        "  - Icons from Modrinth",
        "  - Cached on disk",
        "- Fix crash",
    ]


def test_internal_commits_are_skipped():
    text = changelog.build([("tests: share one window", "- detail"), ("release: tweak workflow", ""),
                            ("ci: cache", ""), ("Real change", "")])
    assert "share one window" not in text and "workflow" not in text
    assert "- Real change" in text


def test_markers_removed_only_when_standalone():
    text = changelog.build([("Big rewrite #MAJOR", "- explains #minor/#major in text")])
    assert "- Big rewrite\n" in text
    assert "#minor/#major" in text


def test_co_author_lines_are_dropped():
    text = changelog.build([("Change", "- item\n- Co-Authored-By: someone <x@y.z>")])
    assert "Co-Authored-By" not in text and "  - item" in text


def test_empty_release_still_has_a_line():
    assert "Maintenance" in changelog.build([("tests: only tests", "")])
