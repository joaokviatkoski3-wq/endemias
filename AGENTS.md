# Instrucoes para agentes de IA

Estas instrucoes se aplicam a todo o repositorio.

Antes de iniciar qualquer trabalho, leia `CONTEXTO_PARA_IA.md`. Ele registra o
estado atual do projeto, a migracao gradual para PostgreSQL, os modulos ja
homologados, as pendencias e os cuidados operacionais.

Quando houver colaboracao entre Codex e Claude Code, leia tambem
`docs/GUIA_TRABALHO_MULTIAGENTE.md` e respeite a separacao entre implementacao,
revisao e integracao na `master`.

Claude Code atua somente como revisor por padrao. O usuario pode, como excecao,
pedir diretamente que ele implemente ou corrija codigo em uma branch definida.
Essa autorizacao excepcional deve seguir os limites de escopo, revisao
independente e integracao descritos em `docs/GUIA_TRABALHO_MULTIAGENTE.md`.

## Versionamento do sistema

Agentes de IA tem autonomia para atualizar a numeracao da versao do sistema quando julgarem que o conjunto de alteracoes justifica uma nova versao. Nao e necessario solicitar confirmacao previa exclusivamente para essa atualizacao.

Use versionamento semantico como orientacao:

- incremente o patch (`1.9.0` para `1.9.1`) para correcoes e ajustes compativeis;
- incremente o minor (`1.9.x` para `1.10.0`) para novas funcionalidades compativeis;
- incremente o major (`1.x.x` para `2.0.0`) somente para mudancas estruturais ou incompatibilidades relevantes.

Nao e necessario alterar a versao a cada pequena edicao isolada. Considere o impacto funcional e agrupe mudancas relacionadas quando fizer sentido.

A fonte oficial da versao e `app_core/version.py`. Ao atualiza-la:

- mantenha `APP_VERSION`, `APP_VERSION_DATE` e `APP_VERSION_LABEL` coerentes;
- atualize referencias documentais que declarem explicitamente a versao atual;
- valide os pontos que exibem a versao, incluindo o sistema, a tela de login e `iniciar.bat`;
- inclua a atualizacao da versao no commit e no push correspondentes.
