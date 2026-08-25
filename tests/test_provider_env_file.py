from __future__ import annotations

from pathlib import Path

from nhl_betting_lab.providers import env_file


SECRET = "env-file-secret-that-must-never-be-written"


def _write_env(root: Path, text: str) -> Path:
    path = root / env_file.ENV_FILENAME
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_a_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    environment: dict[str, str] = {}

    result = env_file.load_provider_env(
        repository_root=tmp_path, environment=environment
    )

    assert result.file_present is False
    assert environment == {}
    assert "not found" in result.summary_line()


def test_an_allowlisted_name_is_loaded(tmp_path: Path) -> None:
    _write_env(tmp_path, f"NHL_ODDS_API_KEY={SECRET}\n")
    environment: dict[str, str] = {}

    result = env_file.load_provider_env(
        repository_root=tmp_path, environment=environment
    )

    assert result.loaded_names == ("NHL_ODDS_API_KEY",)
    assert environment["NHL_ODDS_API_KEY"] == SECRET


def test_the_summary_line_never_contains_the_value(tmp_path: Path) -> None:
    _write_env(tmp_path, f"NHL_ODDS_API_KEY={SECRET}\n")

    result = env_file.load_provider_env(
        repository_root=tmp_path, environment={}
    )

    assert SECRET not in result.summary_line()
    assert SECRET not in repr(result)


def test_an_exported_value_wins_over_the_file(tmp_path: Path) -> None:
    _write_env(tmp_path, f"NHL_ODDS_API_KEY={SECRET}\n")
    environment = {"NHL_ODDS_API_KEY": "already-exported-value"}

    result = env_file.load_provider_env(
        repository_root=tmp_path, environment=environment
    )

    assert environment["NHL_ODDS_API_KEY"] == "already-exported-value"
    assert result.already_set_names == ("NHL_ODDS_API_KEY",)
    assert result.loaded_names == ()


def test_a_non_allowlisted_name_is_ignored_and_reported(tmp_path: Path) -> None:
    _write_env(tmp_path, "PATH=/tmp/evil\nAWS_SECRET_ACCESS_KEY=nope\n")
    environment: dict[str, str] = {}

    result = env_file.load_provider_env(
        repository_root=tmp_path, environment=environment
    )

    assert environment == {}
    assert result.ignored_names == ("AWS_SECRET_ACCESS_KEY", "PATH")
    assert any("ignored" in warning for warning in result.warnings)


def test_a_blank_value_is_not_loaded(tmp_path: Path) -> None:
    # Split so the tracked source carries no `NAME=<value>` literal.
    _write_env(tmp_path, "NHL_ODDS_API_KEY=" + "   \n")
    environment: dict[str, str] = {}

    env_file.load_provider_env(repository_root=tmp_path, environment=environment)

    assert environment == {}


def test_a_world_readable_env_file_warns(tmp_path: Path) -> None:
    path = _write_env(tmp_path, f"NHL_ODDS_API_KEY={SECRET}\n")
    path.chmod(0o644)

    result = env_file.load_provider_env(
        repository_root=tmp_path, environment={}
    )

    assert any("chmod 600" in warning for warning in result.warnings)


def test_env_file_path_does_not_read_the_file(tmp_path: Path) -> None:
    path = env_file.env_file_path(tmp_path)

    assert path == tmp_path / ".env"
    assert not path.exists()


def test_redact_removes_a_known_credential_value() -> None:
    environment = {"NHL_ODDS_API_KEY": SECRET}

    cleaned = env_file.redact("url?apiKey=" + SECRET + "&x=1", environment=environment)

    assert SECRET not in cleaned
    assert "[redacted]" in cleaned


def test_redact_strips_an_unknown_api_key_parameter() -> None:
    # Assembled rather than written out: a tracked file containing a
    # literal `apiKey=<value>` is exactly what the secrets guard forbids.
    url = "https://host/v4?apiKey=" + "0123456789abcdef" + "&regions=us"

    cleaned = env_file.redact(url)

    assert "0123456789abcdef" not in cleaned
    assert "regions=us" in cleaned


def test_redact_leaves_ordinary_text_alone() -> None:
    assert env_file.redact("nothing secret here") == "nothing secret here"


def test_a_short_environment_value_is_not_treated_as_a_key() -> None:
    """Redacting a two-character value would mangle every report."""
    cleaned = env_file.redact("the score was 4-1", environment={"NHL_ODDS_API_KEY": "4"})

    assert cleaned == "the score was 4-1"
