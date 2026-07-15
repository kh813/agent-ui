"""
Tests for drive_migrator.py — pure logic functions.

Covers:
  - _parse_folder_id(): Drive URL pattern recognition
  - _predict_method(): migration method prediction from capabilities / ownership
  - _assign_batches(): batch number assignment for task lists
    Includes move_folder tasks (subfolders moved as a unit without recursion into
    their contents) — these are type "folder" and receive batch 0 like create_folder tasks.

Google API, config, and logger are mocked so no network or OAuth is required.

Run:
  venv/bin/pytest python/tests/test_drive_migrator.py -v
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

_SRC_DIR   = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SRC_DIR / "scripts" / "tools"
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_SRC_DIR))

# Prevent _reexec_with_venv() from re-executing us: pretend googleapiclient is installed.
for _mod in [
    "googleapiclient", "googleapiclient.discovery",
    "googleapiclient.http", "googleapiclient.errors",
    "google", "google.oauth2", "google.oauth2.credentials",
    "google_auth_oauthlib", "google_auth_oauthlib.flow",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
]:
    sys.modules.setdefault(_mod, MagicMock())

_config_mock = MagicMock()
_config_mock.OAUTH_CLIENT_ID     = "test_client_id"
_config_mock.OAUTH_CLIENT_SECRET = "test_client_secret"
_config_mock.USER_EMAIL          = "test@example.com"
sys.modules["config"] = _config_mock

_logger_mock = MagicMock()
_logger_mock.get_logger.return_value = MagicMock()
_logger_mock.log_startup = MagicMock()
sys.modules["scripts"]        = MagicMock()
sys.modules["scripts.auth"]   = MagicMock()
sys.modules["scripts.logger"] = _logger_mock

import drive_migrator  # noqa: E402


# ── _parse_folder_id ─────────────────────────────────────────────

class TestParseFolderId:
    """Drive URL patterns → folder ID string."""

    def test_folders_url(self):
        url = "https://drive.google.com/drive/folders/FOLDER_ID_ABC123"
        assert drive_migrator._parse_folder_id(url) == "FOLDER_ID_ABC123"

    def test_folders_url_with_query_string(self):
        url = "https://drive.google.com/drive/folders/FOLDER_ID_XYZ?usp=sharing"
        assert drive_migrator._parse_folder_id(url) == "FOLDER_ID_XYZ"

    def test_folders_url_with_user_prefix(self):
        url = "https://drive.google.com/drive/u/0/folders/FOLDER_U0_ID_QQQ"
        assert drive_migrator._parse_folder_id(url) == "FOLDER_U0_ID_QQQ"

    def test_shared_drives_url(self):
        url = "https://drive.google.com/drive/shared-drives/SHARED_DRV_ID_RRR"
        assert drive_migrator._parse_folder_id(url) == "SHARED_DRV_ID_RRR"

    def test_shared_drives_url_with_query_string(self):
        url = "https://drive.google.com/drive/shared-drives/SHARED_DRV_ID?usp=sharing"
        assert drive_migrator._parse_folder_id(url) == "SHARED_DRV_ID"

    def test_id_query_param(self):
        url = "https://drive.google.com/open?id=OPEN_FOLDER_ID_12345"
        assert drive_migrator._parse_folder_id(url) == "OPEN_FOLDER_ID_12345"

    def test_plain_id_exactly_25_chars(self):
        plain_id = "A" * 25
        assert drive_migrator._parse_folder_id(plain_id) == plain_id

    def test_plain_id_with_hyphens_and_underscores(self):
        plain_id = "AbCdEf-GhIjKl_MnOpQrStUvW"   # 26 chars
        assert drive_migrator._parse_folder_id(plain_id) == plain_id

    def test_whitespace_stripped(self):
        url = "  https://drive.google.com/drive/folders/TRIM_ID_12345678901  "
        assert drive_migrator._parse_folder_id(url) == "TRIM_ID_12345678901"

    def test_short_string_returns_none(self):
        assert drive_migrator._parse_folder_id("ABC123") is None

    def test_empty_string_returns_none(self):
        assert drive_migrator._parse_folder_id("") is None

    def test_unrecognized_url_returns_none(self):
        assert drive_migrator._parse_folder_id("https://example.com/folder") is None

    def test_plain_text_returns_none(self):
        assert drive_migrator._parse_folder_id("not a url at all") is None


# ── _predict_method ──────────────────────────────────────────────

class TestPredictMethod:
    """Migration method prediction from capabilities and file ownership.

    _USER_DOMAIN is "example.com" (derived from mocked USER_EMAIL).
    """

    INTERNAL = [{"emailAddress": "user@example.com"}]
    EXTERNAL  = [{"emailAddress": "user@external.com"}]
    NO_OWNER  = []

    # ── move ──────────────────────────────────────────────────────

    def test_move_for_internal_owner_with_can_move(self):
        caps = {"canMoveItemOutOfDrive": True, "canCopy": True, "canDelete": True}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "move"

    def test_move_when_no_owners(self):
        # Empty owners list → external=False → treated as internal
        caps = {"canMoveItemOutOfDrive": True, "canCopy": True}
        assert drive_migrator._predict_method(caps, self.NO_OWNER) == "move"

    # ── copy+delete ────────────────────────────────────────────────

    def test_copy_delete_for_external_owner_even_if_can_move(self):
        caps = {"canMoveItemOutOfDrive": True, "canCopy": True, "canDelete": True}
        assert drive_migrator._predict_method(caps, self.EXTERNAL) == "copy+delete"

    def test_copy_delete_when_cannot_move_but_can_delete(self):
        caps = {"canMoveItemOutOfDrive": False, "canCopy": True, "canDelete": True}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "copy+delete"

    def test_copy_delete_when_canTrash_is_true(self):
        caps = {"canMoveItemOutOfDrive": False, "canCopy": True, "canDelete": False, "canTrash": True}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "copy+delete"

    def test_copy_delete_when_move_unknown_but_can_delete(self):
        # canMoveItemOutOfDrive absent → None → not True → skip move
        caps = {"canCopy": True, "canDelete": True}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "copy+delete"

    # ── copy-only ─────────────────────────────────────────────────

    def test_copy_only_when_cannot_move_and_cannot_delete(self):
        caps = {"canMoveItemOutOfDrive": False, "canCopy": True, "canDelete": False, "canTrash": False}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "copy-only"

    def test_copy_only_when_move_unknown_and_cannot_delete(self):
        caps = {"canCopy": True, "canDelete": False}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "copy-only"

    # ── will_fail ─────────────────────────────────────────────────

    def test_will_fail_when_cannot_copy_and_cannot_move(self):
        caps = {"canMoveItemOutOfDrive": False, "canCopy": False}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "will_fail"

    def test_will_fail_when_cannot_copy_and_move_unknown(self):
        caps = {"canCopy": False}
        assert drive_migrator._predict_method(caps, self.INTERNAL) == "will_fail"

    def test_will_fail_when_cannot_copy_regardless_of_owner(self):
        caps = {"canCopy": False}
        assert drive_migrator._predict_method(caps, self.EXTERNAL) == "will_fail"


# ── _assign_batches ──────────────────────────────────────────────

class TestAssignBatches:
    """Batch number assignment for task lists."""

    def _folder(self, path="folder"):
        return {"type": "folder", "path": path}

    def _file(self, path="file.pdf"):
        return {"type": "file", "path": path}

    def _shortcut(self, path="link"):
        return {"type": "shortcut", "path": path}

    # ── return value ──────────────────────────────────────────────

    def test_returns_zero_for_empty_list(self):
        assert drive_migrator._assign_batches([], batch_size=100) == 0

    def test_returns_zero_for_folders_only(self):
        tasks = [self._folder("a"), self._folder("b")]
        assert drive_migrator._assign_batches(tasks, batch_size=100) == 0

    def test_returns_one_for_small_file_list(self):
        tasks = [self._file() for _ in range(10)]
        assert drive_migrator._assign_batches(tasks, batch_size=100) == 1

    def test_exact_batch_size_is_one_batch(self):
        tasks = [self._file() for _ in range(100)]
        assert drive_migrator._assign_batches(tasks, batch_size=100) == 1

    def test_one_over_batch_size_creates_second_batch(self):
        tasks = [self._file() for _ in range(101)]
        assert drive_migrator._assign_batches(tasks, batch_size=100) == 2

    # ── batch numbers ─────────────────────────────────────────────

    def test_folders_assigned_batch_zero(self):
        tasks = [self._folder("a"), self._folder("b")]
        drive_migrator._assign_batches(tasks, batch_size=100)
        assert all(t["batch"] == 0 for t in tasks)

    def test_files_start_at_batch_one(self):
        tasks = [self._file("f1"), self._file("f2")]
        drive_migrator._assign_batches(tasks, batch_size=100)
        assert all(t["batch"] == 1 for t in tasks)

    def test_batch_boundary_at_exact_size(self):
        tasks = [self._file() for _ in range(101)]
        drive_migrator._assign_batches(tasks, batch_size=100)
        assert tasks[99]["batch"] == 1
        assert tasks[100]["batch"] == 2

    def test_folders_not_counted_in_file_index(self):
        tasks = [self._folder("root")] + [self._file(f"f{i}") for i in range(101)]
        drive_migrator._assign_batches(tasks, batch_size=100)
        assert tasks[0]["batch"] == 0            # folder
        assert tasks[100]["batch"] == 1          # file index 99 → batch 1
        assert tasks[101]["batch"] == 2          # file index 100 → batch 2

    def test_shortcuts_counted_with_files_for_batching(self):
        # 50 files + 60 shortcuts = 110 items → batch size 100 → 2 batches
        tasks = [self._file() for _ in range(50)] + [self._shortcut() for _ in range(60)]
        total = drive_migrator._assign_batches(tasks, batch_size=100)
        assert total == 2
        assert all(t["batch"] == 1 for t in tasks[:100])   # files 0-49, shortcuts 0-49
        assert all(t["batch"] == 2 for t in tasks[100:])   # shortcuts 50-59

    def test_mixed_types_correct_assignment(self):
        tasks = [self._folder("root")] + [self._file(f"f{i}") for i in range(200)]
        total = drive_migrator._assign_batches(tasks, batch_size=100)
        assert total == 2
        assert tasks[0]["batch"] == 0
        assert all(t["batch"] == 1 for t in tasks[1:101])
        assert all(t["batch"] == 2 for t in tasks[101:])

    def test_move_folder_tasks_get_batch_zero(self):
        # move_folder subfolders are type "folder" → batch 0, same as create_folder.
        # Their contents are not in the task list (not scanned), so they don't affect file batches.
        tasks = [
            {"type": "folder", "method": "move_folder",   "path": "A"},
            {"type": "folder", "method": "create_folder", "path": "B"},
            {"type": "folder", "method": "move_folder",   "path": "B/C"},
        ]
        total = drive_migrator._assign_batches(tasks, batch_size=100)
        assert total == 0
        assert all(t["batch"] == 0 for t in tasks)

    def test_move_folder_does_not_consume_file_batch_index(self):
        # move_folder tasks don't add their (unscanned) contents to the task list,
        # so file batch boundaries should be based only on explicit file tasks.
        tasks = (
            [{"type": "folder", "method": "move_folder", "path": "big"}]
            + [self._file(f"f{i}") for i in range(101)]
        )
        total = drive_migrator._assign_batches(tasks, batch_size=100)
        assert total == 2
        assert tasks[0]["batch"] == 0           # move_folder folder
        assert tasks[100]["batch"] == 1         # file index 99 → batch 1
        assert tasks[101]["batch"] == 2         # file index 100 → batch 2
