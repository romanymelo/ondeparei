from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

MISSING_TOKEN_MESSAGE = "TMDB_TOKEN não definido. Copie .env.example para .env e preencha o token."


class ConfigError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    tmdb_token: SecretStr
    tmdb_region: str = "BR"
    tmdb_language: str = "pt-BR"
    log_level: str = "INFO"


def load_settings(env_file: str | None = ".env") -> Settings:
    try:
        settings = Settings(_env_file=env_file)
    except ValidationError as exc:
        raise ConfigError(MISSING_TOKEN_MESSAGE) from exc
    if not settings.tmdb_token.get_secret_value().strip():
        raise ConfigError(MISSING_TOKEN_MESSAGE)
    return settings
