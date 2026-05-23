"""Tests for KarmaForge web interface (Gradio app)."""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestTheme:
    """Theme configuration tests."""

    def test_create_theme(self):
        from karmaforge.web.theme import create_theme
        theme = create_theme()
        assert theme is not None

    def test_create_theme_is_gradio_theme(self):
        import gradio as gr
        from karmaforge.web.theme import create_theme
        theme = create_theme()
        assert isinstance(theme, gr.Theme)


class TestCreateApp:
    """App bootstrap tests."""

    def test_create_app_returns_blocks(self):
        import gradio as gr
        from karmaforge.web.app import create_app
        app = create_app()
        assert isinstance(app, gr.Blocks)
        assert hasattr(app, "theme")
        assert hasattr(app, "css")

    def test_app_title(self):
        from karmaforge.web.app import create_app
        app = create_app()
        assert "KarmaForge" in app.title


class TestSettingsTab:
    """Settings tab tests."""

    def test_read_env_key(self):
        from karmaforge.web.tabs.settings import _read_env
        # Should return default when no .env
        result = _read_env("NONEXISTENT_KEY_12345", "fallback")
        assert result == "fallback"

    def test_write_and_read_env(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        # Patch the env path finder
        from karmaforge.web.tabs import settings

        original = settings._find_env_path
        settings._find_env_path = lambda: env_path
        try:
            settings._write_env("TEST_KEY", "test_value_123")
            result = settings._read_env("TEST_KEY", "")
            assert result == "test_value_123"
            assert env_path.exists()
            content = env_path.read_text(encoding="utf-8-sig")
            assert "TEST_KEY=test_value_123" in content
        finally:
            settings._find_env_path = original

    def test_write_env_updates_existing(self, tmp_path):
        from karmaforge.web.tabs.settings import _write_env, _read_env
        import karmaforge.web.tabs.settings as settings_mod

        env_path = tmp_path / ".env"
        env_path.write_text("TEST_KEY=old_value\nOTHER_KEY=keep_me\n", encoding="utf-8")

        original = settings_mod._find_env_path
        settings_mod._find_env_path = lambda: env_path
        try:
            _write_env("TEST_KEY", "new_value")
            result = _read_env("TEST_KEY", "")
            assert result == "new_value"
            content = env_path.read_text(encoding="utf-8-sig")
            assert "OTHER_KEY=keep_me" in content
        finally:
            settings_mod._find_env_path = original


class TestLoadDotenv:
    """.env loading tests."""

    def test_load_dotenv_from_project_root(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        env_path.write_text("KF_TEST_VAR=hello_world\n", encoding="utf-8")

        from karmaforge.web import app as web_app
        original = web_app.PROJECT_ROOT
        web_app.PROJECT_ROOT = tmp_path
        try:
            web_app._load_dotenv()
            assert os.environ.get("KF_TEST_VAR") == "hello_world"
        finally:
            web_app.PROJECT_ROOT = original
            os.environ.pop("KF_TEST_VAR", None)

    def test_load_dotenv_handles_missing_file(self, tmp_path):
        from karmaforge.web.app import _load_dotenv
        # Should not raise
        _load_dotenv()

    def test_load_dotenv_skips_comments(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "# This is a comment\nKF_COMMENT_TEST=value\n",
            encoding="utf-8",
        )

        from karmaforge.web import app as web_app
        original = web_app.PROJECT_ROOT
        web_app.PROJECT_ROOT = tmp_path
        try:
            web_app._load_dotenv()
            assert os.environ.get("KF_COMMENT_TEST") == "value"
        finally:
            web_app.PROJECT_ROOT = original
            os.environ.pop("KF_COMMENT_TEST", None)


class TestLoadSubreddits:
    """Subreddit list loading tests."""

    def test_load_subreddit_list_no_db(self):
        from karmaforge.web.app import _load_subreddit_list
        # Should return empty list gracefully when no DB
        result = _load_subreddit_list()
        assert isinstance(result, list)


class TestFeedbackLoading:
    """Feedback loading tests."""

    def test_load_feedback_empty(self, tmp_path, monkeypatch):
        from karmaforge.web import app as web_app
        feedback_path = tmp_path / "feedback.jsonl"
        monkeypatch.setattr(web_app, "DEFAULT_FEEDBACK", str(feedback_path))
        result = web_app._load_feedback_entries()
        assert result == []

    def test_load_feedback_with_entries(self, tmp_path, monkeypatch):
        from karmaforge.web import app as web_app
        feedback_path = tmp_path / "feedback.jsonl"
        entries = [
            {"generation_id": "gen_01", "performance": "viral"},
            {"generation_id": "gen_02", "performance": "failed"},
        ]
        with open(feedback_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        monkeypatch.setattr(web_app, "DEFAULT_FEEDBACK", str(feedback_path))
        result = web_app._load_feedback_entries()
        assert len(result) == 2
        assert result[0]["generation_id"] == "gen_01"

    def test_load_feedback_skips_invalid_json(self, tmp_path, monkeypatch):
        from karmaforge.web import app as web_app
        feedback_path = tmp_path / "feedback.jsonl"
        with open(feedback_path, "w", encoding="utf-8") as f:
            f.write('{"valid": "json"}\n')
            f.write("this is not json\n")
            f.write('{"another": "valid"}\n')

        monkeypatch.setattr(web_app, "DEFAULT_FEEDBACK", str(feedback_path))
        result = web_app._load_feedback_entries()
        assert len(result) == 2


class TestGenerationFileLoading:
    """Generation file listing tests."""

    def test_list_generations_empty(self, tmp_path, monkeypatch):
        from karmaforge.web import app as web_app
        gen_dir = tmp_path / "generations"
        gen_dir.mkdir()
        monkeypatch.setattr(web_app, "DEFAULT_GENERATIONS", str(gen_dir))
        result = web_app._list_generation_files()
        assert result == []

    def test_list_generations_with_files(self, tmp_path, monkeypatch):
        from karmaforge.web import app as web_app
        gen_dir = tmp_path / "generations"
        gen_dir.mkdir()
        (gen_dir / "gen_aaa.json").write_text(json.dumps({
            "generation_id": "gen_aaa",
            "selected_title": {"title": "Test Title", "score": 85},
        }), encoding="utf-8")
        (gen_dir / "gen_bbb.json").write_text(json.dumps({
            "generation_id": "gen_bbb",
            "selected_title": {"title": "Another", "score": 70},
        }), encoding="utf-8")

        monkeypatch.setattr(web_app, "DEFAULT_GENERATIONS", str(gen_dir))
        result = web_app._list_generation_files()
        assert len(result) == 2

    def test_list_generations_skips_corrupt(self, tmp_path, monkeypatch):
        from karmaforge.web import app as web_app
        gen_dir = tmp_path / "generations"
        gen_dir.mkdir()
        (gen_dir / "gen_good.json").write_text(json.dumps({"generation_id": "good"}), encoding="utf-8")
        (gen_dir / "gen_bad.json").write_text("not json", encoding="utf-8")

        monkeypatch.setattr(web_app, "DEFAULT_GENERATIONS", str(gen_dir))
        result = web_app._list_generation_files()
        assert len(result) == 1


class TestFormatDetail:
    """History detail formatting tests."""

    def test_format_gen_detail_basic(self):
        from karmaforge.web.app import _format_gen_detail
        gen = {
            "generation_id": "gen_test",
            "created_at": "2026-05-23T12:00:00+00:00",
            "matched_subreddits": [{"subreddit": "python"}],
            "selected_title": {"title": "My Test Title", "score": 92},
            "candidate_titles": [
                {"title": "My Test Title", "score": 92, "hook_type": "tutorial_howto"},
                {"title": "Another", "score": 75, "hook_type": "story_opener"},
            ],
        }
        result = _format_gen_detail(gen, None)
        assert "gen_test" in result
        assert "My Test Title" in result
        assert "r/python" in result

    def test_format_gen_detail_with_body(self):
        from karmaforge.web.app import _format_gen_detail
        gen = {
            "generation_id": "gen_body",
            "created_at": "2026-05-23T12:00:00+00:00",
            "matched_subreddits": [],
            "body": "This is a long body post about Python.",
            "self_check": {"passed": True},
        }
        result = _format_gen_detail(gen, None)
        assert "Python" in result
        assert "Passed" in result

    def test_format_gen_detail_with_tracking(self):
        from karmaforge.web.app import _format_gen_detail
        gen = {
            "generation_id": "gen_tracked",
            "created_at": "2026-05-23T12:00:00+00:00",
            "matched_subreddits": [],
        }
        fb = {
            "actual_upvotes": 500, "subreddit_median": 50,
            "num_comments": 30, "upvote_ratio": 0.94, "performance": "viral",
        }
        result = _format_gen_detail(gen, fb)
        assert "500" in result
        assert "viral" in result
        assert "30" in result


class TestLLMInit:
    """LLM initialization tests."""

    def test_init_llm_no_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        from karmaforge.web.app import _init_llm
        client, available = _init_llm()
        assert client is None
        assert available is False

    def test_init_llm_with_key(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test-key-12345")
        monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
        from karmaforge.web.app import _init_llm
        client, available = _init_llm()
        assert available is True
        assert client is not None
