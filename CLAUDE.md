# OndeParei — instruções para o Claude

Catálogo das séries disponíveis no streaming do Brasil (API da TMDB), com contas (Supabase), marcações, episódios e tempo de séries. App pessoal, para o dono e poucos amigos. No ar em https://ondeparei-xi.vercel.app.

## Comandos

No Bash, antes de tudo: `export PATH="/c/Users/Romany Melo/.local/bin:$PATH"` (o `uv` fica ali).

```
uv sync                                        # dependências
uv run uvicorn app.main:app --port 8000        # rodar (http://localhost:8000)
uv run pytest -q                               # testes do dia a dia (sem internet)
uv run pytest -m tmdb                          # contrato com a API real da TMDB
uv run pytest -m supabase                      # contrato com o Supabase real (cria e apaga 2 usuários)
uv run python -m app.importar email@x.com      # importação única do data/catalogo.db antigo
```

- **Windows: não use `--reload`.** Ele trava e o servidor fica com o código antigo. Para ver uma mudança no Python, pare e suba de novo. Templates e CSS são relidos do disco sem reiniciar.
- Se a porta 8000 estiver ocupada, pode ser um servidor de outra sessão: confira antes de derrubar.

## Mapa

| Onde | O quê |
|---|---|
| `app/main.py` | cria o app, middlewares (CSRF por fora, sessão por dentro) e páginas de erro |
| `app/routes.py` | catálogo `/`, busca `/buscar`, série `/serie/{id}` |
| `app/catalog.py`, `filters.py`, `mappers.py`, `tmdb/` | TMDB: serviço, filtros → parâmetros, JSON → modelos, cliente com cache |
| `app/auth/` | contas: cliente do Supabase Auth, sessão em cookies, CSRF, formulários e páginas |
| `app/tracking/` | marcações: regras puras, serviço, rotas, `TrackingStore` e o repositório no Supabase |
| `app/templates/`, `app/static/` | HTML (Jinja2 + HTMX) e CSS |
| `supabase/migracoes/` | SQL das tabelas, RLS e funções (rodado no SQL Editor do painel) |
| `tests/` | pytest + respx; `fakes.py` tem `FakeCatalog`, `FakeAuth`, `SqliteStore` |
| `docs/superpowers/specs/` e `plans/` | specs e planos de cada fase: leia a spec antes de mudar um comportamento |

## Regras que não podem ser quebradas

- **Segredos só no `.env`** (fora do git). Nunca leia, imprima, logue ou cole valores de chaves, nem em mensagens de commit. Para conferir se uma variável existe, conte os nomes (`grep -c "^NOME=" .env`), sem mostrar valores.
- **`SUPABASE_SECRET_KEY` nunca vai para a Vercel** nem para o app em execução: só a importação e os testes de contrato a usam.
- **Atribuição da TMDB e do JustWatch fica no rodapé** (logo e aviso de "não endossado"). É exigida pelos termos da TMDB.
- **Nenhuma dependência nova** sem pedir ao dono. Supabase e TMDB são acessados só com `httpx`.
- **Mudança no banco:** novo arquivo em `supabase/migracoes/` (`002_...sql`). Nunca edite o `001`, que já está aplicado. O dono roda o SQL no painel.
- **Marcações são por conta** e a RLS do Supabase garante isso: nunca use a chave secreta no caminho de uma requisição de usuário.
- **Outras sessões do Claude podem estar mexendo no repositório.** Mudanças inesperadas não commitadas são do dono: não reverta nem inclua nos seus commits. Monte o commit só com os seus trechos.

## Convenções

- Identificadores em inglês; textos da tela, nomes de templates e parâmetros de URL em português.
- TDD: escreva o teste, veja falhar, implemente, veja passar, rode a suíte inteira.
- Sem JavaScript próprio além do HTMX (exceção: o `onclick` do "← Voltar").
- Fragmentos HTMX respondem 200 (inclusive os de erro), menos "Ação inválida" (400). Sem HTMX, ações POST respondem 303.
- Visual "a sala escura, a tela acesa": tokens de cor em `:root` (`--meia-noite`, `--veludo`, `--fio`, `--tela`, `--nevoa`, `--projetor` âmbar), fonte Archivo local. A barra âmbar "onde parei" (`--pausa`) só mostra progresso real. Ícones são SVG da macro `icone()`, nunca emoji na interface.
- Mensagens de commit terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Deploy

- A Vercel publica sozinha a cada push no `main` (região São Paulo, `gru1`, em `vercel.json`).
- Variáveis na Vercel: `TMDB_TOKEN`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`.
- No Supabase (Authentication → URL Configuration): Site URL do site e Redirect URLs com `/nova-senha` (localhost e Vercel).
- Recuperação de senha usa PKCE (cookie `op_pkce`). Sem SMTP próprio, o Supabase só envia e-mail para membros da organização.
