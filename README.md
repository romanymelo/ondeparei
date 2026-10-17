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

Abra o `.env` e preencha `TMDB_TOKEN` e as variáveis do Supabase (veja **Contas (Supabase)** abaixo). O arquivo está no `.gitignore`, então as chaves nunca vão para o git.

| Variável | Padrão | Uso |
|---|---|---|
| `TMDB_TOKEN` | — | obrigatório |
| `TMDB_REGION` | `BR` | país da disponibilidade |
| `TMDB_LANGUAGE` | `pt-BR` | idioma dos textos |
| `LOG_LEVEL` | `INFO` | nível de log |
| `SUPABASE_URL` | — | obrigatório: URL do projeto no Supabase |
| `SUPABASE_PUBLISHABLE_KEY` | — | obrigatório: chave pública (publishable ou anon) |
| `SUPABASE_SECRET_KEY` | — | só para a importação e os testes de contrato; **nunca compartilhe** |
| `DATABASE_PATH` | `data/catalogo.db` | banco local antigo, lido só pela importação |

## Rodar

```
uv run uvicorn app.main:app --reload
```

Depois, abra http://localhost:8000.

> No Windows, o `--reload` às vezes detecta a mudança ("Reloading...") mas não sobe o processo novo, e o app continua com o código antigo. Se isso acontecer, pare com Ctrl+C e rode o comando de novo.

## Contas (Supabase)

Qualquer pessoa navega pelo catálogo sem conta. Para marcar séries, favoritar, marcar episódios ou abrir **Minhas séries**, o app pede para **Entrar** ou **Criar conta** (nome, sobrenome, e-mail e senha) e depois volta para a mesma página. Cada conta só vê as próprias marcações.

### Preparar o projeto no Supabase (uma vez)

1. Crie um projeto em https://supabase.com (de preferência na região **São Paulo**, `sa-east-1`).
2. **SQL Editor** → cole o conteúdo de `supabase/migracoes/001_marcacoes.sql` → **Run**.
3. **Authentication → Sign In / Providers → Email**: deixe ligado e **desligue "Confirm email"**.
4. **Authentication → URL Configuration**: em **Site URL**, coloque `http://localhost:8000` (no deploy, o endereço do site).
5. **Authentication → Emails → Reset Password**: no modelo, troque o link por
   `{{ .SiteURL }}/nova-senha?token_hash={{ .TokenHash }}&type=recovery`
6. **Project Settings → API Keys**: copie para o `.env` a URL do projeto (`SUPABASE_URL`), a chave pública (`SUPABASE_PUBLISHABLE_KEY`) e a chave secreta (`SUPABASE_SECRET_KEY`). Cole direto no arquivo: nunca em chat, e-mail ou print.

### Trazer as marcações antigas

As marcações da fase sem login ficaram em `data/catalogo.db`. Depois de criar a sua conta no app:

```
uv run python -m app.importar seu@email.com
```

O comando mostra quantas séries e episódios foram importados e o tempo de séries antes e depois. Pode rodar de novo sem duplicar nada, e o `data/catalogo.db` não é apagado.

## Marcações

Na página de cada série dá para marcar **Quero assistir**, **Assistindo** ou **Assistido** e favoritar. Clicando numa temporada, você marca episódio por episódio (ou "até aqui", ou a temporada inteira); a página **Minhas séries** mostra tudo e o próximo episódio de cada série.

- No topo de **Minhas séries** e no cabeçalho, o tempo de séries (como no TV Time): meses, dias e horas assistidos e o total de episódios.
- As marcações ficam no banco do Supabase, na conta de cada pessoa.

## Testes

```
uv run pytest               # suíte completa, sem internet
uv run pytest -m tmdb       # teste de contrato contra a API real (usa o token)
uv run pytest -m supabase   # contrato com o Supabase real: tabelas, RLS e funções (usa a chave secreta)
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
  auth/            # contas: cliente do Supabase Auth, sessão em cookies, CSRF e páginas
  tracking/        # marcações: regras, serviço, rotas e o repositório no Supabase
  importar.py      # importação única do data/catalogo.db para uma conta
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
supabase/migracoes/ # SQL das tabelas, RLS e funções (rodar no SQL Editor)
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
