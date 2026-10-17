import pytest

from app.config import ConfigError, load_settings


def test_reads_token_and_defaults(monkeypatch):
    monkeypatch.setenv("TMDB_TOKEN", "abc")
    s = load_settings(env_file=None)
    assert s.tmdb_token.get_secret_value() == "abc"
    assert (s.tmdb_region, s.tmdb_language, s.log_level) == ("BR", "pt-BR", "INFO")


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="TMDB_TOKEN não definido. Copie .env.example para .env e preencha o token."):
        load_settings(env_file=None)


def test_blank_token_raises(monkeypatch):
    monkeypatch.setenv("TMDB_TOKEN", "   ")
    with pytest.raises(ConfigError):
        load_settings(env_file=None)
