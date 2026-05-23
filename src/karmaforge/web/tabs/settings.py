"""Settings tab — API key, model, and browser configuration."""

import os
from pathlib import Path

import gradio as gr


def _find_env_path() -> Path:
    """Find .env file relative to project root."""
    cwd = Path.cwd()
    env = cwd / ".env"
    if env.exists():
        return env
    # Try relative to this file: src/karmaforge/web/tabs/settings.py → project root
    return (Path(__file__).parent.parent.parent.parent.parent / ".env").resolve()


def _read_env(key: str, default: str = "") -> str:
    """Read a value from .env file."""
    env_path = _find_env_path()
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    return os.environ.get(key, default)


def _write_env(key: str, value: str) -> None:
    """Write or update a key in .env file."""
    env_path = _find_env_path()
    lines: list[str] = []
    found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()

    new_line = f"{key}={value}\n"
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            lines[i] = new_line
            found = True
            break
    if not found:
        lines.append(new_line)

    if not env_path.exists():
        env_path.parent.mkdir(parents=True, exist_ok=True)

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.environ[key] = value


def build(shared_state: dict) -> None:
    """Build the Settings tab."""
    with gr.Column():
        gr.Markdown("## Settings")

        api_key_val = _read_env("LLM_API_KEY", os.environ.get("LLM_API_KEY", ""))
        model_val = os.environ.get("LLM_MODEL", "deepseek-v4-pro")
        headless_val = shared_state.get("headless", True)

        api_key = gr.Textbox(
            label="LLM API Key",
            value=api_key_val,
            type="password",
            placeholder="sk-...",
        )
        model = gr.Dropdown(
            label="Model",
            choices=["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat"],
            value=model_val,
        )
        headless = gr.Checkbox(
            label="Playwright Headless Mode",
            value=headless_val,
        )
        save_btn = gr.Button("Save Settings", variant="primary")
        status = gr.Markdown()

        def on_save(key: str, mdl: str, hl: bool) -> str:
            _write_env("LLM_API_KEY", key)
            _write_env("LLM_MODEL", mdl)
            shared_state["headless"] = hl
            shared_state["api_key"] = key
            shared_state["model"] = mdl
            # Re-init LLM client
            if key:
                from ...llm import LLMClient, LLMConfig, LLMProvider
                shared_state["llm"] = LLMClient(LLMConfig(
                    provider=LLMProvider("deepseek"),
                    api_key=key,
                    model=mdl,
                    api_base_url="https://api.deepseek.com/v1",
                    max_tokens=4096,
                    temperature=0.7,
                    request_timeout=60,
                ))
                shared_state["llm_available"] = True
            else:
                shared_state["llm"] = None
                shared_state["llm_available"] = False
            return "Saved."

        save_btn.click(
            fn=on_save,
            inputs=[api_key, model, headless],
            outputs=[status],
        )
