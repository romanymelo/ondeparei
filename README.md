# OndeParei — catálogo de séries no streaming

App web pessoal que mostra as séries disponíveis **agora** nos serviços de streaming do Brasil, com filtros, busca por nome e página de detalhes. Os dados vêm da [API da TMDB](https://developer.themoviedb.org/docs/getting-started); a disponibilidade vem do JustWatch.

Esta é a **fase 1 (catálogo)**. As fases 2 (contas e listas) e 3 (deploy) terão specs próprias. O design está em [`docs/superpowers/specs/`](docs/superpowers/specs/).

## Pré-requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/). No Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Conta na TMDB e o **API Read Access Token**: themoviedb.org → Configurações → API (é o token longo que começa com `eyJ`)

## Configuração

```
uv sync
copy .env.example .env
```

Abra o `.env` e preencha `TMDB_TOKEN`. O arquivo está no `.gitignore`, então o token nunca vai para o git.

| Variável | Padrão | Uso |
|---|---|---|
| `TMDB_TOKEN` | — | obrigatório |
| `TMDB_REGION` | `BR` | país da disponibilidade |
| `TMDB_LANGUAGE` | `pt-BR` | idioma dos textos |
| `LOG_LEVEL` | `INFO` | nível de log |

## Rodar

```
uv run uvicorn app.main:app --reload
```

Depois, abra http://localhost:8000.

> No Windows, o `--reload` às vezes detecta a mudança ("Reloading...") mas não sobe o processo novo, e o app continua com o código antigo. Se isso acontecer, pare com Ctrl+C e rode o comando de novo.

## Marcações

Na página de cada série dá para marcar **Quero assistir**, **Assistindo** ou **Assistido** e favoritar. Clicando numa temporada, você marca episódio por episódio (ou "até aqui", ou a temporada inteira); a página **Minhas séries** mostra tudo e o próximo episódio de cada série.

- No topo de **Minhas séries**, o contador de tempo de séries (como no TV Time): meses, dias e horas assistidos e o total de episódios.
- As marcações ficam num banco SQLite em `data/catalogo.db` (outro caminho: variável `DATABASE_PATH` no `.env`).
- **Backup:** com o app parado, copie o arquivo `data/catalogo.db`.
- **Recomeçar do zero:** com o app parado, apague esse arquivo.
- Ainda sem login: quem abrir o app no seu computador vê e altera as marcações.

## Testes

```
uv run pytest               # suíte completa, sem internet
uv run pytest -m tmdb       # teste de contrato contra a API real (usa o token)
```

Para atualizar as fixtures com respostas reais da TMDB:

```
uv run python -m tests.fixtures.capturar
```

## Estrutura

```
app/
  main.py          # cria o app, lifespan, páginas de erro
  routes.py        # rotas: /, /buscar, /serie/{id}
  tracking/        # marcações: regras, banco SQLite, serviço e rotas
  catalog.py       # serviço: orquestra as chamadas à TMDB
  filters.py       # URL → Filters → parâmetros do /discover/tv
  mappers.py       # JSON da TMDB → modelos
  models.py        # dataclasses do domínio
  config.py        # variáveis de ambiente
  templating.py    # Jinja2, filtros e constantes da interface
  tmdb/client.py   # HTTP com a TMDB: cache, nova tentativa no 429, erros
  tmdb/cache.py    # cache em memória com TTL e LRU
  templates/       # HTML (Jinja2 + HTMX)
  static/          # CSS, HTMX, logo da TMDB
tests/             # pytest + respx (TMDB simulada) + fixtures reais
```

## Limitações conhecidas

- O catálogo inclui séries disponíveis para alugar ou comprar, e o filtro de serviço não distingue o tipo. A página de detalhes mostra o quadro exato.
- A busca por nome ignora os filtros do catálogo.
- O catálogo vai até a página 500 (10 mil séries por combinação de filtros).
- A disponibilidade pode estar algumas horas desatualizada (cache de até 6 h).
- A TMDB não fornece link direto para cada serviço.
- O que conta como episódio "já exibido" vem da TMDB e pode atrasar algumas horas.
- Uma série "Assistida" não volta sozinha para "Assistindo" quando sai temporada nova.

---

Este produto usa a API da TMDB, mas não é endossado nem certificado pela TMDB. Dados de disponibilidade: JustWatch.
