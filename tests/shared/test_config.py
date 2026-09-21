"""Proves Phase 0's Local Execution Gate (Configuration_and_Secrets.md)."""

from __future__ import annotations

import pytest

from sentinel.shared.config import ConfigurationError, MANDATORY_ENV_VARS, load_settings

FULL_ENV = {
    "GITHUB_TOKEN": "ghp_test",
    "GITHUB_WEBHOOK_SECRET": "whsec_test",
    "GITHUB_OAUTH_CLIENT_ID": "client_id",
    "GITHUB_OAUTH_CLIENT_SECRET": "client_secret",
    "DATABASE_PATH": "/tmp/sentinel.sqlite",
}


def test_loads_successfully_when_all_mandatory_vars_present() -> None:
    settings = load_settings(env=FULL_ENV)

    assert settings.github_token == "ghp_test"
    assert settings.database_path == "/tmp/sentinel.sqlite"
    assert settings.optional == {}


def test_captures_optional_vars_when_present() -> None:
    env = {**FULL_ENV, "OPENAI_API_KEY": "sk-test", "OLLAMA_BASE_URL": "http://localhost:11434"}

    settings = load_settings(env=env)

    assert settings.optional == {"OPENAI_API_KEY": "sk-test", "OLLAMA_BASE_URL": "http://localhost:11434"}


@pytest.mark.parametrize("missing_var", MANDATORY_ENV_VARS)
def test_refuses_to_start_when_a_single_mandatory_var_is_missing(missing_var: str) -> None:
    env = {k: v for k, v in FULL_ENV.items() if k != missing_var}

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings(env=env)

    assert missing_var in str(exc_info.value)


def test_reports_every_missing_mandatory_var_at_once() -> None:
    with pytest.raises(ConfigurationError) as exc_info:
        load_settings(env={})

    message = str(exc_info.value)
    for var in MANDATORY_ENV_VARS:
        assert var in message


def test_secret_values_excludes_empty_optional_entries() -> None:
    settings = load_settings(env=FULL_ENV)

    assert "" not in settings.secret_values()
    assert "ghp_test" in settings.secret_values()
