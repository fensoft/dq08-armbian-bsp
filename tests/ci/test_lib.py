from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts/ci"))

from _lib import git_commit  # noqa: E402


class GitCommitTests(unittest.TestCase):
    def test_reads_container_owned_worktree_without_global_git_config(self) -> None:
        expected = git_commit(REPOSITORY_ROOT)
        with mock.patch.dict(
            os.environ, {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}, clear=False
        ):
            self.assertEqual(git_commit(REPOSITORY_ROOT), expected)


if __name__ == "__main__":
    unittest.main()
