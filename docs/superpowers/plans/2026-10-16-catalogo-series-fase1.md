# Catálogo de Séries (Fase 1) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App web pessoal (FastAPI + Jinja2 + HTMX) que lista as séries disponíveis agora no streaming do Brasil via API da TMDB, com filtros, busca por nome e página de detalhes.

**Architecture:** Três camadas, cada uma conhece só a de baixo: `routes.py` (HTTP do navegador, escolhe página inteira ou fragmento HTMX) → `catalog.py` (orquestra chamadas; usa `filters.py` e `mappers.py`, funções puras) → `tmdb/client.py` (HTTP com a TMDB + `tmdb/cache.py`). Refinamento em relação à spec §5: a lógica que a spec põe em `catalog.py` foi dividida em `filters.py` (URL → `Filters` → parâmetros), `mappers.py` (JSON → modelos) e `catalog.py` (serviço), para manter os arquivos focados.

**Tech Stack:** Python 3.12, uv, FastAPI, uvicorn, Jinja2, HTMX 2.x, httpx (async), pydantic-settings, pytest, pytest-asyncio, respx.

**Spec:** `docs/superpowers/specs/2026-10-16-catalogo-series-design.md` (leia junto com este plano).

## Global Constraints

- Python ≥ 3.12; dependências só via `uv add` e exatamente as da spec §5; comandos sempre via `uv run ...`.
- Projeto em `C:\Projetos\catalogo-series` (fora do Google Drive). Ambiente Windows.
- Região e idioma vêm de `Settings` (`TMDB_REGION` padrão `BR`, `TMDB_LANGUAGE` padrão `pt-BR`); nunca fixos fora dos defaults do `Settings`.
- O token só vai no cabeçalho `Authorization: Bearer <TMDB_TOKEN>`. Nunca em HTML, URL, logs ou fixtures.
- TMDB: base `https://api.themoviedb.org/3`. Imagens: `https://image.tmdb.org/t/p/{tamanho}{path}`. Tamanhos: grade `w342`, pôster do detalhe `w500`, fundo `w1280`, logos `w92`, elenco `w185`, temporadas `w185`.
- Timeout de 10 s. No 429, uma nova tentativa após `Retry-After` (padrão 1 s, máximo 2 s).
- Validade do cache: listas 24 h; detalhes e onde assistir 6 h; catálogo e busca 1 h. Máximo de 1000 entradas.
- Testes nunca acessam a internet (respx). O teste de contrato roda só com `uv run pytest -m tmdb`.
- Identificadores de código em inglês. Textos da interface, nomes de templates e parâmetros de URL em português: `servicos`, `tipos`, `generos`, `ano_de`, `ano_ate`, `nota`, `ordem`, `pagina`, `q`.
- Nenhum JavaScript próprio além do HTMX 2.x local (`app/static/htmx.min.js`, sem CDN). Única exceção: o `onclick` do "← Voltar".
- Fragmentos HTMX respondem com status 200, inclusive os de erro.
- Nome provisório do app: **SériesBR**, na constante `APP_NAME` de `app/templating.py`.
- Tema escuro (mockup aprovado): `--bg #0f1115`, `--panel #171a21`, `--line #2a2f3a`, `--text #e8eaf0`, `--muted #8b93a7`, `--accent #f5c518`. Layout responsivo; a largura de referência do celular é 375 px.
- Textos fixos (copiar exatamente):
  - Rodapé: `Este produto usa a API da TMDB, mas não é endossado nem certificado pela TMDB.` · `Dados de disponibilidade: JustWatch`
  - Configuração: `TMDB_TOKEN não definido. Copie .env.example para .env e preencha o token.`
  - Erros: `Série não encontrada` · `Página não encontrada` · `Problema de configuração com a TMDB (token inválido)` · `A TMDB não respondeu. Tente novamente em instantes.` · botão `Tentar novamente`
  - Catálogo: `Nenhuma série encontrada com esses filtros.` · `indisponível no momento` · `Carregar mais`
  - Busca: `N resultados para "q" · a busca ignora os filtros do catálogo` (singular: `1 resultado para "q" · ...`) · `Nenhuma série encontrada para "q".` · `Fora do streaming no BR`
  - Detalhes: `Onde assistir no Brasil` · `Ver opções de streaming ↗` · `Disponibilidade fornecida pelo JustWatch.` · `Não disponível em streaming no Brasil no momento` · `Sinopse não disponível.` · `← Voltar`
- Números: milhar com ponto (`1.284`); nota com uma casa e vírgula (`8,6`).
- Toda mensagem de commit termina com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **`ordem=recentes` junto com `ano_ate`** gera dois `first_air_date.lte`. Esperado: vale a data mais antiga das duas. Teste na Task 5.
2. **Série com campos faltando na TMDB** (sem pôster, sem data, sem `watch/providers` ou sem `BR`, sem vídeos, sem `aggregate_credits`). Esperado: a página de detalhes abre normalmente. Teste na Task 6.
3. **Busca com caracteres especiais** (`café & cia`, `<script>`). Esperado: o termo aparece escapado na página e codificado no link de "Carregar mais". Testes na Task 10.
4. **`pagina` além do total** (URL editada, ex.: `pagina=7` com 3 páginas). Esperado: grade vazia, sem botão "Carregar mais" e sem erro. Teste na Task 9.
5. **Id de série não numérico ou negativo** (`/serie/abc`, `/serie/-5`). Esperado: página HTML 404 "Página não encontrada", não um JSON 422. Teste na Task 11.

---

## Pré-requisitos (antes da Task 1; precisam do usuário)

- [ ] **uv instalado.** Não está nesta máquina. **Peça confirmação ao usuário** antes de rodar, no PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. Depois, abra um terminal novo e confira `uv --version`.
- [ ] **Token da TMDB.** Necessário a partir da Task 2. O usuário cria uma conta em themoviedb.org → Configurações → API e copia o **API Read Access Token**. Ele vai no `.env`, que a Task 1 cria a partir do `.env.example`.

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/config.py` | `Settings`, `load_settings`, `ConfigError` |
| `app/models.py` | dataclasses do domínio + `ALL_TYPES` |
| `app/filters.py` | URL → `Filters`; `Filters` → parâmetros do `/discover/tv` |
| `app/mappers.py` | JSON da TMDB → modelos; URLs de imagem; rótulos |
| `app/catalog.py` | `Catalog`: orquestra as chamadas, TTLs, concorrência da busca |
| `app/tmdb/cache.py` | `TTLCache`, `make_key` |
| `app/tmdb/client.py` | `TMDBClient`, `create_http_client`, exceções |
| `app/templating.py` | `templates`, `is_htmx`, filtros Jinja, `APP_NAME` |
| `app/main.py` | `create_app`, lifespan, handlers de erro, `app` |
| `app/routes.py` | rotas `/`, `/buscar`, `/serie/{id}` |
| `app/templates/*.html` | `base`, `catalogo`, `_grade`, `_cartoes`, `_cartao`, `busca`, `serie`, `erro`, `_erro` |
| `app/static/` | `style.css`, `htmx.min.js`, `tmdb-logo.svg` |
| `tests/helpers.py` | `load_fixture`, `FakeClock` |
| `tests/fakes.py` | `FakeCatalog`, `make_card`, `make_page`, `make_detail` |
| `tests/fixtures/` | `capturar.py` + JSON capturados |

---

### Task 1: Esqueleto do projeto e configuração

**Files:**
- Create: `pyproject.toml` (via uv), `uv.lock`, `.gitignore`, `.env.example`, `app/__init__.py`, `app/tmdb/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class Settings(BaseSettings)` com os campos `tmdb_token: SecretStr`, `tmdb_region: str = "BR"`, `tmdb_language: str = "pt-BR"`, `log_level: str = "INFO"`
  - `class ConfigError(RuntimeError)`
  - `def load_settings(env_file: str | None = ".env") -> Settings`

- [ ] **Step 1: Criar o projeto e as dependências**

```
uv init --bare --python 3.12
uv add fastapi "uvicorn[standard]" jinja2 httpx pydantic-settings
uv add --dev pytest pytest-asyncio respx
```

No `pyproject.toml`, adicione:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
addopts = "-m 'not tmdb'"
markers = ["tmdb: chama a API real da TMDB (requer TMDB_TOKEN)"]
```

Crie também:
- `.gitignore`: `.env`, `.venv/`, `__pycache__/`, `.superpowers/`, `.pytest_cache/`
- `.env.example`: `TMDB_TOKEN=`, `TMDB_REGION=BR`, `TMDB_LANGUAGE=pt-BR`, `LOG_LEVEL=INFO` (uma variável por linha)
- `app/__init__.py`, `app/tmdb/__init__.py` e `tests/__init__.py`, vazios

- [ ] **Step 2: Escrever os testes que falham** (`tests/test_config.py`)

```python
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
```

- [ ] **Step 3: Rodar e ver falhar.** Comando: `uv run pytest tests/test_config.py -v`. Esperado: FAIL com `ModuleNotFoundError: app.config`.

- [ ] **Step 4: Implementar `app/config.py`.** Use `SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")`. `load_settings` passa `_env_file=env_file` e converte tanto o `ValidationError` quanto o token em branco em `ConfigError` com a mensagem exata.

- [ ] **Step 5: Rodar e ver passar.** Comando: `uv run pytest -v`. Esperado: 3 passed.

- [ ] **Step 6: Commit**

```
git add .gitignore .env.example pyproject.toml uv.lock app tests
git commit -m "chore: esqueleto do projeto e configuração"
```

---

### Task 2: Contrato com a TMDB e captura das fixtures

Pede `TMDB_TOKEN` no `.env` (`copy .env.example .env` e preencher).

**Files:**
- Create: `tests/test_tmdb_contract.py`, `tests/fixtures/capturar.py`, `tests/fixtures/*.json`, `tests/helpers.py`

**Interfaces:**
- Consumes: `load_settings()` (Task 1)
- Produces:
  - `tests/helpers.py` com `def load_fixture(name: str) -> Any`, que relê o arquivo a cada chamada para que cada teste receba uma cópia nova, e `class FakeClock` (atributo `t: float = 0.0`; ao ser chamado, retorna `t`)
  - os arquivos `providers_tv.json`, `genres_tv.json`, `discover.json`, `search_office.json`, `watch_providers_<id>.json` (um por resultado da busca e um para o 100088) e `tv_100088.json`

- [ ] **Step 1: Escrever o teste de contrato** (`tests/test_tmdb_contract.py`)

Coloque `pytestmark = pytest.mark.tmdb` no módulo. Use `httpx.Client(base_url="https://api.themoviedb.org/3", headers={"Authorization": f"Bearer {token}"})` com o token de `load_settings()`.

```python
def test_append_watch_providers_on_tv_details(api):
    r = api.get("/tv/100088", params={"language": "pt-BR",
        "append_to_response": "aggregate_credits,videos,watch/providers",
        "include_video_language": "pt,en,null"})
    assert r.status_code == 200
    d = r.json()
    assert "results" in d["watch/providers"]
    assert "cast" in d["aggregate_credits"] and "results" in d["videos"]

def test_provider_list_has_display_priorities(api):
    r = api.get("/watch/providers/tv", params={"watch_region": "BR"})
    assert "BR" in r.json()["results"][0]["display_priorities"]

def test_discover_beyond_page_500_is_rejected(api):
    r = api.get("/discover/tv", params={"page": 501, "watch_region": "BR",
                                        "with_watch_monetization_types": "flatrate"})
    assert r.status_code != 200 or r.json()["results"] == []
```

- [ ] **Step 2: Rodar contra a API real.** Comando: `uv run pytest -m tmdb -v`. Esperado: 3 passed. **Se algum falhar, registre na mensagem de commit e siga a alternativa:**
  - teste 1 falhou → na Task 7, `detail` busca `/tv/{id}/watch/providers` separadamente
  - teste 2 falhou → na Task 6, `to_provider_list` ordena só por `display_priority`
  - teste 3 → nenhuma ação (o limite de 500 já está no mapper)

- [ ] **Step 3: Escrever `tests/fixtures/capturar.py`.** É executado com `uv run python tests/fixtures/capturar.py`. Usa o mesmo cliente do Step 1 e grava JSON com `indent=2, ensure_ascii=False`, enxugando assim:
  - `providers_tv.json`: `/watch/providers/tv?watch_region=BR&language=pt-BR` → `results[:15]`, e em cada item `display_priorities` fica só com `BR`
  - `genres_tv.json`: `/genre/tv/list?language=pt-BR`, completo
  - `discover.json`: `/discover/tv` com os parâmetros padrão da spec §8.2 → `results[:3]`
  - `search_office.json`: `/search/tv?query=office&language=pt-BR` → `results[:3]`
  - `watch_providers_<id>.json`: `/tv/{id}/watch/providers` para cada um dos 3 resultados da busca e para o `100088`, com `results` só com a chave `BR` (se ela existir)
  - `tv_100088.json`: detalhes com o `append_to_response` do Step 1. Fica só com `aggregate_credits.cast[:12]` (sem `crew`), `videos.results[:5]` e `watch/providers.results` só com `BR`

- [ ] **Step 4: Capturar e conferir.** Rode o script. Esperado: 9 arquivos `.json` em `tests/fixtures/`. Confira que nenhum deles contém o token:

```
uv run python -c "import pathlib; from app.config import load_settings; t = load_settings().tmdb_token.get_secret_value(); print(any(t in p.read_text(encoding='utf-8') for p in pathlib.Path('tests/fixtures').glob('*.json')))"
```

Esperado: `False`.

- [ ] **Step 5: Commit**

```
git add tests/test_tmdb_contract.py tests/fixtures tests/helpers.py
git commit -m "test: contrato com a TMDB e fixtures capturadas"
```

---

### Task 3: Cache com prazo de validade

**Files:**
- Create: `app/tmdb/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: `FakeClock` (Task 2)
- Produces:
  - `class TTLCache` com `__init__(self, max_entries: int = 1000, clock: Callable[[], float] = time.monotonic)`, `get(self, key: Hashable) -> Any | None`, `set(self, key: Hashable, value: Any, ttl: float) -> None` e `__len__`
  - `def make_key(path: str, params: Mapping[str, Any]) -> tuple`

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_value_available_before_ttl():
    clock = FakeClock(); c = TTLCache(clock=clock)
    c.set("k", 1, ttl=10); clock.t = 9.9
    assert c.get("k") == 1

def test_value_expires_at_ttl():
    clock = FakeClock(); c = TTLCache(clock=clock)
    c.set("k", 1, ttl=10); clock.t = 10
    assert c.get("k") is None and len(c) == 0

def test_evicts_least_recently_used():
    c = TTLCache(max_entries=2, clock=FakeClock())
    c.set("a", 1, ttl=60); c.set("b", 2, ttl=60); c.get("a"); c.set("c", 3, ttl=60)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3

def test_set_overwrites_value_and_ttl():
    clock = FakeClock(); c = TTLCache(clock=clock)
    c.set("k", 1, ttl=5); clock.t = 4; c.set("k", 2, ttl=5); clock.t = 8
    assert c.get("k") == 2

def test_make_key_ignores_param_order():
    assert make_key("/x", {"a": 1, "b": 2}) == make_key("/x", {"b": 2, "a": 1})
    assert make_key("/x", {"a": 1}) != make_key("/y", {"a": 1})
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_cache.py -v`. Esperado: FAIL (módulo inexistente).
- [ ] **Step 3: Implementar `app/tmdb/cache.py`** com um `OrderedDict` de `key -> (expira_em, valor)`. O `get` remove a entrada vencida e chama `move_to_end` nas válidas; o `set` descarta a mais antiga (`popitem(last=False)`) quando passa de `max_entries`.
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest tests/test_cache.py -v`. Esperado: 5 passed.
- [ ] **Step 5: Commit.** `git add app/tmdb/cache.py tests/test_cache.py` e `git commit -m "feat: cache em memória com TTL e LRU"`

---

### Task 4: Cliente da TMDB

**Files:**
- Create: `app/tmdb/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `TTLCache` e `make_key` (Task 3), `FakeClock`
- Produces:
  - exceções `TMDBError(Exception)`, `TMDBAuthError(TMDBError)`, `TMDBNotFound(TMDBError)` e `TMDBUnavailable(TMDBError)`
  - `BASE_URL = "https://api.themoviedb.org/3"`
  - `def create_http_client(token: str, timeout: float = 10.0) -> httpx.AsyncClient`, que já define `base_url`, `Authorization` e `Accept: application/json`
  - `class TMDBClient` com `__init__(self, http: httpx.AsyncClient, cache: TTLCache, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep)` e `async def get(self, path: str, params: Mapping[str, Any] | None = None, *, ttl: float) -> dict[str, Any]`

- [ ] **Step 1: Escrever os testes que falham.** Para todos os testes:
  - fixture `tmdb` = `TMDBClient(create_http_client("tok-secreto"), TTLCache(clock=FakeClock()), sleep=fake_sleep)`, em que `fake_sleep` grava os valores numa lista `sleeps`
  - mocks com `respx.mock(base_url=BASE_URL)`

```python
async def test_sends_bearer_token(tmdb, mock):
    route = mock.get("/genre/tv/list").respond(json={"genres": []})
    await tmdb.get("/genre/tv/list", ttl=60)
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-secreto"

async def test_second_identical_call_uses_cache(tmdb, mock):
    route = mock.get("/x").respond(json={"ok": 1})
    await tmdb.get("/x", {"a": "1", "b": "2"}, ttl=60)
    assert await tmdb.get("/x", {"b": "2", "a": "1"}, ttl=60) == {"ok": 1}
    assert route.call_count == 1

async def test_errors_are_not_cached(tmdb, mock):
    route = mock.get("/x").mock(side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": 1})])
    with pytest.raises(TMDBUnavailable): await tmdb.get("/x", ttl=60)
    assert await tmdb.get("/x", ttl=60) == {"ok": 1} and route.call_count == 2

@pytest.mark.parametrize("header, expected", [({"Retry-After": "1"}, 1.0), ({"Retry-After": "5"}, 2.0), ({}, 1.0), ({"Retry-After": "abc"}, 1.0)])
async def test_429_retries_once_after_retry_after(tmdb, mock, sleeps, header, expected):
    mock.get("/x").mock(side_effect=[httpx.Response(429, headers=header), httpx.Response(200, json={"ok": 1})])
    assert await tmdb.get("/x", ttl=60) == {"ok": 1}
    assert sleeps == [expected]

async def test_429_twice_raises_unavailable(tmdb, mock):
    mock.get("/x").mock(side_effect=[httpx.Response(429), httpx.Response(429)])
    with pytest.raises(TMDBUnavailable): await tmdb.get("/x", ttl=60)

@pytest.mark.parametrize("effect, exc", [(httpx.Response(401), TMDBAuthError), (httpx.Response(404), TMDBNotFound),
    (httpx.Response(503), TMDBUnavailable), (httpx.ReadTimeout("t"), TMDBUnavailable), (httpx.ConnectError("c"), TMDBUnavailable)])
async def test_maps_failures_to_exceptions(tmdb, mock, effect, exc):
    mock.get("/x").mock(side_effect=[effect])
    with pytest.raises(exc): await tmdb.get("/x", ttl=60)

async def test_token_never_logged(tmdb, mock, caplog):
    caplog.set_level(logging.DEBUG)
    mock.get("/x").respond(401)
    with pytest.raises(TMDBAuthError): await tmdb.get("/x", ttl=60)
    assert "tok-secreto" not in caplog.text
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_client.py -v`. Esperado: FAIL (módulo inexistente).
- [ ] **Step 3: Implementar `app/tmdb/client.py`.** Chave do cache: `make_key(path, params)`. Só respostas 2xx são guardadas, com `ttl`. As exceções de rede e de timeout do httpx viram `TMDBUnavailable`. Registre nos logs só o caminho e o status, nunca os cabeçalhos.
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest tests/test_client.py -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: cliente da TMDB com cache, retry no 429 e exceções"`

---

### Task 5: Modelos e filtros

**Files:**
- Create: `app/models.py`, `app/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Produces, em `app/models.py` (todas `@dataclass(frozen=True)`):
  - `ALL_TYPES = ("flatrate", "free", "ads", "rent", "buy")`
  - `Filters(providers: tuple[int, ...] = (), types: tuple[str, ...] = ALL_TYPES, genres: tuple[int, ...] = (), year_from: int | None = None, year_to: int | None = None, min_rating: int | None = None, sort: str = "popularidade", page: int = 1)`, com a propriedade `active_count -> int`. Ela conta 1 para cada item ativo: serviços preenchidos, tipos diferentes de todos, gêneros preenchidos, algum ano preenchido, nota preenchida.
  - `Provider(id: int, name: str, logo_url: str | None)` e `Genre(id: int, name: str)`
  - `SeriesCard(id: int, name: str, year: int | None, rating: float | None, poster_url: str | None, providers: tuple[Provider, ...] | None = None)`
  - `CatalogPage(items: tuple[SeriesCard, ...], page: int, total_pages: int, total_results: int)`
  - `WatchOptions(link: str | None, by_type: dict[str, tuple[Provider, ...]])`
  - `Season(number: int, name: str, year: int | None, episode_count: int, poster_url: str | None)` e `CastMember(name: str, character: str, profile_url: str | None)`
  - `SeriesDetail(id, name, original_name, overview, first_year, last_year, years_label: str, status_label, in_production: bool, seasons_count, episodes_count, genres: tuple[str, ...], rating: float | None, vote_count: int, poster_url, backdrop_url, trailer_youtube_key: str | None, seasons: tuple[Season, ...], cast: tuple[CastMember, ...], watch: WatchOptions)`
- Produces, em `app/filters.py`:
  - constantes `SORTS = {"popularidade": "popularity.desc", "nota": "vote_average.desc", "recentes": "first_air_date.desc", "nome": "name.asc"}`, `RATINGS = (5, 6, 7, 8)`, `MAX_PAGE = 500` e `MIN_VOTES = 50`
  - `def parse_page(values: Sequence[str]) -> int`
  - `def parse_filters(query: Mapping[str, Sequence[str]], current_year: int) -> Filters`
  - `def discover_params(filters: Filters, region: str, language: str, today: date) -> dict[str, str]`

- [ ] **Step 1: Escrever os testes que falham** (`tests/test_filters.py`)

```python
def test_empty_query_gives_defaults():
    assert parse_filters({}, 2026) == Filters()

def test_parses_all_fields():
    q = {"servicos": ["8", "1899"], "tipos": ["flatrate"], "generos": ["18"], "ano_de": ["2015"],
         "ano_ate": ["2020"], "nota": ["7"], "ordem": ["nota"], "pagina": ["3"]}
    assert parse_filters(q, 2026) == Filters(providers=(8, 1899), types=("flatrate",), genres=(18,),
        year_from=2015, year_to=2020, min_rating=7, sort="nota", page=3)

def test_invalid_values_fall_back_to_defaults():
    q = {"servicos": ["abc", "8", "8"], "tipos": ["xyz"], "ano_de": ["1800"], "ano_ate": ["2028"],
         "nota": ["9"], "ordem": ["aleatorio"], "pagina": ["501"]}
    assert parse_filters(q, 2026) == Filters(providers=(8,))

@pytest.mark.parametrize("raw", [["0"], ["-1"], ["x"], []])
def test_bad_page_is_1(raw):
    assert parse_page(raw) == 1

def test_year_upper_bound_is_next_year():
    assert parse_filters({"ano_ate": ["2027"]}, 2026).year_to == 2027

def test_swaps_reversed_years():
    f = parse_filters({"ano_de": ["2020"], "ano_ate": ["2015"]}, 2026)
    assert (f.year_from, f.year_to) == (2015, 2020)

def test_active_count():
    assert Filters().active_count == 0
    assert Filters(providers=(8,), min_rating=7).active_count == 2
    assert Filters(types=("flatrate",), year_to=2020).active_count == 2

TODAY = date(2026, 10, 16)

def test_default_discover_params():
    assert discover_params(Filters(), "BR", "pt-BR", TODAY) == {"watch_region": "BR", "language": "pt-BR",
        "with_watch_monetization_types": "flatrate|free|ads|rent|buy", "sort_by": "popularity.desc", "page": "1"}

def test_full_discover_params():
    p = discover_params(Filters(providers=(8, 1899), genres=(18, 35), year_from=2015, year_to=2020, min_rating=7),
                        "BR", "pt-BR", TODAY)
    assert p["with_watch_providers"] == "8|1899" and p["with_genres"] == "18|35"
    assert p["first_air_date.gte"] == "2015-01-01" and p["first_air_date.lte"] == "2020-12-31"
    assert p["vote_average.gte"] == "7" and p["vote_count.gte"] == "50"

def test_sort_by_rating_requires_min_votes():
    p = discover_params(Filters(sort="nota"), "BR", "pt-BR", TODAY)
    assert p["sort_by"] == "vote_average.desc" and p["vote_count.gte"] == "50"

def test_recent_sort_excludes_future():
    p = discover_params(Filters(sort="recentes"), "BR", "pt-BR", TODAY)
    assert p["sort_by"] == "first_air_date.desc" and p["first_air_date.lte"] == "2026-10-16"

# Review Focus 1
@pytest.mark.parametrize("year_to, expected", [(2020, "2020-12-31"), (2027, "2026-10-16")])
def test_recent_sort_with_year_to_uses_earlier_date(year_to, expected):
    p = discover_params(Filters(sort="recentes", year_to=year_to), "BR", "pt-BR", TODAY)
    assert p["first_air_date.lte"] == expected

def test_name_sort():
    assert discover_params(Filters(sort="nome"), "BR", "pt-BR", TODAY)["sort_by"] == "name.asc"
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_filters.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar `app/models.py` e `app/filters.py`** seguindo as regras da spec §8.2:
  - ids repetidos são removidos mantendo a ordem
  - o ano vale de 1900 até `current_year + 1`
  - sem nenhum tipo válido, usa `ALL_TYPES`
  - chaves ausentes não entram no dict
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest tests/test_filters.py -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: modelos e tradução dos filtros"`

---

### Task 6: Mappers (JSON da TMDB → modelos)

**Files:**
- Create: `app/mappers.py`
- Test: `tests/test_mappers.py`

**Interfaces:**
- Consumes: modelos (Task 5), `load_fixture` (Task 2)
- Produces:
  - constantes `IMAGE_BASE = "https://image.tmdb.org/t/p"` e `WATCH_TYPE_LABELS = {"flatrate": "Assinatura", "free": "Grátis", "ads": "Com anúncios", "rent": "Aluguel", "buy": "Compra"}`
  - `STATUS_LABELS`, com os valores da tabela da spec §8.4
  - `def image_url(path: str | None, size: str) -> str | None`
  - `def to_card(item: Mapping) -> SeriesCard` e `def to_catalog_page(data: Mapping) -> CatalogPage`, com `total_pages` limitado a 500
  - `def to_provider_list(data: Mapping, region: str) -> tuple[Provider, ...]` e `def to_genres(data: Mapping) -> tuple[Genre, ...]`
  - `def to_watch_options(region_data: Mapping | None) -> WatchOptions` e `def card_providers(region_data: Mapping | None, limit: int = 4) -> tuple[Provider, ...]`
  - `def pick_trailer(videos: Sequence[Mapping]) -> str | None` e `def years_label(first: int | None, last: int | None, in_production: bool) -> str`
  - `def to_detail(data: Mapping, region: str, overview_fallback: str = "") -> SeriesDetail`

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_image_url():
    assert image_url(None, "w342") is None
    assert image_url("/a.jpg", "w342") == "https://image.tmdb.org/t/p/w342/a.jpg"

def test_to_card_full_and_empty():
    c = to_card({"id": 1, "name": "X", "first_air_date": "2023-01-15", "vote_average": 8.64, "vote_count": 10, "poster_path": "/p.jpg"})
    assert c == SeriesCard(1, "X", 2023, 8.64, "https://image.tmdb.org/t/p/w342/p.jpg", None)
    e = to_card({"id": 2, "name": "Y", "first_air_date": "", "vote_average": 0, "vote_count": 0, "poster_path": None})
    assert (e.year, e.rating, e.poster_url) == (None, None, None)

def test_total_pages_capped_at_500():
    assert to_catalog_page({"page": 1, "total_pages": 800, "total_results": 16000, "results": []}).total_pages == 500

def test_parses_real_discover_and_search_fixtures():
    for name in ("discover.json", "search_office.json"):
        data = load_fixture(name)
        assert [c.id for c in to_catalog_page(data).items] == [r["id"] for r in data["results"]]

def test_provider_list_sorted_by_region_priority():
    data = {"results": [{"provider_id": 1, "provider_name": "A", "logo_path": "/a.png", "display_priority": 0, "display_priorities": {"BR": 5}},
                        {"provider_id": 2, "provider_name": "B", "logo_path": "/b.png", "display_priority": 9, "display_priorities": {"BR": 1}},
                        {"provider_id": 3, "provider_name": "C", "logo_path": None, "display_priority": 3, "display_priorities": {}}]}
    assert [p.id for p in to_provider_list(data, "BR")] == [2, 3, 1]

def p(i, prio=0): return {"provider_id": i, "provider_name": f"P{i}", "logo_path": f"/{i}.png", "display_priority": prio}

def test_watch_options_grouped_in_type_order():
    w = to_watch_options({"link": "L", "buy": [p(3, 2), p(2, 1)], "flatrate": [p(1)]})
    assert w.link == "L" and list(w.by_type) == ["flatrate", "buy"]
    assert [x.id for x in w.by_type["buy"]] == [2, 3]
    assert to_watch_options(None) == WatchOptions(None, {})

def test_card_providers_unique_limited_to_4():
    d = {"flatrate": [p(1)], "ads": [p(1), p(2)], "rent": [p(3)], "buy": [p(4), p(5)]}
    assert [x.id for x in card_providers(d)] == [1, 2, 3, 4]
    assert card_providers(None) == ()

def v(key, lang, type_="Trailer", site="YouTube"): return {"key": key, "iso_639_1": lang, "type": type_, "site": site}

def test_pick_trailer_priority():
    assert pick_trailer([v("en", "en"), v("ptT", "pt", "Teaser"), v("pt", "pt"), v("vim", "pt", site="Vimeo")]) == "pt"
    assert pick_trailer([v("t1", "en", "Teaser"), v("t2", "pt", "Teaser")]) == "t2"
    assert pick_trailer([v("x", "fr")]) == "x"
    assert pick_trailer([]) is None

@pytest.mark.parametrize("args, label", [((2023, 2025, True), "2023–"), ((2013, 2019, False), "2013–2019"),
                                         ((2019, 2019, False), "2019"), ((None, None, False), "")])
def test_years_label(args, label):
    assert years_label(*args) == label

def test_to_detail_from_real_fixture():
    data = load_fixture("tv_100088.json")
    d = to_detail(data, "BR")
    assert d.id == 100088 and len(d.cast) <= 10
    assert d.cast[0].character == data["aggregate_credits"]["cast"][0]["roles"][0]["character"]
    assert d.watch == to_watch_options(data["watch/providers"]["results"].get("BR"))

def test_to_detail_rules():
    data = load_fixture("tv_100088.json")
    data.update(status="Returning Series", overview="", seasons=[
        {"season_number": 0, "name": "Especiais", "air_date": None, "episode_count": 1, "poster_path": None},
        {"season_number": 1, "name": "Temporada 1", "air_date": "2023-01-15", "episode_count": 9, "poster_path": None}])
    d = to_detail(data, "BR", overview_fallback="English")
    assert d.status_label == "Em exibição" and d.overview == "English"
    assert [s.number for s in d.seasons] == [1, 0]
    data["status"] = "Algo Novo"
    assert to_detail(data, "BR").status_label == "Algo Novo"

# Review Focus 2
def test_to_detail_tolerates_missing_optional_fields():
    d = to_detail({"id": 1, "name": "X"}, "BR")
    assert (d.poster_url, d.backdrop_url, d.trailer_youtube_key) == (None, None, None)
    assert (d.cast, d.seasons, d.genres, d.years_label) == ((), (), (), "")
    assert d.watch == WatchOptions(None, {})
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_mappers.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar `app/mappers.py`.**
  - Use `.get` com defaults em tudo que é opcional.
  - Os providers de cada tipo são ordenados por `display_priority`. Na lista de serviços, a ordem vem de `display_priorities[region]`; sem ela, de `display_priority`.
  - `pick_trailer`: considera só `site == "YouTube"`. Percorre `("Trailer", "Teaser")` e, para cada tipo, procura `"pt"`, depois `"en"`, depois qualquer idioma.
  - `original_name` faz fallback para `name`.
  - `in_production` vem de `data["in_production"]`.
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest tests/test_mappers.py -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: conversão do JSON da TMDB em modelos"`

---

### Task 7: Serviço `Catalog`

**Files:**
- Create: `app/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `TMDBClient`, `BASE_URL` e as exceções (Task 4); `discover_params` e `Filters` (Task 5); os mappers (Task 6)
- Produces:
  - constantes `TTL_LISTS = 24 * 3600`, `TTL_DETAIL = 6 * 3600`, `TTL_RESULTS = 3600`, `SEARCH_CONCURRENCY = 10` e `MAX_QUERY = 100`
  - `class Catalog`, com:
    - `__init__(self, client: TMDBClient, region: str, language: str, today: Callable[[], date] = date.today)`
    - `async discover(self, filters: Filters) -> CatalogPage`
    - `async providers(self) -> tuple[Provider, ...]`
    - `async genres(self) -> tuple[Genre, ...]`
    - `async search(self, query: str, page: int) -> CatalogPage`
    - `async detail(self, series_id: int) -> SeriesDetail`

- [ ] **Step 1: Escrever os testes que falham.** Fixture `catalog` = `Catalog(TMDBClient(create_http_client("t"), TTLCache()), "BR", "pt-BR", today=lambda: date(2026, 10, 16))`, com `respx.mock(base_url=BASE_URL)`.

```python
async def test_discover_sends_translated_params(catalog, mock):
    route = mock.get("/discover/tv").respond(json=load_fixture("discover.json"))
    page = await catalog.discover(Filters(providers=(8,), sort="nota"))
    params = route.calls.last.request.url.params
    assert params["with_watch_providers"] == "8" and params["vote_count.gte"] == "50" and params["watch_region"] == "BR"
    assert len(page.items) == 3

async def test_providers_and_genres(catalog, mock):
    mock.get("/watch/providers/tv").respond(json=load_fixture("providers_tv.json"))
    mock.get("/genre/tv/list").respond(json=load_fixture("genres_tv.json"))
    assert len(await catalog.providers()) == 15
    assert all(g.name for g in await catalog.genres())

async def test_search_attaches_providers_per_card(catalog, mock):
    data = load_fixture("search_office.json"); ids = [r["id"] for r in data["results"]]
    mock.get("/search/tv").respond(json=data)
    mock.get(f"/tv/{ids[0]}/watch/providers").respond(json={"id": ids[0], "results": {"BR": {"flatrate": [
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/n.png", "display_priority": 0}]}}})
    mock.get(f"/tv/{ids[1]}/watch/providers").respond(json={"id": ids[1], "results": {}})
    mock.get(f"/tv/{ids[2]}/watch/providers").respond(500)
    page = await catalog.search("office", 1)
    assert [c.providers is None for c in page.items] == [False, False, True]
    assert page.items[0].providers[0].name == "Netflix" and page.items[1].providers == ()

async def test_search_limits_concurrency(catalog, mock):
    results = [{"id": i, "name": f"S{i}", "first_air_date": "", "vote_average": 0, "vote_count": 0, "poster_path": None} for i in range(1, 21)]
    mock.get("/search/tv").respond(json={"page": 1, "total_pages": 1, "total_results": 20, "results": results})
    in_flight = peak = 0
    async def slow(request):
        nonlocal in_flight, peak
        in_flight += 1; peak = max(peak, in_flight); await asyncio.sleep(0.01); in_flight -= 1
        return httpx.Response(200, json={"results": {}})
    route = mock.get(url__regex=r"/tv/\d+/watch/providers").mock(side_effect=slow)
    await catalog.search("s", 1)
    assert route.call_count == 20 and peak <= 10

async def test_search_truncates_query(catalog, mock):
    route = mock.get("/search/tv").respond(json={"page": 1, "total_pages": 0, "total_results": 0, "results": []})
    await catalog.search("a" * 150, 1)
    assert route.calls.last.request.url.params["query"] == "a" * 100

async def test_detail_uses_append_to_response(catalog, mock):
    route = mock.get("/tv/100088").respond(json=load_fixture("tv_100088.json"))
    d = await catalog.detail(100088)
    params = route.calls.last.request.url.params
    assert params["append_to_response"] == "aggregate_credits,videos,watch/providers"
    assert params["include_video_language"] == "pt,en,null" and params["language"] == "pt-BR"
    assert d.id == 100088

async def test_detail_falls_back_to_english_overview(catalog, mock):
    data = load_fixture("tv_100088.json"); data["overview"] = ""
    mock.get("/tv/100088", params__contains={"language": "en-US"}).respond(json={"overview": "English text"})
    mock.get("/tv/100088", params__contains={"language": "pt-BR"}).respond(json=data)
    assert (await catalog.detail(100088)).overview == "English text"

async def test_detail_fallback_failure_is_ignored(catalog, mock):
    data = load_fixture("tv_100088.json"); data["overview"] = ""
    mock.get("/tv/100088", params__contains={"language": "en-US"}).respond(503)
    mock.get("/tv/100088", params__contains={"language": "pt-BR"}).respond(json=data)
    assert (await catalog.detail(100088)).overview == ""

async def test_detail_not_found_propagates(catalog, mock):
    mock.get("/tv/1").respond(404)
    with pytest.raises(TMDBNotFound): await catalog.detail(1)
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_catalog.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar `app/catalog.py`.**
  - TTLs: `providers` e `genres` usam `TTL_LISTS`; `discover` e a chamada `/search/tv` usam `TTL_RESULTS`; `detail`, o fallback em inglês e o onde assistir de cada série usam `TTL_DETAIL`.
  - `search`: corta a query em `MAX_QUERY` e usa `include_adult="false"`. Faz as chamadas de onde assistir com `asyncio.Semaphore(SEARCH_CONCURRENCY)` + `asyncio.gather(..., return_exceptions=True)`. Se uma chamada lançar `TMDBError`, o cartão fica com `providers=None`. Senão, `card_providers(resp["results"].get(region))`, montado com `dataclasses.replace`.
  - `detail`: se a Task 2 mostrou que o `append_to_response` com `watch/providers` não funciona, busque `/tv/{id}/watch/providers` em paralelo e injete em `data["watch/providers"]`.
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest tests/test_catalog.py -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: serviço Catalog (discover, busca, detalhes)"`

---

### Task 8: App web: fábrica, layout base e páginas de erro

**Files:**
- Create: `app/templating.py`, `app/main.py`, `app/routes.py` (só o `router = APIRouter()` e `get_catalog`), `app/templates/base.html`, `erro.html`, `_erro.html`, `app/static/style.css`, `app/static/htmx.min.js`, `app/static/tmdb-logo.svg`, `tests/fakes.py`, `tests/conftest.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `Settings`, `load_settings` e `ConfigError` (Task 1); `TMDBClient`, `create_http_client` e as exceções (Task 4); `TTLCache` (Task 3); `Catalog` (Task 7)
- Produces:
  - `app/templating.py`:
    - `APP_NAME = "SériesBR"` e `templates: Jinja2Templates` (diretório `app/templates`)
    - globais Jinja `APP_NAME` e `WATCH_TYPE_LABELS`
    - filtros Jinja `milhar` (`format_thousands(n: int) -> str`) e `nota` (`format_rating(x: float) -> str`)
    - `def is_htmx(request: Request) -> bool`, que verifica `HX-Request == "true"`
  - `app/routes.py`: `def get_catalog(request: Request) -> Catalog`, que retorna `request.app.state.catalog`
  - `app/main.py`: `def create_app(settings: Settings | None = None, catalog: Catalog | None = None) -> FastAPI` e `app = create_app()`
  - `tests/fakes.py`:
    - `FakeCatalog(*, discover=None, providers=(), genres=(), search=None, detail=None, error=None, providers_error=None, genres_error=None)`, com os mesmos 5 métodos assíncronos do `Catalog`. Cada método lança `error` (ou o erro específico) ou retorna o valor configurado, e registra `(nome_do_método, args)` em `.calls`.
    - `HX = {"HX-Request": "true"}`
    - `make_card(id=1, name="Série 1", **kw) -> SeriesCard`
    - `make_page(n=3, page=1, total_pages=1, total_results=None) -> CatalogPage`, com cartões `make_card(i, f"Série {i}")` para i de 1 a n e `total_results=None` virando `n`
    - `make_detail(**kw) -> SeriesDetail`, com padrões que reproduzem o exemplo "The Last of Us" do mockup: `years_label="2023–"`, `status_label="Em exibição"`, `rating=8.6`, trailer `"abc123"`, `by_type={"flatrate": (Provider(1899, "Max", "https://image.tmdb.org/t/p/w92/max.png"),)}`, link `"https://www.themoviedb.org/tv/100088/watch?locale=BR"`, uma temporada "Temporada 1" e o elenco "Pedro Pascal"/"Joel"
  - `tests/conftest.py`, com as fixtures:
    - `make_client`: uma função `(fake) -> TestClient`, já aberto como context manager e fechado no teardown
    - `fake`: padrão `FakeCatalog(discover=make_page(), search=make_page(), detail=make_detail())`; os módulos de teste a sobrescrevem quando precisarem
    - `client`: `make_client(fake)`

- [ ] **Step 1: Baixar os arquivos estáticos**
  - `curl -L -o app/static/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js`
  - O SVG "blue_short" da página https://www.themoviedb.org/about/logos-attribution, salvo como `app/static/tmdb-logo.svg`
  - Confira se o arquivo do HTMX começa com JavaScript, não com HTML de erro.

- [ ] **Step 2: Escrever os testes que falham** (`tests/test_app.py`)

O cliente é `TestClient(create_app(catalog=FakeCatalog()))` usado como context manager. Para os handlers, o teste registra rotas que só lançam a exceção: `app.add_api_route("/boom/{kind}", ...)`.

```python
def test_unknown_route_renders_html_404(client):
    r = client.get("/nao-existe")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"] and "Página não encontrada" in r.text

def test_layout_has_attributions_search_and_htmx(client):
    t = client.get("/nao-existe").text
    assert "Este produto usa a API da TMDB, mas não é endossado nem certificado pela TMDB." in t
    assert "Dados de disponibilidade: JustWatch" in t and 'src="/static/tmdb-logo.svg"' in t
    assert 'action="/buscar"' in t and 'src="/static/htmx.min.js"' in t and "SériesBR" in t

@pytest.mark.parametrize("kind, status, text", [("unavailable", 503, "A TMDB não respondeu. Tente novamente em instantes."),
    ("auth", 502, "Problema de configuração com a TMDB (token inválido)"), ("notfound", 404, "Série não encontrada")])
def test_tmdb_errors_full_page(boom_client, kind, status, text):
    r = boom_client.get(f"/boom/{kind}")
    assert r.status_code == status and text in r.text and "<html" in r.text

def test_tmdb_error_htmx_fragment(boom_client):
    r = boom_client.get("/boom/unavailable", headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/?nota=7"})
    assert r.status_code == 200 and "<html" not in r.text
    assert "A TMDB não respondeu" in r.text and "Tentar novamente" in r.text and "/?nota=7" in r.text

def test_missing_token_fails_startup(monkeypatch, tmp_path):
    monkeypatch.delenv("TMDB_TOKEN", raising=False); monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        with TestClient(create_app()): pass

@pytest.mark.parametrize("n, s", [(1284, "1.284"), (12, "12"), (1234567, "1.234.567")])
def test_format_thousands(n, s): assert format_thousands(n) == s

def test_format_rating(): assert format_rating(8.64) == "8,6"
```

- [ ] **Step 3: Rodar e ver falhar.** Comando: `uv run pytest tests/test_app.py -v`. Esperado: FAIL.
- [ ] **Step 4: Implementar.**
  - **`create_app`:**
    - monta `/static` e inclui o `router`
    - o `lifespan` usa o `catalog` recebido. Sem ele, chama `load_settings()`; em caso de `ConfigError`, registra no log em nível ERROR e relança. Depois configura `logging.basicConfig(level=...)`, cria `create_http_client` → `TMDBClient(http, TTLCache())` → `Catalog(...)`, guarda em `app.state.catalog` e fecha o http no fim.
  - **Handlers de erro** para `TMDBNotFound`, `TMDBAuthError`, `TMDBUnavailable` e o 404 do Starlette:
    - página inteira: `erro.html` com os status da spec §9
    - pedido HTMX: `_erro.html` com status 200
    - o link "Tentar novamente" aponta para o cabeçalho `HX-Current-URL` (ou `request.url`)
  - **`base.html`:**
    - cabeçalho: `<a href="/" class="logo">` com `APP_NAME`; o formulário `<form action="/buscar" method="get" role="search">` com `<input type="search" name="q" maxlength="100" placeholder="Buscar série pelo nome…">`, preenchido com `q` quando existir; e `<div class="menu-usuario"></div>` vazio (espaço da fase 2)
    - `<script src="/static/htmx.min.js" defer>`
    - rodapé com o logo e os dois textos de atribuição
  - **`style.css`:** tokens do tema (Global Constraints), cabeçalho, rodapé e a página de erro.
- [ ] **Step 5: Rodar e ver passar.** Comando: `uv run pytest -v`. Esperado: todos passam.
- [ ] **Step 6: Commit.** `git commit -m "feat: app FastAPI com layout base e páginas de erro"`

---

### Task 9: Página do catálogo (`/`)

**Files:**
- Modify: `app/routes.py`, `app/static/style.css`
- Create: `app/templates/catalogo.html`, `_grade.html`, `_cartoes.html`, `_cartao.html`
- Test: `tests/test_routes_catalogo.py`

**Interfaces:**
- Consumes: `parse_filters` (Task 5), `WATCH_TYPE_LABELS` (Task 6), `get_catalog`, `is_htmx` e `templates` (Task 8), `FakeCatalog` e `make_page` (Task 8)
- Produces:
  - `def query_dict(request: Request) -> dict[str, list[str]]`
  - `def next_page_url(path: str, query_items: Sequence[tuple[str, str]], next_page: int) -> str`, que remove os `pagina` existentes, acrescenta `pagina=N` no fim e usa `urlencode`
  - `_cartao.html`, que espera a variável `card` (usado também na Task 10)
  - `_grade.html` e `_cartoes.html`, que esperam `page: CatalogPage`, `has_next: bool` e `next_url: str`

- [ ] **Step 1: Escrever os testes que falham.** Neste módulo, sobrescreva a fixture `fake` com `FakeCatalog(discover=make_page(n=3, page=1, total_pages=2, total_results=1284), providers=(Provider(8, "Netflix", None),), genres=(Genre(18, "Drama"),))`. Importe `HX` de `tests.fakes`.

```python
def test_full_page(client):
    t = client.get("/").text
    assert 'id="filtros"' in t and 'hx-target="#grade"' in t and 'hx-push-url="true"' in t
    assert "Netflix" in t and "Drama" in t and "1.284 séries" in t and "Carregar mais" in t
    assert 'for="mostrar-filtros"' in t and "Filtros (0)" in t

def test_htmx_first_page_returns_grid_fragment(client):
    t = client.get("/", headers=HX).text
    assert "<html" not in t and 'class="contador"' in t

def test_htmx_next_page_returns_only_cards(make_client):
    t = make_client(FakeCatalog(discover=make_page(page=2, total_pages=3))).get("/?servicos=8&pagina=2", headers=HX).text
    assert 'class="contador"' not in t and "Série 1" in t and "servicos=8" in t and "pagina=3" in t

def test_next_page_url():
    assert next_page_url("/", [("servicos", "8"), ("servicos", "1899"), ("pagina", "1")], 2) == "/?servicos=8&servicos=1899&pagina=2"
    assert next_page_url("/buscar", [("q", "café & cia")], 2) == "/buscar?q=caf%C3%A9+%26+cia&pagina=2"

def test_invalid_query_uses_defaults(client, fake):
    assert client.get("/?servicos=abc&nota=99&pagina=x").status_code == 200
    assert ("discover", (Filters(),)) in fake.calls

def test_filters_prefilled(client):
    t = client.get("/?servicos=8&nota=7&tipos=flatrate").text
    assert 'name="servicos" value="8" checked' in t and 'value="7" selected' in t
    assert 'name="tipos" value="flatrate" checked' in t and 'name="tipos" value="buy" checked' not in t
    assert "Filtros (3)" in t

def test_provider_list_failure_still_renders(make_client):
    r = make_client(FakeCatalog(discover=make_page(), providers_error=TMDBUnavailable())).get("/")
    assert r.status_code == 200 and "indisponível no momento" in r.text

def test_discover_error_in_htmx_is_fragment(make_client):
    r = make_client(FakeCatalog(error=TMDBUnavailable())).get("/", headers=HX)
    assert r.status_code == 200 and "A TMDB não respondeu" in r.text

def test_empty_results_message(make_client):
    t = make_client(FakeCatalog(discover=make_page(n=0, total_pages=0, total_results=0))).get("/").text
    assert "Nenhuma série encontrada com esses filtros." in t and "Carregar mais" not in t

# Review Focus 4
def test_page_beyond_total_has_no_button(make_client):
    r = make_client(FakeCatalog(discover=make_page(n=0, page=7, total_pages=3, total_results=50))).get("/?pagina=7", headers=HX)
    assert r.status_code == 200 and "Carregar mais" not in r.text
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_routes_catalogo.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar a rota `GET /` e os templates.**
  - **Rota:**
    - `parse_filters(query_dict(request), date.today().year)` → `catalog.discover`
    - `has_next = page.page < page.total_pages`; `next_url = next_page_url(request.url.path, request.query_params.multi_items(), page.page + 1)`. Use a página devolvida pela TMDB, não a pedida na URL.
    - na lista de serviços do filtro, mostre `<img alt="{{ p.name }}">` quando houver `logo_url` e, senão, o nome em texto
    - com HTMX e `filters.page > 1` → `_cartoes.html`; com HTMX nos outros casos → `_grade.html`; sem HTMX → `catalogo.html`
    - na página inteira, `providers()` e `genres()` são chamados à parte, cada um com `try/except TMDBError` → `None` → o template mostra `indisponível no momento`
  - **`catalogo.html`** (opção A do mockup):
    - `<form id="filtros" hx-get="/" hx-trigger="change" hx-target="#grade" hx-push-url="true">` envolve a lateral e a barra com o `<select name="ordem">`; o `#grade` fica fora do formulário
    - toggle para celular: `<input type="checkbox" id="mostrar-filtros" hidden>` + `<label for="mostrar-filtros">Filtros ({{ filters.active_count }})</label>`, que só é visível abaixo de 768 px
    - checkboxes exatamente no formato `<input type="checkbox" name="servicos" value="{{ id }}"{% if ... %} checked{% endif %}>`, e o mesmo para `tipos` e `generos`
    - serviços: os 12 primeiros visíveis; o resto dentro de `<details><summary>ver todos (N)</summary>`
    - gêneros dentro de `<details>`
    - anos: `<input type="number" name="ano_de|ano_ate" min="1900" max="{{ ano_atual + 1 }}">`
    - `<select name="nota">` com a opção vazia "Qualquer nota" e `★ 5+` … `★ 8+`, no formato `value="7" selected`
    - `<select name="ordem">` com as opções Popularidade, Nota, Mais recentes e Nome A–Z
  - **`_grade.html`:** `<p class="contador">{{ total|milhar }} séries</p>` + `<div class="cartoes">`, com os cartões e o botão `<button type="button" class="carregar-mais" hx-get="{{ next_url }}" hx-target="this" hx-swap="outerHTML">Carregar mais</button>` (que ocupa a linha toda da grade). Com a lista vazia, mostra a mensagem de vazio.
  - **`_cartao.html`:**
    - `<a class="cartao" href="/serie/{{ card.id }}">`
    - `<img loading="lazy" alt="{{ card.name }}">`, ou um placeholder
    - nome, ano e `★ {{ card.rating|nota }}` (só quando há nota)
    - quando `card.providers is not none`: até 4 logos; se a tupla for vazia, `class="cartao esmaecido"` + `<span class="fora">Fora do streaming no BR</span>`
  - **CSS:** lateral com 220 px e grade `repeat(auto-fill, minmax(150px, 1fr))`. Abaixo de 768 px, a lateral fica escondida até `#mostrar-filtros:checked` e a grade passa a ter 2 colunas.
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: página do catálogo com filtros e HTMX"`

---

### Task 10: Busca (`/buscar`)

**Files:**
- Modify: `app/routes.py`, `app/static/style.css`
- Create: `app/templates/busca.html`
- Test: `tests/test_routes_busca.py`

**Interfaces:**
- Consumes: `parse_page` (Task 5), `next_page_url`, `query_dict`, `_cartao.html` e `_cartoes.html` (Task 9), `FakeCatalog`
- Produces: a rota `GET /buscar`

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_blank_query_redirects_home(client):
    r = client.get("/buscar?q=%20%20", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"

def test_results_page_with_notice(make_client):
    c = make_client(FakeCatalog(search=make_page(n=3, total_results=3)))
    t = c.get("/buscar?q=office").text
    assert '3 resultados para "office" · a busca ignora os filtros do catálogo' in t
    assert 'value="office"' in t

def test_singular_and_empty(make_client):
    assert '1 resultado para "x"' in make_client(FakeCatalog(search=make_page(n=1, total_results=1))).get("/buscar?q=x").text
    assert 'Nenhuma série encontrada para "x".' in make_client(FakeCatalog(search=make_page(n=0, total_results=0))).get("/buscar?q=x").text

def test_card_availability_states(make_client):
    netflix = Provider(8, "Netflix", "https://image.tmdb.org/t/p/w92/n.png")
    cards = (make_card(1, "Com", providers=(netflix,)), make_card(2, "Sem", providers=()), make_card(3, "Falhou", providers=None))
    t = make_client(FakeCatalog(search=CatalogPage(cards, 1, 1, 3))).get("/buscar?q=s").text
    assert t.count("Fora do streaming no BR") == 1 and t.count("esmaecido") == 1 and 'alt="Netflix"' in t

def test_passes_query_and_page(make_client):
    fake = FakeCatalog(search=make_page())
    make_client(fake).get("/buscar?q=office&pagina=2", headers=HX)
    assert ("search", ("office", 2)) in fake.calls

# Review Focus 3
def test_query_is_escaped(make_client):
    t = make_client(FakeCatalog(search=make_page(n=0, total_results=0))).get("/buscar", params={"q": "<script>alert(1)</script>"}).text
    assert "<script>alert(1)</script>" not in t and "&lt;script&gt;" in t

def test_next_page_link_encodes_query(make_client):
    t = make_client(FakeCatalog(search=make_page(total_pages=2))).get("/buscar", params={"q": "café & cia"}).text
    assert "/buscar?q=caf%C3%A9+%26+cia&amp;pagina=2" in t
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_routes_busca.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar.**
  - `q = query_params.get("q", "").strip()`; se ficar vazio, `RedirectResponse("/", status_code=303)`.
  - Com HTMX e `pagina > 1` → `_cartoes.html` (mesmo `next_page_url`, com `path="/buscar"`). Senão, `busca.html`, que reaproveita `_cartao.html`, o botão "Carregar mais" e a contagem/aviso com os textos exatos.
  - As aspas ficam no template como literais; só `q` passa pelo escape automático do Jinja.
  - A busca do cabeçalho vem preenchida com `q`.
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: busca por nome com disponibilidade por série"`

---

### Task 11: Página de detalhes (`/serie/{id}`)

**Files:**
- Modify: `app/routes.py`, `app/static/style.css`
- Create: `app/templates/serie.html`
- Test: `tests/test_routes_serie.py`

**Interfaces:**
- Consumes: `make_detail` e `FakeCatalog` (Task 8), `WATCH_TYPE_LABELS` (Task 6), os handlers de erro (Task 8)
- Produces: a rota `GET /serie/{series_id:int}` (o conversor `int` do Starlette faz `/serie/abc` cair no 404 HTML)

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_detail_main_sections(make_client):
    t = make_client(FakeCatalog(detail=make_detail())).get("/serie/100088").text
    for s in ("The Last of Us", "2023–", "Em exibição", "Onde assistir no Brasil", "Assinatura", 'alt="Max"',
              "youtube-nocookie.com/embed/abc123", "Ver opções de streaming ↗",
              'href="https://www.themoviedb.org/tv/100088/watch?locale=BR"', "Disponibilidade fornecida pelo JustWatch.",
              "Temporada 1", "Pedro Pascal", "Joel", "history.back()", "← Voltar", "★ 8,6"):
        assert s in t, s

def test_without_trailer_and_providers(make_client):
    d = make_detail(trailer_youtube_key=None, watch=WatchOptions(None, {}))
    t = make_client(FakeCatalog(detail=d)).get("/serie/1").text
    assert "youtube-nocookie" not in t and "Ver opções de streaming" not in t
    assert "Não disponível em streaming no Brasil no momento" in t

def test_original_name_only_when_different(make_client):
    assert "Shōgun" not in make_client(FakeCatalog(detail=make_detail(name="Xógum", original_name="Xógum"))).get("/serie/1").text
    assert "Shōgun" in make_client(FakeCatalog(detail=make_detail(name="Xógum", original_name="Shōgun"))).get("/serie/1").text

def test_empty_overview_message(make_client):
    assert "Sinopse não disponível." in make_client(FakeCatalog(detail=make_detail(overview=""))).get("/serie/1").text

def test_unknown_series_is_404(make_client):
    r = make_client(FakeCatalog(error=TMDBNotFound())).get("/serie/999")
    assert r.status_code == 404 and "Série não encontrada" in r.text

# Review Focus 5
@pytest.mark.parametrize("path", ["/serie/abc", "/serie/-5"])
def test_invalid_id_is_html_404(client, path):
    r = client.get(path)
    assert r.status_code == 404 and "text/html" in r.headers["content-type"] and "Página não encontrada" in r.text
```

- [ ] **Step 2: Rodar e ver falhar.** Comando: `uv run pytest tests/test_routes_serie.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar a rota e o `serie.html`**, seguindo o mockup aprovado (spec §8.4):
  - `← Voltar` = `<a href="/" class="voltar" onclick="if (history.length > 1) { history.back(); return false; }">← Voltar</a>`
  - tags: `years_label`, `status_label`, "N temporadas · M ep." (singular "1 temporada"), gêneros, `★ {{ rating|nota }} ({{ vote_count|milhar }} votos)`
  - o trailer é um `<iframe src="https://www.youtube-nocookie.com/embed/{{ key }}" loading="lazy" title="Trailer" allowfullscreen>`
  - "Onde assistir": um bloco por tipo em `watch.by_type`, com `WATCH_TYPE_LABELS` + `<img alt="{{ p.name }}">`, e o botão com `target="_blank" rel="noopener"` só quando houver `link`
  - o comentário `{# fase 2: botões Assistida/Favorita aqui #}` ao lado do título
  - CSS: fundo de 1280 px com gradiente, pôster sobreposto e duas colunas (sinopse/trailer | onde assistir), que viram uma abaixo de 768 px
- [ ] **Step 4: Rodar e ver passar.** Comando: `uv run pytest -v`. Esperado: todos passam.
- [ ] **Step 5: Commit.** `git commit -m "feat: página de detalhes da série"`

---

### Task 12: README e verificação final

**Files:**
- Create: `README.md`

- [ ] **Step 1: Escrever o `README.md`** com os pré-requisitos (uv e token), a configuração do `.env` e os comandos da spec §14.
- [ ] **Step 2: Rodar a suíte completa.** `uv run pytest -v` deve passar sem rede; `uv run pytest -m tmdb -v` deve passar com o token.
- [ ] **Step 3: Verificação manual** com `uv run uvicorn app.main:app --reload`, no navegador, em largura de computador e de celular (375 px no DevTools). Confira os critérios 1 a 6 da spec §4:
  1. o app sobe em `http://localhost:8000`
  2. o filtro "Netflix + Max, Assinatura, Drama, nota ≥ 7" mostra séries corretas; confira em 2 delas pela página de detalhes
  3. só a grade muda; a URL reflete os filtros; o botão voltar funciona; "Carregar mais" funciona
  4. buscar "office" mostra os logos e "Fora do streaming no BR"
  5. os detalhes mostram sinopse, temporadas, elenco, trailer e onde assistir
  6. reinicie o servidor com `$env:HTTPS_PROXY="http://127.0.0.1:9"` (o httpx respeita a variável) e confira a mensagem "A TMDB não respondeu…"; depois, remova a variável
- [ ] **Step 4: Commit.** `git add README.md` e `git commit -m "docs: README com instruções de uso"`
- [ ] **Step 5: Backup no GitHub.** **Pergunte ao usuário** antes de criar o repositório. Se ele aprovar: `gh repo create catalogo-series --private --source . --push`.
