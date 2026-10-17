# Catálogo de Séries — Design (Fase 1: Catálogo)

- **Data:** 2026-10-16
- **Status:** aguardando revisão
- **Escopo deste documento:** subprojeto 1 de 3 (Catálogo). Contas/listas e deploy terão specs próprias.

## 1. Objetivo

Um app web pessoal que mostra as séries disponíveis **agora** nos serviços de streaming do Brasil, com filtros, busca por nome e página de detalhes. Os dados vêm da API da TMDB (que usa dados de disponibilidade do JustWatch).

**Para quem:** o dono do projeto e, nas fases seguintes, algumas pessoas convidadas (família e amigos), cada uma com a própria conta.

### Roadmap

| Fase | Subprojeto | Conteúdo |
|---|---|---|
| **1 (esta spec)** | Catálogo | Catálogo com filtros, busca, detalhes. Roda localmente. |
| 2 | Contas + listas | Login, contas por convite, marcar "assistida" e "favorita", telas "minhas listas", banco de dados. |
| 3 | Deploy | Hospedagem online, banco em produção, HTTPS, acesso por link de qualquer lugar. |

## 2. Escopo da Fase 1

**Inclui:**
- Catálogo em grade de pôsteres com filtros por serviço, tipo de disponibilidade, gênero, ano de estreia e nota mínima, além de ordenação.
- Busca por nome.
- Página de detalhes da série com "onde assistir no Brasil".
- Layout responsivo (computador e celular).

**Não inclui (fica para depois ou foi descartado):**
- Contas, login, listas de assistidas e favoritas, banco de dados (fase 2).
- Deploy (fase 3).
- Busca enquanto digita, porque cada letra geraria cerca de 20 chamadas à TMDB.
- Detalhes de episódios, filmes, outras regiões e outros idiomas.

## 3. Premissas

- Região fixa **BR**; textos da TMDB em **pt-BR**.
- O usuário tem uma conta na TMDB e gera o **API Read Access Token** (token v4, usado como Bearer).
- O código fica em `C:\Projetos\catalogo-series`, **fora do Google Drive**. Pastas sincronizadas causam problemas com `.venv` e `.git`. O backup é feito via GitHub (repositório privado, criado mais adiante com confirmação do usuário).
- Python 3.12+ e [uv](https://docs.astral.sh/uv/) instalados.

## 4. Critérios de sucesso

1. `uv run uvicorn app.main:app --reload` sobe o app em `http://localhost:8000`.
2. Filtrar "Netflix + Max, Assinatura, Drama, nota ≥ 7" mostra só séries que atendem aos filtros (conferível na página de detalhes de cada uma).
3. Mudar um filtro atualiza só a grade, sem recarregar a página; a URL reflete os filtros, e o botão voltar do navegador funciona.
4. Buscar "office" lista as séries com esse nome e mostra onde cada uma está no BR (ou "Fora do streaming no BR").
5. A página de uma série mostra sinopse, temporadas, elenco, trailer (quando houver) e onde assistir, agrupado por tipo.
6. Com a TMDB fora do ar, o app mostra uma mensagem amigável em vez de quebrar.
7. `uv run pytest` passa sem acessar a internet.

## 5. Arquitetura

FastAPI renderiza HTML com Jinja2 no servidor; HTMX troca só os pedaços da página que mudam. O token da TMDB nunca chega ao navegador.

```
Navegador ──HTTP──▶ FastAPI (uvicorn)
                     ├─ routes.py        → lê a URL, escolhe página inteira ou fragmento HTMX
                     ├─ catalog.py       → regras: Filters → parâmetros TMDB; JSON → modelos
                     └─ tmdb/client.py   → HTTP com a TMDB (httpx assíncrono) + tmdb/cache.py
                                              │
                                              ▼ HTTPS
                                      api.themoviedb.org/3
```

**Regra de dependência:** cada camada conhece só a de baixo. `catalog.py` não sabe nada de HTTP do navegador nem de HTML; `client.py` não sabe nada de regras de negócio.

### Estrutura de pastas

```
catalogo-series/
  pyproject.toml           # uv; dependências e configuração do pytest
  .env.example             # modelo das variáveis de ambiente (o .env real não vai pro git)
  .gitignore               # .env, .venv/, __pycache__/, .superpowers/, .pytest_cache/
  app/
    main.py                # cria o app, lifespan (abre/fecha o cliente HTTP), static, templates, handlers de erro
    config.py              # Settings (pydantic-settings)
    models.py              # dataclasses do domínio
    catalog.py             # lógica do catálogo, busca e detalhes
    routes.py              # rotas HTTP
    tmdb/
      __init__.py
      client.py            # TMDBClient + exceções
      cache.py             # TTLCache
    templates/
      base.html            # cabeçalho (logo, busca, espaço do menu do usuário), rodapé com atribuições
      catalogo.html        # página do catálogo (filtros + grade)
      _grade.html          # fragmento: contador + cartões + botão "Carregar mais"
      _cartoes.html        # fragmento: só cartões + próximo botão "Carregar mais"
      _cartao.html         # um cartão de série (incluído pelos outros)
      busca.html           # resultados da busca
      serie.html           # página de detalhes
      erro.html            # página de erro (404, configuração, indisponível)
      _erro.html           # fragmento de erro para pedidos HTMX
    static/
      style.css
      htmx.min.js          # HTMX 2.x, arquivo local (sem CDN)
      tmdb-logo.svg        # logo oficial da TMDB para a atribuição
  tests/
    conftest.py
    fixtures/              # respostas reais da TMDB, capturadas uma vez e enxugadas
    test_cache.py
    test_client.py
    test_catalog.py
    test_routes.py
    test_tmdb_contract.py  # marcado @pytest.mark.tmdb; desligado por padrão
  docs/superpowers/specs/
```

### Dependências

- **Produção:** `fastapi`, `uvicorn[standard]`, `jinja2`, `httpx`, `pydantic-settings`
- **Desenvolvimento:** `pytest`, `pytest-asyncio`, `respx`

### Configuração (`config.py`)

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `TMDB_TOKEN` | sim | — | API Read Access Token (guardado como `SecretStr`) |
| `TMDB_REGION` | não | `BR` | `watch_region` |
| `TMDB_LANGUAGE` | não | `pt-BR` | `language` |
| `LOG_LEVEL` | não | `INFO` | nível de log |

Sem `TMDB_TOKEN`, o app **não inicia** e mostra a mensagem: `TMDB_TOKEN não definido. Copie .env.example para .env e preencha o token.`

## 6. Modelos (`models.py`)

Dataclasses imutáveis (`frozen=True`):

- **`Filters`**: `providers: tuple[int, ...]`, `types: tuple[str, ...]`, `genres: tuple[int, ...]`, `year_from: int | None`, `year_to: int | None`, `min_rating: int | None`, `sort: str`, `page: int`.
- **`Provider`**: `id`, `name`, `logo_url`.
- **`SeriesCard`**: `id`, `name`, `year: int | None`, `rating: float | None` (None quando não há votos), `poster_url: str | None`, `providers: tuple[Provider, ...] | None`. `None` = não consultado (catálogo) ou consulta falhou; tupla vazia = não está em nenhum streaming no BR.
- **`CatalogPage`**: `items: tuple[SeriesCard, ...]`, `page`, `total_pages` (limitado a 500), `total_results`.
- **`WatchOptions`**: `link: str | None` (página da TMDB com os links para os serviços), `by_type: dict[str, tuple[Provider, ...]]`, na ordem flatrate, free, ads, rent, buy, só com os tipos não vazios.
- **`Season`**: `number`, `name`, `year: int | None`, `episode_count`, `poster_url: str | None`.
- **`CastMember`**: `name`, `character`, `profile_url: str | None`.
- **`SeriesDetail`**: `id`, `name`, `original_name`, `overview`, `first_year`, `last_year`, `status_label`, `in_production`, `seasons_count`, `episodes_count`, `genres: tuple[str, ...]`, `rating`, `vote_count`, `poster_url`, `backdrop_url`, `trailer_youtube_key: str | None`, `seasons: tuple[Season, ...]`, `cast: tuple[CastMember, ...]` (máx. 10), `watch: WatchOptions`.

**Identificador:** as séries são sempre identificadas pelo `id` da TMDB. A fase 2 vai guardar só `(usuário, tmdb_id, tipo_de_lista)`.

**Imagens:** URLs montadas como `https://image.tmdb.org/t/p/{tamanho}{path}`, com a base fixa no código (não consultamos `/configuration`). Tamanhos: pôster da grade `w342`, pôster do detalhe `w500`, fundo `w1280`, logos `w92`, elenco `w185`, temporadas `w185`.

## 7. Integração com a TMDB

Base: `https://api.themoviedb.org/3`, cabeçalho `Authorization: Bearer <TMDB_TOKEN>`.

| Uso | Endpoint | Parâmetros principais | Cache |
|---|---|---|---|
| Lista de serviços (filtro) | `GET /watch/providers/tv` | `watch_region`, `language` | 24 h |
| Lista de gêneros (filtro) | `GET /genre/tv/list` | `language` | 24 h |
| Catálogo | `GET /discover/tv` | ver §8.2 | 1 h |
| Busca | `GET /search/tv` | `query`, `page`, `language`, `include_adult=false` | 1 h |
| Onde assistir (busca) | `GET /tv/{id}/watch/providers` | — | 6 h |
| Detalhes | `GET /tv/{id}` | `language`, `append_to_response=aggregate_credits,videos,watch/providers`, `include_video_language=pt,en,null` | 6 h |
| Sinopse em inglês (se faltar em pt-BR) | `GET /tv/{id}` | `language=en-US` | 6 h |

### Cliente (`tmdb/client.py`)

- Um único `httpx.AsyncClient`, criado no `lifespan` do app e fechado no desligamento.
- Assinatura: `async def get(path: str, params: dict, ttl: float) -> dict`.
- Timeout de 10 s.
- Consulta o cache antes de chamar; guarda só respostas 2xx.
- **429:** espera `Retry-After` (padrão 1 s, máximo 2 s) e tenta **uma** vez mais.
- Exceções (todas herdam de `TMDBError`):
  - `TMDBAuthError` → 401
  - `TMDBNotFound` → 404
  - `TMDBUnavailable` → 429 após a nova tentativa, 5xx, timeout, erro de rede

### Cache (`tmdb/cache.py`)

- `TTLCache(max_entries=1000, clock=time.monotonic)`: o relógio é injetável para os testes.
- Chave: `(path, tuple(sorted(params.items())))`.
- Expira por TTL; ao passar de `max_entries`, descarta a entrada usada há mais tempo (LRU via `OrderedDict`).
- Em memória, por processo. Reiniciar limpa o cache, o que é aceitável. Sem locks, porque tudo roda num único event loop; duas buscas simultâneas pelo mesmo item podem chamar a TMDB duas vezes, o que também é aceitável.

## 8. Páginas e comportamento

### 8.1 Layout geral (`base.html`)

- **Cabeçalho:** nome do app, campo de busca (formulário `GET /buscar`, enviado com Enter) e um **espaço reservado e vazio** para o menu do usuário (fase 2).
- **Rodapé:** logo da TMDB + "Este produto usa a API da TMDB, mas não é endossado nem certificado pela TMDB." + "Dados de disponibilidade: JustWatch". As duas atribuições são exigidas pela TMDB.
- Tema escuro, responsivo. Sem JavaScript próprio além do HTMX. O painel de filtros no celular usa `<details>`/CSS.

### 8.2 Catálogo (`GET /`)

**Layout:** filtros numa lateral à esquerda e grade de pôsteres à direita (opção A aprovada no mockup). No celular, a lateral vira um botão "Filtros (n)" que abre o painel.

**Parâmetros da URL**: os nomes são em português. Os parâmetros de múltipla escolha se repetem (`servicos=8&servicos=1899`), que é como um formulário HTML com checkboxes envia.

| Parâmetro | Valores | Vira na TMDB |
|---|---|---|
| `servicos` | ids de provedor | `with_watch_providers=8\|1899` (OU) |
| `tipos` | `flatrate`, `free`, `ads`, `rent`, `buy` | `with_watch_monetization_types=...` (OU) |
| `generos` | ids de gênero | `with_genres=18\|35` (OU) |
| `ano_de` | ano | `first_air_date.gte=AAAA-01-01` |
| `ano_ate` | ano | `first_air_date.lte=AAAA-12-31` |
| `nota` | `5`, `6`, `7`, `8` | `vote_average.gte=N` |
| `ordem` | `popularidade` (padrão), `nota`, `recentes`, `nome` | `popularity.desc`, `vote_average.desc`, `first_air_date.desc`, `name.asc` |
| `pagina` | 1–500 | `page` |

**Regras de tradução (`catalog.py`):**
1. Sempre envia `watch_region=BR`, `language=pt-BR` e `with_watch_monetization_types`. É isso que garante "disponível em streaming".
2. Nenhum tipo marcado (ou só valores inválidos) = todos os cinco tipos.
3. Quando há `nota` ou `ordem=nota`, adiciona `vote_count.gte=50`, para evitar séries obscuras com 1 voto e nota 10.
4. `ordem=recentes` adiciona `first_air_date.lte=<hoje>` para não listar estreias futuras.
5. **Valores inválidos são ignorados** e voltam ao padrão, sem erro: ids não numéricos, tipo desconhecido, ano fora de 1900..(ano atual + 1), nota fora da lista, ordem desconhecida, página fora de 1..500. Se `ano_de > ano_ate`, os dois são trocados.

**Filtros na tela:**
- **Serviços:** logos vindos de `/watch/providers/tv`, ordenados pela prioridade de exibição no BR. Os 12 primeiros ficam visíveis e o resto aparece em "ver todos".
- **Tipo:** cinco checkboxes (Assinatura, Grátis, Com anúncios, Aluguel, Compra), todas marcadas por padrão.
- **Gênero:** lista de `/genre/tv/list` em pt-BR, recolhível.
- **Ano de estreia:** "de" e "até".
- **Nota mínima:** select.
- **Ordenação:** select acima da grade, parte do mesmo formulário dos filtros (atributo `form`), então mudar a ordem também atualiza só a grade.

**HTMX:**
- O formulário de filtros tem `hx-get="/" hx-trigger="change" hx-target="#grade" hx-push-url="true"`.
- Pedido com `HX-Request` e `pagina=1` → `_grade.html` (contador + cartões + botão).
- O botão "Carregar mais" faz `hx-get` da próxima página com `hx-swap="outerHTML"`. Pedido com `HX-Request` e `pagina>1` → `_cartoes.html` (cartões + novo botão), que substitui o botão antigo. O botão some quando `pagina >= total_pages`, com `total_pages` limitado a 500.
- Pedido sem `HX-Request` → `catalogo.html` completo, com os filtros preenchidos a partir da URL.

**Cartão:** pôster (placeholder quando não há imagem), nome, ano e nota. Leva para `/serie/{id}`.

### 8.3 Busca (`GET /buscar?q=...&pagina=N`)

- `q` vazio → redireciona para `/`. `q` é cortado em 100 caracteres.
- Chama `/search/tv` e, para cada resultado, `/tv/{id}/watch/providers` **em paralelo**, com no máximo 10 chamadas simultâneas (`asyncio.Semaphore(10)` + `gather(return_exceptions=True)`).
- O cartão mostra até 4 logos de provedores do BR, sem repetição, na ordem flatrate, free, ads, rent, buy.
  - Nenhum provedor → cartão esmaecido com "Fora do streaming no BR".
  - Consulta falhou → cartão normal, sem logos e sem aviso.
- Mantém a ordem de relevância da TMDB. Mostra "N resultados para "q" · a busca ignora os filtros do catálogo".
- "Carregar mais" funciona igual ao catálogo.

### 8.4 Detalhes (`GET /serie/{id}`)

- Uma chamada a `/tv/{id}` com `append_to_response` (ver §7).
- Se `overview` vier vazio em pt-BR, busca o de `en-US`.
- **Cabeçalho:**
  - imagem de fundo (`backdrop`), pôster e título; o nome original aparece só se for diferente
  - anos: `2023–` se ainda está em exibição ou produção, `2013–2019` se terminou
  - status traduzido
  - temporadas e episódios, gêneros, nota e número de votos
- **Status traduzido:**

  | TMDB | Exibido |
  |---|---|
  | Returning Series | Em exibição |
  | Ended | Encerrada |
  | Canceled | Cancelada |
  | In Production | Em produção |
  | Planned | Planejada |
  | Pilot | Piloto |

  Qualquer outro valor é exibido como veio.
- **Sinopse** e **trailer:** primeiro vídeo `site=YouTube` e `type=Trailer`, preferindo o idioma `pt`, depois `en`, depois qualquer outro; se não houver trailer, aceita `type=Teaser`. É incorporado via `youtube-nocookie.com/embed/{key}` com `loading="lazy"`. Se não houver vídeo, a seção não aparece.
- **Onde assistir no Brasil:** `watch/providers.results.BR`, agrupado por tipo (Assinatura, Grátis, Com anúncios, Aluguel, Compra), com logos.
  - O botão "Ver opções de streaming ↗" abre o `link` da TMDB, que tem os links para cada serviço. **A TMDB não fornece link direto para cada serviço.**
  - Sem dados no BR: "Não disponível em streaming no Brasil no momento".
- **Temporadas:** cartões com nome, ano e número de episódios; a temporada 0 ("Especiais") vai para o fim.
- **Elenco principal:** os 10 primeiros de `aggregate_credits.cast` (todas as temporadas), com nome e personagem (primeiro papel em `roles`).
- **Espaço reservado** (não exibido nesta fase) para os botões "Assistida" e "Favorita" da fase 2.
- **"← Voltar":** `history.back()`, com link para `/` se não houver histórico.

## 9. Tratamento de erros

Handlers de exceção registrados em `main.py`:

| Situação | Página inteira | Pedido HTMX |
|---|---|---|
| `TMDBNotFound` em `/serie/{id}` | `erro.html` "Série não encontrada", status 404 | — |
| `TMDBAuthError` | `erro.html` "Problema de configuração com a TMDB (token inválido)", status 502; log ERROR | `_erro.html` na grade |
| `TMDBUnavailable` | `erro.html` "A TMDB não respondeu. Tente novamente em instantes." + botão, status 503; log WARNING | `_erro.html` na grade com "Tentar novamente" |
| Rota inexistente | `erro.html` "Página não encontrada", status 404 | — |

- **Fragmentos de erro HTMX respondem com status 200.** Por padrão, o HTMX 2 não troca o conteúdo da página em respostas 4xx/5xx; com 200, a mensagem aparece só na área da grade e o resto da página continua funcionando.
- Falha ao carregar as listas de serviços ou gêneros: a página do catálogo abre mesmo assim, com aquele filtro mostrando "indisponível no momento".
- Logs via `logging` padrão para stdout, que é o que os serviços de hospedagem esperam (fase 3). O token nunca aparece nos logs.

## 10. Testes

- **Ferramentas:** pytest, pytest-asyncio, respx (simula a TMDB) e o `TestClient` do FastAPI. **Nenhum teste acessa a internet:** o respx falha se houver uma chamada não simulada.
- **Desenvolvimento orientado a testes (TDD):** cada comportamento começa com um teste falhando.
- **Fixtures:** respostas reais da TMDB (discover, search, details com append, watch providers, providers list, genres) capturadas uma vez e enxugadas em `tests/fixtures/*.json`.

| Arquivo | O que cobre |
|---|---|
| `test_cache.py` | expiração por TTL com relógio falso; descarte LRU ao passar do limite; chaves independem da ordem dos parâmetros |
| `test_client.py` | cabeçalho Bearer; a segunda chamada idêntica vem do cache; erros não vão para o cache; 429 → nova tentativa → sucesso; 429 duas vezes → `TMDBUnavailable`; 401/404/5xx/timeout → exceção certa |
| `test_catalog.py` | `Filters` → parâmetros (cada filtro, OU com `\|`, tipos vazios = todos, regra do `vote_count.gte`, `recentes` com `lte`, `watch_region` sempre presente); JSON → modelos (sem pôster, sem data, sem votos); agrupamento do "onde assistir"; escolha do trailer; sinopse em inglês quando falta a de pt-BR; status traduzido; temporada 0 no fim; busca: provedores por cartão, cartão sem provedores, consulta que falhou |
| `test_routes.py` | parsing da URL com valores inválidos; `HX-Request` + `pagina=1` → `_grade`; `pagina>1` → `_cartoes`; sem HX → página inteira; `q` vazio → redirect; 404 de série; erro da TMDB em HTMX → fragmento com status 200; rodapé com as atribuições |
| `test_tmdb_contract.py` | `@pytest.mark.tmdb`, roda só com `pytest -m tmdb` e token real: confirma as suposições da §12. Fica fora da execução padrão via `addopts = "-m 'not tmdb'"` no `pyproject.toml` (o `-m` da linha de comando prevalece). |

- **Verificação manual final:** rodar com o token real e repetir os critérios de sucesso 2 a 6 da §4.

## 11. Limitações conhecidas

- **Filtros de serviço e de tipo são independentes na TMDB:** "Netflix + Aluguel" pode trazer uma série que está na Netflix por assinatura e para alugar em outro serviço. A página de detalhes mostra o quadro exato.
- **A busca ignora os filtros do catálogo** (o `/search/tv` não os aceita).
- **O `/discover/tv` vai até a página 500** (10 mil resultados). Segundo o fórum da TMDB, não está na documentação oficial. Com filtros, isso raramente importa.
- **A disponibilidade pode estar algumas horas desatualizada** (JustWatch → TMDB → nosso cache de até 6 h).
- **Não há link direto para cada serviço**, só para a página da TMDB.

## 12. A confirmar no início da implementação

O teste de contrato e a primeira tarefa do plano devem confirmar, com o token real:

1. `append_to_response=watch/providers` funciona em `/tv/{id}`. **Se não funcionar:** chamada separada a `/tv/{id}/watch/providers`, em paralelo com os detalhes.
2. `/watch/providers/tv` traz `display_priorities` por país. **Se não trouxer:** usar `display_priority`.
3. O comportamento de `page > 500` no discover. **Se der erro:** o limite de 500 da §6 já evita o problema.

## 13. Preparação para as fases 2 e 3

- Toda a configuração vem de variáveis de ambiente, prontas para o servidor de hospedagem.
- O espaço do menu do usuário no cabeçalho e o dos botões "Assistida/Favorita" no detalhe já estão previstos no layout.
- `SeriesCard` e `catalog.py` são reaproveitáveis para mostrar as listas da fase 2 a partir de `tmdb_id`s.
- O app é um processo único, sem estado além do cache em memória: deploy simples em um único serviço.

## 14. Como rodar (desenvolvimento)

```
uv sync
copy .env.example .env      # e preencher TMDB_TOKEN
uv run uvicorn app.main:app --reload
uv run pytest               # testes (sem internet)
uv run pytest -m tmdb       # teste de contrato (com token real)
```
