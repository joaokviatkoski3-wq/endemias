# Revisão funcional 2.0.0 — registro de continuidade

Em 05/11/2026, após aprovação visual do usuário e promoção para **2.0.0**, foi
realizada revisão ampla dos sistemas Endemias/Ambiental e de suas integrações.

O diagnóstico técnico completo está **somente no computador do operador**,
pois o repositório é público e há itens ainda pendentes de tratamento:

- Área de Trabalho: `VSATT - Auditoria funcional 2.0.0.md`.
- Cópia de trabalho e evidências: `C:\endemias-interface\.venv\auditoria-geral`
  e `.venv\auditoria-campo`, `.venv\auditoria-entomologia`,
  `.venv\auditoria-ambiental`.
- Não incluir esses relatórios, provas, bancos ou estruturas privadas em commits.

## Cobertura registrada

- Código dos módulos, importadores, consultas, edição, exportações e ligações.
- Dez estruturas de formulários **implantados** do Kobo consultadas, sem ler
  respostas, tokens no relatório ou listas nominais.
- Inventário de301 rotas únicas,44 combinações de página/setor,148 GETs deAPI e
  73 navegações por perfil em probe fictício. Estes números não equivalem a
  executar todos os métodos e combinações de cada rota.
- Chromium Endemias/comuns:27 páginas distintas,81 navegações,33 subabas e
  filtros/controles dirigidos. Ambiental/comuns:18 páginas e oito subabas.
- Suíte de preparação da promoção:1.030 testes OK, seis ignorados.
- Diagnóstico agrupado por causa/impacto, com reprodução, referências,
  prioridades, decisões de negócio e limites. As correções não fazem parte
  desta etapa; devem ser preparadas em mudanças próprias após ler o relatório.

## Segurança operacional da revisão

Ensaios usaram dados exclusivamente fictícios e caminhos isolados. Não houve
reimportação, alteração de formulários/respostas Kobo, reconciliação em massa,
restauração de produção ou mudanças de contas/configuração durante a auditoria.
A intervenção autorizada foi a promoção da versão, com backups prévios e
prova da mesma identidade limitada. O SQLite congelado manteve o hash anterior.

Nenhum envio remoto ao Conta Ovos foi feito. Operação de campo real, ensaio
físico offline em aparelhos, concorrência e restauração completa continuam
dependendo de homologação própria. Testes passarem não substitui o diagnóstico.

Antes de iniciar o próximo pacote, o operador deve abrir o relatório local,
preservar sua ordem de prioridade e validar os critérios de cada correção.
