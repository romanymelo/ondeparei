# Marcações e episódios (Fase 2a) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Marcar séries como Quero assistir / Assistindo / Assistido e favoritas, marcar episódios um a um (com "até aqui" e "temporada inteira"), e mostrar o progresso em "Minhas séries", nos selos do catálogo e na barra âmbar "onde parei".

**Architecture:** Um pacote novo `app/tracking/` com quatro camadas: `rules.py` (funções puras sobre pares `(temporada, episódio)`), `db.py` + `repository.py` (SQLite da biblioteca padrão; todo o SQL fica no repositório), `service.py` (`TrackingService`: busca a TMDB pelo `Catalog`, valida, aplica as regras e grava numa transação) e `routes.py` (páginas da temporada e de Minhas séries, mais as ações POST). As rotas da fase 1 só ganham o bloco de status na página da série e os selos nos cartões.

Refinamentos em relação à spec, decididos aqui:
- **(a)** `SeasonDetail` traz só os dados da temporada (`series_id`, `number`, `name`, `episodes`). O nome da série e a lista de temporadas para os atalhos vêm do `SeriesDetail`, que o `SeasonView` carrega junto.
- **(b)** `SeriesDetail` ganha também `poster_path`, para o snapshot.
- **(c)** A página da temporada fica em `tracking/routes.py`, junto das ações que devolvem o mesmo bloco.
- **(d)** O cartão dos Especiais mostra só "N marcados", sem barra, porque os exibidos da temporada 0 só são conhecidos abrindo a temporada (spec §3).
- **(e)** Quando o `last_episode_to_air` é um especial, `last_aired` passa a ser o último episódio da última temporada ≥ 1 cuja estreia (`air_date`) é anterior ou igual à data desse especial.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX 2.0.4 (local), `sqlite3` da biblioteca padrão, pytest, pytest-asyncio e respx.

**Spec:** `docs/superpowers/specs/2026-10-16-marcacoes-design.md` (leia junto com este plano). A identidade visual é a da spec da fase 1, `docs/superpowers/specs/2026-10-16-catalogo-series-design.md`.

## Global Constraints

- **Ambiente:** projeto em `C:\Projetos\catalogo-series`, no Windows. No Bash, comece com `export PATH="/c/Users/Romany Melo/.local/bin:$PATH"`. Todo comando roda via `uv run ...`.
- **Nenhuma dependência nova.** O banco usa o `sqlite3` da biblioteca padrão. Formulários POST são lidos com `urllib.parse.parse_qs(await request.body())`, porque o `python-multipart` não está instalado. Nunca use `Form(...)` do FastAPI.
- **Banco:** arquivo em `DATABASE_PATH` (padrão `data/catalogo.db`); `data/` entra no `.gitignore`. Use `LOCAL_USER_ID = 1`.
- **Status:** valores `want`, `watching` e `watched`. Rótulos: `want` → "Quero assistir", `watching` → "Assistindo", `watched` → "Assistido". Favorito → "Favorita".
- **URLs:**
  - campos de formulário `status`, `temporada` e `episodio`;
  - parâmetro `aba`, com os valores `assistindo` (padrão), `quero`, `assistidas` e `favoritas`.
- **Identificadores:** código em inglês; textos da tela e nomes de templates em português.
- **A TMDB é consultada antes de qualquer gravação.** Toda ação grava numa única transação. Cache da temporada: 6 h (`TTL_DETAIL`).
- **Ícones:** SVG em linha, nunca emoji. Saem da macro `icone(nome)` de `app/templates/_icones.html`, com `nome` igual a `want`, `watching`, `watched` ou `favorite`. Nesta spec e neste plano, ✓ ▶ 🔖 ♥ são só abreviações.
- **Paleta:** a da fase 1, já em `:root`: `--meia-noite`, `--veludo`, `--fio`, `--tela`, `--nevoa`, `--projetor`, `--projetor-brilho`. Não crie cores novas.
- **Barra de progresso:** componente `.progresso` > `.progresso-feito`, com a largura em `style="--pausa: N%"`. Tem o mesmo visual da `.pausa` do destaque (3 px, trilho `--fio`, preenchimento `--projetor`), mas sem animação. A porcentagem é arredondada (`(1, 3)` → `33%`).
- **Datas:** formato `dd/mm/aaaa`. Episódio: `T2E3`.
- **Respostas HTMX:**
  - fragmentos respondem com 200, inclusive os de erro;
  - exceção: "Ação inválida" responde 400 com HTMX ou sem;
  - sem HTMX, toda ação POST responde com redirecionamento 303.
- **Textos fixos** (copiar exatamente):
  - `Minhas séries` · `Quero assistir` · `Assistindo` · `Assistido` · `Favorita`
  - `Próximo: T1E2 — Episódio 2` (sem título: `Próximo: T1E2`) · `Em dia` (seguido do ícone `watched`)
  - na aba Assistindo: `Em dia (aguardando episódios)`
  - `X de Y assistidos` · `Marcar temporada inteira` · `Desmarcar temporada` · `Marcar até aqui` · `próximo`
  - `E3 · Título` · `Estreia em 01/01/2027` · `Data a definir` · `Em breve` · `3 marcados` · `Sinopse`
  - abas: `Assistindo` · `Quero assistir` · `Assistidas` · `Favoritas`
  - `Nenhuma série aqui ainda.` · link `Explorar o catálogo`
  - `Ação inválida` · `Não foi possível salvar sua marcação. Tente novamente.`
- **Testes:** nunca acessam a internet. O banco de teste fica em `tmp_path` ou `":memory:"`.
- **Commits:** toda mensagem termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Servidor local:** sem `--reload`, que trava no Windows. Para ver uma mudança, pare e suba de novo.

## Review Focus

1. **Duplo clique no ✓ ou em "Marcar até aqui"**, que chega como dois POSTs seguidos. Esperado: sem erro de chave duplicada; "até aqui" repetido não muda nada; ✓ repetido desmarca. Testes nas Tasks 2 e 4.
2. **Dados da TMDB que mudam depois da marcação:** episódios marcados que deixaram de existir ou de contar como exibidos. Esperado: progresso, status automático e próximo episódio consideram só os episódios exibidos e nunca passam de 100%. Testes nas Tasks 1 e 4.
3. **`last_episode_to_air` é um especial.** Esperado: as temporadas normais continuam contando como exibidas (refinamento **e**). Teste na Task 3.
4. **Corpo de formulário estranho:** `episodio=-1`, `1.5`, `abc`, campo ausente, temporada inexistente. Esperado: 400 "Ação inválida", nunca um JSON 422 nem um 500. Testes na Task 6.
5. **Série sem nenhum episódio exibido** (`last_aired` igual a `None`, série anunciada). Esperado:
   - o status manual funciona;
   - na página da temporada, não aparecem ✓, "Marcar até aqui" nem "Marcar temporada inteira";
   - os cartões de temporada mostram "Em breve".

   Testes nas Tasks 5 e 6.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/models.py` | + `Episode`, `SeasonDetail`, `Marks`, `TrackedSeries`, `SeriesTracking`, `SeasonView`, `MySeries`; `SeriesDetail` + `poster_path`, `last_aired` |
| `app/tracking/rules.py` | regras puras: exibidos, especiais, próximo, até aqui, temporada, status automático, progresso |
| `app/tracking/db.py` | `connect()` com WAL e migrações via `PRAGMA user_version` |
| `app/tracking/repository.py` | `TrackingRepository`: todo o SQL |
| `app/tracking/service.py` | `TrackingService`, `InvalidAction`, `TABS` |
| `app/tracking/routes.py` | página da temporada, Minhas séries e ações POST |
| `app/mappers.py` | + `to_season_detail`; `to_detail` lê `poster_path` e `last_aired` |
| `app/catalog.py` | + `season()` |
| `app/config.py` | + `database_path` |
| `app/main.py` | abre o banco no `lifespan`, registra o router novo e os handlers de `InvalidAction` e `sqlite3.Error` |
| `app/routes.py` | `get_tracking`; selos no catálogo e na busca; bloco de status na página da série |
| `app/templating.py` | + `MARK_LABELS`, `TAB_LABELS`; filtros `porcento`, `ep`, `data` |
| `app/templates/` | novos: `_icones.html`, `_status.html`, `temporada.html`, `_temporada.html`, `minhas_series.html`, `_cartao_minha.html`; alterados: `base.html`, `serie.html`, `_cartao.html` |
| `app/static/style.css` | seção nova `/* Marcações */` no fim |
| `tests/fakes.py` | `FakeCatalog.season()`, `details=`; `make_episode`, `make_season`, `tracked_detail`, `tracked_catalog` |

---

### Task 1: Modelos e regras puras

**Files:**
- Modify: `app/models.py`
- Create: `app/tracking/__init__.py` (vazio), `app/tracking/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Produces, em `app/models.py`, todos como `@dataclass(frozen=True)`:
  - `Episode(season: int, number: int, name: str, overview: str, air_date: date | None, runtime: int | None, still_url: str | None)`
  - `SeasonDetail(series_id: int, number: int, name: str, episodes: tuple[Episode, ...])`
  - `Marks(status: str | None = None, favorite: bool = False)`
  - `TrackedSeries(tmdb_id: int, name: str, poster_url: str | None, marks: Marks, next_episode: tuple[int, int] | None = None, caught_up: bool = False, progress: tuple[int, int] | None = None)`
  - `SeriesTracking(marks: Marks, next_episode: tuple[int, int] | None, next_title: str | None, season_progress: dict[int, tuple[int, int]])`. A chave é o número da temporada e o valor é (marcados, exibidos); a temporada 0 vem como (marcados, 0).
  - `SeasonView(detail: SeriesDetail, season: SeasonDetail, marks: Marks, watched: frozenset[tuple[int, int]], aired: frozenset[tuple[int, int]], next_episode: tuple[int, int] | None)`. Tem as propriedades:
    - `progress -> tuple[int, int]`, igual a `(len(watched & aired), len(aired))`;
    - `complete -> bool`, verdadeiro quando há `aired` e todos estão em `watched`.
  - `MySeries(tab: str, counts: dict[str, int], items: tuple[TrackedSeries, ...])`. As chaves de `counts` são as da URL (`assistindo`, `quero`, `assistidas` e `favoritas`).
  - `SeriesDetail` ganha **no fim**, com padrão `None`: `poster_path: str | None = None` e `last_aired: tuple[int, int] | None = None`.
- Produces, em `app/tracking/rules.py`, com `Ep = tuple[int, int]`:
  - `aired_episodes(seasons: Iterable[tuple[int, int]], last_aired: Ep | None) -> list[Ep]` (recebe `(número, episode_count)`)
  - `aired_specials(episodes: Iterable[Episode], today: date) -> list[Ep]`
  - `next_episode(aired: Sequence[Ep], watched: Collection[Ep]) -> Ep | None`
  - `up_to(aired: Sequence[Ep], target: Ep) -> list[Ep]`
  - `season_episodes(aired: Sequence[Ep], season: int) -> list[Ep]`
  - `auto_status(current: str | None, aired: Sequence[Ep], watched: Collection[Ep]) -> str | None`
  - `progress(aired: Iterable[Ep], watched: Collection[Ep]) -> tuple[int, int]`

- [ ] **Step 1: Escreva `tests/test_rules.py`**

```python
from datetime import date

import pytest

from app.models import Episode
from app.tracking.rules import (aired_episodes, aired_specials, auto_status, next_episode, progress,
                                season_episodes, up_to)

AIRED = aired_episodes([(1, 3), (2, 4)], (2, 2))  # T1E1–T1E3, T2E1–T2E2


def test_aired_episodes_until_last_aired():
    assert AIRED == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)]


def test_aired_episodes_empty_without_last_aired():
    assert aired_episodes([(1, 3)], None) == []


def test_aired_episodes_ignore_specials():
    assert aired_episodes([(0, 5), (1, 2)], (1, 2)) == [(1, 1), (1, 2)]


def special(n, air_date):
    return Episode(0, n, f"Especial {n}", "", air_date, None, None)


def test_aired_specials_by_air_date():
    episodes = [special(1, date(2026, 10, 16)), special(2, date(2026, 10, 17)), special(3, None)]
    assert aired_specials(episodes, today=date(2026, 10, 16)) == [(0, 1)]


def test_next_episode_is_first_aired_not_watched():
    assert next_episode(AIRED, {(1, 1), (1, 3)}) == (1, 2)
    assert next_episode(AIRED, set(AIRED)) is None


def test_up_to_crosses_seasons():
    assert up_to(AIRED, (2, 1)) == [(1, 1), (1, 2), (1, 3), (2, 1)]


def test_season_episodes():
    assert season_episodes(AIRED, 2) == [(2, 1), (2, 2)]


@pytest.mark.parametrize(("current", "watched", "expected"), [
    (None, set(AIRED), "watched"),
    ("want", set(AIRED), "watched"),
    ("want", {(1, 1)}, "watching"),
    ("watched", {(1, 1)}, "watching"),  # Assistido manual + 1 episódio → Assistindo
    (None, set(), None),
    ("want", set(), "want"),
    ("want", {(0, 1)}, "want"),         # especiais não contam
    ("watched", {(3, 1)}, "watched"),   # marcado fora dos exibidos não conta
])
def test_auto_status(current, watched, expected):
    assert auto_status(current, AIRED, watched) == expected


def test_auto_status_without_aired_keeps_current():
    assert auto_status("want", [], {(1, 1)}) == "want"


def test_progress_counts_only_aired():
    assert progress(season_episodes(AIRED, 1), {(1, 1), (0, 2), (2, 1), (1, 9)}) == (1, 3)
```

- [ ] **Step 2:** `uv run pytest tests/test_rules.py -q`. Expected: erro de coleta `ModuleNotFoundError: No module named 'app.tracking'`.
- [ ] **Step 3:** Escreva os modelos e as regras com as assinaturas do bloco Interfaces. O episódio `(t, e)` está exibido quando `t ≥ 1` e `(t, e) ≤ last_aired`, comparando as tuplas. `aired_specials` mantém a ordem dos episódios recebidos.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam (os 136 anteriores + os novos).
- [ ] **Step 5: Commit**

```bash
git add app/models.py app/tracking tests/test_rules.py
git commit -m "feat(marcacoes): modelos e regras puras de episódios e status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Banco SQLite e repositório

**Files:**
- Create: `app/tracking/db.py`, `app/tracking/repository.py`
- Modify: `app/config.py` (+ `database_path: str = "data/catalogo.db"`), `.gitignore` (+ `data/`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `Marks` e `TrackedSeries` (Task 1), `image_url` de `app/mappers.py`.
- Produces, em `app/tracking/db.py`:
  - `MIGRATIONS: tuple[str, ...]`; a migração 1 é o SQL da spec §6, copiado sem mudança.
  - `connect(path: str | Path) -> sqlite3.Connection`: cria a pasta (exceto para `":memory:"`), usa `check_same_thread=False`, `journal_mode=WAL` e `foreign_keys=ON`, e aplica as migrações de índice ≥ `user_version`.
- Produces, em `app/tracking/repository.py`, `LOCAL_USER_ID = 1` e `TrackingRepository(conn, user_id: int = LOCAL_USER_ID, now: Callable[[], datetime] = <agora em UTC>)`, com os métodos:
  - `marks(tmdb_id: int) -> Marks`: devolve `Marks()` quando a série não tem linha.
  - `marks_for(tmdb_ids: Sequence[int]) -> dict[int, Marks]`: só as séries que têm linha; com lista vazia devolve `{}` sem rodar SQL.
  - `watched(tmdb_id: int) -> frozenset[tuple[int, int]]`
  - `save(tmdb_id: int, *, name: str, poster_path: str | None, status: str | None, favorite: bool, add: Iterable[tuple[int, int]] = (), remove: Iterable[tuple[int, int]] = ()) -> None`: numa única transação (`with conn:`), faz o seguinte:
    - insere os `add` com `INSERT OR IGNORE`;
    - apaga os `remove`;
    - grava a linha da série com `INSERT ... ON CONFLICT DO UPDATE`, com snapshot e `updated_at = now().isoformat()`;
    - apaga a linha se ela ficou sem status, sem favorito e sem episódios.
  - `counts() -> dict[str, int]`: as chaves são `watching`, `want`, `watched` e `favorite`.
  - `list_tab(tab: str) -> list[TrackedSeries]`: `tab` é um de `watching`, `want`, `watched` ou `favorite`. A ordem é `updated_at` decrescente e `poster_url` usa `image_url(poster_path, "w342")`.

- [ ] **Step 1: Escreva `tests/test_repository.py`**

```python
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Marks
from app.tracking.db import MIGRATIONS, connect
from app.tracking.repository import TrackingRepository


class Ticks:
    """Relógio que avança 1 s a cada leitura."""

    def __init__(self):
        self.t = datetime(2026, 10, 17, tzinfo=UTC)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "t.db")
    yield TrackingRepository(conn, now=Ticks())
    conn.close()


def save(repo, tmdb_id, status=None, favorite=False, **kw):
    repo.save(tmdb_id, name=f"S{tmdb_id}", poster_path=f"/{tmdb_id}.jpg", status=status, favorite=favorite, **kw)


def test_connect_creates_folder_and_migrates(tmp_path):
    conn = connect(tmp_path / "data" / "x.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"series_tracking", "watched_episodes"} <= tables
    conn.close()


def test_marks_survive_reopening(tmp_path):
    path = tmp_path / "t.db"
    conn = connect(path)
    save(TrackingRepository(conn), 1, "want", favorite=True)
    conn.close()
    conn = connect(path)
    assert TrackingRepository(conn).marks(1) == Marks("want", True)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn.close()


def test_unmarked_series_has_empty_marks(repo):
    assert repo.marks(99) == Marks()


def test_episodes_add_remove_and_repeat(repo):
    save(repo, 1, "watching", add=[(1, 1), (1, 2)])
    save(repo, 1, "watching", add=[(1, 2)], remove=[(1, 1)])  # repetir não dá erro
    assert repo.watched(1) == frozenset({(1, 2)})


def test_marks_for_returns_only_tracked(repo):
    save(repo, 1, "watching")
    save(repo, 2, favorite=True)
    assert repo.marks_for([1, 2, 3]) == {1: Marks("watching", False), 2: Marks(None, True)}
    assert repo.marks_for([]) == {}


def test_tabs_counts_and_order(repo):
    save(repo, 1, "watching")
    save(repo, 2, "watched", favorite=True)
    save(repo, 3, "watching")
    assert [s.tmdb_id for s in repo.list_tab("watching")] == [3, 1]
    assert [s.tmdb_id for s in repo.list_tab("favorite")] == [2]
    assert repo.counts() == {"watching": 2, "want": 0, "watched": 1, "favorite": 1}
    item = repo.list_tab("watched")[0]
    assert (item.name, item.poster_url) == ("S2", "https://image.tmdb.org/t/p/w342/2.jpg")


def test_updating_moves_series_to_top(repo):
    save(repo, 1, "watching")
    save(repo, 2, "watching")
    save(repo, 1, "watching")
    assert [s.tmdb_id for s in repo.list_tab("watching")] == [1, 2]


def test_row_without_marks_is_deleted(repo):
    save(repo, 1, "want")
    save(repo, 1, None)
    assert repo.marks_for([1]) == {} and repo.counts()["want"] == 0
    save(repo, 2, None, add=[(0, 1)])  # um especial marcado mantém a linha
    assert repo.watched(2) == frozenset({(0, 1)}) and 2 in repo.marks_for([2])


def test_unknown_status_is_refused(repo):
    with pytest.raises(sqlite3.IntegrityError):
        save(repo, 1, "xyz")
```

- [ ] **Step 2:** `uv run pytest tests/test_repository.py -q`. Expected: erro de coleta `No module named 'app.tracking.db'`.
- [ ] **Step 3:** Implemente `db.py`, `repository.py`, o campo `database_path` em `Settings` e a linha `data/` no `.gitignore`. Em `migrate`, depois de cada `executescript`, rode `PRAGMA user_version = N`.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam.
- [ ] **Step 5: Commit**

```bash
git add app/tracking app/config.py .gitignore tests/test_repository.py
git commit -m "feat(marcacoes): banco SQLite com migrações e repositório

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Temporadas na TMDB, `last_aired` e dublês

**Files:**
- Modify: `app/mappers.py`, `app/catalog.py`, `tests/fakes.py`, `tests/fixtures/capturar.py`, `tests/test_tmdb_contract.py`
- Create: `tests/fixtures/season_100088_1.json`, `tests/fixtures/season_100088_2.json` (gerados pelo capturar)
- Test: `tests/test_mappers.py`, `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Episode`, `SeasonDetail` e os campos novos de `SeriesDetail` (Task 1).
- Produces:
  - `to_season_detail(data: Mapping, series_id: int) -> SeasonDetail`: episódios em ordem de `episode_number`; `still_url` em `w300`; `air_date` vazio ou inválido vira `None`; `overview` ausente vira `""`.
  - `to_detail` preenche `poster_path` e `last_aired`, este último vindo de `last_episode_to_air` com o refinamento **e**.
  - `Catalog.season(series_id: int, season_number: int) -> SeasonDetail`: faz `GET /tv/{id}/season/{n}` com `language` e `ttl=TTL_DETAIL`. Uma temporada inexistente lança `TMDBNotFound`.
  - Em `tests/fakes.py`:
    - `FakeCatalog(..., seasons: dict[int, SeasonDetail] | None = None, details: dict[int, SeriesDetail] | None = None)`. `season(series_id, number)` registra a chamada, lança o `error` configurado e lança `TMDBNotFound` quando o número não está em `seasons`. Com `details`, `detail(id)` devolve `details[id]` ou lança `TMDBNotFound`.
    - `make_detail` passa a usar `poster_path="/tlou.jpg"` e `last_aired=(1, 9)`.
    - `make_episode(season: int, number: int, **kw) -> Episode`: os padrões são `name=f"Episódio {number}"`, `overview=""`, `air_date=date(2023, 1, number)`, `runtime=50` e `still_url=None`; o que vier em `kw` substitui o padrão.
    - `make_season(number: int = 1, count: int = 3, future_from: int | None = None) -> SeasonDetail`: os episódios a partir de `future_from` estreiam em `date(2027, 1, 1)`, e o nome é `"Especiais"` quando `number == 0` e `f"Temporada {number}"` nos outros casos.
    - `tracked_detail(**kw) -> SeriesDetail`: é o `make_detail` com `seasons=(Season(1, "Temporada 1", 2023, 3, None), Season(2, "Temporada 2", 2025, 3, None))` e `last_aired=(2, 2)`. O que vier em `kw` substitui esses valores (ex.: `tracked_detail(last_aired=None)`).
    - `tracked_catalog(detail=None, **kw) -> FakeCatalog`: usa `tracked_detail()` e `seasons={1: make_season(1, 3), 2: make_season(2, 3, future_from=3)}`.

- [ ] **Step 1: Gere as fixtures.** Em `capturar.py`, para `n in (1, 2)`, faça `GET /tv/100088/season/{n}` com `language`. De cada episódio, guarde só `episode_number`, `season_number`, `name`, `overview`, `air_date`, `runtime` e `still_path`, e grave em `season_100088_{n}.json`. Rode `uv run python -m tests.fixtures.capturar` e depois `git checkout -- tests/fixtures/*.json`, para que as fixtures antigas voltem ao estado anterior; os dois arquivos novos ficam. Confira com `git status --short tests/fixtures`. Expected: só os dois `season_*.json` novos.
- [ ] **Step 2: Escreva os testes.** Em `tests/test_mappers.py` (importe `date` e `to_season_detail`):

```python
def test_to_season_detail_from_fixture():
    s = to_season_detail(load_fixture("season_100088_1.json"), series_id=100088)
    assert (s.series_id, s.number, len(s.episodes)) == (100088, 1, 9)
    first = s.episodes[0]
    assert (first.season, first.number, first.air_date) == (1, 1, date(2023, 1, 15))
    assert first.still_url.startswith("https://image.tmdb.org/t/p/w300/")


def test_to_season_detail_tolerates_missing_fields():
    s = to_season_detail({"season_number": 0, "name": "Especiais", "episodes": [
        {"episode_number": 2, "name": "B", "air_date": "", "still_path": None},
        {"episode_number": 1, "name": "A"}]}, series_id=5)
    assert [e.number for e in s.episodes] == [1, 2]
    second = s.episodes[1]
    assert (second.air_date, second.still_url, second.runtime, second.overview) == (None, None, None, "")


def test_detail_reads_last_aired_and_poster_path():
    data = load_fixture("tv_100088.json")
    d = to_detail(data, "BR")
    assert d.last_aired == (2, 7) and d.poster_path == data["poster_path"]


def test_last_aired_is_none_without_last_episode():
    data = load_fixture("tv_100088.json")
    data["last_episode_to_air"] = None
    assert to_detail(data, "BR").last_aired is None


def test_last_aired_when_last_episode_is_a_special():
    data = load_fixture("tv_100088.json")
    data["last_episode_to_air"] = {"season_number": 0, "episode_number": 3, "air_date": "2024-12-25"}
    data["seasons"] = [{"season_number": 1, "episode_count": 9, "air_date": "2023-01-15", "name": "T1"},
                       {"season_number": 2, "episode_count": 7, "air_date": "2025-04-13", "name": "T2"}]
    assert to_detail(data, "BR").last_aired == (1, 9)
```

Em `tests/test_catalog.py`:

```python
async def test_season_maps_episodes_in_pt_br(catalog, mock):
    route = mock.get("/tv/100088/season/1").respond(json=load_fixture("season_100088_1.json"))
    s = await catalog.season(100088, 1)
    assert (s.number, len(s.episodes)) == (1, 9)
    assert route.calls.last.request.url.params["language"] == "pt-BR"


async def test_unknown_season_raises_not_found(catalog, mock):
    mock.get("/tv/100088/season/9").respond(404, json={"status_code": 34})
    with pytest.raises(TMDBNotFound):
        await catalog.season(100088, 9)
```

- [ ] **Step 3:** `uv run pytest tests/test_mappers.py tests/test_catalog.py -q`. Expected: `ImportError` de `to_season_detail` e, depois que o import existir, falhas em `last_aired`/`season`.
- [ ] **Step 4:** Implemente `to_season_detail`, os dois campos novos em `to_detail`, `Catalog.season` e as mudanças em `tests/fakes.py`. Acrescente também dois testes de contrato em `tests/test_tmdb_contract.py`:
  - `test_season_has_episode_numbers_and_dates`: o primeiro episódio de `/tv/100088/season/1` tem `episode_number`, `season_number`, `air_date`, `name`, `runtime` e `still_path`;
  - `test_details_have_last_episode_to_air`: `/tv/100088` tem `last_episode_to_air` com `season_number` e `episode_number`.
- [ ] **Step 5:** `uv run pytest -q` e depois `uv run pytest -m tmdb -q`. Expected: tudo passa, inclusive os 6 testes de contrato.
- [ ] **Step 6: Commit**

```bash
git add app/mappers.py app/catalog.py tests
git commit -m "feat(marcacoes): temporadas da TMDB, último episódio exibido e dublês

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `TrackingService`

**Files:**
- Create: `app/tracking/service.py`
- Test: `tests/test_tracking_service.py`

**Interfaces:**
- Consumes: as regras (Task 1), `TrackingRepository` (Task 2) e `Catalog.detail` / `Catalog.season` (Task 3).
- Produces:
  - `class InvalidAction(ValueError)`
  - `TABS = {"assistindo": "watching", "quero": "want", "assistidas": "watched", "favoritas": "favorite"}` e `DEFAULT_TAB = "assistindo"`
  - `TrackingService(catalog, repo: TrackingRepository, today: Callable[[], date] = date.today)`, com os métodos:
    - `marks_for(tmdb_ids: Sequence[int]) -> dict[int, Marks]`: repassa para o repositório.
    - `async series(detail: SeriesDetail) -> SeriesTracking`: `next_title` vem de `catalog.season` só quando o status é `watching` e existe próximo episódio. Se essa busca falhar (`TMDBError`), `next_title` fica `None`.
    - `async set_status(series_id: int, status: str) -> SeriesTracking`: status fora de `want`, `watching` e `watched` lança `InvalidAction`; repetir o status ativo grava `None`.
    - `async toggle_favorite(series_id: int) -> SeriesTracking`
    - `async season(series_id: int, number: int) -> SeasonView`: busca o detalhe e a temporada com `asyncio.gather`. Os erros da TMDB sobem sem tratamento.
    - `async toggle_episode(series_id: int, season: int, episode: int) -> SeasonView`
    - `async mark_up_to(series_id: int, season: int, episode: int) -> SeasonView`
    - `async toggle_season(series_id: int, season: int) -> SeasonView`
    - `async my_series(tab: str) -> MySeries`: uma aba desconhecida vira `DEFAULT_TAB`. Só na aba `assistindo`, o serviço busca o detalhe de cada série, com no máximo 10 buscas simultâneas (`asyncio.Semaphore(10)`), e preenche `next_episode`, `progress` e `caught_up`. Se a busca de uma série falhar (`TMDBError`), o item segue sem esses campos.

Fluxo das ações de episódio:
1. Busca o detalhe.
2. Verifica se a temporada está em `detail.seasons`; se não estiver, lança `InvalidAction`.
3. Busca a temporada.
4. Calcula os exibidos da temporada. Para t ≥ 1, usa `season_episodes(aired_episodes(...), t)`; para t = 0, usa `aired_specials(season.episodes, today())`.
5. Valida o alvo: precisa estar entre os exibidos (no "até aqui" e no ✓). No "temporada inteira", precisa haver algum exibido. Se não, lança `InvalidAction`.
6. Calcula `add` e `remove`, e o novo status com `auto_status`, que usa só os exibidos das temporadas ≥ 1.
7. Chama `repo.save` uma única vez, com o snapshot `detail.name` e `detail.poster_path`.

"Até aqui" na temporada 0 marca os especiais exibidos de número ≤ e.

- [ ] **Step 1: Escreva `tests/test_tracking_service.py`**

```python
from datetime import date

import pytest

from app.models import Season
from app.tmdb.client import TMDBUnavailable
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository
from app.tracking.service import InvalidAction, TrackingService
from tests.fakes import FakeCatalog, make_detail, make_season, tracked_catalog, tracked_detail

ID = 100088
TODAY = date(2026, 10, 17)


@pytest.fixture
def repo():
    conn = connect(":memory:")
    yield TrackingRepository(conn)
    conn.close()


def service(repo, catalog=None):
    return TrackingService(catalog or tracked_catalog(), repo, today=lambda: TODAY)


async def test_marking_an_episode_starts_watching(repo):
    view = await service(repo).toggle_episode(ID, 1, 1)
    assert view.watched == frozenset({(1, 1)}) and view.marks.status == "watching"
    assert view.progress == (1, 3) and view.next_episode == (1, 2)


async def test_toggling_twice_unmarks(repo):
    s = service(repo)
    await s.toggle_episode(ID, 1, 1)
    assert (await s.toggle_episode(ID, 1, 1)).watched == frozenset()


async def test_up_to_crosses_seasons_and_last_aired_means_watched(repo):
    s = service(repo)
    view = await s.mark_up_to(ID, 2, 2)
    assert repo.watched(ID) == {(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)} and view.marks.status == "watched"
    assert (await s.mark_up_to(ID, 2, 2)).marks.status == "watched"  # repetir não muda nada
    assert (await s.toggle_episode(ID, 1, 2)).marks.status == "watching"


async def test_whole_season_marks_then_unmarks(repo):
    s = service(repo)
    assert (await s.toggle_season(ID, 1)).progress == (3, 3)
    assert (await s.toggle_season(ID, 1)).progress == (0, 3)


@pytest.mark.parametrize(("season", "episode"), [(2, 3), (5, 1), (1, 0)])
async def test_unaired_or_unknown_episode_is_refused(repo, season, episode):
    with pytest.raises(InvalidAction):
        await service(repo).toggle_episode(ID, season, episode)
    assert repo.marks_for([ID]) == {}


async def test_tmdb_failure_saves_nothing(repo):
    with pytest.raises(TMDBUnavailable):
        await service(repo, tracked_catalog(error=TMDBUnavailable("fora"))).toggle_episode(ID, 1, 1)
    assert repo.marks_for([ID]) == {}


async def test_status_toggles_off_and_is_validated(repo):
    s = service(repo)
    assert (await s.set_status(ID, "want")).marks.status == "want"
    assert (await s.set_status(ID, "want")).marks.status is None
    with pytest.raises(InvalidAction):
        await s.set_status(ID, "xyz")


async def test_manual_watched_does_not_mark_episodes(repo):
    await service(repo).set_status(ID, "watched")
    assert repo.watched(ID) == frozenset()


async def test_favorite_toggles_and_saves_snapshot(repo):
    assert (await service(repo).toggle_favorite(ID)).marks.favorite is True
    item = repo.list_tab("favorite")[0]
    assert (item.name, item.poster_url) == ("The Last of Us", "https://image.tmdb.org/t/p/w342/tlou.jpg")


async def test_series_tracking_has_next_title_and_season_progress(repo):
    s = service(repo)
    await s.toggle_episode(ID, 1, 1)
    t = await s.series(tracked_detail())
    assert (t.next_episode, t.next_title) == ((1, 2), "Episódio 2")
    assert t.season_progress == {1: (1, 3), 2: (0, 2)}


async def test_watched_episodes_outside_aired_do_not_inflate_progress(repo):
    repo.save(ID, name="x", poster_path=None, status="watching", favorite=False, add=[(1, 1), (2, 3), (7, 1)])
    t = await service(repo).series(tracked_detail())
    assert t.season_progress == {1: (1, 3), 2: (0, 2)} and t.next_episode == (1, 2)


async def test_specials_count_by_date_and_never_change_status(repo):
    detail = make_detail(seasons=(Season(0, "Especiais", None, 2, None), Season(1, "Temporada 1", 2023, 3, None)),
                         last_aired=(1, 3))
    s = service(repo, FakeCatalog(detail=detail, seasons={0: make_season(0, 2, future_from=2), 1: make_season(1, 3)}))
    view = await s.toggle_episode(ID, 0, 1)
    assert view.marks.status is None and view.progress == (1, 1)
    with pytest.raises(InvalidAction):
        await s.toggle_episode(ID, 0, 2)
    assert (await s.series(detail)).season_progress[0] == (1, 0)


async def test_my_series_watching_tab(repo):
    details = {ID: tracked_detail(), 1399: tracked_detail(id=1399, name="Outra")}
    s = service(repo, tracked_catalog(details=details))
    await s.toggle_episode(ID, 1, 1)
    await s.mark_up_to(1399, 2, 2)
    await s.set_status(1399, "watching")  # tudo visto, mas ainda "Assistindo": em dia
    repo.save(777, name="Sumiu", poster_path=None, status="watching", favorite=False)  # some da TMDB
    view = await s.my_series("assistindo")
    by_id = {i.tmdb_id: i for i in view.items}
    assert (by_id[ID].next_episode, by_id[ID].progress, by_id[ID].caught_up) == ((1, 2), (1, 5), False)
    assert (by_id[1399].next_episode, by_id[1399].caught_up) == (None, True)
    assert (by_id[777].next_episode, by_id[777].progress) == (None, None)
    assert view.tab == "assistindo" and view.counts["assistindo"] == 3


async def test_my_series_unknown_tab_falls_back(repo):
    assert (await service(repo).my_series("xyz")).tab == "assistindo"
```

- [ ] **Step 2:** `uv run pytest tests/test_tracking_service.py -q`. Expected: erro de coleta `No module named 'app.tracking.service'`.
- [ ] **Step 3:** Implemente o `service.py` conforme o bloco Interfaces e o fluxo acima.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam.
- [ ] **Step 5: Commit**

```bash
git add app/tracking/service.py tests/test_tracking_service.py
git commit -m "feat(marcacoes): TrackingService com status automático e Minhas séries

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Banco no app, erros e bloco de status na página da série

**Files:**
- Modify: `app/main.py`, `app/routes.py`, `app/templating.py`, `app/templates/serie.html`, `app/static/style.css`, `tests/conftest.py`
- Create: `app/tracking/routes.py` (com `router = APIRouter()` e as rotas de status e favorito), `app/templates/_icones.html`, `app/templates/_status.html`
- Test: `tests/test_routes_tracking.py`

**Interfaces:**
- Consumes: `TrackingService`, `InvalidAction` (Task 4), `connect` (Task 2).
- Produces:
  - `create_app(settings=None, catalog=None, database_path: str | Path | None = None)`. No modo de teste (com `catalog` informado), o banco é `database_path or ":memory:"`; nos outros casos, é `config.database_path`. O `lifespan` cria `app.state.tracking = TrackingService(catalog, TrackingRepository(conn))` e fecha a conexão no fim.
  - `get_tracking(request) -> TrackingService`, em `app/routes.py`.
  - Em `app/tracking/routes.py`:
    - `read_form(request) -> dict[str, str]`: usa `parse_qs`, ficando com o primeiro valor de cada campo.
    - `int_field(form, name) -> int`: lança `InvalidAction` quando o campo está ausente, não é inteiro (`"1.5"`, `"abc"`) ou é negativo.
  - `POST /serie/{id:int}/status` e `POST /serie/{id:int}/favorito`: com HTMX, devolvem `_status.html`; sem HTMX, redirecionam com 303 para `/serie/{id}`.
  - Handlers em `main.py`:
    - `InvalidAction` → "Ação inválida", status 400 com HTMX (fragmento `_erro.html`) ou sem;
    - `sqlite3.Error` → `logger.error(...)`, "Não foi possível salvar sua marcação. Tente novamente.", fragmento 200 com HTMX e página 500 sem.

    Para isso, `_error_response` ganha o parâmetro `htmx_status: int = 200`.
  - `conftest.make_client(fake, db=None)` passa `database_path=db or tmp_path / "catalogo.db"`.
  - Em `templating.py`:
    - `MARK_LABELS = {"want": "Quero assistir", "watching": "Assistindo", "watched": "Assistido", "favorite": "Favorita"}` (global do Jinja);
    - filtro `porcento((feitos, total)) -> "33%"` (`"0%"` quando o total é 0);
    - filtro `ep((t, e)) -> "T1E2"`.
- **Markup exigido pelos testes:**
  - o bloco tem a raiz `<div id="status-serie" class="status-serie">`;
  - cada pílula é `<button class="status-opcao" name="status" value="want" aria-pressed="true|false">` dentro de um `<form method="post" action="/serie/{id}/status" hx-post=... hx-target="#status-serie" hx-swap="outerHTML">`;
  - o favorito é `<button class="favorita" aria-pressed="true|false" aria-label="Favorita" title="Favorita">` num form igual, apontando para `/favorito`.
  - Com status `watching`, aparece o link `<a class="proximo" href="/serie/{id}/temporada/{t}#ep-{e}">`, com o texto `Próximo: T1E2 — Episódio 2`; sem próximo episódio, aparece `Em dia`.
  - O `_status.html` recebe `series_id` e `tracking`.
  - Na `serie.html`, o comentário `{# fase 2: ... #}` é trocado por `{% set series_id = serie.id %}{% include "_status.html" %}`. Os cartões de temporada passam a ser `<a class="temporada" href="/serie/{id}/temporada/{n}">`, com `.progresso` na capa quando há exibidos, e mostram uma linha de progresso:
    - nada exibido → `Em breve`;
    - completa → `3/3` + ícone `watched`;
    - parcial → `1/3`;
    - temporada 0 → `N marcados`, só quando N > 0.
- **Ícones** (`_icones.html`): a macro `icone(nome)` gera `<svg class="icone" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">` com um `path`:
  - `want`: `M6 3h12v18l-6-4-6 4z`
  - `watching`: `M7 4l13 8-13 8z`
  - `watched`: `M4 12.5l5 5L20 6.5`
  - `favorite`: `M12 20s-7-4.4-9.2-9A5 5 0 0 1 12 6a5 5 0 0 1 9.2 5c-2.2 4.6-9.2 9-9.2 9z`
- **CSS** (seção `/* Marcações */`):
  - `.status-serie`: flex com quebra de linha e `gap: 10px`, margem de 18 px acima.
  - `.status-opcao`: pílula com contorno `--fio` e texto `--tela`; quando `aria-pressed="true"`, fica com fundo `--projetor`, texto `--meia-noite` e peso 600.
  - `.favorita`: botão redondo de 44 px; quando `aria-pressed="true"`, o SVG ganha `fill: var(--projetor); stroke: var(--projetor)`.
  - `transition: background-color .15s, color .15s`, desligada em `@media (prefers-reduced-motion: reduce)`.
  - `.proximo`: cor `--projetor`, ocupando a linha toda.
  - `.temporada .temporada-capa`: `position: relative`, contendo a `.progresso`.

- [ ] **Step 1: Escreva `tests/test_routes_tracking.py`**

```python
import sqlite3

import pytest

from app.tmdb.client import TMDBUnavailable
from app.tracking.db import connect
from app.tracking.repository import TrackingRepository
from tests.fakes import HX, tracked_catalog, tracked_detail

ID = 100088


def seed(db, tmdb_id=ID, **kw):
    conn = connect(db)
    fields = {"name": "The Last of Us", "poster_path": None, "status": None, "favorite": False} | kw
    TrackingRepository(conn).save(tmdb_id, **fields)
    conn.close()


def saved_marks(db):
    conn = connect(db)
    marks = TrackingRepository(conn).marks_for([ID])
    conn.close()
    return marks


def test_status_survives_restart(make_client, tmp_path):
    db = tmp_path / "persistente.db"
    r = make_client(tracked_catalog(), db=db).post(f"/serie/{ID}/status", data={"status": "want"},
                                                   follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/serie/{ID}"
    page = make_client(tracked_catalog(), db=db).get(f"/serie/{ID}").text
    assert 'value="want" aria-pressed="true"' in page


def test_status_with_htmx_returns_only_the_block(make_client):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/status", data={"status": "watching"}, headers=HX)
    assert r.status_code == 200 and 'id="status-serie"' in r.text and "<html" not in r.text
    assert "Próximo: T1E1 — Episódio 1" in r.text


def test_favorite_toggles(make_client):
    c = make_client(tracked_catalog())
    assert 'class="favorita" aria-pressed="true"' in c.post(f"/serie/{ID}/favorito", headers=HX).text
    assert 'class="favorita" aria-pressed="false"' in c.post(f"/serie/{ID}/favorito", headers=HX).text


@pytest.mark.parametrize("body", [{"status": "xyz"}, {}])
def test_invalid_status_is_400(make_client, body):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/status", data=body, headers=HX)
    assert r.status_code == 400 and "Ação inválida" in r.text


def test_season_cards_link_and_show_progress(make_client, tmp_path):
    db = tmp_path / "c.db"
    seed(db, status="watching", add=[(1, 1)])
    t = make_client(tracked_catalog(), db=db).get(f"/serie/{ID}").text
    assert f'href="/serie/{ID}/temporada/1"' in t and 'style="--pausa: 33%"' in t
    assert "1/3" in t and "0/2" in t
    assert "Próximo: T1E2 — Episódio 2" in t


def test_series_without_aired_episodes_says_soon(make_client):
    t = make_client(tracked_catalog(detail=tracked_detail(last_aired=None))).get(f"/serie/{ID}").text
    assert t.count("Em breve") == 2 and "--pausa" not in t.split('class="temporadas"')[1]


def test_save_failure_shows_friendly_message(make_client, monkeypatch):
    def broken_save(self, *args, **kwargs):
        raise sqlite3.OperationalError("disco cheio")

    monkeypatch.setattr(TrackingRepository, "save", broken_save)
    c = make_client(tracked_catalog())
    r = c.post(f"/serie/{ID}/status", data={"status": "want"}, headers=HX)
    assert r.status_code == 200 and "Não foi possível salvar sua marcação. Tente novamente." in r.text
    assert c.post(f"/serie/{ID}/status", data={"status": "want"}).status_code == 500


def test_tmdb_down_on_action_saves_nothing(make_client, tmp_path):
    db = tmp_path / "c.db"
    c = make_client(tracked_catalog(error=TMDBUnavailable("fora")), db=db)
    r = c.post(f"/serie/{ID}/status", data={"status": "want"}, headers=HX)
    assert r.status_code == 200 and "A TMDB não respondeu" in r.text
    assert saved_marks(db) == {}
```

- [ ] **Step 2:** `uv run pytest tests/test_routes_tracking.py -q`. Expected: falha. Os POSTs dão 404, porque as rotas ainda não existem, e `make_client` não aceita `db`.
- [ ] **Step 3:** Implemente tudo o que está no bloco Interfaces, inclusive o CSS. Em `app/routes.py`, `series_page` passa `"tracking": await tracking.series(serie)` para o template.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam, inclusive os testes antigos da página da série.
- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat(marcacoes): status e favorita na página da série, com banco no app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Página da temporada e ações nos episódios

**Files:**
- Modify: `app/tracking/routes.py`, `app/templating.py` (filtro `data`), `app/static/style.css`
- Create: `app/templates/temporada.html`, `app/templates/_temporada.html`
- Test: `tests/test_routes_tracking.py` (acrescentar)

**Interfaces:**
- Consumes: `TrackingService.season`, `toggle_episode`, `mark_up_to` e `toggle_season` (Task 4); `read_form`, `int_field` e `MARK_LABELS` (Task 5).
- Produces:
  - `GET /serie/{id:int}/temporada/{n:int}`: devolve a página. Um `TMDBNotFound` vira `HTTPException(404)`, que mostra "Página não encontrada".
  - `POST /serie/{id:int}/episodio` e `POST /serie/{id:int}/ate-aqui`: recebem `temporada` e `episodio`.
  - `POST /serie/{id:int}/temporada/{n:int}/toda`

  Com HTMX, as três ações devolvem `_temporada.html`; sem HTMX, redirecionam com 303 para `/serie/{id}/temporada/{t}`.
  - Filtro `data(d: date) -> "15/01/2023"`.
- **Markup exigido pelos testes:**
  - O bloco tem a raiz `<div id="temporada" class="temporada-bloco">`. Ele contém o progresso (`X de Y assistidos` + `.progresso`), o botão "Marcar temporada inteira" ou "Desmarcar temporada" (só quando há episódios exibidos) e a lista `<ol class="episodios">`.
  - Cada episódio é um `<li id="ep-{n}" class="episodio">`. Ganha a classe extra `episodio--proximo` quando é o próximo da série, e `episodio--futuro` quando ainda não foi ao ar.
  - Os forms de ✓ e de "Marcar até aqui" levam `<input type="hidden" name="temporada" value="{t}">` e `<input type="hidden" name="episodio" value="{n}">`, além de `hx-post`, `hx-target="#temporada"` e `hx-swap="outerHTML"`.
  - O ✓ é um `<button class="marcar" aria-pressed="true|false" aria-label="Marcar E{n} como assistido">`.
  - Episódios não exibidos não têm nenhum dos dois forms.
  - Linha do episódio:
    - título `E{n} · {nome}`;
    - meta: a data quando já foi ao ar; `Estreia em dd/mm/aaaa` ou `Data a definir` quando não foi; depois `· N min` quando há duração;
    - sinopse num `<details><summary>Sinopse</summary>…</details>`;
    - rótulo `próximo` no próximo episódio.
  - A página `temporada.html` tem:
    - o link `<a href="/serie/{id}">← {nome da série}</a>`;
    - o título `{season.name}`;
    - os atalhos para as temporadas de `detail.seasons`, com a 0 por último, já que o mapper ordena assim, e `aria-current="page"` na atual;
    - o bloco incluído.
- **CSS:**
  - `.episodio`: grid `40px 160px 1fr`; abaixo de 600 px, vira `40px 1fr` e a imagem some.
  - `.marcar`: círculo de 40 px com contorno `--fio`; quando `aria-pressed="true"`, fundo `--projetor` e ícone `--meia-noite`.
  - `.episodio--proximo`: `border-left: 3px solid var(--projetor)`.
  - `.episodio--futuro`: `opacity: .55`.
  - `.ate-aqui`: botão de texto em `--nevoa`, sempre visível.
  - `.progresso--topo`: versão em bloco (`position: relative`, altura de 4 px).

- [ ] **Step 1: Acrescente os testes**

```python
def test_season_page_lists_episodes(make_client):
    t = make_client(tracked_catalog()).get(f"/serie/{ID}/temporada/2").text
    assert 'id="ep-1"' in t and "E1 · Episódio 1" in t and "01/01/2023" in t and "0 de 2 assistidos" in t
    assert "Estreia em 01/01/2027" in t and 'name="episodio" value="3"' not in t
    assert "Marcar temporada inteira" in t and f'href="/serie/{ID}"' in t


def test_toggle_episode_with_htmx_updates_block(make_client):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/episodio", data={"temporada": 1, "episodio": 1},
                                            headers=HX)
    assert r.status_code == 200 and 'id="temporada"' in r.text and "<html" not in r.text
    assert "1 de 3 assistidos" in r.text and 'style="--pausa: 33%"' in r.text
    assert 'id="ep-2" class="episodio episodio--proximo"' in r.text


@pytest.mark.parametrize(("path", "body"), [
    ("/episodio", {"temporada": 1, "episodio": 2}),
    ("/ate-aqui", {"temporada": 1, "episodio": 2}),
    ("/temporada/1/toda", {}),
])
def test_episode_actions_without_htmx_redirect_to_season(make_client, path, body):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}{path}", data=body, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/serie/{ID}/temporada/1"


def test_whole_season_button_flips(make_client):
    t = make_client(tracked_catalog()).post(f"/serie/{ID}/temporada/1/toda", headers=HX).text
    assert "3 de 3 assistidos" in t and "Desmarcar temporada" in t


@pytest.mark.parametrize("body", [
    {"temporada": "1", "episodio": "abc"}, {"temporada": "1"}, {"temporada": "1", "episodio": "-1"},
    {"temporada": "1", "episodio": "1.5"}, {"temporada": "2", "episodio": "3"}, {"temporada": "9", "episodio": "1"},
])
def test_invalid_episode_is_400(make_client, body):
    r = make_client(tracked_catalog()).post(f"/serie/{ID}/episodio", data=body, headers=HX)
    assert r.status_code == 400 and "Ação inválida" in r.text


def test_unknown_season_page_is_404(make_client):
    r = make_client(tracked_catalog()).get(f"/serie/{ID}/temporada/9")
    assert r.status_code == 404 and "Página não encontrada" in r.text


def test_season_page_without_aired_episodes_has_no_actions(make_client):
    t = make_client(tracked_catalog(detail=tracked_detail(last_aired=None))).get(f"/serie/{ID}/temporada/1").text
    assert "Marcar temporada inteira" not in t and 'name="episodio"' not in t
```

- [ ] **Step 2:** `uv run pytest tests/test_routes_tracking.py -q`. Expected: os testes novos falham com 404, porque as rotas ainda não existem.
- [ ] **Step 3:** Implemente as rotas, os templates, o filtro `data` e o CSS conforme o bloco Interfaces.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam.
- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat(marcacoes): página da temporada com ✓, até aqui e temporada inteira

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Minhas séries e link no cabeçalho

**Files:**
- Modify: `app/tracking/routes.py`, `app/templating.py`, `app/templates/base.html`, `app/static/style.css`
- Create: `app/templates/minhas_series.html`, `app/templates/_cartao_minha.html`
- Test: `tests/test_routes_tracking.py` (acrescentar)

**Interfaces:**
- Consumes: `TrackingService.my_series` e `TABS` (Task 4).
- Produces:
  - `GET /minhas-series?aba=...`
  - `TAB_LABELS = {"assistindo": "Assistindo", "quero": "Quero assistir", "assistidas": "Assistidas", "favoritas": "Favoritas"}`, global do Jinja e nessa ordem.
- **Markup exigido pelos testes:**
  - **Cabeçalho:** a `.menu-usuario` do `base.html` ganha `<a class="link-topo" href="/minhas-series">Minhas séries</a>`, com `aria-current="page"` quando `request.url.path == "/minhas-series"`.
  - **Abas:** cada uma é `<a class="aba" href="/minhas-series?aba={chave}">`, com `aria-current="page"` na ativa, o ícone, o rótulo e `<span class="contagem">N</span>`.
  - **Título:** `<h1 class="vitrine-titulo">Minhas séries</h1>`.
  - **Cartões** (`_cartao_minha.html`): usam as classes `.cartao`, `.cartao-quadro` e `.cartao-info` do catálogo. Quando há `progress` com exibidos, a capa leva `.progresso`. Na aba Assistindo, embaixo do nome, aparece:
    - `Próximo: T1E2` como link para `/serie/{id}/temporada/{t}#ep-{e}`;
    - ou `Em dia (aguardando episódios)` quando `caught_up`.
  - **Lista vazia:** `Nenhuma série aqui ainda.` e `<a class="botao" href="/">Explorar o catálogo</a>`.
- **CSS:**
  - `.link-topo`: texto `--tela`; com `aria-current`, `border-bottom: 2px solid var(--projetor)`.
  - `.abas`: flex com quebra de linha.
  - `.aba`: pílula; com `aria-current`, `border-bottom` âmbar.
  - `.contagem`: cor `--nevoa`.

- [ ] **Step 1: Acrescente os testes**

```python
def test_header_links_to_my_series(client):
    assert 'href="/minhas-series"' in client.get("/").text


def test_my_series_tabs_with_counts(make_client, tmp_path):
    db = tmp_path / "m.db"
    seed(db, status="watching", add=[(1, 1)])
    seed(db, 1399, name="Outra", status="want", favorite=True)
    details = {ID: tracked_detail(), 1399: tracked_detail(id=1399, name="Outra")}
    c = make_client(tracked_catalog(details=details), db=db)
    t = c.get("/minhas-series").text
    assert 'href="/minhas-series?aba=assistindo" aria-current="page"' in t
    assert t.count('<span class="contagem">1</span>') == 3 and '<span class="contagem">0</span>' in t
    assert "The Last of Us" in t and "Próximo: T1E2" in t and 'style="--pausa: 20%"' in t and "Outra" not in t
    t = c.get("/minhas-series?aba=quero").text
    assert "Outra" in t and "The Last of Us" not in t


def test_unknown_tab_shows_watching(make_client):
    t = make_client(tracked_catalog()).get("/minhas-series?aba=xyz").text
    assert 'href="/minhas-series?aba=assistindo" aria-current="page"' in t


def test_empty_tab_points_to_catalog(make_client):
    t = make_client(tracked_catalog()).get("/minhas-series?aba=favoritas").text
    assert "Nenhuma série aqui ainda." in t and "Explorar o catálogo" in t


def test_caught_up_series(make_client, tmp_path):
    db = tmp_path / "e.db"
    seed(db, status="watching", add=[(1, 1), (1, 2), (1, 3), (2, 1), (2, 2)])
    assert "Em dia (aguardando episódios)" in make_client(tracked_catalog(), db=db).get("/minhas-series").text
```

- [ ] **Step 2:** `uv run pytest tests/test_routes_tracking.py -q`. Expected: os testes novos falham, com 404 em `/minhas-series` e sem o link no cabeçalho.
- [ ] **Step 3:** Implemente a rota, os templates, o link no cabeçalho e o CSS.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam.
- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat(marcacoes): página Minhas séries com abas e próximo episódio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Selos nos cartões do catálogo e da busca

**Files:**
- Modify: `app/routes.py`, `app/templates/_cartao.html`, `app/static/style.css`
- Test: `tests/test_routes_tracking.py` (acrescentar)

**Interfaces:**
- Consumes: `TrackingService.marks_for` (Task 4), `MARK_LABELS` e `icone` (Task 5).
- Produces:
  - Em `catalog_page` (página inteira e fragmento) e em `search_page` (página e "Carregar mais"), o contexto ganha `"marks": tracking.marks_for([c.id for c in page.items])`, com uma única chamada por resposta.
  - Em `_cartao.html`, dentro de `.cartao-quadro`, quando há `marks` para o card, entra `<span class="selos">`. Ele contém:
    - `<span class="selo" role="img" aria-label="{{ MARK_LABELS[status] }}">{{ icone(status) }}</span>`, quando há status;
    - `<span class="selo" role="img" aria-label="Favorita">{{ icone("favorite") }}</span>`, quando é favorita.

  Um card sem `marks` ou com `Marks(None, False)` não ganha selo.
- **CSS:**
  - `.selos`: `position: absolute; top: 8px; left: 8px; display: flex; gap: 4px`.
  - `.selo`: círculo de 26 px com `background: rgba(14, 20, 48, .85)` e `color: var(--projetor)`; o SVG dentro tem 14 px.
  - Na favorita, o coração é preenchido (`fill: currentColor`).

- [ ] **Step 1: Acrescente o teste** (importe `FakeCatalog`, `make_page` e `make_detail` de `tests.fakes`):

```python
def test_catalog_more_and_search_show_badges(make_client, tmp_path):
    db = tmp_path / "s.db"
    seed(db, 1, name="Série 1", status="watching", favorite=True)
    c = make_client(FakeCatalog(discover=make_page(), search=make_page(), detail=make_detail()), db=db)
    for url, headers in [("/", {}), ("/?pagina=2", HX), ("/buscar?q=serie", {})]:
        t = c.get(url, headers=headers).text
        assert t.count('class="selo"') == 2, url
        assert 'aria-label="Assistindo"' in t and 'aria-label="Favorita"' in t
```

- [ ] **Step 2:** `uv run pytest tests/test_routes_tracking.py -q`. Expected: falha com `assert 0 == 2`.
- [ ] **Step 3:** Implemente o que está no bloco Interfaces.
- [ ] **Step 4:** `uv run pytest -q`. Expected: todos passam.
- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "feat(marcacoes): selos de status e favorita nos cartões

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Revisão visual, documentação e verificação com o usuário

**Files:**
- Modify: `app/static/style.css` (só os ajustes que as capturas pedirem), `README.md`, `docs/superpowers/specs/2026-10-16-marcacoes-design.md` (o campo Status passa a "implementada")

- [ ] **Step 1: Suba o servidor sem `--reload`.** Pare o anterior e libere a porta 8000. Com a TMDB real, marque alguns episódios em uma série e marque outra como favorita.
- [ ] **Step 2: Capture as telas** com o Edge headless, em 1366×900 e no celular. Para o celular, use 390 px com o wrapper de iframe `shots/celular.html` da pasta scratchpad, porque o headless não desce de cerca de 500 px. As telas são:
  - série (bloco de status e cartões de temporada);
  - temporada (episódios, próximo, futuros, barra no topo);
  - Minhas séries (abas, barra nos pôsteres, Próximo);
  - catálogo com selos.

  Confira cada tela contra a spec §10. Também não pode haver rolagem horizontal no celular, emoji nem botões que pareçam desligados.
- [ ] **Step 3:** Corrija o CSS conforme o que as capturas mostrarem e rode `uv run pytest -q`. Expected: todos passam.
- [ ] **Step 4: Atualize o README.** Inclua uma seção curta "Marcações": o banco fica em `data/catalogo.db`; para fazer backup, copie o arquivo; para recomeçar do zero, apague o arquivo com o app parado.
- [ ] **Step 5: Commit**

```bash
git add app/static/style.css README.md docs/superpowers/specs/2026-10-16-marcacoes-design.md
git commit -m "docs: marcações no README e ajustes visuais da revisão

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verifique no navegador do usuário.** Passe pelos critérios 1 a 8 e o 10 da spec, por voltar e avançar, e pela largura de celular.
