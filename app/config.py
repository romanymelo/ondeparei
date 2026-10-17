from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

MISSING_TOKEN_MESSAGE = "TMDB_TOKEN não definido. Copie .env.example para .env e preencha o token."
MISSING_SUPABASE_MESSAGE = "SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY não definidos. Veja o README."


class ConfigError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    tmdb_token: SecretStr
    tmdb_region: str = "BR"
    tmdb_language: str = "pt-BR"
    log_level: str = "INFO"
    database_path: str = "data/catalogo.db"  # só a importação usa (fase 2b)
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: SecretStr | None = None  # só para a importação e os testes de contrato


def load_settings(env_file: str | None = ".env") -> Settings:
    try:
        settings = Settings(_env_file=env_file)
    except ValidationError as exc:
        raise ConfigError(MISSING_TOKEN_MESSAGE) from exc
    if not settings.tmdb_token.get_secret_value().strip():
        raise ConfigError(MISSING_TOKEN_MESSAGE)
    if not settings.supabase_url.strip() or not settings.supabase_publishable_key.strip():
        raise ConfigError(MISSING_SUPABASE_MESSAGE)
    return settings
