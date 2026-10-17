import pytest

from app.config import ConfigError, load_settings


@pytest.fixture(autouse=True)
def supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "pk")


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


@pytest.mark.parametrize("var", ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"])
def test_missing_supabase_raises(monkeypatch, var):
    monkeypatch.setenv("TMDB_TOKEN", "abc")
    monkeypatch.setenv(var, "")
    with pytest.raises(ConfigError, match="SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY não definidos. Veja o README."):
        load_settings(env_file=None)


def test_reads_supabase_settings(monkeypatch):
    monkeypatch.setenv("TMDB_TOKEN", "abc")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sk")
    s = load_settings(env_file=None)
    assert (s.supabase_url, s.supabase_publishable_key) == ("https://proj.supabase.co", "pk")
    assert s.supabase_secret_key.get_secret_value() == "sk"
