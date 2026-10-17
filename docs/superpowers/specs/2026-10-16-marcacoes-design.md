# Marcações e acompanhamento de episódios — Design (Fase 2a)

- **Data:** 2026-10-16 (telas revistas em 2026-10-17 para a identidade visual nova da fase 1)
- **Status:** aguardando revisão
- **Depende de:** Fase 1, Catálogo (`2026-10-16-catalogo-series-design.md`), já implementada no branch `feat/fase-1-catalogo`

## 1. Objetivo

Permitir marcar cada série como **Quero assistir**, **Assistindo** ou **Assistido**, marcar **favoritas** e acompanhar **episódio por episódio** onde você parou. O progresso aparece numa página **"Minhas séries"** e em **selos** no catálogo.

### Roadmap revisado

| Fase | Conteúdo |
|---|---|
| 1 | Catálogo (feito) |
| **2a (esta spec)** | Marcações, episódios, Minhas séries e selos. **Sem login**: um único usuário, app local. |
| 2b | Login, contas por convite e proteção CSRF. Cada pessoa com as próprias marcações. |
| 3 | Deploy online |

## 2. Escopo

**Inclui:**
- Status da série (Quero assistir / Assistindo / Assistido) e favorito (♥), na página da série.
- Página da temporada com os episódios: ✓ individual, "marcar até aqui" e "marcar/desmarcar temporada inteira".
- Status automático conforme os episódios marcados.
- Página "Minhas séries", com abas e "Próximo: TxEy" na aba Assistindo.
- Selos de status e favorito nos cartões do catálogo e da busca.
- Banco de dados SQLite.

**Não inclui:**
- Login e contas (fase 2b).
- Aviso de "nova temporada" para séries já assistidas.
- Histórico, desfazer, estatísticas.
- Importar de outros apps.
- Filtro "esconder assistidas" (descartado pelo usuário).

## 3. Premissas

- **Episódio exibido** é todo episódio `(t, e)` com `t ≥ 1` e `(t, e) ≤ last_episode_to_air` (comparação primeiro pela temporada, depois pelo episódio). Esse campo vem dos detalhes da série na TMDB e é a **única** referência para saber o que já foi ao ar, tanto nas regras quanto na tela.
- Os episódios de cada temporada são numerados de 1 a `episode_count`, que é o padrão da TMDB.
- **Especiais** (temporada 0) podem ser vistos e marcados, mas **não contam** para progresso, status automático nem "próximo episódio". Como o `last_episode_to_air` não cobre a temporada 0, um especial conta como exibido quando a data de exibição é anterior ou igual à data de hoje (`air_date ≤ hoje`). Essa data vem de `/tv/{id}/season/0`.
- Marcar "Assistido" à mão **não** marca episódios. Para isso existem os atalhos.
- Quando sai uma temporada nova de uma série "Assistida", o status não muda sozinho.
- O nome e o pôster da série são guardados no banco (snapshot) e atualizados a cada ação, para "Minhas séries" abrir sem chamar a TMDB para cada série.

## 4. Critérios de sucesso

1. Status e favorito definidos na página da série continuam lá depois de reiniciar o app.
2. Na temporada, o ✓ marca e desmarca **sem recarregar a página**, e a barra de progresso e o "próximo" atualizam na hora.
3. "Marcar até aqui" em T2E3 marca a T1 inteira e mais T2E1 a T2E3.
4. Marcar o último episódio exibido muda o status para **Assistido**. Desmarcar qualquer um volta para **Assistindo**.
5. Minhas séries mostra as quatro abas com contagens. Na aba Assistindo aparece "Próximo: TxEy", com link para o episódio, ou "Em dia ✓".
6. Os cartões do catálogo e da busca mostram os selos de status e de favorita.
7. Episódios que ainda não foram ao ar não podem ser marcados.
8. Com a TMDB fora do ar, uma marcação mostra a mensagem de erro e **não grava nada**.
9. `uv run pytest` passa sem internet.
10. A barra âmbar "onde parei" mostra o progresso real (marcados ÷ exibidos) nos cartões de temporada, na página da temporada e na aba Assistindo.

## 5. Arquitetura

```
app/
  tracking/
    __init__.py
    db.py           # abre o SQLite (WAL) e aplica as migrações (PRAGMA user_version)
    repository.py   # TrackingRepository: todo o SQL
    rules.py        # regras puras: episódios exibidos, status automático, "até aqui", próximo episódio
    service.py      # TrackingService: Catalog + repositório + regras
    routes.py       # /minhas-series e as ações POST
  catalog.py        # + season(series_id, season_number)
  mappers.py        # + to_season_detail(); to_detail() passa a ler last_episode_to_air
  models.py         # + Episode, SeasonDetail, Marks, TrackedSeries; SeriesDetail ganha last_aired
  routes.py         # + página /serie/{id}/temporada/{n}; selos no catálogo e na busca
  config.py         # + DATABASE_PATH
```

**Dependências entre as partes:** as rotas chamam o `TrackingService`, que chama o `Catalog` e o `TrackingRepository` e usa `rules.py`. As regras são funções puras, sem banco nem HTTP. O repositório é a única parte que conhece SQL. **Nenhuma dependência nova:** usa o `sqlite3` da biblioteca padrão.

## 6. Banco de dados

**Arquivo:** definido por `DATABASE_PATH`, com padrão `data/catalogo.db`. A pasta é criada se não existir, e `data/` entra no `.gitignore`. Para fazer backup, basta copiar o arquivo.

**Conexão:** uma única `sqlite3.connect(path, check_same_thread=False)`, aberta no `lifespan` do app, com `PRAGMA journal_mode=WAL` e `PRAGMA foreign_keys=ON`. As operações levam frações de milissegundo e rodam direto nas rotas assíncronas. Cada ação é uma transação (`with conn:`).

**Migrações:** `db.py` tem uma lista `MIGRATIONS` de scripts SQL. Ao iniciar, o app aplica os scripts de índice ≥ `PRAGMA user_version` e atualiza o `user_version`. A fase 2b só acrescenta um script.

**Migração 1:**
```sql
CREATE TABLE series_tracking (
    user_id     INTEGER NOT NULL DEFAULT 1,
    tmdb_id     INTEGER NOT NULL,
    status      TEXT CHECK (status IN ('want', 'watching', 'watched')),  -- NULL = sem status
    favorite    INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    name        TEXT NOT NULL,
    poster_path TEXT,
    updated_at  TEXT NOT NULL,  -- ISO 8601 UTC
    PRIMARY KEY (user_id, tmdb_id)
);

CREATE TABLE watched_episodes (
    user_id    INTEGER NOT NULL DEFAULT 1,
    tmdb_id    INTEGER NOT NULL,
    season     INTEGER NOT NULL,
    episode    INTEGER NOT NULL,
    watched_at TEXT NOT NULL,
    PRIMARY KEY (user_id, tmdb_id, season, episode)
);
```

- **Usuário:** `user_id` é sempre `LOCAL_USER_ID = 1` nesta fase. Na fase 2b ele vira chave estrangeira para a tabela de usuários.
- **Limpeza:** quando uma série fica sem status, sem favorito e sem episódios marcados, a linha dela em `series_tracking` é apagada.

## 7. Modelos novos

`@dataclass(frozen=True)`, como os da fase 1:

- **`Episode`**: `season: int`, `number: int`, `name: str`, `overview: str`, `air_date: date | None`, `runtime: int | None`, `still_url: str | None` (`w300`).
- **`SeasonDetail`**: `series_id`, `series_name`, `number`, `name`, `episodes: tuple[Episode, ...]`, mais a lista de temporadas da série para os atalhos (T1, T2…).
- **`Marks`**: `status: str | None` (`want`/`watching`/`watched`) e `favorite: bool`.
- **`TrackedSeries`** (cartão de Minhas séries): `tmdb_id`, `name`, `poster_url`, `marks: Marks`, `next_episode: tuple[int, int] | None`, `caught_up: bool`, `progress: tuple[int, int] | None` (marcados, exibidos; só na aba Assistindo).
- **`SeriesDetail`** ganha `last_aired: tuple[int, int] | None`, vindo de `last_episode_to_air`.

**Rótulos de status:** `want` → "Quero assistir" (🔖), `watching` → "Assistindo" (▶), `watched` → "Assistido" (✓).

**Ícones:** nesta spec, 🔖 ▶ ✓ ♥ são só abreviações. Na tela, são ícones SVG desenhados em linha (traço de 2px, `currentColor`), não emoji: emoji muda de aparência em cada sistema e destoa da fonte Archivo e da paleta.

## 8. Regras (`rules.py`)

Todas são funções puras. Os episódios são representados por pares `(temporada, episódio)`.

- **`aired_episodes(seasons, last_aired)`:** a lista ordenada dos episódios exibidos, a partir de `[(número, episode_count)]` das temporadas ≥ 1 e de `last_aired`. Vazia se `last_aired` for `None`.
- **`next_episode(aired, watched)`:** o primeiro episódio exibido não marcado, ou `None` ("Em dia").
- **`up_to(aired, target)`:** os episódios exibidos ≤ `target`. Usada pelo "marcar até aqui".
- **`season_episodes(aired, season)`:** os episódios exibidos de uma temporada. Usada pelo "temporada inteira".
- **`auto_status(current, aired, watched)`:** o status depois de qualquer ação nos episódios. Considera só episódios exibidos da temporada ≥ 1:

| Situação | Novo status |
|---|---|
| há episódios exibidos e **todos** estão marcados | `watched` |
| **alguns** marcados | `watching` (vale também se estava `want` ou `watched`) |
| **nenhum** marcado | `current` (não muda) |

**Ações nos episódios**, todas seguidas de `auto_status`:

| Ação | Efeito |
|---|---|
| ✓ em um episódio | marca ou desmarca só ele (precisa estar exibido) |
| marcar até aqui `(t, e)` | marca todos de `up_to`; não desmarca nada |
| temporada inteira `t` | se todos os exibidos da temporada estão marcados, desmarca a temporada; senão, marca todos |

**Temporada 0 (Especiais):** as três ações funcionam igual, mas a lista de episódios exibidos vem das datas da própria temporada (`air_date ≤ hoje`) em vez de `aired_episodes`. O `auto_status` ignora a temporada 0, então marcar especiais nunca muda o status.

**Status manual:** muda só o status. Clicar no status que já está ativo remove o status (`NULL`).

## 9. Integração com a TMDB

| Uso | Endpoint | Cache |
|---|---|---|
| Episódios da temporada | `GET /tv/{id}/season/{n}?language=pt-BR` | 6 h (`TTL_DETAIL`) |
| Episódios exibidos e snapshot | `GET /tv/{id}` (o mesmo dos detalhes) | 6 h (já existe) |

- `Catalog.season(series_id, season_number) -> SeasonDetail`
- Uma temporada inexistente devolve 404 → `TMDBNotFound` → página 404.

## 10. Telas

Os mockups aprovados ficam fora do repositório e foram feitos antes do visual novo. As telas seguem a identidade da fase 1 ("a sala escura, a tela acesa": meia-noite `#0e1430`, veludo `#171f48`, fio `#2b3570`, tela `#eef0ff`, névoa `#9aa3cc`, projetor âmbar `#ffb547`, fonte Archivo).

**A barra "onde parei" vira dado real.** A barra âmbar fina (`.pausa`, largura em `--pausa`) é a assinatura do app e hoje é decorativa no destaque. Nesta fase ela passa a mostrar o progresso de verdade, com `--pausa` = marcados ÷ exibidos:
- na base de cada cartão de temporada, na página da série;
- no topo da página da temporada, junto de "X de Y assistidos";
- na base do pôster dos cartões da aba Assistindo, em Minhas séries.

O destaque da tela inicial continua com a barra decorativa. A barra não aparece quando nada foi ao ar. É a única peça de destaque das telas novas: o resto usa os componentes que já existem (pílulas, botões, grade de pôsteres).

Resumo das telas:

**Cabeçalho:** link de texto **"Minhas séries"** no espaço `.menu-usuario`, com sublinhado âmbar quando a página está aberta.

**Página da série** (`serie.html`):
- **Seletor de status** logo abaixo da linha de informações (anos, situação, temporadas): três pílulas (🔖 Quero assistir, ▶ Assistindo, ✓ Assistido). A ativa fica preenchida em âmbar com texto meia-noite; as outras têm contorno `--fio`. No celular, as pílulas quebram linha.
- Botão redondo **♥ Favorita** ao lado: contorno quando desligado, coração preenchido em âmbar quando ligado. Troca de cor com transição de 150 ms, desligada com `prefers-reduced-motion`.
- Com status `watching`: **"▶ Próximo: TxEy — título"**, com link para `/serie/{id}/temporada/{x}#ep-{y}`. Se não houver próximo: "Em dia ✓".
- O bloco de status (`_status.html`) é trocado via HTMX.
- **Temporadas:** os cartões passam a ser links para a página da temporada. Cada um mostra a barra "onde parei" na base da imagem e o texto "marcados/exibidos" ("9/9 ✓" quando completa), ou "Em breve" quando nada foi ao ar.

**Página da temporada** (`temporada.html`, nova):
- Link "← nome da série", título "Temporada N" e atalhos para as outras temporadas, com os Especiais por último.
- Barra de progresso com "X de Y assistidos" e o botão "✓ Marcar temporada inteira" (ou "Desmarcar temporada").
- **Lista de episódios:**
  - cada linha tem `id="ep-{n}"`, botão ✓ circular de 40px (contorno `--fio`; marcado, fica preenchido em âmbar com o check em meia-noite), imagem 16:9 (some em telas com menos de 600px), "E{n} · título", data (dd/mm/aaaa) e duração em `--nevoa`
  - a sinopse fica em `<details>`
  - o próximo episódio da série, se for desta temporada, ganha borda esquerda âmbar e o rótulo "próximo"
  - "marcar até aqui" aparece nos episódios exibidos e não marcados, como botão discreto em `--nevoa`, **sempre visível** (não só no hover)
- **Episódios não exibidos** ficam esmaecidos, com "Estreia em dd/mm/aaaa" (ou "Data a definir") e sem ✓.
- Todo o conteúdo variável fica num bloco (`_temporada.html`) que as ações devolvem via HTMX.

**Minhas séries** (`minhas_series.html`, nova):
- **Abas:**
  - ▶ Assistindo (`aba=assistindo`, o padrão)
  - 🔖 Quero assistir (`aba=quero`)
  - ✓ Assistidas (`aba=assistidas`)
  - ♥ Favoritas (`aba=favoritas`)

  Cada aba mostra a contagem. Um valor de aba inválido cai na aba padrão.
- **Cabeçalho da página:** título "Minhas séries" no mesmo letreiro condensado de "Séries no streaming agora"; abas em pílulas com a contagem, a ativa com sublinhado âmbar.
- **Cartões:** a mesma grade de pôsteres do catálogo, com pôster e nome do snapshot embaixo, ordenados por `updated_at` decrescente.
- **Aba Assistindo:** cada cartão tem a barra "onde parei" na base do pôster e, embaixo do nome, "Próximo: TxEy" em âmbar (link direto para o episódio) ou "Em dia ✓ (aguardando episódios)". Para isso, o app busca os detalhes de cada série com no máximo 10 chamadas simultâneas. Se a busca de uma série falhar, só aquele cartão fica sem a barra e sem a linha "Próximo".
- **Lista vazia:** "Nenhuma série aqui ainda." e um link para o catálogo.

**Selos** (`_cartao.html`): dentro de `.cartao-quadro`, no canto superior esquerdo do pôster, uma pastilha circular de 26px (meia-noite a 85% de opacidade) com o ícone do status em âmbar, e uma segunda pastilha com ♥ quando é favorita. Cada pastilha tem `aria-label` ("Assistindo", "Favorita"). Séries sem marcação não têm selo. Nome, ano e nota continuam embaixo do pôster, como hoje.

## 11. Rotas

| Método e rota | Corpo (form) | Resposta com HTMX | Resposta sem HTMX |
|---|---|---|---|
| `GET /serie/{id:int}/temporada/{n:int}` | — | página | página |
| `GET /minhas-series` | `aba` (query) | página | página |
| `POST /serie/{id:int}/status` | `status` = `want`/`watching`/`watched` | `_status.html` | 303 → `/serie/{id}` |
| `POST /serie/{id:int}/favorito` | — | `_status.html` | 303 → `/serie/{id}` |
| `POST /serie/{id:int}/episodio` | `temporada`, `episodio` | `_temporada.html` | 303 → página da temporada |
| `POST /serie/{id:int}/ate-aqui` | `temporada`, `episodio` | `_temporada.html` | 303 → página da temporada |
| `POST /serie/{id:int}/temporada/{n:int}/toda` | — | `_temporada.html` | 303 → página da temporada |

**Fluxo de toda ação POST:**
1. `catalog.detail(id)` (normalmente já no cache) fornece os episódios exibidos e o snapshot.
2. A entrada é validada.
3. Uma única transação grava a marcação, recalcula o status, atualiza o snapshot e o `updated_at`, e apaga a linha se ela ficar vazia.
4. O bloco é renderizado.

A TMDB é consultada **antes** de qualquer gravação.

**Selos:** `/` e `/buscar` chamam `repository.marks_for(ids)` uma única vez por página, também nos fragmentos de "Carregar mais".

## 12. Erros

| Situação | Resposta |
|---|---|
| TMDB fora do ar numa ação | os mesmos handlers da fase 1 (fragmento 200 com HTMX, 503 na página inteira); **nada é gravado** |
| Valor inválido (status desconhecido, episódio inexistente, não exibido, número não inteiro) | 400 com o fragmento "Ação inválida". O HTMX não troca o conteúdo em 4xx, então a tela não muda. |
| Temporada inexistente na TMDB | página 404 "Página não encontrada" |
| Erro do SQLite (`sqlite3.Error`) | "Não foi possível salvar sua marcação. Tente novamente." (fragmento 200 com HTMX; página 500); log ERROR |

**Pendência registrada para a fase 2b:** as ações POST não têm proteção CSRF. Isso é aceitável enquanto o app roda só localmente, mas a proteção é **obrigatória** antes de ir para a internet, junto com o login.

## 13. Testes

Mesmo esquema da fase 1: TDD, nada de internet, TMDB simulada (`FakeCatalog` ganha `season()`).

| Arquivo | Como | O que cobre |
|---|---|---|
| `test_rules.py` | funções puras | `aired_episodes` (sem Especiais, `last_aired` `None`, temporada parcial); `next_episode` e "Em dia"; `up_to` atravessando temporadas; `season_episodes`; cada linha da tabela de `auto_status`, incluindo "Assistido manual + 1 episódio → Assistindo" |
| `test_repository.py` | SQLite real em `tmp_path` | migração do zero e ao reabrir (`user_version`); status; favorito; episódios individuais e em lote; `marks_for(ids)`; listas por aba e contagens; ordem por `updated_at`; limpeza da linha vazia |
| `test_tracking_service.py` | `FakeCatalog` + repositório real | episódio → status automático; até aqui; temporada inteira (marcar e desmarcar); TMDB falhando → nada gravado; episódio não exibido → recusado |
| `test_routes_tracking.py` | `TestClient` + `FakeCatalog` + banco temporário | página da temporada (lista, progresso com `--pausa` certo, próximo, não exibidos sem ✓, `id="ep-N"`); cada POST: fragmento com HTMX e 303 sem; 400 em inválidos; Minhas séries (abas, contagens, aba inválida, vazio, Próximo/Em dia, barra de progresso); selos no catálogo, na busca e no "Carregar mais"; mensagem de falha ao gravar |
| `test_mappers.py` | fixtures reais | `to_season_detail`; `last_aired` |
| `test_tmdb_contract.py` | API real (`-m tmdb`) | formato de `/tv/{id}/season/{n}` (`episode_number`, `air_date`) e presença de `last_episode_to_air` |

**Fixtures:** o `capturar` passa a gravar `season_100088_1.json` e `season_100088_2.json`.

**Verificação manual no navegador, com o usuário:** os critérios 1 a 8 e o 10, mais voltar/avançar e a largura de celular.

## 14. Limitações conhecidas

- Assume episódios numerados de 1 a N em cada temporada. Uma numeração fora do padrão na TMDB pode desalinhar o "até aqui".
- O que conta como "exibido" depende do `last_episode_to_air` da TMDB, que pode atrasar algumas horas (cache de 6 h).
- Uma série "Assistida" não volta sozinha para "Assistindo" quando sai uma temporada nova.
- A aba Assistindo faz uma chamada (com cache) por série para calcular o próximo episódio.
- Sem login: quem acessar o app no seu computador vê e altera as marcações.
