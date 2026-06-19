# Cartilha de Operação — Sistema Endemias
## Versão para cobertura de férias

> **Leia isso antes de começar.** Se tiver dúvida em qualquer passo, **não clique em "Confirmar"** sem ter certeza.

---

## 1. Importar dados do KoboToolbox (passo mais importante)

### 1.1 Acesse o sistema
Abra o navegador e digite o endereço do servidor (peça ao colega se não souber).

### 1.2 Faça login
Use seu usuário e senha. Se esqueceu a senha, peça para um **admin** resetar.

### 1.3 Vá em "Processar Planilhas"
Menu superior → **Administração** → **Processar Planilhas**.

### 1.4 Escolha o formulário
Na aba **Kobo API**, selecione o tipo de trabalho (PE, TB, TBO, PVE, LARVAS etc.).

### 1.5 Clique em "Prévia"
Isso mostra uma amostra dos registros que serão importados.

> ⚠️ **ATENÇÃO**: Se aparecer **"Campos obrigatórios vazios"** em vermelho, **NÃO IMPORTE**. Chame alguém da equipe técnica para verificar.

### 1.6 Confirme a importação
Se a prévia estiver OK (sem avisos vermelhos), clique em **"Importar"** e depois em **"Confirmar"**.

Aguarde o processamento terminar. Não feche a aba.

---

## 2. O que fazer se der erro na importação

| Sintoma | O que fazer |
|---|---|
| "Token recusado pelo Kobo" | O token de API expirou. Chame o administrador técnico. |
| "Campos obrigatórios vazios" na prévia | O formulário Kobo pode ter mudado. **Não confirme**. Chame alguém da equipe. |
| "Banco de dados bloqueado" | Outro usuário está importando ao mesmo tempo. Aguarde 2 minutos e tente de novo. |
| Página travou no meio da importação | Não clique em "Confirmar" de novo. Aguarde 1 minuto, atualize a página (F5) e verifique se os dados já apareceram no Dashboard. |
| Número de visitas importadas parece errado | Compare com o total exibido na prévia. Se divergir, cancele e tente novamente. |

---

## 3. Como fazer backup manual (segurança)

### 3.1 Acesse a Central do Sistema
Menu superior → **Administração** → **Central do Sistema**.

### 3.2 Clique em "Backup"
O sistema cria uma cópia do banco automaticamente.

### 3.3 Verifique a data
Certifique-se de que o backup foi criado hoje.

> 💡 **Dica**: O sistema já faz backup automático antes de toda importação. Só faça manual se estiver com medo de algo dar errado.

---

## 4. Tarefas do dia a dia (checklist)

- [ ] Importar dados do Kobo (se houver)
- [ ] Verificar Dashboard se os números fazem sentido
- [ ] Verificar notificações pendentes (badge no menu)
- [ ] Se houver foco positivo, gerar notificação e imprimir
- [ ] Fazer backup manual se for fazer algo arriscado

---

## 5. Quem chamar em emergência

| Problema | Quem chamar |
|---|---|
| Sistema não abre / tela branca | Admin técnico (IT/Suporte) |
| Erro na importação do Kobo | Admin técnico ou quem configurou o token |
| Dados sumiram / parecem errados | Admin técnico IMEDIATAMENTE |
| Não consigo fazer login | Admin do sistema (pode resetar senha) |
| Preciso criar usuário novo | Admin do sistema |

---

## 6. Dicas rápidas

- **Não use o botão "Voltar" do navegador** durante importação. Use os botões do sistema.
- **Sempre faça prévia antes de confirmar**. Não pule essa etapa.
- **Se o sistema ficar lento**, avise o admin técnico — pode estar faltando espaço no disco.
- **Não apague nada do computador** onde o sistema roda (pasta `C:\endemias` ou similar).

---

## 7. Lembrete final

> Se você não tem certeza do que está fazendo, **pare e pergunte**. É melhor esperar 10 minutos por ajuda do que corrigir um erro que pode levar horas.

**Boa sorte! O sistema está estável e com backup automático. Siga os passos com calma.**
