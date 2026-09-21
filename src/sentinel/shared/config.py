"""Configuration loading and the local execution gate.

Per docs/03_API/Configuration_and_Secrets.md: a secret is read from its
environment variable; SentinelAI refuses to start rather than run in a
partially-functional state when a *mandatory* secret is missing. AI
provider keys and security-intelligence credentials are optional — their
absence degrades gracefully instead (AI_Agent_Architecture.md §8), so they
are not part of the startup gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

MANDATORY_ENV_VARS: tuple[str, ...] = (
    "GITHUB_TOKEN",
    "GITHUB_WEBHOOK_SECRET",
    "GITHUB_OAUTH_CLIENT_ID",
    "GITHUB_OAUTH_CLIENT_SECRET",
    "DATABASE_PATH",
)

# Present only if the operator configured that specific optional capability.
OPTIONAL_ENV_VARS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_BASE_URL",
)


class ConfigurationError(RuntimeError):
    """Raised when a mandatory secret/config value is missing at startup.

    Per Configuration_and_Secrets.md's Local Execution Gate: this must stop
    the application from starting, never let it run in a partially-usable
    state.
    """


@dataclass(frozen=True)
class Settings:
    github_token: str
    github_webhook_secret: str
    github_oauth_client_id: str
    github_oauth_client_secret: str
    database_path: str
    optional: dict[str, str] = field(default_factory=dict)

    def secret_values(self) -> tuple[str, ...]:
        """Every raw secret value currently loaded.

        Used exclusively by the logging redaction filter to scrub these
        values out of any log line — never the other way around
        (Observability_and_Logging.md's "never logged" table).
        """
        values = [
            self.github_token,
            self.github_webhook_secret,
            self.github_oauth_client_id,
            self.github_oauth_client_secret,
        ]
        values.extend(v for v in self.optional.values() if v)
        return tuple(v for v in values if v)


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Reads and validates configuration from the environment.

    Raises ConfigurationError naming every missing mandatory variable at
    once (not just the first one found), so an operator fixing the .env
    file doesn't have to restart repeatedly to discover each missing value
    one at a time.
    """
    source = env if env is not None else os.environ

    missing = [name for name in MANDATORY_ENV_VARS if not source.get(name)]
    if missing:
        raise ConfigurationError(
            "Missing mandatory configuration: "
            + ", ".join(missing)
            + ". SentinelAI will not start in a partially-functional state "
            "(Configuration_and_Secrets.md's Local Execution Gate)."
        )

    optional = {name: source[name] for name in OPTIONAL_ENV_VARS if source.get(name)}

    return Settings(
        github_token=source["GITHUB_TOKEN"],
        github_webhook_secret=source["GITHUB_WEBHOOK_SECRET"],
        github_oauth_client_id=source["GITHUB_OAUTH_CLIENT_ID"],
        github_oauth_client_secret=source["GITHUB_OAUTH_CLIENT_SECRET"],
        database_path=source["DATABASE_PATH"],
        optional=optional,
    )
