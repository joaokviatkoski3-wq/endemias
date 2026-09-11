# Mapas-base e politica de uso

Atualizado em 11/09/2026.

## Estado vigente

O sistema nao acessa diretamente `tile.openstreetmap.org`. Em 11/09/2026, o
servico publico retornou HTTP 403 com aviso de descumprimento da politica de
uso, afetando o mapa territorial e os mapas dos RGs impressos.

As telas usam atualmente:

- mapa de ruas: Esri World Street Map;
- satelite: Esri World Imagery;
- rotulos sobre o satelite: Esri World Boundaries and Places.

A atribuicao das fontes permanece visivel no controle do Leaflet. A impressao
de RG limita a duas as renderizacoes simultaneas, em vez de solicitar todos os
mini-mapas de uma vez.

## Pontos abrangidos

- `templates/mapa.html`;
- `templates/registro_geografico.html`;
- `templates/registro_geografico_impressao.html`.

## Regra operacional

Nao reintroduzir o servidor publico padrao do OpenStreetMap como dependencia
de producao. Ele e um servico comunitario, sem SLA, e pode bloquear usos que
gerem carga excessiva ou nao atendam integralmente a sua politica. O uso de
dados provenientes do OpenStreetMap em atribuicoes de outros provedores nao e
uma requisicao ao servidor bloqueado.

Se o volume ou os requisitos de disponibilidade crescerem, substituir as URLs
fixas por configuracao de um provedor contratado ou por infraestrutura propria,
mantendo atribuicao, limites, cache e licencas exigidos pelo provedor escolhido.
