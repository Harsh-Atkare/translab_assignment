import subprocess
import sys
import textwrap


def _run(script: str, cwd, env=None) -> str:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_dotenv_is_read_on_import(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from-dotenv\n")

    import os

    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    env["PYTHONPATH"] = str(tmp_path.parent) + ":" + os.getcwd()

    out = _run(
        """
        from app.config import get_settings
        print(get_settings().gemini_api_key)
        """,
        cwd=tmp_path,
        env=env,
    )
    assert out == "from-dotenv"


def test_real_env_var_beats_dotenv(tmp_path):

    (tmp_path / ".env").write_text("GEMINI_API_KEY=from-dotenv\n")

    import os

    env = dict(os.environ)
    env["GEMINI_API_KEY"] = "from-environment"
    env["PYTHONPATH"] = os.getcwd()

    out = _run(
        """
        from app.config import get_settings
        print(get_settings().gemini_api_key)
        """,
        cwd=tmp_path,
        env=env,
    )
    assert out == "from-environment"


def test_missing_dotenv_is_not_an_error(tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    env["PYTHONPATH"] = os.getcwd()

    out = _run(
        """
        from app.config import get_settings
        print(repr(get_settings().gemini_api_key))
        """,
        cwd=tmp_path,
        env=env,
    )
    assert out == "''"
