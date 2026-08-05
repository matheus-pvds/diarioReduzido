# Módulo `processor.py` — Cliente Gemini (IA de resumo)

Responsável por enviar o PDF do diário oficial ao Google Gemini, aguardar o
processamento do arquivo e gerar o resumo estruturado (título + resumo +
"Conclusões da IA") com failover automático entre modelos.

No `import` do módulo, `load_dotenv()` é chamado (carrega o `.env`), o que
faz com que qualquer import indireto de `app.py` → `processor.py` também
carregue as variáveis de ambiente do `.env`.

---

## Classe `GeminiClient`

### `__init__(self)`
- Lê `GEMINI_API_KEY` do ambiente.
- Lança `ValueError` se a chave não estiver configurada.
- Importa `google.genai` **lazily** (com supressão de warnings) para manter o
  cold start rápido em ambiente serverless nas rotas que não usam Gemini.
- Instancia `self.client = genai.Client(api_key=...)`.

### `process_pdf(self, pdf_data, prompt=None)`
Processa os bytes de um PDF e devolve o texto gerado pelo modelo.

**Parâmetros**
- `pdf_data`: bytes do arquivo PDF.
- `prompt`: instrução customizada (default é o prompt editorial em PT-BR que
  pede título impactante, resumo detalhado, seção `### Conclusões da IA` e a
  linha `DATA PUBLICACAO: DD/MM/AAAA`).

**Fluxo interno**
1. **Upload em memória**: `io.BytesIO(pdf_data)` → `client.files.upload(...)`
   com `mime_type='application/pdf'` e `display_name='diary.pdf'`.
2. **Espera de processamento**: loop de até 180s consultando `files.get(...)`
   enquanto o arquivo estiver `PROCESSING`.
3. **Failover de modelos** (lista do mais rápido ao mais robusto):
   `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-2.5-flash`,
   `gemini-2.0-flash-lite`, `gemini-2.0-flash`, `gemini-3.1-pro-preview`,
   `gemini-2.5-pro`.
   - Orçamento total de 200s para todas as tentativas.
   - A cada modelo: `client.models.generate_content(model, [file, prompt])`.
   - Remove marcadores técnicos acidentais (`[SYSTEM ERROR]`,
     `(AI: fallback-logic)`, `Summary fallback:`, `[API RATE LIMIT REACHED]`).
   - Resposta vazia → tenta o próximo modelo.
   - Sucesso → deleta o arquivo da API (`files.delete`) e retorna
     `(texto, nome_do_modelo)`.
4. **Falha total**: deleta o arquivo (best effort) e retorna
   `("Desculpe, não foi possível gerar o resumo automático...", "indisponível")`.

**Retorno**
- `tuple[str, str]` → `(conteúdo_gerado, modelo_utilizado)`.

---

## Relação com o restante do app

- O `app.py` importa `GeminiClient` e o usa em:
  - `perform_update_logic()` — atualização diária automática.
  - `search_date()` — busca por data específica.
  - `/api/reprocess-latest` — reprocessamento.
- A saída crua do modelo é interpretada por `app.parse_content()`
  (prefixos `TITULO:` / `DATA PUBLICACAO:` e marcador `### Conclusões da IA`).
