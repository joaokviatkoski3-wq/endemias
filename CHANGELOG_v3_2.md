# Changelog — Sistema Endemias v3.2 (Fase 2)
**Data:** 2026-05  
**Arquivos alterados:** `app.py`, `etl.py`, `criar_banco.py`, `migrar_banco_v3_1.py`  
**Arquivos novos:** `templates/erro_csrf.html`, `CHANGELOG_v3_2.md`  
**Versão anterior:** v3.1 (Fase 1 — aprovada e em produção)

---

## Como aplicar

1. Substitua `app.py`, `etl.py`, `criar_banco.py` e `migrar_banco_v3_1.py` pelos desta versão
2. Se ainda não rodou `migrar_banco_v3_1.py` da Fase 1, rode agora — ele também aplica as correções de DB desta fase
3. Se já rodou, rode novamente — é idempotente (verifica antes de alterar)
4. Instale as dependências (se ainda não fez):
   ```
   pip install -r requirements.txt
   ```
5. Inicie normalmente com `iniciar.bat`

> **Nota sobre o flask-wtf:** A proteção CSRF agora está **ativa**. Se tiver algum formulário customizado que você adicionou fora do sistema padrão, ele precisará do campo `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.

---

## Correções aplicadas

### SEC-03 — Proteção CSRF completa *(crítico — concluído)*

**O que era:** Nenhum formulário tinha proteção contra cross-site request forgery. Qualquer site poderia forçar ações no sistema enquanto o usuário estava logado.

**O que foi feito:**

- `flask_wtf.CSRFProtect` ativado globalmente em `app.py`
- Token CSRF injetado via `<meta name="csrf-token">` no `base.html` — disponível para todo JavaScript da página
- Helper `getCsrf()` adicionado ao JS global do `base.html` — recupera o token sem repetição de código
- Helper `apiPost()` adicionado ao JS global — encapsula `fetch POST` com CSRF automático
- Campo `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` adicionado nos 5 formulários HTML:
  - `login.html`
  - `minha_senha.html`
  - `admin_usuarios.html`
  - `notificacoes.html` (form de impressão em lote)
  - `foco_detalhe.html` (form de impressão individual)
- Header `X-CSRFToken: getCsrf()` adicionado em todos os 9 `fetch POST/PUT/DELETE`:
  - `processar.html` — upload e cancelamento do ETL
  - `foco_detalhe.html` — salvar foco
  - `notificacoes.html` — atualizar status
  - `admin_usuarios.html` — editar campo e resetar senha
  - `agenda.html` — criar, editar e excluir evento
- Rotas isentas com `@csrf.exempt` (3 no total):
  - `/login` — não tem sessão prévia para gerar token
  - `/processar/stream/<job_id>` — SSE via GET
  - `/processar/confirmar/<job_id>` — SSE via GET
- Handler de erro `CSRFError` com resposta JSON para AJAX e template amigável `erro_csrf.html` para formulários
- Token com validade de 1 hora (`WTF_CSRF_TIME_LIMIT = 3600`)

### SEC-04 — Validação real de conteúdo no upload *(alto — concluído)*

**O que era:** Upload validava apenas a extensão `.xlsx` — um arquivo de qualquer tipo renomeado passava pela checagem. O nome do arquivo também podia conter caracteres perigosos.

**O que foi feito:**

- Função `_validar_arquivo_xlsx(file_storage)` criada com dupla validação:
  1. **Extensão:** deve terminar em `.xlsx` (case-insensitive)
  2. **Magic bytes:** lê os primeiros 4 bytes e verifica `PK\x03\x04` (assinatura real de todo arquivo XLSX/ZIP)
- `werkzeug.utils.secure_filename()` aplicado em todos os nomes de arquivo recebidos (elimina `../`, caracteres especiais, path traversal)
- Arquivos inválidos são **rejeitados individualmente** com mensagem clara — não interrompem os válidos
- Warning logado em `endemias.log` para cada arquivo rejeitado, incluindo IP do solicitante
- Se **nenhum** arquivo válido for enviado, retorna erro 400 com lista dos motivos de rejeição

### ETL-03 — Remoção de `carregar_larvas()` duplicada *(alto — concluído)*

**O que era:** A função `carregar_larvas()` existia no `etl.py` mas nunca era chamada — a lógica de carregamento de larvas estava reimplementada inline em `processar_upload()`. Duas lógicas paralelas sem nenhuma relação, com risco de divergência silenciosa.

**O que foi feito:**

- Função `carregar_larvas()` removida completamente do `etl.py` (~35 linhas eliminadas)
- A lógica inline em `processar_upload()` permanece como única fonte de verdade
- Redução: `etl.py` de 833 → 798 linhas

### DB-06 — Colunas `SISPNCD` e `CONTAOVOS_STATUS` documentadas *(médio — concluído)*

**O que era:** Duas colunas existentes no banco real (`SISPNCD VARCHAR(20)` e `CONTAOVOS_STATUS INTEGER`) não estavam no `criar_banco.py`. Um novo deploy não as criaria, causando erros silenciosos ou queries que falhavam.

**O que foi feito em `criar_banco.py`:**
```sql
-- DB-06: colunas adicionadas por migração posterior (existem no banco real)
-- SISPNCD: codigo de registro no SisPNCD
SISPNCD          VARCHAR(20),
-- CONTAOVOS_STATUS: 0=pendente, 1=preenchido, NULL=não aplicável
CONTAOVOS_STATUS INTEGER CHECK(CONTAOVOS_STATUS IN (0,1))
```

**O que foi feito em `migrar_banco_v3_1.py`:**
- Passo `[6b/7]` verifica se as colunas existem e as adiciona via `ALTER TABLE` se ausentes
- Idempotente — pode ser executado múltiplas vezes sem erro

### COD-03 — Lógica de relatório de agente unificada *(médio — concluído)*

**O que era:** A rota `/relatorio-agente/pdf` e a rota `/api/relatorio-agente` tinham as mesmas ~240 linhas de queries SQL duplicadas. Qualquer correção precisava ser feita nos dois lugares.

**O que foi feito:**

- Função privada `_obter_dados_relatorio_agente(nome, d_ini, d_fim)` criada com toda a lógica de consulta e cálculo
- Retorna um `dict` completo com todos os dados necessários para o template PDF e para o JSON da API
- `relatorio_agente_pdf()` reduzida de ~130 linhas para 12 linhas (chama a função e passa `**dados` para o template)
- `api_relatorio_agente()` reduzida de ~110 linhas para 12 linhas (chama a função e serializa `dados` para JSON)
- Resultado: **~240 linhas de código duplicado eliminadas**, single source of truth para toda a lógica de relatório de agente
- Qualquer nova métrica ou correção de query é feita em um único lugar

---

## Impacto por arquivo

| Arquivo | v3.0 | v3.1 | v3.2 | Δ total |
|---|---|---|---|---|
| `app.py` | 1.896 | 1.996 | 2.043 | +147 (inclui ~240 eliminadas + novas funções) |
| `etl.py` | 798 | 820 | 785 | −13 (carregar_larvas removida) |
| `criar_banco.py` | 328 | 338 | 345 | +17 |
| `migrar_banco_v3_1.py` | — | 161 | 192 | +31 |
| Templates alterados | — | — | 7 | — |
| Templates novos | — | — | 1 | erro_csrf.html |

---

## Pendências para Fase 3 (próximo mês)

- [ ] **ARQ-02** — Dividir `app.py` em blueprints Flask (visitas, notificações, dashboard, ETL, admin, agenda)
- [ ] **ARQ-04** — Migrar para Flask-g para conexões por request (elimina try/finally manual)
- [ ] **DB-02** — Confirmar remoção da tabela `endemias` órfã (o script de migração já pergunta)
- [ ] Testes de integração básicos para rotas críticas (ETL, notificações, relatório)

---

## Notas de uso após esta atualização

**Token CSRF expirado:** Se um usuário ficar com a página aberta por mais de 1 hora sem interagir e tentar salvar um formulário, verá a mensagem "Token de segurança expirado. Recarregue a página." — basta recarregar e tentar novamente. Esse comportamento é correto e esperado.

**Upload de arquivo inválido:** Se alguém tentar subir um arquivo que não é realmente um XLSX (ex: um CSV renomeado como .xlsx), receberá a mensagem "Conteúdo não é um arquivo XLSX válido". O arquivo deve ser aberto e salvo novamente como XLSX pelo Excel.
