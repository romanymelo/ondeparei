# Contas com Supabase (Fase 2b) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Contas com e-mail e senha no Supabase, com navegação livre para visitante, login exigido só para salvar, marcações por conta no banco do Supabase (RLS), CSRF e importação das marcações locais.

**Architecture:**
- **Pacote novo `app/auth/`:**
  - cliente HTTP do serviço de login do Supabase;
  - validação dos formulários;
  - sessão em cookies, com um middleware que preenche `request.state.user`;
  - middleware de CSRF;
  - páginas de conta.
- **Interface assíncrona `TrackingStore`:** as marcações passam a ser acessadas por ela. Há duas implementações:
  - `SupabaseTrackingRepository` (PostgREST mais funções SQL), em produção;
  - `VisitorStore`, para quem não está logado: lê vazio e, ao gravar, exige login.

  Os testes usam um `SqliteStore` assíncrono, só de teste, por cima do repositório SQLite que já existe.
- **`TrackingService`:** passa a ser montado a cada pedido, com o store da pessoa. As regras não mudam.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX 2.0.4, httpx, Supabase (Auth e PostgREST), pytest, respx.

**Spec:** `docs/superpowers/specs/2026-10-17-contas-design.md` (leia junto). A identidade visual é a da fase 1, e as regras de marcação são as da spec `2026-10-16-marcacoes-design.md`.

## Global Constraints

- **Ambiente:** projeto em `C:\Projetos\catalogo-series`, branch `feat/fase-2b-contas`. No Bash, comece com `export PATH="/c/Users/Romany Melo/.local/bin:$PATH"`. Todo comando roda via `uv run ...`.
- **Nenhuma dependência nova.** Supabase só via `httpx` (`{SUPABASE_URL}/auth/v1/...` e `{SUPABASE_URL}/rest/v1/...`). Formulários lidos com `read_form` (`parse_qs`), como hoje.
- **Segredos:** chaves só no `.env`. Nunca imprimir, logar ou pôr em HTML, fixtures ou mensagens de commit.
  - `SUPABASE_PUBLISHABLE_KEY` vai no cabeçalho `apikey` de toda chamada.
  - `SUPABASE_SECRET_KEY` é usada **só** por `app/importar.py` e pelos testes `-m supabase`.
- **Cookies:**
  - `op_acesso` (access token) e `op_renovacao` (refresh token, `max_age` de 180 dias);
  - atributos `HttpOnly`, `SameSite=Lax`, `Path=/`, e `Secure` quando o pedido é HTTPS.
- **Validação do usuário:** fica em cache por até 300 s, sem passar do vencimento do token. A chave do cache é o `sha256` do token.
- **`proximo`:** aceito só se começar com `/` e não começar com `//` ou `/\`; fora disso, vira `/`.
- **CSRF:** POST, PUT, PATCH e DELETE exigem `Origin` (ou, na falta dele, `Referer`) com a mesma origem do site. Se não, a resposta é 403 "Pedido recusado".
- **Textos fixos** (copiar exatamente):
  - **Botões e links:** `Entrar` · `Criar conta` · `Sair` · `Esqueci minha senha` · `Pedir outro link` · `Minhas séries`
  - **Títulos das páginas:** `Entrar` · `Criar conta` · `Esqueci minha senha` · `Nova senha`
  - **Campos:** `Nome` · `Sobrenome` · `E-mail` · `Senha` · `Confirme a senha` · `Nova senha`
  - **Validação:** `Informe seu nome.` · `Informe seu sobrenome.` · `Use até 60 caracteres.` · `Informe um e-mail válido.` · `Informe sua senha.` · `A senha precisa ter pelo menos 8 caracteres.` · `As senhas não são iguais.`
  - **Erros do Supabase:** `E-mail ou senha incorretos.` · `Já existe uma conta com este e-mail.` · `Use uma senha mais forte (mínimo de 8 caracteres).` · `Muitas tentativas. Aguarde um minuto e tente de novo.` · `Não foi possível falar com o servidor de contas. Tente novamente em instantes.` · `Este link expirou.`
  - **Recuperação de senha:** `Se houver uma conta com esse e-mail, enviamos um link para criar uma senha nova.`
  - **CSRF:** `Pedido recusado`
  - **Configuração:** `SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY não definidos. Veja o README.`
  - **Importação:** `Conta não encontrada: crie a conta no app primeiro.`
- **Erros de marcação:** `TrackingUnavailable` responde com fragmento 200 (HTMX) ou página 503, com a mensagem de servidor de contas indisponível. Substitui o handler de `sqlite3.Error` no app.
- **Testes do dia a dia** (`uv run pytest`) nunca usam a internet. Os de contrato com o Supabase rodam só com `uv run pytest -m supabase` (marcador novo, também excluído por padrão no `pyproject.toml`).
- **Commits:** toda mensagem termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Servidor local:** sem `--reload`. Para ver uma mudança, pare e suba de novo.

## Review Focus

1. **Redirecionamento aberto pelo `proximo`:** `//evil.com`, `/\evil.com` e `https://evil.com`. Esperado: vira `/`. Teste na Task 2.
2. **Access token vencido no meio de uma ação HTMX:** a ação deve funcionar, e a resposta deve trazer os cookies novos. Teste na Task 3.
3. **Sessão revogada em outro aparelho** (a renovação é recusada): a pessoa vira visitante, os cookies são apagados e não aparece tela de erro. Teste na Task 3.
4. **Supabase fora do ar quando uma pessoa logada abre a página de uma série:** a página abre como visitante (200), não 503. Teste na Task 3.
5. **Nome com HTML no cadastro** (`<b>Ro</b>`): aparece escapado no cabeçalho. Teste na Task 6.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/auth/client.py` | `User`, `Session`, erros, `SupabaseAuth` (HTTP com `/auth/v1`) |
| `app/auth/forms.py` | validação pura dos formulários; `safe_next` |
| `app/auth/session.py` | cookies, `UserResolver` (cache e renovação), `SessionMiddleware`, `LoginRequired` |
| `app/auth/csrf.py` | `CSRFMiddleware` |
| `app/auth/routes.py` | páginas de conta |
| `app/tracking/store.py` | `TrackingStore` (Protocol), `TrackingUnavailable`, `VisitorStore`, `StoreFactory` |
| `app/tracking/supabase_repository.py` | `SupabaseTrackingRepository` |
| `supabase/migracoes/001_marcacoes.sql` | tabelas, RLS e funções (spec §7) |
| `app/importar.py` | importação única |
| `tests/fakes.py` | + `FakeAuth`, `SqliteStore`, `sqlite_stores`, `TEST_USER` |

---

### Task 1: Configuração e cliente de login do Supabase

**Files:**
- Modify: `app/config.py`, `.env.example`, `pyproject.toml` (marcador `supabase` e `addopts = "-m 'not tmdb and not supabase'"`), `tests/test_config.py`
- Create: `app/auth/__init__.py`, `app/auth/client.py`
- Test: `tests/test_auth_client.py`

**Interfaces:**
- Produces, em `app/config.py`:
  - `Settings` ganha `supabase_url: str = ""`, `supabase_publishable_key: str = ""` e `supabase_secret_key: SecretStr | None = None`.
  - `load_settings` lança `ConfigError("SUPABASE_URL e SUPABASE_PUBLISHABLE_KEY não definidos. Veja o README.")` quando um dos dois está vazio.
- Produces, em `app/auth/client.py`:
  - `@dataclass(frozen=True) User(id: str, email: str, first_name: str, last_name: str)`
  - `@dataclass(frozen=True) Session(access_token: str, refresh_token: str, expires_at: int, user: User)`
  - Exceções: `AuthError` e as filhas `InvalidCredentials`, `EmailTaken`, `WeakPassword`, `RateLimited`, `AuthUnavailable`, `InvalidRecoveryLink` e `InvalidSession`.
  - `SupabaseAuth(http: httpx.AsyncClient, url: str, publishable_key: str)` com os métodos:
    - `async sign_up(email, password, first_name, last_name) -> Session`
    - `async sign_in(email, password) -> Session`
    - `async refresh(refresh_token) -> Session`
    - `async get_user(access_token) -> User`
    - `async sign_out(access_token) -> None`
    - `async recover(email) -> None`
    - `async verify_recovery(token_hash) -> Session`
    - `async update_password(access_token, password) -> None`
- **Tradução das respostas do Supabase:**
  - `user_metadata.first_name` e `user_metadata.last_name` viram campos do `User`; quando faltam, ficam `""`.
  - `Session.expires_at` vem do campo `expires_at` da resposta; sem ele, é `now + expires_in`.
  - Erros por `error_code` ou status:
    - `invalid_credentials` → `InvalidCredentials`;
    - `user_already_exists` ou `email_exists` → `EmailTaken`;
    - `weak_password` → `WeakPassword`;
    - status 429 → `RateLimited`;
    - `otp_expired`, ou 403 no `/verify` → `InvalidRecoveryLink`;
    - 401 ou 403 em `/user` ou `/token?grant_type=refresh_token`, ou `refresh_token_not_found` → `InvalidSession`;
    - `httpx.HTTPError`, 5xx ou resposta que não é JSON → `AuthUnavailable`.

- [ ] **Step 1: Testes (`tests/test_auth_client.py`)**, com `respx` em `https://proj.supabase.co/auth/v1` e um `SupabaseAuth` criado com essa URL e a chave `"pk"`:

```python
SESSION = {"access_token": "a1", "refresh_token": "r1", "expires_at": 2000000000,
           "user": {"id": "u-1", "email": "eu@x.com", "user_metadata": {"first_name": "Romany", "last_name": "Melo"}}}

async def test_sign_up_sends_names_and_returns_session(auth, mock):
    route = mock.post("/signup").respond(json=SESSION)
    s = await auth.sign_up("eu@x.com", "segredo123", "Romany", "Melo")
    body = json.loads(route.calls.last.request.content)
    assert body == {"email": "eu@x.com", "password": "segredo123", "data": {"first_name": "Romany", "last_name": "Melo"}}
    assert route.calls.last.request.headers["apikey"] == "pk"
    assert s == Session("a1", "r1", 2000000000, User("u-1", "eu@x.com", "Romany", "Melo"))

@pytest.mark.parametrize(("status", "payload", "error"), [
    (400, {"error_code": "invalid_credentials"}, InvalidCredentials),
    (422, {"error_code": "user_already_exists"}, EmailTaken),
    (422, {"error_code": "email_exists"}, EmailTaken),
    (422, {"error_code": "weak_password"}, WeakPassword),
    (429, {"error_code": "over_request_rate_limit"}, RateLimited),
    (503, {}, AuthUnavailable),
])
async def test_errors_are_translated(auth, mock, status, payload, error): ...  # mesma tradução em sign_up e sign_in

async def test_network_error_is_unavailable(auth, mock): ...                  # side_effect=httpx.ConnectError
async def test_sign_in_uses_password_grant(auth, mock): ...                   # POST /token, params grant_type=password
async def test_refresh_uses_refresh_grant_and_401_is_invalid_session(auth, mock): ...
async def test_get_user_sends_bearer(auth, mock): ...                         # Authorization: Bearer a1 -> User
async def test_get_user_401_is_invalid_session(auth, mock): ...
async def test_recover_and_verify_recovery(auth, mock): ...                   # verify: {"type": "recovery", "token_hash": "th"}; 403 -> InvalidRecoveryLink
async def test_update_password_puts_with_bearer(auth, mock): ...
async def test_sign_out_posts_logout(auth, mock): ...
```

E em `tests/test_config.py`: `test_missing_supabase_raises` (com `TMDB_TOKEN` definido e `SUPABASE_URL` vazio, levanta a mensagem exata). Os testes existentes de config passam a definir `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` com `monkeypatch`.

- [ ] **Step 2:** `uv run pytest tests/test_auth_client.py tests/test_config.py -q`. Expected: `ModuleNotFoundError: app.auth` e falha no teste de config.
- [ ] **Step 3:** Implemente com as assinaturas e traduções acima. O timeout é o do `httpx.AsyncClient` recebido (10 s em produção).
- [ ] **Step 4:** `uv run pytest -q`. Expected: tudo passa.
- [ ] **Step 5: Commit** — `feat(contas): cliente de login do Supabase e configuração`.

---

### Task 2: Validação dos formulários

**Files:**
- Create: `app/auth/forms.py`
- Test: `tests/test_auth_forms.py`

**Interfaces:**
- Produces:
  - `safe_next(value: str | None) -> str`
  - `@dataclass(frozen=True) SignupData(first_name, last_name, email, password)`
  - `validate_signup(form: Mapping[str, str]) -> tuple[SignupData | None, dict[str, str]]`: as chaves do dict de erros são os nomes dos campos (`nome`, `sobrenome`, `email`, `senha`, `confirmacao`); nome e sobrenome são guardados sem os espaços das pontas.
  - `validate_login(form) -> tuple[tuple[str, str] | None, dict[str, str]]`, que devolve `(email, senha)`.
  - `validate_new_password(form) -> tuple[str | None, dict[str, str]]`, com os campos `senha` e `confirmacao`.
  - `EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")`. O e-mail é normalizado com `strip().lower()`.

- [ ] **Step 1: Testes:**

```python
@pytest.mark.parametrize("value", [None, "", "//evil.com", "/\\evil.com", "https://evil.com", "evil.com", "javascript:x"])
def test_safe_next_rejects_outside(value):
    assert safe_next(value) == "/"

def test_safe_next_keeps_local_path():
    assert safe_next("/serie/1?aba=x") == "/serie/1?aba=x"

def test_signup_ok_strips_and_lowercases():
    data, errors = validate_signup({"nome": " Romany ", "sobrenome": "Melo", "email": " Eu@X.com ",
                                    "senha": "segredo123", "confirmacao": "segredo123"})
    assert errors == {} and data == SignupData("Romany", "Melo", "eu@x.com", "segredo123")

def test_signup_errors():
    _, errors = validate_signup({"nome": "", "sobrenome": "x" * 61, "email": "eu@", "senha": "curta", "confirmacao": "outra"})
    assert errors == {"nome": "Informe seu nome.", "sobrenome": "Use até 60 caracteres.",
                      "email": "Informe um e-mail válido.", "senha": "A senha precisa ter pelo menos 8 caracteres.",
                      "confirmacao": "As senhas não são iguais."}

def test_login_requires_email_and_password(): ...  # {"email": "Informe um e-mail válido.", "senha": "Informe sua senha."}
def test_new_password(): ...                        # senha curta; confirmação diferente; ok devolve a senha
```

- [ ] **Step 2:** rode; Expected: `ModuleNotFoundError`.
- [ ] **Step 3:** implemente.
- [ ] **Step 4:** `uv run pytest -q`; Expected: tudo passa.
- [ ] **Step 5: Commit** — `feat(contas): validação dos formulários de conta`.

---

### Task 3: Sessão em cookies, CSRF e app com auth injetável

**Files:**
- Create: `app/auth/session.py`, `app/auth/csrf.py`
- Modify: `app/main.py`, `tests/conftest.py`, `tests/fakes.py`
- Test: `tests/test_auth_session.py`, `tests/test_csrf.py`

**Interfaces:**
- Consumes: `SupabaseAuth`, `User`, `Session` e os erros (Task 1).
- Produces, em `app/auth/session.py`:
  - `ACCESS_COOKIE = "op_acesso"`, `REFRESH_COOKIE = "op_renovacao"`, `REFRESH_MAX_AGE = 180 * 24 * 3600`, `USER_CACHE_TTL = 300`.
  - `class LoginRequired(Exception)`
  - `set_session_cookies(response, session: Session, secure: bool) -> None` e `clear_session_cookies(response) -> None`.
  - `@dataclass Resolution(user: User | None, access_token: str | None, new_session: Session | None, clear: bool)`
  - `UserResolver(auth, clock=time.time)` com `async resolve(access: str | None, refresh: str | None) -> Resolution`. Usa um `TTLCache(clock=clock)` próprio.
  - `SessionMiddleware`, um `BaseHTTPMiddleware` que recebe o resolver no construtor. Ele grava `request.state.user`, `request.state.access_token` e `request.state.watch_time = None`; depois da resposta, aplica `new_session` ou `clear`.
- **Fluxo do `resolve`:**
  1. Com access token em cache, devolve o usuário.
  2. Com access token: chama `get_user`.
     - Deu certo: guarda em cache e devolve.
     - `InvalidSession`: tenta a renovação.
     - `AuthUnavailable`: devolve visitante, sem limpar os cookies.
  3. Sem access token, mas com refresh token: tenta a renovação.
  4. Renovação:
     - deu certo: devolve o usuário com `new_session`;
     - `InvalidSession`: devolve visitante com `clear=True`;
     - `AuthUnavailable`: devolve visitante sem limpar.
- Produces, em `app/auth/csrf.py`: `CSRFMiddleware`, que responde 403 com o HTML mínimo `<p>Pedido recusado</p>`.
- Produces, em `app/main.py`:
  - `create_app(settings=None, catalog=None, auth=None, database_path=None)`. O `database_path` e o serviço global de marcações continuam até a Task 4. No modo de teste (com `catalog` informado), `auth` vem de quem chama.
  - `app.state.auth`.
  - Ordem dos middlewares: CSRF por fora, sessão por dentro.
  - Handler de `LoginRequired`, que chama `login_redirect(request)`:
    - HTMX: 200 vazio com `HX-Redirect: /entrar?proximo=<urlencode(caminho relativo de HX-Current-URL)>`;
    - GET: 303 para `/entrar?proximo=<path?query>`;
    - outros métodos: 303 para `/entrar?proximo=<Referer relativo ou />`.

    Sempre passa por `safe_next`.
- Produces, em `tests/fakes.py`:
  - `TEST_USER = User("00000000-0000-0000-0000-000000000001", "eu@teste.com", "Romany", "Melo")`
  - `FakeAuth(users_by_token: dict[str, User] | None = None, accounts: dict[str, tuple[str, User]] | None = None, error: AuthError | None = None)`: tem os mesmos métodos do `SupabaseAuth`, guarda as chamadas em `.calls` e lança `error` quando configurado. `sign_in` confere `accounts[email] == (senha, user)`. `sign_up` cria a conta e devolve `Session("tok-novo", "ref-novo", 2000000000, user)`. `refresh` e `get_user` usam `users_by_token`.
- Produces, em `tests/conftest.py`:
  - `make_client(fake, db=None, user=TEST_USER)`: cria o app com `auth=FakeAuth({"tok-teste": user} if user else {})` e o `database_path` de hoje.
  - Todo cliente envia `Origin: http://testserver` por padrão.
  - Com `user`, o cliente já leva o cookie `op_acesso=tok-teste`.

- [ ] **Step 1: Testes (`tests/test_auth_session.py`)**, com `UserResolver(FakeAuth(...), clock=FakeClock())` e rotas reais via `make_client`:

```python
async def test_valid_token_is_cached(): ...                 # 2 resolves -> 1 chamada get_user
async def test_cache_never_outlives_token_expiry(): ...      # expires_at = agora+10: no 11º segundo chama de novo
async def test_expired_token_refreshes_and_sets_new_cookies(): ...  # get_user InvalidSession + refresh ok -> new_session
async def test_revoked_refresh_clears_cookies(): ...         # refresh InvalidSession -> user None, clear True
async def test_supabase_down_is_visitor_without_clearing(): ...    # AuthUnavailable -> user None, clear False

def test_cookie_attributes(make_client): ...                 # Set-Cookie de op_renovacao: HttpOnly; SameSite=lax; Path=/; Max-Age=15552000
def test_htmx_action_with_expired_token_works_and_renews(make_client): ...   # Review Focus 2
def test_revoked_session_becomes_visitor_without_error(make_client): ...     # Review Focus 3: GET /serie/... 200 + cookies apagados
def test_supabase_down_logged_user_sees_series_page(make_client): ...        # Review Focus 4: FakeAuth(error=AuthUnavailable()) -> 200
def test_visitor_action_htmx_gets_hx_redirect(make_client): ...  # user=None, POST status com HX -> 200 e HX-Redirect "/entrar?proximo=%2Fserie%2F100088"
def test_visitor_action_page_gets_303_to_login(make_client): ...  # sem HX, com Referer http://testserver/serie/100088 -> Location /entrar?proximo=%2Fserie%2F100088
def test_visitor_my_series_redirects_to_login(make_client): ...  # GET /minhas-series?aba=quero -> 303 /entrar?proximo=%2Fminhas-series%3Faba%3Dquero
```

E `tests/test_csrf.py`:

```python
@pytest.mark.parametrize("headers", [{"Origin": "https://evil.com"}, {"Origin": ""}, {"Referer": "https://evil.com/x"}])
def test_post_from_other_origin_is_refused(make_client, headers): ...  # cliente sem o Origin padrão; 403 e "Pedido recusado"
def test_post_without_origin_and_referer_is_refused(make_client): ...
def test_same_origin_by_referer_is_accepted(make_client): ...
def test_get_is_never_checked(make_client): ...
```

- [ ] **Step 2:** rode; Expected: falham, porque os módulos ainda não existem.
- [ ] **Step 3:** Implemente `session.py`, `csrf.py`, as mudanças em `main.py`, os fakes e o conftest. Nesta task, `get_tracking` e as rotas ainda usam o serviço global; o `LoginRequired` só é lançado a partir da Task 4. Os testes de visitante da Step 1 entram aqui marcados com `xfail(strict=True, reason="Task 4")`.
- [ ] **Step 4:** `uv run pytest -q`. Expected: tudo passa, exceto os `xfail` esperados.
- [ ] **Step 5: Commit** — `feat(contas): sessão em cookies, CSRF e app com auth e stores injetáveis`.

---

### Task 4: Marcações por conta e visitante

**Files:**
- Create: `app/tracking/store.py`
- Modify: `app/main.py`, `app/tracking/service.py`, `app/tracking/routes.py`, `app/routes.py`, `app/templates/base.html`, `app/templating.py`, `tests/conftest.py`, `tests/fakes.py`, `tests/test_tracking_service.py`, `tests/test_routes_tracking.py`, `tests/test_auth_session.py` (tirar os `xfail`)

**Interfaces:**
- Consumes: `LoginRequired`, `request.state.user`, `request.state.access_token`, `FakeAuth` e `TEST_USER` (Task 3).
- Produces, em `app/tracking/store.py`:
  - `class TrackingUnavailable(Exception)`
  - `class TrackingStore(Protocol)`, com os métodos async `marks`, `marks_for`, `watched`, `save`, `counts`, `list_tab`, `watch_time`, `missing_runtimes` e `set_runtimes`. Assinaturas e retornos são iguais aos do `TrackingRepository` SQLite de hoje, todos com `async def`.
  - `StoreFactory = Callable[[User, str], TrackingStore]`, que recebe o usuário e o access token.
  - `class VisitorStore`: as leituras devolvem vazio (`Marks()`, `{}`, `frozenset()`, contagens zeradas, `[]`, `(0, 0)`); `save` e `set_runtimes` lançam `LoginRequired`.
- Produces, em `app/main.py`:
  - `create_app(settings=None, catalog=None, auth=None, stores: StoreFactory | None = None)`. Sai o `database_path` e o serviço global (`app.state.tracking`); entra `app.state.stores`.
- Produces, em `tests/fakes.py` e `tests/conftest.py`:
  - `SqliteStore(conn, user_id)`: as mesmas operações do `TrackingRepository(conn, user_id=user_id)`, em `async def`.
  - `sqlite_stores(path) -> StoreFactory`: abre uma conexão com `connect(path)` e devolve `lambda user, token: SqliteStore(conn, user.id)`.
  - `make_client(fake, db=None, user=TEST_USER)` passa `stores=sqlite_stores(db or tmp_path / "catalogo.db")`.
- Produces, no serviço e nas rotas:
  - `TrackingService(catalog, store: TrackingStore, today=...)`: toda chamada ao store usa `await`, e `marks_for` vira `async`. As regras e os fluxos não mudam.
  - Em `app/tracking/routes.py`:
    - `get_tracking(request) -> TrackingService`: lança `LoginRequired` sem usuário; com usuário, usa `app.state.stores(user, token)`.
    - `page_tracking(request) -> TrackingService`: sem usuário, usa `VisitorStore()`.
  - **Rotas:**
    - os POSTs e `/minhas-series` usam `get_tracking`;
    - `/`, `/buscar`, `/serie/{id}` e `/serie/{id}/temporada/{n}` usam `page_tracking`;
    - `fill_runtimes` em segundo plano só é agendado quando há usuário.
  - **Templates:**
    - `base.html` lê `request.state.user` e `request.state.watch_time` (este é preenchido só na Task 7; por enquanto, `None`);
    - a função global `tempo_de_series` e a `watch_time_of` saem de `templating.py`;
    - a montagem do cabeçalho para visitante e para logado fica para a Task 6; nesta task, só a troca da fonte do contador.

- [ ] **Step 1: Ajuste os testes:**
  - Em `tests/test_tracking_service.py`, o fixture `repo` passa a ser `SqliteStore(connect(":memory:"), TEST_USER.id)`, e as asserções chamam `await repo.watched(...)`, `await repo.marks_for(...)` e assim por diante.
  - Em `tests/test_routes_tracking.py`, o `seed` grava com `TrackingRepository(conn, user_id=TEST_USER.id)`, e `saved_marks` também.
  - Os testes do contador no cabeçalho (`test_header_*`, `test_marking_watched_fills_runtimes_right_after_the_click`) ficam `xfail(strict=True, reason="Task 7")`.
  - Acrescente:

```python
def test_visitor_browses_series_and_season_without_marks(make_client):
    c = make_client(tracked_catalog(), user=None)
    assert c.get(f"/serie/{ID}").status_code == 200 and 'value="want" aria-pressed="false"' in c.get(f"/serie/{ID}").text
    assert 'aria-pressed="true"' not in c.get(f"/serie/{ID}/temporada/1").text

def test_visitor_sees_no_badges(make_client, tmp_path): ...  # seed para TEST_USER; user=None em "/": nenhum class="selo"

def test_two_users_do_not_see_each_other(make_client, tmp_path):
    db = tmp_path / "dois.db"
    make_client(tracked_catalog(), db=db).post(f"/serie/{ID}/status", data={"status": "want"})
    other = User("00000000-0000-0000-0000-000000000002", "outro@teste.com", "Ana", "Silva")
    page = make_client(tracked_catalog(), db=db, user=other).get(f"/serie/{ID}").text
    assert 'value="want" aria-pressed="true"' not in page
```

- [ ] **Step 2:** rode; Expected: falham, porque o serviço ainda chama o store sem `await` e os testes de visitante ainda não passam.
- [ ] **Step 3:** Implemente e retire o `xfail` dos testes de visitante da Task 3.
- [ ] **Step 4:** `uv run pytest -q`. Expected: tudo passa, exceto os `xfail` da Task 7.
- [ ] **Step 5: Commit** — `feat(contas): marcações por conta e navegação de visitante`.

---

### Task 5: Banco no Supabase e repositório via PostgREST

**Files:**
- Create: `supabase/migracoes/001_marcacoes.sql`, `app/tracking/supabase_repository.py`, `tests/test_supabase_repository.py`, `tests/test_supabase_contract.py`

**Interfaces:**
- Consumes: `TrackingStore` e `TrackingUnavailable` (Task 3).
- **O SQL:** contém exatamente as tabelas da spec §7, RLS ligado, a política única `for all to authenticated` em cada tabela e `revoke all ... from anon`. As funções (`language plpgsql` ou `sql`, `security invoker`, `set search_path = ''`, com nomes qualificados `public.` e `execute` só para `authenticated`) são:
  - `save_tracking(p_tmdb_id int, p_name text, p_poster_path text, p_status text, p_favorite boolean, p_add jsonb, p_remove jsonb) returns void`. `p_add` é `[{season, episode, runtime}]` e `p_remove` é `[{season, episode}]`. Ordem dentro da função: inserir com `on conflict do nothing`; apagar; fazer o upsert da série com `updated_at = now()`; apagar a linha vazia.
  - `tracking_counts() returns json`, no formato `{"watching": n, "want": n, "watched": n, "favorite": n}`.
  - `watch_time() returns json`, no formato `{"episodes": n, "minutes": n}`.
  - `missing_runtimes() returns json`, no formato `[{"tmdb_id": n, "season": n}]`.
  - `set_runtimes(p_tmdb_id int, p_runtimes jsonb) returns void`, que só atualiza as linhas com `runtime is null`.
- Produces: `SupabaseTrackingRepository(http: httpx.AsyncClient, url: str, publishable_key: str, access_token: str)`, que implementa o `TrackingStore`. Todo pedido leva `apikey` e `Authorization: Bearer <access_token>`.

| Método | Pedido |
|---|---|
| `marks_for(ids)` | `GET /rest/v1/series_tracking?select=tmdb_id,status,favorite&tmdb_id=in.(1,2)` (lista vazia: `{}` sem pedido) |
| `marks(id)` | `marks_for([id])` |
| `watched(id)` | `GET /rest/v1/watched_episodes?select=season,episode&tmdb_id=eq.<id>` |
| `save(...)` | `POST /rest/v1/rpc/save_tracking`; `runtimes` vira `runtime` em cada item de `p_add` (`null` se desconhecido) |
| `counts()` / `watch_time()` / `missing_runtimes()` | `POST /rest/v1/rpc/<nome>` com `{}` |
| `set_runtimes(id, runtimes)` | `POST /rest/v1/rpc/set_runtimes` |
| `list_tab(tab)` | `GET /rest/v1/series_tracking?select=tmdb_id,name,poster_path,status,favorite&<filtro>&order=updated_at.desc`; o filtro é `status=eq.<tab>` ou `favorite=is.true`; `poster_url` com `w342` |

Erros: `httpx.HTTPError`, status ≥ 500 ou 401 viram `TrackingUnavailable`. O 4xx de `save` com status inválido vira `InvalidAction`.

- [ ] **Step 1: Testes com respx (`tests/test_supabase_repository.py`):** URL e filtros de cada linha da tabela; o cabeçalho `Authorization: Bearer tok`; o corpo exato da `save_tracking`, por exemplo:

```python
async def test_save_sends_one_rpc_with_everything(repo, mock):
    route = mock.post("/rest/v1/rpc/save_tracking").respond(204)
    await repo.save(7, name="X", poster_path="/p.jpg", status="watching", favorite=True,
                    add=[(1, 1), (1, 2)], remove=[(0, 1)], runtimes={(1, 1): 50})
    assert json.loads(route.calls.last.request.content) == {
        "p_tmdb_id": 7, "p_name": "X", "p_poster_path": "/p.jpg", "p_status": "watching", "p_favorite": True,
        "p_add": [{"season": 1, "episode": 1, "runtime": 50}, {"season": 1, "episode": 2, "runtime": None}],
        "p_remove": [{"season": 0, "episode": 1}]}
```

Também: a tradução de erros (`ConnectError`, 503 e 401 viram `TrackingUnavailable`), `marks_for([])` sem pedido e a conversão de `list_tab` para `TrackedSeries`.

- [ ] **Step 2: Testes de contrato (`tests/test_supabase_contract.py`, `pytestmark = pytest.mark.supabase`):**
  - **Fixture:** cria dois usuários temporários com `POST /auth/v1/admin/users` (`email_confirm: true`, senha aleatória, e-mail `teste-<uuid>@ondeparei.test`), entra com cada um e, no fim, apaga os dois com `DELETE /auth/v1/admin/users/<id>`.
  - **Cabeçalhos de administração:** quando a chave secreta começa com `sb_secret_`, vai só `apikey`; senão, `apikey` mais `Authorization: Bearer`.
  - **Testes:**
    - `test_save_and_read_back`;
    - `test_other_user_sees_nothing_and_cannot_change` (as leituras do segundo usuário voltam vazias, e um `save` dele no mesmo `tmdb_id` não altera a linha do primeiro);
    - `test_anon_has_no_access` (sem Bearer: a leitura volta vazia ou dá 401, e a RPC dá 401 ou 404);
    - `test_counts_watch_time_missing_and_set_runtimes`;
    - `test_empty_row_is_deleted`.
- [ ] **Step 3:** `uv run pytest tests/test_supabase_repository.py -q`. Expected: falha, porque o módulo ainda não existe.
- [ ] **Step 4:** Implemente o SQL e o repositório. `uv run pytest -q`. Expected: tudo passa. O contrato fica para a Task 9, depois que o usuário rodar o SQL.
- [ ] **Step 5: Commit** — `feat(contas): tabelas, RLS e funções no Supabase e repositório via PostgREST`.

---

### Task 6: Páginas de conta e cabeçalho

**Files:**
- Create: `app/auth/routes.py`, `app/templates/entrar.html`, `app/templates/criar_conta.html`, `app/templates/esqueci_senha.html`, `app/templates/nova_senha.html`, `app/templates/_campo.html`
- Modify: `app/main.py` (registrar o router), `app/templates/base.html`, `app/static/style.css` (seção `/* Contas */`)
- Test: `tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `app.state.auth`, `validate_*`, `safe_next`, `set_session_cookies`, `clear_session_cookies` e `read_form`.
- **Rotas** (spec §6.3):
  - `GET/POST /entrar` e `/criar-conta`. Logado, o GET vai em 303 para `/`. Em caso de sucesso, grava os cookies e responde 303 para `safe_next(form["proximo"])`.
  - `POST /sair`: chama `sign_out` (ignora `AuthError`), apaga os cookies e responde 303 para `/`.
  - `GET/POST /esqueci-senha`. O POST sempre mostra a mensagem fixa, mesmo com `AuthError`, exceto `RateLimited` e `AuthUnavailable`, que mostram as próprias mensagens.
  - `GET /nova-senha?token_hash=…&type=recovery`: chama `verify_recovery`. Se der certo, grava a sessão nos cookies e mostra o formulário. Se der `InvalidRecoveryLink`, mostra `Este link expirou.` com o link `Pedir outro link` para `/esqueci-senha`.
  - `POST /nova-senha`: exige usuário na sessão, senão `Este link expirou.`. Chama `update_password` e responde 303 para `/`.
- **Mensagens de erro** (Global Constraints): `InvalidCredentials`, `EmailTaken` (com link `Entrar`), `WeakPassword`, `RateLimited` e `AuthUnavailable`. O formulário volta com status 200 e com os valores digitados, menos as senhas.
- **Markup:**
  - Cada página usa `<main class="conta">`, com um cartão `.conta-cartao`, o título `h1.vitrine-titulo` e o formulário `method="post"` com `<input type="hidden" name="proximo">`.
  - A macro `campo(nome, rotulo, tipo, valor, erro, autocomplete)` gera `<label>`, o `<input>` e `<p class="campo-erro" id="erro-{nome}">`, com `aria-describedby` e `aria-invalid` quando há erro.
  - Valores de `autocomplete`: `given-name`, `family-name`, `email`, `current-password` e `new-password`.
- **Cabeçalho (`base.html`):**
  - **Visitante:** `<a class="link-topo" href="/entrar?proximo=<urlencode(path?query)>">Entrar</a>` e `<a class="botao botao--pequeno" href="/criar-conta">Criar conta</a>`.
  - **Logado:** o contador; `<button class="usuario-botao" popovertarget="menu-usuario">{{ user.first_name or user.email }}</button>`; e o `<div id="menu-usuario" popover>` com o link `Minhas séries` e `<form method="post" action="/sair"><button>Sair</button></form>`.
- **CSS:**
  - o cartão tem largura máxima de 420 px e é centralizado, com fundo `--veludo`, borda `--fio` e raio de 18 px;
  - os campos têm o mesmo estilo da busca do cabeçalho;
  - os erros aparecem em `#ffb3a6`;
  - o botão principal é o `.botao` âmbar ocupando a largura toda;
  - o menu do usuário reaproveita o estilo `.menu` dos popovers do catálogo.

- [ ] **Step 1: Testes (`tests/test_auth_routes.py`, com `FakeAuth` configurado):**

```python
def test_sign_up_logs_in_and_goes_back(make_client): ...
    # user=None; POST /criar-conta com proximo=/serie/1 -> 303 Location /serie/1 e cookies op_acesso/op_renovacao gravados
def test_sign_up_validation_keeps_values_without_passwords(make_client): ...   # 200, "Informe seu nome.", value="eu@x.com", sem "segredo"
def test_email_taken_offers_login(make_client): ...                            # FakeAuth(error=EmailTaken()) -> mensagem + href="/entrar"
def test_login_wrong_password(make_client): ...                                # "E-mail ou senha incorretos."
def test_login_with_unsafe_next_goes_home(make_client): ...                    # proximo=//evil.com -> Location /
def test_logged_user_visiting_login_goes_home(make_client): ...                # GET /entrar -> 303 /
def test_logout_clears_cookies(make_client): ...                               # POST /sair -> 303 / e Set-Cookie op_acesso=""; Max-Age=0
def test_forgot_password_always_same_message(make_client): ...                 # e-mail existente e inexistente -> mesma frase
def test_recovery_link_expired(make_client): ...                               # FakeAuth verify -> InvalidRecoveryLink -> "Este link expirou." e href="/esqueci-senha"
def test_new_password_flow(make_client): ...                                   # GET com token_hash ok -> formulário; POST -> update_password chamado; 303 /
def test_auth_unavailable_message_on_login(make_client): ...                   # AuthUnavailable -> mensagem do servidor de contas
def test_header_visitor_links(make_client): ...                                # user=None em /serie/1 -> href="/entrar?proximo=%2Fserie%2F1" e "Criar conta"
def test_header_logged_shows_first_name_and_menu(make_client): ...             # "Romany", popovertarget="menu-usuario", action="/sair"
def test_html_in_name_is_escaped(make_client): ...                             # Review Focus 5: first_name "<b>Ro</b>" -> "&lt;b&gt;Ro&lt;/b&gt;"
```

- [ ] **Step 2:** rode; Expected: 404 nas rotas novas.
- [ ] **Step 3:** Implemente as rotas, os templates e o CSS.
- [ ] **Step 4:** `uv run pytest -q`. Expected: tudo passa, exceto os `xfail` da Task 7.
- [ ] **Step 5: Commit** — `feat(contas): páginas de entrar, criar conta, sair e recuperar senha`.

---

### Task 7: Produção ligada ao Supabase, contador no cabeçalho e erros

**Files:**
- Modify: `app/main.py`, `app/auth/session.py`, `tests/test_routes_tracking.py` (tirar os `xfail` da Task 7), `tests/test_app.py`

**Interfaces:**
- Consumes: `SupabaseAuth` (Task 1), `SupabaseTrackingRepository` (Task 5) e `SessionMiddleware` (Task 3).
- Produces:
  - **Produção:** no `create_app` sem `catalog`, o app cria um `httpx.AsyncClient(timeout=10)` para o Supabase, com `auth = SupabaseAuth(...)` e `stores = lambda user, token: SupabaseTrackingRepository(http, url, key, token)`. O cliente é fechado no fim do `lifespan`.
  - **Contador do cabeçalho:** o `SessionMiddleware` preenche `request.state.watch_time`, com `await app.state.stores(user, token).watch_time()`, só em GET de página inteira (não HTMX) com usuário. Se der `TrackingUnavailable`, fica `None`.
  - **Erros:** o handler de `TrackingUnavailable` usa `_error_response` com status 503 e a mensagem fixa. O handler de `sqlite3.Error` sai, e com ele o `SAVE_ERROR`.

- [ ] **Step 1: Testes:**
  - Os testes do contador no cabeçalho, marcados com `xfail` na Task 4, passam a ser cobrados.
  - Novo: `test_tracking_unavailable_message`. O `stores` do teste devolve um store cujo `save` lança `TrackingUnavailable`; com HTMX, a resposta é 200 com a mensagem, e sem HTMX é 503.
  - Novo: `test_header_counter_hidden_when_store_fails`. O `watch_time` lança `TrackingUnavailable`, a página abre (200) e não há `contador-topo`.
  - O `test_save_failure_shows_friendly_message` (SQLite) é substituído pelo `test_tracking_unavailable_message`.
- [ ] **Step 2:** rode; Expected: os testes do cabeçalho e os novos falham.
- [ ] **Step 3:** Implemente.
- [ ] **Step 4:** `uv run pytest -q`. Expected: tudo passa, sem nenhum `xfail` restante.
- [ ] **Step 5: Commit** — `feat(contas): app de produção ligado ao Supabase, contador por conta`.

---

### Task 8: Importação das marcações locais

**Files:**
- Create: `app/importar.py`
- Test: `tests/test_importar.py`

**Interfaces:**
- Consumes: `connect` e `TrackingRepository` (SQLite), e `load_settings`.
- Produces: `async def import_local(db_path, email, http, url, secret_key) -> Summary`, mais o `main(argv)` do comando `python -m app.importar <email>`.
  - `Summary(series: int, episodes: int, minutes_before: int, minutes_after: int)`.
  - Sem `SUPABASE_SECRET_KEY`, o `main` sai com código 2 e a mensagem `SUPABASE_SECRET_KEY não definido no .env (necessário só para a importação).`
- **Passos:**
  1. Procura o usuário em `GET /auth/v1/admin/users?page=N&per_page=200`, de página em página, até achar o e-mail, ignorando maiúsculas e minúsculas, ou até a lista vir vazia. Se não achar, lança `LookupError("Conta não encontrada: crie a conta no app primeiro.")`.
  2. Lê as tabelas SQLite inteiras, ignorando o `user_id` local.
  3. Faz `POST /rest/v1/series_tracking?on_conflict=user_id,tmdb_id` e `POST /rest/v1/watched_episodes?on_conflict=user_id,tmdb_id,season,episode`, com `Prefer: resolution=merge-duplicates` e o `user_id` da conta. Os pedidos vão em lotes de 500 linhas, com os cabeçalhos de administração da Task 5.
  4. `minutes_after` vem de `GET /rest/v1/watched_episodes?select=runtime&user_id=eq.<id>`, somando.
- **Saída do `main`:** `Importado: N séries, M episódios. Tempo de séries: <tempo_tv antes> → <tempo_tv depois>.`

- [ ] **Step 1: Testes (respx e SQLite de exemplo em `tmp_path`):**
  - `test_imports_with_upsert_and_user_id` confere o corpo e o `Prefer` dos dois POSTs;
  - `test_account_not_found`;
  - `test_lookup_is_paginated_and_case_insensitive`;
  - `test_running_twice_sends_the_same_upserts`.
- [ ] **Step 2:** rode; Expected: `ModuleNotFoundError`.
- [ ] **Step 3:** implemente.
- [ ] **Step 4:** `uv run pytest -q`; Expected: tudo passa.
- [ ] **Step 5: Commit** — `feat(contas): importação das marcações locais para a conta`.

---

### Task 9: README, painel do Supabase e verificação com o usuário

**Files:**
- Modify: `README.md`, `.env.example`, `docs/superpowers/specs/2026-10-17-contas-design.md` (Status: implementada)

- [ ] **Step 1: README.** Uma seção "Contas (Supabase)" com os 5 passos do painel (spec §10), o modelo exato do link do e-mail de recuperação, o comando de importação e o comando `uv run pytest -m supabase`.
- [ ] **Step 2: Pare e peça ao usuário.** Ele precisa rodar o SQL, ajustar o painel e preencher o `.env`, colando as chaves direto no arquivo e nunca no chat. Depois disso, confira `uv run pytest -m supabase -q`. Expected: todos os testes de contrato passam. Se algum falhar, ajuste o SQL ou o repositório e repita.
- [ ] **Step 3:** O usuário cria a conta no app. Depois rode `uv run python -m app.importar <email dele>`. Expected: o tempo de séries antes e depois é o mesmo.
- [ ] **Step 4: Revisão visual.** Suba o servidor e capture as telas de Entrar, Criar conta e do cabeçalho (visitante e logado), no desktop (1366) e no celular (390, pelo wrapper de iframe). Corrija o CSS no que for preciso.
- [ ] **Step 5:** `uv run pytest -q`. Expected: tudo passa. Commit: `docs: contas com Supabase no README`.
- [ ] **Step 6:** Verificação no navegador com o usuário: critérios 1 a 9 da spec e largura de celular.
