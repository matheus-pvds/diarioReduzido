# Módulo `app.py` — Aplicação Flask do Diário Reduzido

O módulo central da aplicação. Define a instância Flask, o banco de dados
(SQLAlchemy), os modelos, todas as rotas HTTP e as funções de negócio
(autenticação, assinaturas, streaks, scraping do diário, comentários etc).

---

## 1. Estrutura de inicialização

### Instância e configuração
| Item | Detalhe |
|---|---|
| `app` | Instância `Flask(__name__` |
| `app.secret_key` | Env `SECRET_KEY` ou valor aleatório |
| `app.config['SQLALCHEMY_DATABASE_URI']` | Env `POSTGRES_URL` (fallback `sqlite:///local.db`); converte `postgres://` → `postgresql://` |
| Pool p/ Postgres | `pool_pre_ping`, `pool_recycle=300`, `pool_size=2`, `max_overflow=4`, `pool_timeout=20`, `connect_timeout=10` |
| Cookies de sessão | `HttpOnly`, `SameSite=Lax`, `Secure` se env `VERCEL=true` |
| `db` | Instância `SQLAlchemy(app)` |
| `BRT` | `timezone(timedelta(hours=-3))` — fuso de Brasília |

### Bootstrap (executado em `with app.app_context():`)
1. `db.create_all()` — cria as tabelas.
2. `migrate_columns()` — adiciona colunas novas em tabelas existentes.
3. `dedupe_posts_by_link()` — remove posts duplicados pelo `pdf_link`.
4. `ensure_constraints()` — garante NOT NULL e UNIQUE no banco.
5. Cria o usuário `admin` (env `ADMIN_PASSWORD`, default `admin`).
6. Cria `AppConfig` `last_checked_timestamp` e `is_checking`.
7. Se `RUN_POST_MIGRATION=true`, executa `migrate_existing_posts()`.

### Hooks globais
| Função | Papel |
|---|---|
| `ensure_schema()` (`before_request`) | Roda migrações sob demanda na primeira requisição (`app._schema_checked`). |
| `add_security_headers()` (`after_request`) | Adiciona headers de segurança (CSP, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy). |
| `inject_security()` (`context_processor`) | Injeta `csrf_token` e `google_client_id` em todos os templates. |

---

## 2. Variáveis de ambiente usadas

| Variável | Uso |
|---|---|
| `SECRET_KEY` | Chave da sessão Flask |
| `POSTGRES_URL` | URI do banco (Postgres em produção) |
| `VERCEL` | `true` ativa cookies Secure |
| `RUN_POST_MIGRATION` | `true` roda migração de conteúdo no boot |
| `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Criação do usuário admin |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | Envio de e-mail (verificação, reset, notificação) |
| `RECAPTCHA_SITE_KEY`, `RECAPTCHA_SECRET_KEY` | Google reCAPTCHA |
| `GOOGLE_CLIENT_ID` | OAuth de login/cadastro com Google |
| `ASAAS_API_KEY`, `ASAAS_WEBHOOK_SECRET` | Integração de pagamento |
| `GEMINI_API_KEY` | Usada via `processor.py` |

---

## 3. Modelos (SQLAlchemy)

### `Post`
| Campo | Tipo | Observação |
|---|---|---|
| `id` | Integer PK | |
| `title` | String(200) NOT NULL | Título jornalístico |
| `content` | Text NOT NULL | Resumo em markdown |
| `summary` | Text | Teaser |
| `commentary` | Text | "Conclusões da IA" |
| `date` | DateTime(tz) | Criação (default `now(BRT)`) |
| `publication_date` | Date | Data do diário |
| `model` | String(100) | Modelo Gemini usado |
| `pdf_link` | String(500) UNIQUE | URL do PDF original |
| `comments` | rel. `Comment` | Cascade delete |

### `AppConfig`
Tabela chave-valor: `key` (String 50, UNIQUE), `value` (String 500), `timestamp`.

### `User`
Campos principais: `id`, `username` (UNIQUE), `email` (UNIQUE), `password`,
`google_id` (UNIQUE, nullable — vínculo com conta Google), `password_set`
(bool — indica se o usuário definiu senha), `is_paid`, `requests_made`,
`email_verified`, `verification_token`, `reset_token`, `reset_token_expires`,
`points`, `paid_until`, `streak_count`, `last_streak_date`, `streak_freezes`,
`theme`, `title`, `purchased_themes`, `badge`, `purchased_badges`,
`first_purchase_done`, `font`.

Relacionamentos: `favorites` (Favorite), `comments` (Comment).

### `Favorite`
`user_id` FK, `post_id` FK, `created_at`.

### `LoginAttempt`
`ip_address` (indexado), `timestamp`, `success` — usado p/ rate limit.

### `Comment`
`content`, `created_at`, `edited_at`, `user_id`, `post_id`, `parent_id`
(respostas aninhadas via relação `replies`).

---

## 4. Constantes de negócio

- `PLAN_DAYS`: dias de cada plano (`1dia`, `1mes`, `3meses`, `6meses`, `12meses`).
- `PLAN_VALUES`: preços em R$.
- `FREE_MONTH_POINTS = 360`: pontos para 1 mês grátis.
- `BADGES`: mapa de distintivos (nome + emoji).
- `BADGE_PRICE = 5.00`.
- `PIX_PAYLOAD` / `PIX_QR_IMAGE`: dados fixos do PIX do mantenedor.
- `COMBOS`: combos de compra (plano + temas + freezes + badge).
- `STREAK_THEMES`, `THEME_PRICES`: temas por streak e preços.
- `STREAK_FONTS`, `ADMIN_FONT`: fontes por streak (7→365 dias).
- `STREAK_TITLES`, `PIONEER_TITLE`, `PIONEER_BADGE`: títulos por streak.
- `STREAK_BONUS_POINTS`: bônus de pontos ao atingir marcos.
- `CHECK_STALE_MINUTES = 15`: tempo p/ considerar checagem "presa".

---

## 5. Funções utilitárias

### E-mail
- `send_email(to, subject, body)` — envia e-mail via SMTP (MIMEText, STARTTLS).
  Aceita `to` como string ou lista (usando Bcc). Retorna `bool`.

### Preços e desbloqueios
- `get_theme_price(req_streak, user_streak=0)` — preço com desconto proporcional
  à streak atual.
- `get_font_css(font_id)` / `get_font_name(font_id)` — resolvem CSS/nome da fonte.
- `get_unlocked_fonts(user)` — fontes liberadas (admin: todas).
- `get_all_font_urls()` / `get_user_font_url(user)` — URLs do Google Fonts.
- `get_purchasable_themes(user)` / `get_purchasable_badges(user)` — itens
  compráveis/desbloqueados.
- `get_unlocked_titles(user)` / `get_user_title(user)` — títulos por streak.
- `get_unlocked_themes(user)` — temas por streak/compra.

### Banco e migração
- `dedupe_posts_by_link()` — agrupa posts por `pdf_link`, migra favoritos e
  comentários p/ o post mantido, apaga duplicados.
- `ensure_constraints()` — corrige NOT NULL e adiciona UNIQUE ausentes.
- `migrate_columns()` — renomeia colunas antigas (`COLUMN_RENAMES`) e adiciona
  colunas novas ausentes.
- `migrate_existing_posts()` — separa `commentary` ("Conclusões da IA") e
  `title` de posts antigos.

### Conteúdo / texto
- `generate_summary(text, limit=350)` — gera teaser por heurística de frases-chave.
- `make_teaser(content, limit=200)` — atalho p/ `generate_summary`.
- `parse_content(text)` — interpreta a saída do Gemini: prefixos `TITULO:` e
  `DATA PUBLICACAO:` e marcador `### Conclusões da IA`. Retorna
  `(title, content, commentary, pub_date)`.
- `parse_title(text)` — retorna só `(title, content)`.
- `render_md(text)` — markdown → HTML (`markdown.markdown`, ext. `extra`).

### Autenticação / segurança
- `login_required(f)` — decorator: redireciona p/ `/login?next=...` se não logado.
- `get_current_user()` — usuário da sessão ou `None`.
- `get_client_ip()` — IP real (via `X-Forwarded-For`).
- `validate_csrf()` — compara token do form com o da sessão (comparação segura).
- `check_rate_limit(ip, max_attempts=10, window_minutes=15)` — limite de falhas.
- `record_attempt(ip, success)` — registra tentativa em `LoginAttempt`.
- `failed_attempt_count(ip)` — contagem de falhas nos últimos 15 min.
- `should_show_captcha(ip)` — exige captcha após ≥5 falhas.
- `_captcha_disabled()` — true em TESTING/debug/desenvolvimento.
- `generate_captcha()` — gera conta matemática simples na sessão.
- `validate_captcha(answer)` — valida captcha matemático ou reCAPTCHA.

### Streak / gamificação
- `update_streak(user)` — incrementa streak diária, aplica congelamentos
  (`streak_freezes`), concede `STREAK_BONUS_POINTS` em marcos e registra o
  primeiro usuário a atingir 365 dias (`first_365_user_id`).
- `check_premium_expiry(user)` — revoga `is_paid` se `paid_until` expirou.
- `get_premium_days_left(user)` — dias restantes de premium.

### Diário oficial (fluxo híbrido: API + portal)
- `DADOS_ABERTOS_BASE` / `DADOS_ABERTOS_CLIENT` — endpoint da API oficial de
  Dados Abertos do PortalFácil (Lei 12.527) e `idCliente=94` (Governador Valadares).
- `fetch_diarios_index(year)` — consulta a API oficial e retorna o índice de
  edições do ano (`numDiario`, `dtPublicacao`, etc.), paginando (pageSize=100).
- `_parse_publicacao_dt(value)` — converte `dtPublicacao` (`DD/MM/AAAA HH:MM:SS`)
  em `datetime` BRT.
- `latest_diario_from_api()` — retorna `(numDiario, dt_publicacao)` da edição
  mais recente via API (tenta ano atual e anterior). Em erro → `(None, None)`.
- `fetch_daily_diary()` — abre a página do caderno de Governador Valadares e
  localiza o link estático do PDF da edição atual (`a.btn-primary.arquivo-pdf`).
  Retorna `(pdf_url, pub_date)`.
- `_extract_date_from_url(url)` — extrai data `DD-MM-YYYY` da URL.
- `extract_ajaxpro_handler(html)` — localiza o caminho do handler AjaxPro
  (`ajaxpro/diel_diel_lis,...`).
- `_parse_datatable_js(text)` — interpreta a resposta `new Ajax.Web.DataTable(...)`
  do portal e retorna uma lista de dicts.
- `search_diary_by_date(target_date)` — **fluxo híbrido**: (1) a API oficial
  confirma se existe edição na data e obtém o `numDiario`; (2) o AjaxPro
  (`GetDiario` com `nuEdicao`) resolve o GUID do PDF. Retorna `(pdf_url, pub_date)`.
- `_stdlib_get` / `_stdlib_post` / `fetch_diarios_index_stdlib(year)` /
  `_stdlib_decode(data, headers)` / `search_diary_by_date_stdlib(target_date)` —
  versão stdlib-only (sem `requests`/`bs4`) do mesmo mecanismo, útil em
  ambientes serverless restritos. Decodifica respeitando o charset do header.
- `_AjaxHandlerParser` (`html.parser.HTMLParser`) — varre os `<script>` da
  página e captura o caminho do handler AjaxPro usado pela versão stdlib.
- `set_checking(value)` / `is_checking()` — trava anti-corrida em memória que
  impede duas checagens simultâneas (`/api/perform-check`).
- `is_weekend()` — identifica sábado/domingo (no fuso BRT).
- `get_check_interval()` — retorna o intervalo em minutos até a próxima
  checagem automática: 15 min em dia útil, 60 min logo após publicação
  (`CHECK_STALE_MINUTES`), 360 min em fins de semana.
- `perform_update_logic()` — orquestra a atualização diária (ver abaixo).

### Google
- `_unique_username(base)` — gera nome de usuário único (sanitiza e acrescenta
  sufixo numérico se necessário).
- `_verify_google_credential(credential)` — valida o ID token com `google-auth`.
- `_google_email_and_sub(idinfo)` — extrai e-mail/sub validados.
- `_google_user(email, sub)` — localiza usuário por `google_id` ou `email`.

---

## 6. Rotas

### Páginas públicas
| Rota | Método | Descrição |
|---|---|---|
| `/` | GET | Home: última edição, teasers, favoritos, temas, checagem automática. |
| `/post/<int:id>` | GET | Exibe um post específico (renderiza `index.html`). |
| `/share/<int:post_id>` | GET | Página de compartilhamento (antes da data do post → erro). |
| `/archive` | GET | Arquivo de todas as edições (**login obrigatório**). |
| `/coffee` | GET | Redireciona p/ `/planos`. |
| `/planos` | GET | Página de planos/doação. |
| `/pagamento/sucesso` / `/pagamento/falha` | GET | Confirmação de pagamento. |
| `/favicon.ico` | GET | Favicon estático. |

### Autenticação
| Rota | Método | Descrição |
|---|---|---|
| `/login` | GET/POST | Login por usuário+senha com rate limit, captcha e CSRF. |
| `/register` | GET/POST | Cadastro (valida nome/email/senha, envia verificação, `password_set=True`, 3 freezes). |
| `/api/google-login` | POST | Verifica ID token Google; se usuário existir (por `google_id`/email), vincula e loga; se não, retorna `needs_username` + sugestão. |
| `/api/google-signup` | POST | Cria a conta Google com o nome de usuário escolhido (valida unicidade). |
| `/logout` | GET | Encerra a sessão. |
| `/verify-email/<token>` | GET | Confirma e-mail. |
| `/forgot` | GET/POST | Envia link de redefinição de senha. |
| `/reset/<token>` | GET/POST | Redefine a senha (`password_set=True`). |

### Configurações de conta
| Rota | Método | Descrição |
|---|---|---|
| `/update-username` | POST | Altera nome de usuário (único, 3–80 chars, regex). Admin bloqueado. |
| `/update-email` | POST | Altera e-mail (único); envia verificação se SMTP ativo. Admin bloqueado. |
| `/update-password` | POST | Altera senha (exige atual se `password_set`; contas Google podem definir senha). |

### Diário / conteúdo
| Rota | Método | Descrição |
|---|---|---|
| `/search-date` | POST | Busca diário por data (limite: 1 pedido/dia p/ gratuito), processa com Gemini e publica. |
| `/api/reprocess-latest` | POST | Admin/pago: reprocessa o último post com PDF vazio. |
| `/api/migrate-content` | GET | Admin: roda `migrate_existing_posts()`. |
| `/api/should-check` | GET | Retorna se já deve checar novo diário (+ intervalo). |
| `/api/perform-check` | GET | Executa `perform_update_logic()` (com trava `is_checking`). |
| `/api/status` | GET | Status do último post e se há checagem em andamento. |

### Favoritos e comentários
| Rota | Método | Descrição |
|---|---|---|
| `/favorite/<int:post_id>` | POST | Alterna favorito (limite 5 p/ gratuito). |
| `/favorites` | GET | Lista favoritos (renderiza `archive.html`). |
| `/comment/<int:post_id>` | POST | Cria comentário (2–1000 chars). |
| `/comment/<id>/edit`, `/comment/<id>/delete`, `/comment/<id>/reply` | POST | Edita/remove/responde (autor ou admin). |

### Dashboard / personalização
| Rota | Método | Descrição |
|---|---|---|
| `/dashboard` | GET | Painel do usuário (streak, pontos, títulos, temas, fontes, planos). |
| `/theme` | POST | Altera tema (somente desbloqueados). |
| `/update-title` | POST | Altera título. |
| `/update-badge` | POST | Altera distintivo. |
| `/update-font` | POST | Altera fonte. |

### Pagamentos (Asaas)
| Rota | Método | Descrição |
|---|---|---|
| `/api/create-checkout` | POST | Cria cliente, tokeniza cartão (se aplicável) e gera pagamento PIX/cartão/boleto. |
| `/api/payment-status/<payment_id>` | GET | Consulta status do pagamento. |
| `/api/asaas-webhook` | POST | Webhook do Asaas: processa `PAYMENT_CONFIRMED`, aplica plano/combo/tema/distintivo/freezes e pontos. |

---

## 7. Fluxos importantes

### Atualização diária (`perform_update_logic`)
1. `latest_diario_from_api()` consulta a API oficial de Dados Abertos e retorna
   a edição mais recente (`numDiario`, `dtPublicacao`).
2. Se a data da edição for mais recente que o último `Post.publication_date` →
   `fetch_daily_diary()` obtém a URL estática do PDF da edição atual.
3. Se a API estiver indisponível → fallback direto em `fetch_daily_diary()`.
4. Se o `pdf_link` ainda não existe no banco → baixa o PDF com `requests`.
5. `GeminiClient().process_pdf(pdf_content)` extrai texto + modelo usado.
6. `parse_content()` separa título, resumo, "Conclusões da IA" e data.
7. Cria o `Post` (data: IA → API → URL), commita e envia e-mail de notificação
   aos assinantes pagos.
8. Retorna `{status, message}` (`success` / `error` / `no_change`).

### Login com Google
1. O botão (Google Identity Services) gera um ID token no navegador.
2. `POST /api/google-login` recebe o token (JWT) e o valida com `google-auth`.
3. Se já existe usuário com aquele `google_id` ou e-mail → vincula o `google_id`,
   marca e-mail verificado e loga (redireciona p/ `dashboard` ou `next`).
4. Se não existe → responde `{needs_username, suggested_username}` e o front
   mostra um modal; ao confirmar, `POST /api/google-signup` valida unicidade,
   cria o usuário (`password_set=False`, 3 freezes, senha aleatória) e loga.

### Cobrança / planos
- `PLAN_VALUES` + `PLAN_DAYS` definem preço e duração.
- O webhook do Asaas atualiza `paid_until`, `is_paid`, pontos, temas, badges,
  freezes e o combo. O primeiro pagamento dá 1 dia extra.
