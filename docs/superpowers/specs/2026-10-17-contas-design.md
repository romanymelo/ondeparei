# Contas com Supabase — Design (Fase 2b)

- **Data:** 2026-10-17
- **Status:** aguardando revisão
- **Depende de:** Fase 1 (catálogo) e Fase 2a (marcações), já no `main`
- **Branch:** `feat/fase-2b-contas`

## 1. Objetivo

Cada pessoa tem a própria conta, com e-mail e senha, e as próprias marcações, favoritas e tempo de séries. Quem não tem conta navega livremente; o login só é pedido na hora de salvar alguma coisa.

### Roadmap

| Fase | Conteúdo |
|---|---|
| 1 | Catálogo (feito) |
| 2a | Marcações, episódios, Minhas séries, selos, tempo de séries (feito) |
| **2b (esta spec)** | Contas no Supabase, marcações por conta, proteção CSRF |
| 3 | Deploy online |

## 2. Escopo

**Inclui:**
- Cadastro aberto com nome, sobrenome, e-mail e senha. **Sem confirmação de e-mail** por enquanto (decisão do usuário).
- Entrar, sair, "Esqueci minha senha" e "Nova senha".
- Navegação livre sem login; login exigido para salvar e para Minhas séries.
- Marcações, favoritas, episódios e tempo de séries guardados no banco do Supabase, separados por conta com RLS.
- Proteção CSRF nos POSTs.
- Importação única das marcações atuais (`data/catalogo.db`) para a conta do usuário.

**Não inclui:**
- Configurações além das marcações, como serviços assinados ou filtros lembrados (decisão do usuário: "nada além disso, por enquanto").
- Login social (Google etc.), troca de e-mail, edição de nome, exclusão de conta pela interface.
- Confirmação de e-mail (fica para quando houver servidor de e-mail próprio).

## 3. Decisões

- **Abordagem A:** login e dados no Supabase. O app fala com o Supabase só por HTTP (`httpx`), como já fala com a TMDB. **Nenhuma dependência nova.**
- **Segurança das marcações no banco:** RLS com `user_id = auth.uid()` em todas as tabelas. O app faz as chamadas de dados com o token da própria pessoa; a chave secreta nunca é usada pelo app, só pelo comando de importação e pelos testes de contrato.
- **Visitante:** vê os botões de marcar. Ao clicar, vai para `/entrar?proximo=<página atual>` e, depois de entrar, volta para essa página **sem executar a ação** (a pessoa clica de novo).
- **Sessão:** continua até a pessoa sair.

## 4. Critérios de sucesso

1. Sem login, catálogo, busca, página da série e página da temporada funcionam; o cabeçalho mostra "Entrar" e "Criar conta" e não mostra o contador.
2. Sem login, clicar em qualquer ação de marcar, ou abrir Minhas séries, leva para Entrar; depois de entrar, a pessoa volta à página de onde veio.
3. Criar conta com nome, sobrenome, e-mail e senha já deixa a pessoa logada, com o primeiro nome no cabeçalho.
4. Duas contas diferentes nunca veem as marcações uma da outra (provado no teste de contrato contra o Supabase real).
5. Fechar e abrir o navegador mantém a pessoa logada; "Sair" encerra a sessão.
6. "Esqueci minha senha" envia o e-mail; o link leva a "Nova senha", e a senha nova funciona no login.
7. Um POST vindo de outro site é recusado (CSRF).
8. Supabase fora do ar: o catálogo continua navegável; ações mostram a mensagem de erro e não gravam nada pela metade.
9. Depois da importação, a conta do usuário tem as mesmas marcações, episódios, durações e o mesmo tempo de séries de antes.
10. `uv run pytest` passa sem internet.

## 5. Arquitetura

```
app/
  auth/
    __init__.py
    client.py       # SupabaseAuth: cadastro, login, renovação, saída, recuperação e troca de senha (httpx)
    session.py      # cookies, usuário atual (com cache curto), renovação automática, middleware
    csrf.py         # middleware: recusa POST de outra origem
    routes.py       # /entrar, /criar-conta, /sair, /esqueci-senha, /nova-senha
    forms.py        # validação dos formulários (puro)
  tracking/
    supabase_repository.py  # SupabaseTrackingRepository: mesmos métodos do repositório, via PostgREST + funções
    repository.py           # (SQLite) passa a servir só à importação
    service.py              # métodos do repositório viram assíncronos (await)
  importar.py       # comando único: data/catalogo.db -> conta do usuário
  config.py         # + SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY (opcional)
supabase/
  migracoes/001_marcacoes.sql   # tabelas, RLS e funções; rodado uma vez no editor SQL do Supabase
```

**Dependências entre as partes:** as rotas usam o usuário atual (`request.state.user`). O `TrackingService` é montado **por pedido**, com um `SupabaseTrackingRepository` que leva o token da pessoa. As regras (`rules.py`) não mudam.

## 6. Login (`app/auth/`)

### 6.1 Cliente (`client.py`)

Chamadas ao serviço de login do Supabase (`{SUPABASE_URL}/auth/v1`), sempre com o cabeçalho `apikey: <chave pública>`:

| Ação | Chamada |
|---|---|
| Criar conta | `POST /signup` com `email`, `password` e `data: {first_name, last_name}` (vão para `user_metadata`) |
| Entrar | `POST /token?grant_type=password` |
| Renovar | `POST /token?grant_type=refresh_token` |
| Quem é | `GET /user` com `Authorization: Bearer <access_token>` |
| Sair | `POST /logout` com o token |
| Pedir recuperação | `POST /recover` com o e-mail |
| Validar link de recuperação | `POST /verify` com `type: recovery` e `token_hash` (devolve uma sessão) |
| Gravar senha nova | `PUT /user` com `password`, usando o token da sessão de recuperação |

- **Resultado:** `Session(access_token, refresh_token, expires_at, user)` e `User(id, email, first_name, last_name)`.
- **Erros do Supabase viram exceções do domínio:**
  - `InvalidCredentials` — credenciais inválidas;
  - `EmailTaken` — `user_already_exists`;
  - `WeakPassword`;
  - `RateLimited` — 429;
  - `AuthUnavailable` — rede ou 5xx;
  - `InvalidRecoveryLink`.
- **Timeout:** 10 s, como na TMDB.

### 6.2 Sessão (`session.py`)

- **Cookies:** `op_acesso` (access token) e `op_renovacao` (refresh token).
  - Atributos: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` quando o pedido vem por HTTPS.
  - `op_renovacao` dura 180 dias e é renovado a cada uso.
- **Usuário atual:** um middleware lê os cookies e preenche `request.state.user` (ou `None`).
  - A validação (`GET /user`) fica num cache em memória por até 5 minutos, chaveado pelo hash do token e nunca além do vencimento do token.
  - Token vencido: renova com o refresh token e regrava os cookies na resposta.
  - Renovação recusada: apaga os cookies e trata como visitante.
  - Supabase fora do ar: trata como visitante naquele pedido, sem apagar os cookies.
- **Contador do cabeçalho:** para páginas inteiras (não HTMX) de pessoa logada, o middleware busca o tempo de séries e o põe em `request.state.watch_time`. Se a busca falhar, o contador não aparece. O `base.html` passa a ler daí; a função global `tempo_de_series` sai.

### 6.3 Páginas (`routes.py`)

| Rota | O que faz |
|---|---|
| `GET/POST /entrar` | e-mail e senha; sucesso → cookies e 303 para `proximo` (ou `/`) |
| `GET/POST /criar-conta` | nome, sobrenome, e-mail, senha, confirmação; sucesso → logado e 303 para `proximo` (ou `/`) |
| `POST /sair` | chama `/logout`, apaga os cookies, 303 para `/` |
| `GET/POST /esqueci-senha` | pede o e-mail; sempre responde com a mesma mensagem |
| `GET /nova-senha?token_hash=…&type=recovery` | valida o link; se valer, guarda a sessão de recuperação em cookie e mostra o formulário |
| `POST /nova-senha` | grava a senha nova; a pessoa sai logada; 303 para `/` |

- **`proximo`:** só é aceito se for caminho relativo do próprio site (começa com `/` e não com `//`); fora disso, vale `/`.
- **Logado abrindo `/entrar` ou `/criar-conta`:** vai direto para `/`.
- **Validação (`forms.py`, puro):**
  - nome e sobrenome obrigatórios (até 60 caracteres cada);
  - e-mail com formato válido;
  - senha com no mínimo 8 caracteres e confirmação igual.

  O formulário volta com o que foi digitado, menos as senhas.

### 6.4 Cabeçalho

- **Visitante:** links "Entrar" e "Criar conta" (o "Entrar" leva `proximo` = página atual).
- **Logado:**
  - o contador (como hoje);
  - o primeiro nome;
  - um menu em `popover`, igual aos do catálogo, com "Minhas séries" e o botão "Sair" (`<form method="post" action="/sair">`).

### 6.5 Login exigido

- **Exceção:** `LoginRequired`.
- **Quando é lançada:** pela dependência `get_tracking` quando não há usuário, e pela rota de Minhas séries.
- **Resposta:**
  - pedido HTMX: status 200 vazio com `HX-Redirect: /entrar?proximo=<HX-Current-URL relativo>`;
  - página inteira: 303 para `/entrar?proximo=<caminho atual>`.
- **POST sem HTMX:** o `proximo` é o `Referer` relativo; se não houver, `/`.

### 6.6 CSRF (`csrf.py`)

- **Métodos protegidos:** POST, PUT, PATCH e DELETE.
- **Regra:** o pedido precisa de `Origin` igual à origem do próprio site. Sem `Origin`, vale o `Referer`. Sem nenhum dos dois, ou com origem diferente, a resposta é 403 "Pedido recusado".
- **Por que basta:** junto com `SameSite=Lax`, isso fecha o CSRF sem precisar de tokens nos formulários.
- **Testes:** o `TestClient` do conftest passa a mandar `Origin: http://testserver`.

## 7. Banco no Supabase (`supabase/migracoes/001_marcacoes.sql`)

```sql
create table public.series_tracking (
    user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
    tmdb_id     integer not null,
    status      text check (status in ('want', 'watching', 'watched')),
    favorite    boolean not null default false,
    name        text not null,
    poster_path text,
    updated_at  timestamptz not null default now(),
    primary key (user_id, tmdb_id)
);

create table public.watched_episodes (
    user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
    tmdb_id    integer not null,
    season     integer not null,
    episode    integer not null,
    watched_at timestamptz not null default now(),
    runtime    integer,
    primary key (user_id, tmdb_id, season, episode)
);
```

- **RLS:** ligado nas duas tabelas, com uma política `for all to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()))`. O papel `anon` não tem acesso.
- **Funções** (todas `security invoker`, então a RLS vale dentro delas; `execute` só para `authenticated`):

| Função | O que faz |
|---|---|
| `save_tracking(p_tmdb_id, p_name, p_poster_path, p_status, p_favorite, p_add jsonb, p_remove jsonb)` | numa transação: insere `p_add` (`[{season, episode, runtime}]`, ignorando repetidos), apaga `p_remove`, grava a linha da série com o snapshot e `updated_at = now()`, apaga a linha se ficou sem status, favorito e episódios |
| `tracking_counts()` | `{watching, want, watched, favorite}` |
| `watch_time()` | `(episodios, minutos)` |
| `missing_runtimes()` | linhas `(tmdb_id, season)` com duração desconhecida |
| `set_runtimes(p_tmdb_id, p_runtimes jsonb)` | preenche só as durações nulas |

- **Leituras simples via PostgREST** (`/rest/v1/...`): `marks_for` (`series_tracking?tmdb_id=in.(…)`), `watched` (`watched_episodes?tmdb_id=eq.…`) e `list_tab` (filtro por status ou favorito, `order=updated_at.desc`).

## 8. Marcações por conta

- **`SupabaseTrackingRepository(http, url, publishable_key, access_token)`:** tem os mesmos métodos do repositório SQLite (`marks`, `marks_for`, `watched`, `save`, `counts`, `list_tab`, `watch_time`, `missing_runtimes`, `set_runtimes`), agora **assíncronos**. Cada chamada leva `apikey` e `Authorization: Bearer <token da pessoa>`.
- **Erros:** falha de rede, 5xx ou 401 viram `TrackingUnavailable`.
- **`TrackingService`:**
  - as chamadas ao repositório passam a ter `await`; regras e fluxos não mudam;
  - `fill_runtimes` em segundo plano continua, com o repositório da própria pessoa.
- **Rotas:** `get_tracking(request)` monta o serviço por pedido. Sem usuário, lança `LoginRequired`.
- **Catálogo e busca:** só buscam `marks_for` quando há usuário; para visitante, não há selos.
- **Página da série e da temporada:** para visitante, mostram o bloco de status e os ✓ sem marcação; os botões continuam lá e levam ao login.
- **Erro `TrackingUnavailable`:** com HTMX, fragmento 200 "Não foi possível falar com o servidor de contas. Tente novamente em instantes."; página inteira, 503 com a mesma mensagem. Substitui o handler de `sqlite3.Error` no app.

## 9. Importação (`app/importar.py`)

- **Uso:** `uv run python -m app.importar seu@email.com`. Precisa de `SUPABASE_SECRET_KEY` no `.env`.
- **Passos:**
  1. Acha o usuário pela API de administração (`GET /auth/v1/admin/users`, paginado) usando a chave secreta. Se não achar, sai com a mensagem "Conta não encontrada: crie a conta no app primeiro."
  2. Lê `series_tracking` e `watched_episodes` do `data/catalogo.db` (repositório SQLite).
  3. Grava no Supabase com `upsert` (`Prefer: resolution=merge-duplicates`), com o `user_id` da conta. Rodar de novo não duplica nada.
  4. Imprime o resumo: séries, episódios e tempo de séries antes e depois.
- **Arquivo antigo:** o `data/catalogo.db` não é apagado.

## 10. Configuração

`.env` (o `.env.example` ganha as linhas, vazias):

```
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=          # só para a importação e os testes de contrato
```

- **Sem `SUPABASE_URL` ou `SUPABASE_PUBLISHABLE_KEY`:** o app sobe com a mensagem "SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY não definidos. Veja o README."
- **`DATABASE_PATH`:** passa a ser usado só pela importação.

**Passos no painel do Supabase** (vão para o README):
1. Rodar `supabase/migracoes/001_marcacoes.sql` no SQL Editor.
2. Em Authentication → Sign In / Providers: e-mail ligado, "Confirm email" desligado.
3. Em Authentication → URL Configuration: Site URL `http://localhost:8000`.
4. Em Authentication → Emails → Reset password: trocar o link do modelo para `{{ .SiteURL }}/nova-senha?token_hash={{ .TokenHash }}&type=recovery`.
5. Copiar a URL do projeto, a chave pública e a chave secreta para o `.env`.

## 11. Erros

| Situação | Resposta |
|---|---|
| E-mail ou senha errados | "E-mail ou senha incorretos." |
| E-mail já cadastrado | "Já existe uma conta com este e-mail." + link "Entrar" |
| Senha fraca para o Supabase | "Use uma senha mais forte (mínimo de 8 caracteres)." |
| Campo inválido | mensagem embaixo do campo |
| Limite de tentativas (429) | "Muitas tentativas. Aguarde um minuto e tente de novo." |
| Esqueci a senha | sempre "Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova." |
| Link de recuperação inválido ou vencido | "Este link expirou." + botão "Pedir outro link" |
| Supabase fora do ar (login) | "Não foi possível falar com o servidor de contas. Tente novamente em instantes." |
| Supabase fora do ar (marcar, Minhas séries) | mesma mensagem; nada gravado pela metade |
| Sessão revogada ou inválida | cookies apagados; vira visitante, sem erro |
| POST de outra origem | 403 "Pedido recusado" |

## 12. Testes

Mesmo esquema das fases anteriores: TDD, sem internet, Supabase simulado com `respx` (como a TMDB).

| Arquivo | O que cobre |
|---|---|
| `test_auth_forms.py` | validação: campos vazios, nome longo, e-mail inválido, senha curta, confirmação diferente |
| `test_auth_client.py` | cada chamada (corpo, cabeçalhos) e a tradução de cada erro do Supabase |
| `test_auth_session.py` | cookies (atributos), cache da validação, renovação com regravação dos cookies, renovação recusada vira visitante, Supabase fora vira visitante sem apagar cookies |
| `test_auth_routes.py` | entrar, criar conta, sair, esqueci a senha, nova senha; `proximo` seguro (`//evil`, `https://…` → `/`); logado em `/entrar` vai para `/`; mensagens de erro |
| `test_csrf.py` | POST sem origem, com outra origem, com a própria (por `Origin` e por `Referer`) |
| `test_supabase_repository.py` | cada método: URL, filtros, cabeçalhos com o token da pessoa, corpo da `save_tracking`; erros viram `TrackingUnavailable` |
| `test_routes_tracking.py` (ajustado) | visitante: ações levam ao login (HTMX com `HX-Redirect`, página com 303); logado: tudo como hoje |
| `test_importar.py` | lê um SQLite de exemplo e manda os `upsert` certos; conta inexistente; rodar duas vezes |
| `test_supabase_contract.py` (`-m supabase`) | contra o projeto real, com dois usuários temporários criados e apagados pela chave secreta: RLS (um não vê nem altera o outro), `save_tracking` atômica, contagens, `watch_time`, `missing_runtimes`/`set_runtimes`; `anon` sem acesso |

**Verificação manual no navegador, com o usuário:** os critérios 1 a 9 e a largura de celular.

## 13. Limitações conhecidas

- Sem confirmação de e-mail: alguém pode criar conta com o e-mail de outra pessoa (que pode recuperar a conta pelo "Esqueci minha senha").
- O servidor de e-mail gratuito do Supabase envia poucos e-mails por hora: suficiente para poucas pessoas.
- Cada página de pessoa logada faz algumas chamadas ao Supabase; recomenda-se o projeto na região de São Paulo (`sa-east-1`).
- O cache de 5 minutos da validação faz com que uma sessão revogada em outro aparelho ainda funcione por até 5 minutos neste.
