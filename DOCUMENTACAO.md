# Documentação Completa — O Diário Reduzido

> Compilado único de toda a documentação técnica do projeto.
> Cada módulo também possui documentação individual em `docs/`:
> [`docs/APP.md`](docs/APP.md), [`docs/PROCESSOR.md`](docs/PROCESSOR.md),
> [`docs/ASAAS.md`](docs/ASAAS.md).

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Estrutura de arquivos](#3-estrutura-de-arquivos)
4. [Deploy e execução](#4-deploy-e-execução)
5. [Variáveis de ambiente](#5-variáveis-de-ambiente)
6. [Como funciona o download do diário](#6-como-funciona-o-download-do-diário)
7. [Módulo `app.py`](#7-módulo-apppy)
8. [Módulo `processor.py`](#8-módulo-processorpy)
9. [Módulo `asaas.py`](#9-módulo-asaaspy)
10. [Banco de dados](#10-banco-de-dados)
11. [Segurança](#11-segurança)
12. [Gamificação (streaks, pontos, temas)](#12-gamificação-streaks-pontos-temas)
13. [Testes](#13-testes)

---

## 1. Visão geral

**O Diário Reduzido** é uma aplicação web (Flask + SQLAlchemy) que lê o
**Diário Oficial de Governador Valadares (MG)**, baixa o PDF publicado no
portal da prefeitura, processa o conteúdo com o **Google Gemini** e publica um
resumo jornalístico diário para os leitores.

Funcionalidades principais:

- **Resumo automático diário** do Diário Oficial (API oficial + portal + IA).
- **Busca por data** específica no arquivo histórico.
- **Contas de usuário** com e-mail/senha **ou login com Google** (OAuth).
- **Assinaturas** (planos) via **Asaas** (PIX, cartão e boleto).
- **Gamificação**: streaks diários, pontos de fidelidade, títulos, temas,
  fontes e distintivos.
- **Favoritos e comentários** com respostas aninhadas.
- **Envio de e-mail**: verificação, recuperação de senha e notificação de
  novas edições para assinantes pagos.

---

## 2. Arquitetura

```
Navegador (HTML/CSS/JS + Google Identity Services)
        │
        ▼
Flask (app.py)  ──►  PostgreSQL (SQLAlchemy)
        │
        ├──► Portal da Prefeitura (API Dados Abertos + link estático / AjaxPro)
        │        └──► PDF baixado
        │                └──► Gemini (processor.py) ──► resumo + "Conclusões da IA"
        │
        ├──► Google Identity (verificação de ID token via google-auth)
        ├──► Asaas API v3 (asaas.py) — clientes, tokenização, cobranças, webhook
        └──► SMTP (e-mails de verificação, reset e notificação)
```

**Camadas:**

| Camada | Responsável |
|---|---|
| Rotas / views | `app.py` |
| Modelos ORM | `app.py` (classes `Post`, `User`, `Comment`, `Favorite`, `LoginAttempt`, `AppConfig`) |
| IA de resumo | `processor.py` (`GeminiClient`) |
| Pagamentos | `asaas.py` |
| Templates | `templates/*.html` (Jinja2) |
| Estáticos | `static/` (favicon, imagens de loading, QR PIX) |
| Testes | `test/*.py` |

---

## 3. Estrutura de arquivos

```
.
├── app.py                  # Aplicação Flask completa (rotas, modelos, negócio)
├── processor.py            # Cliente Gemini (resumo de PDFs)
├── asaas.py                # Integração Asaas v3 (pagamentos)
├── requirements.txt        # Dependências Python
├── Procfile                # Comando de execução (gunicorn app:app)
├── vercel.json             # Config de deploy serverless (função app.py)
├── conftest.py             # Config de warnings para pytest
├── posts.json              # Dados auxiliares de posts
├── last_pdf.txt            # Último PDF processado (cache auxiliar)
├── docs/                   # Documentação por módulo
│   ├── APP.md
│   ├── PROCESSOR.md
│   └── ASAAS.md
├── templates/
│   ├── index.html          # Home / artigo
│   ├── login.html          # Login, registro e modal de nome do Google
│   ├── dashboard.html      # Painel do usuário
│   ├── archive.html        # Arquivo / favoritos
│   ├── coffee.html         # Página de planos
│   ├── forgot.html         # Recuperação de senha
│   ├── reset.html          # Redefinição de senha
│   ├── pagamento.html      # Confirmação de pagamento
│   └── share.html          # Página de compartilhamento
├── static/
│   ├── favicon.ico
│   ├── img/loading.gif     # Overlay de carregamento
│   └── img/qrCode.png      # QR Code do PIX
└── test/
    ├── test_models.py      # Lista modelos Gemini disponíveis
    ├── test_pipeline.py    # Pipeline: scraper → Gemini → persistência
    ├── test_rendering.py   # Testes E2E com Selenium (todas as rotas)
    ├── test_search.py      # Busca por data (API + AjaxPro) no portal
    └── test_search_date.py # Rota /search-date
```

---

## 4. Deploy e execução

### Local
```bash
pip install -r requirements.txt
python app.py            # serve em http://localhost:5000
```

### Produção (Vercel)
- `Procfile`: `web: gunicorn app:app`
- `vercel.json`:
  ```json
  {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "version": 2,
    "functions": {
      "app.py": { "maxDuration": 300, "memory": 1024 }
    }
  }
  ```
  Máximo de duração 300s e 1 GB de memória para o processamento do PDF/Gemini.

> Obs.: `processor.py` chama `load_dotenv()` no import — por isso as variáveis
> do `.env` são carregadas mesmo que `app.py` não o faça diretamente.

---

## 5. Variáveis de ambiente

| Variável | Obrigatória | Uso |
|---|---|---|
| `SECRET_KEY` | não* | Chave de sessão Flask (*default aleatório) |
| `POSTGRES_URL` | prod | URI do PostgreSQL |
| `VERCEL` | não | `true` ativa cookies de sessão `Secure` |
| `RUN_POST_MIGRATION` | não | `true` executa migração de conteúdo no boot |
| `ADMIN_PASSWORD` / `ADMIN_EMAIL` | não | Criação do usuário admin (default `admin`) |
| `GEMINI_API_KEY` | sim | Chave da API do Google Gemini (`processor.py`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | não | Envio de e-mails |
| `RECAPTCHA_SITE_KEY`, `RECAPTCHA_SECRET_KEY` | não | Google reCAPTCHA no login/registro |
| `GOOGLE_CLIENT_ID` | não | OAuth de login/cadastro com Google |
| `ASAAS_API_KEY` | não | Chave da API do Asaas |
| `ASAAS_WEBHOOK_SECRET` | não | Segredo do webhook do Asaas |
| `ASAAS_BASE_URL` | não | Base da API Asaas (default `https://api.asaas.com/v3`) |

---

## 6. Como funciona o download do diário

> **Fluxo híbrido.** O app usa a **API oficial de Dados Abertos do PortalFácil**
> (Lei 12.527) para detectar e confirmar edições, e o **link estático do portal**
> para baixar o PDF. O endpoint interno **AjaxPro** do site é usado **apenas**
> como resolutor do GUID (URL opaca) do PDF na busca por data. Por isso, apenas
> **edições publicadas** ficam disponíveis — o app depende do que o portal expõe.

### 6.0 API oficial de Dados Abertos
- Endpoint: `https://dadosabertos-portalfacil.azurewebsites.net/api/diarios?type=json&idCliente=94&page=1&pageSize=100&numAno=YYYY`.
- `idCliente=94` = Governador Valadares. Retorna o **índice** de edições do ano
  (`numExercicio`, `numDiario`, `descCaderno`, `dtPublicacao` no formato
  `DD/MM/AAAA HH:MM:SS`). **Não expõe a URL do PDF**.
- Suporta `type=json|xml`, `page`, `pageSize` (máx. 100) e `numAno`.
- `fetch_diarios_index(year)` pagina automaticamente; `latest_diario_from_api()`
  devolve `(numDiario, dtPublicacao)` da edição mais recente (ano atual ou anterior).
- Versão stdlib: `fetch_diarios_index_stdlib(year)` (urllib).

### 6.1 Edição mais recente — `fetch_daily_diary()` (`app.py`)
1. Abre `https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1`.
2. Localiza o link estático do PDF com `a.btn-primary.arquivo-pdf`.
3. Extrai a data de publicação do nome/URL do PDF (`DD-MM-YYYY`).
4. Retorna `(pdf_url, pub_date)`.

### 6.2 Busca por data — `search_diary_by_date()` (`app.py`)
1. **API oficial** confirma se existe edição na data alvo (`fetch_diarios_index`)
   e obtém o `numDiario`.
2. Abre a página do caderno e localiza o handler AjaxPro
   (`ajaxpro/diel_diel_lis,...`).
3. Envia `POST` com `X-AjaxPro-Method: GetDiario` e payload com `nuEdicao`
   (nº da edição) para resolver o **GUID** do PDF.
4. Interpreta a resposta `new Ajax.Web.DataTable(...)` e devolve
   `(pdf_url, pub_date)`.
5. Existe versão equivalente sem dependências externas:
   `search_diary_by_date_stdlib()` (urllib + HTMLParser), que também pagina a
   API e respeita o charset do response.

### 6.3 Orquestração — `perform_update_logic()` (`app.py`)
1. `latest_diario_from_api()` detecta a edição mais recente via **API oficial**.
2. Se a data for mais recente que o último `Post.publication_date`:
   `fetch_daily_diary()` obtém a URL estática do PDF.
3. Se a API estiver indisponível → fallback direto em `fetch_daily_diary()`.
4. Se o `pdf_link` ainda não está no banco (evita duplicatas):
   - `requests.get(pdf_link).content` baixa o PDF.
   - `GeminiClient().process_pdf(pdf_bytes)` extrai texto + modelo usado.
   - `parse_content()` separa título, resumo, "Conclusões da IA" e data.
   - Cria `Post` (data: IA → API → URL), commita e notifica assinantes pagos.
5. Retorna `{status, message}`:
   - `success` — novo diário processado;
   - `no_change` — nenhum diário novo;
   - `error` — falha no processamento.

### 6.4 Check automático
- `/api/perform-check` executa a lógica acima com trava anti-corrida
  (`is_checking` / `set_checking`).
- `/api/should-check` informa ao front se já passou o intervalo
  (`get_check_interval()`: 15 min durante o dia útil, 60 min logo após
  publicação, 360 min em fins de semana).

---

## 7. Módulo `app.py`

> Documentação completa em [`docs/APP.md`](docs/APP.md).

### 7.1 Inicialização
- `app` (Flask), `db` (SQLAlchemy), fuso `BRT` (UTC-3).
- Bootstrap em `with app.app_context()`: `create_all` → `migrate_columns` →
  `dedupe_posts_by_link` → `ensure_constraints` → admin + `AppConfig` → migração.

### 7.2 Modelos
`Post`, `AppConfig`, `User`, `Favorite`, `LoginAttempt`, `Comment`.

Destaques do `User`: `google_id` (vínculo Google), `password_set`,
`streak_count`, `streak_freezes`, `points`, `paid_until`, `is_paid`,
`purchased_themes`, `purchased_badges`, `theme`, `title`, `font`, `badge`.

### 7.3 Funções principais
- **E-mail**: `send_email(to, subject, body)`.
- **Migração**: `migrate_columns`, `ensure_constraints`, `dedupe_posts_by_link`,
  `migrate_existing_posts`.
- **Texto**: `parse_content`, `generate_summary`, `make_teaser`, `render_md`.
- **Segurança**: `login_required`, `get_current_user`, `get_client_ip`,
  `validate_csrf`, `check_rate_limit`, `generate_captcha`, `validate_captcha`,
  `should_show_captcha`.
- **Streak**: `update_streak`, `check_premium_expiry`, `get_premium_days_left`.
- **Desbloqueios**: `get_unlocked_themes`, `get_unlocked_titles`,
  `get_unlocked_fonts`, `get_user_title`, `get_theme_price`,
  `get_purchasable_themes`, `get_purchasable_badges`.
- **Scraping**: `fetch_diarios_index`, `latest_diario_from_api`,
  `fetch_daily_diary`, `search_diary_by_date`,
  `search_diary_by_date_stdlib`, `fetch_diarios_index_stdlib`,
  `_parse_publicacao_dt`, `_parse_datatable_js`,
  `extract_ajaxpro_handler`, `_AjaxHandlerParser`, `_stdlib_get`,
  `_stdlib_post`, `_stdlib_decode`, `set_checking`,
  `is_checking`, `is_weekend`, `get_check_interval`, `perform_update_logic`.
- **Google**: `_unique_username`, `_verify_google_credential`,
  `_google_email_and_sub`, `_google_user`.

### 7.4 Rotas (resumo)

| Grupo | Rotas |
|---|---|
| Públicas | `/`, `/post/<id>`, `/share/<id>`, `/archive`, `/planos`, `/coffee`, `/pagamento/*`, `/favicon.ico` |
| Autenticação | `/login`, `/register`, `/logout`, `/verify-email/<t>`, `/forgot`, `/reset/<t>` |
| Google | `/api/google-login`, `/api/google-signup` |
| Conta | `/update-username`, `/update-email`, `/update-password` |
| Diário | `/search-date`, `/api/should-check`, `/api/perform-check`, `/api/status`, `/api/reprocess-latest`, `/api/migrate-content` |
| Favoritos/comentários | `/favorite/<id>`, `/favorites`, `/comment/<id>`, `/comment/<id>/edit`, `/comment/<id>/delete`, `/comment/<id>/reply` |
| Dashboard/personalização | `/dashboard`, `/theme`, `/update-title`, `/update-badge`, `/update-font` |
| Pagamentos | `/api/create-checkout`, `/api/payment-status/<id>`, `/api/asaas-webhook` |

### 7.5 Fluxo de login com Google
1. Botão Google (Identity Services) gera **ID token** no navegador.
2. `POST /api/google-login` valida o token (`google-auth`) e localiza o usuário
   por `google_id` ou e-mail.
3. **Usuário existente** → vincula `google_id`, marca e-mail verificado, loga.
4. **Usuário novo** → responde `{needs_username, suggested_username}`; o modal
   pede o nome; `POST /api/google-signup` valida unicidade e cria a conta
   (`password_set=False`, 3 freezes, senha aleatória).

---

## 8. Módulo `processor.py`

> Documentação completa em [`docs/PROCESSOR.md`](docs/PROCESSOR.md).

Classe **`GeminiClient`**:
- `__init__()` — exige `GEMINI_API_KEY`, importa `google.genai` lazy.
- `process_pdf(pdf_data, prompt=None)` → `(texto, modelo)`:
  1. Upload do PDF em memória (`files.upload`).
  2. Espera até 180s pelo processamento (`files.get`).
  3. **Failover** entre modelos (flash → pro): `gemini-3.5-flash`,
     `gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-2.0-flash-lite`,
     `gemini-2.0-flash`, `gemini-3.1-pro-preview`, `gemini-2.5-pro`.
  4. Orçamento total de 200s; limpa marcadores técnicos; sucesso → retorna
     `(texto, clean_name)`.
  5. Falha total → mensagem de indisponibilidade + `"indisponível"`.

O prompt default pede (em PT-BR): título impactante, resumo quantificado,
seção `### Conclusões da IA` e linha `DATA PUBLICACAO: DD/MM/AAAA`. A saída é
interpretada por `app.parse_content()`.

---

## 9. Módulo `asaas.py`

> Documentação completa em [`docs/ASAAS.md`](docs/ASAAS.md).

Funções:
- `create_customer(name, email, cpf_cnpj)` → id do cliente (dedup por e-mail).
- `find_customer_by_email(email)` → id ou `None`.
- `tokenize_credit_card(customer_id, credit_card, holder_info, remote_ip)` →
  token do cartão (fallback entre endpoints).
- `create_payment(customer_id, value, description, external_ref, ...)` →
  cobrança (PIX/cartão/boleto), com `externalReference = "<user_id>_<plano>"`.
- `get_payment(payment_id)` → dados do pagamento.
- `process_webhook(payload)` → `user_id` quando `PAYMENT_CONFIRMED`.

Fluxo de assinatura:
1. `/api/create-checkout` cria cliente + tokeniza cartão + gera pagamento.
2. Webhook `/api/asaas-webhook` (autenticado por `ASAAS_WEBHOOK_SECRET`)
   processa a confirmação e aplica plano/combo/tema/badge/freezes/pontos.
3. `paid_until`/`is_paid` controlam o acesso premium (expirado em
   `check_premium_expiry`).

---

## 10. Banco de dados

- **Postgres em produção** (`POSTGRES_URL`), SQLite local.
- Migrações automáticas no boot: colunas novas, renomeações (`COLUMN_RENAMES`),
  NOT NULL e UNIQUE (`ensure_constraints`).
- Relações principais:
  - `User 1—N Favorite N—1 Post`
  - `User 1—N Comment N—1 Post` (com `parent_id` para respostas)
  - `LoginAttempt` para rate limit por IP
  - `AppConfig` chave/valor (timestamps de checagem, `first_365_user_id`)

---

## 11. Segurança

- **CSRF**: token por sessão injetado nos templates e validado via
  `validate_csrf()` em todos os POST.
- **Rate limit** de login por IP (`LoginAttempt`, 10 falhas / 15 min).
- **Captcha** matemático (ou reCAPTCHA) após 5 falhas.
- **Headers** (`after_request`): CSP, `X-Content-Type-Options`,
  `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`.
  O CSP permite `accounts.google.com` e `www.google.com` para o login com
  Google e reCAPTCHA.
- **Senhas** com `werkzeug.security` (hash + salt).
- **Verificação de e-mail** obrigatória para notificações e fluxos sensíveis.
- **Google**: ID token validado com `google-auth` (audience = `GOOGLE_CLIENT_ID`);
  e-mail deve estar verificado pelo Google; nome de usuário validado por regex.

---

## 12. Gamificação (streaks, pontos, temas)

- **Streak**: `update_streak()` incrementa a cada login diário; falhas usam
  `streak_freezes`; marcos dão `STREAK_BONUS_POINTS`.
- **Pontos**: `FREE_MONTH_POINTS = 360` → +30 dias grátis ao atingir.
- **Temas**: por streak (3→365 dias) ou compra (`get_theme_price` com desconto
  proporcional à proximidade).
- **Fontes**: 1 nova a cada 7 dias de streak (`STREAK_FONTS`).
- **Títulos**: por streak (`STREAK_TITLES`), exibidos nos comentários.
- **Distintivos**: `BADGES` compráveis (`BADGE_PRICE = 5.00`); pioneiro
  (primeiro a 365 dias) ganha `PIONEER_BADGE`.
- **Combos**: `COMBOS` (plano + temas + freezes) via Asaas.

---

## 13. Testes

| Arquivo | Tipo | Cobre |
|---|---|---|
| `test/test_pipeline.py` | unit (unittest + mocks) | Scraper (`fetch_daily_diary`), `GeminiClient` com failover, `perform_update_logic` com API mockada (cria post / `no_change`), unicidade de `pdf_link`, `dedupe_posts_by_link`. |
| `test/test_search.py` | integração (rede real) | `extract_ajaxpro_handler`, chamada AjaxPro direta, `_parse_datatable_js`, `search_diary_by_date`, `fetch_daily_diary`. || `test/test_search_date.py` | rota (test client + mocks) | `/search-date` cria post e retorna "Nenhum diário encontrado". |
| `test/test_rendering.py` | E2E (Selenium headless) | Todas as rotas públicas/protegidas, login/registro, renderização de markdown, planos, páginas de pagamento. |
| `test/test_models.py` | utilitário | Lista modelos Gemini disponíveis na API. |

**Rodando:**
```bash
python -m pytest                    # se usar pytest
python test/test_pipeline.py        # por arquivo
python test/test_rendering.py       # requer Chrome + webdriver-manager
```

---

*Documentação gerada a partir do código-fonte. Consulte `docs/` para a versão
por módulo.*
