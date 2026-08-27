# Instrucoes para agentes de IA

Estas instrucoes se aplicam a todo o repositorio.

Antes de iniciar qualquer trabalho, leia `CONTEXTO_PARA_IA.md`. Ele registra o
estado atual do projeto, a migracao gradual para PostgreSQL, os modulos ja
homologados, as pendencias e os cuidados operacionais.

Leia em seguida `docs/ESTADO_ATUAL_PROJETO.md`. Ele e o registro curto e
atualizavel da passagem de contexto entre conversas: define o operador vigente,
a situacao de producao e as proximas prioridades. Os guias
historicos de PostgreSQL continuam sendo referencia tecnica, mas nao devem ser
interpretados como autorizacao para repetir uma etapa ja concluida.

No fluxo vigente, **Codex e o operador unico e principal**: investiga,
implementa, testa, documenta, cria commits, faz push e pode integrar na
`master` as mudancas solicitadas pelo usuario quando as validacoes aplicaveis
passarem. Revisao do Claude nao e etapa obrigatoria nem bloqueio para merge.

Claude pode intervir esporadicamente somente quando o usuario o solicitar. Se
essa intervencao envolver escrita, use branch propria e nunca permita edicao
simultanea dos mesmos arquivos. Leia `docs/GUIA_TRABALHO_MULTIAGENTE.md` para
isolamento e coordenacao, sem interpretar o guia como exigencia de revisao.

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
