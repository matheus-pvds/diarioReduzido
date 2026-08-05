# Módulo `asaas.py` — Integração de pagamentos (Asaas API v3)

Cliente para a API v3 do Asaas: criação de cliente, tokenização de cartão,
criação de cobranças (PIX / cartão / boleto), consulta de pagamento e
interpretação do webhook.

---

## Configuração

| Constante | Fonte | Default |
|---|---|---|
| `API_KEY` | env `ASAAS_API_KEY` | `''` |
| `BASE_URL` | env `ASAAS_BASE_URL` | `https://api.asaas.com/v3` |
| `HEADERS` | — | `access_token: API_KEY`, `Content-Type: application/json` |

`BILLING_TYPES` mapeia os tipos internos do app para o Asaas:
`card → CREDIT_CARD`, `pix → PIX`, `boleto → BOLETO`.

`TOKENIZE_ENDPOINTS` lista os endpoints de tokenização de cartão tentados em
ordem (fallback): `/creditCard/tokenizeCreditCard` e `/creditCard/tokenize`.

---

## Funções

### `create_customer(name, email, cpf_cnpj)` → `str` (id do cliente)
- `POST /customers` com `name`, `email`, `cpfCnpj` (somente dígitos).
- Se o Asaas responder `422` com "already", procura cliente existente por
  e-mail (`find_customer_by_email`) e retorna o id dele.
- Erro: lança `Exception('Erro Asaas ao criar cliente: ...')`.

### `find_customer_by_email(email)` → `str | None`
- `GET /customers?email=...` e retorna o id do primeiro resultado, ou `None`.

### `tokenize_credit_card(customer_id, credit_card, holder_info, remote_ip='')` → `dict`
- `POST` nos endpoints de `TOKENIZE_ENDPOINTS` com payload:
  `customer`, `creditCard`, `creditCardHolderInfo`, `remoteIp`.
- Se um endpoint retornar erro que não seja `404`/`405`, para de tentar.
- Retorna a resposta JSON (contém `creditCardToken`).
- Erro: lança `Exception` com o último texto de erro.

### `create_payment(customer_id, value, description, external_ref, billing_type='card', due_days=3, installments=1, callback_url='', credit_card_token=None, remote_ip='')` → `dict`
- `POST /payments` com:
  - `customer`, `billingType`, `value`, `dueDate` (hoje + `due_days`),
    `description`, `externalReference` (usado para identificar o usuário no webhook).
  - `callbackUrl` (se informado).
  - Para `CREDIT_CARD`: `creditCardToken` e `remoteIp` (se informados);
    se `installments > 1`, envia `installmentCount` e `installmentValue`.
- Retorna a resposta JSON do Asaas.
- Erro: lança `Exception('Erro Asaas ao criar pagamento: ...')`.

### `get_payment(payment_id)` → `dict`
- `GET /payments/<id>` e retorna os dados do pagamento.
- Erro: lança `Exception`.

### `process_webhook(payload)` → `int | None`
- Interpreta o webhook do Asaas:
  - Se `event == 'PAYMENT_CONFIRMED'`, lê `payment.externalReference`
    (formato `"<user_id>_<plano>"`), retorna o `user_id`.
  - Caso contrário, retorna `None`.

---

## Integração com o app

- O `app.py` importa as funções em `app.py:4`:
  `from asaas import create_customer, create_payment, process_webhook, tokenize_credit_card`.
- `get_payment` é importado e usado em `/api/payment-status/<payment_id>`.
- O retorno de `process_webhook` alimenta o tratamento do plano em
  `/api/asaas-webhook` (adiciona dias, pontos, temas, badges e freezes).
