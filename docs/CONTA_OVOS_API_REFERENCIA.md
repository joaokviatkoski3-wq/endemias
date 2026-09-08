# API Conta Ovos

Consulte e envie dados de ovitrampas, quarteirões e visitas de campo diretamente do seu sistema. Esta página documenta todos os endpoints públicos e privados disponíveis.

/pt-br/api [Solicitar chave de API](mailto:contaovosdengue@gmail.com?subject=Solicita%C3%A7%C3%A3o%20de%20chave%20de%20API)

## Sobre a API

Esta API possui endpoints **públicos e privados**. A API pública devolve dados de latitude, longitude e quantidade de ovos de cada município participante ao longo do tempo, sem necessidade de autenticação. A API privada é recomendada apenas para aplicativos que trabalham em parceria com o Conta Ovos, pois ela expõe dados sensíveis e permite inserir, alterar e remover registros.

## Autenticação e chaves

Para utilizar a API privada você precisará de uma chave de acesso (`key`). Para adquiri-la, envie um e-mail para **contaovosdengue@gmail.com** informando:

- Por que você precisa de acesso à API;
- Qual o nível de acesso necessário (municipal, regional, estadual ou país);
- De qual região geográfica você faz parte.

A chave é composta por **45 letras aleatórias** e deve ser enviada no parâmetro `key` de cada requisição privada. O escopo geográfico e o plano vinculados à chave (`api_access_municipality_id`, `state_id`, `region_id`, `country_id`, `plan`) definem automaticamente quais registros ela pode ler ou alterar — uma chave municipal, por exemplo, só consegue ler ou modificar dados do próprio município.

**Onde enviar a chave:** a `key` é sempre lida da query string da URL (`?key=SUA_CHAVE`), inclusive nos endpoints POST. Enviá-la apenas no corpo do formulário resulta em `404 "Wrong key"`. Os demais campos do POST continuam indo no corpo da requisição.

**Paginação:** os parâmetros `page` aceitam no máximo 100 nos endpoints que suportam paginação. Valores inválidos ou ausentes assumem a página 1.

## Códigos de resposta

Todos os endpoints seguem o mesmo padrão de status HTTP:

| Código | Significado |
| --- | --- |
| 200 | Requisição processada com sucesso. |
| 400 | Parâmetro obrigatório ausente, em formato inválido, ou corpo da requisição ilegível. |
| 403 | O recurso informado não pertence ao escopo (município/estado/região) da chave utilizada. |
| 404 | Chave inválida ( _Wrong key_) ou recurso não encontrado. |
| 409 | Já existe um registro para essa combinação de identificador, ano e semana. |
| 500 | Erro interno ao processar a requisição. |

## Como enviar o corpo de um POST

Todos os endpoints POST aceitam três formatos, e você escolhe o que for mais fácil no seu sistema:

| Formato | `Content-Type` |
| --- | --- |
| Formulário simples | `application/x-www-form-urlencoded` |
| Formulário multipart | `multipart/form-data` |
| JSON | `application/json` |

**Não defina o cabeçalho Content-Type à mão** no Postman, no Insomnia ou em bibliotecas de HTTP. Deixe a ferramenta gerá-lo: no multipart ela precisa incluir o boundary, e um Content-Type que não corresponde ao corpo faz todos os campos chegarem vazios.

Quando isso acontece a resposta é 400 com esta mensagem, e ela é sobre o envelope, não sobre os seus campos:

Copiar

```
{
  "error": "Não consegui ler os campos do corpo da requisição. Envie como form-data, x-www-form-urlencoded ou JSON.",
  "dica": "Se usa Postman ou Insomnia, apague o cabeçalho Content-Type e deixe a ferramenta gerá-lo sozinha."
}
```

A chave (key) vai sempre na URL, nunca no corpo.

## Endpoints Públicos

GET`/api/lastcountingpublic`Público

### Últimas contagens lançadas

Retorna as últimas contagens lançadas por localização (municipal, estadual ou país), com o número de ovos e os dados da ovitrampa.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |
| `id` | int | Exibe apenas ocorrências a partir do id informado. Exemplo: `id=7876`. |
| `date` | date | Exibe ocorrências a partir da data de inclusão. Exemplo: `date=2025-01-01`. |
| `date_collect` | date | Exibe ocorrências a partir da data de coleta. Exemplo: `date_collect=2024-12-12`. |
| `date_start` | date | Data inicial para filtrar as contagens. Exemplo: `date_start=2025-01-01`. |
| `date_end` | date | Data final para filtrar as contagens. Exemplo: `date_end=2025-12-31`. |

**Obs.:** se nenhum parâmetro de localização for enviado, o endpoint devolve as últimas contagens do Brasil.

**Respostas específicas:**

- `400` — quando alguma das datas enviadas não está no formato `YYYY-MM-DD`. A resposta traz a lista dos campos inválidos em `invalid_fields`.

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Ponta%20Pora" \
  /pt-br/api/lastcountingpublic

curl -G -d "state=MG" \
  /pt-br/api/lastcountingpublic
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "state_name": "Minas Gerais",\
    "state_code": "MG",\
    "municipality": "Ponta Pora",\
    "municipality_code": "5006606",\
    "eggs": 42,\
    "week": 3,\
    "year": 2025,\
    "time": "2025-01-20 14:32:10",\
    "counting_id": 118342,\
    "ovitrap_website_id": 981,\
    "ovitrap_id": "97",\
    "latitude": -7.000000,\
    "longitude": -8.000000,\
    "date": "2025-01-20",\
    "date_collect": "2025-01-27"\
  }\
]
```

GET`/api/getmunicipalityblocksvisitpublic`Público

### Visitas em Quarteirões

Retorna os dados das visitas (ações de tratamento) realizadas em quarteirões — uma linha por visita, não por quarteirão.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Vista%20Alegre" \
  /pt-br/api/getmunicipalityblocksvisitpublic

curl -G -d "state=MS" \
  /pt-br/api/getmunicipalityblocksvisitpublic
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "block_id": 4521,\
    "block_actions_mean": 3.4,\
    "block_coordinates": "[[-7.123, -34.845], [-7.124, -34.846]]",\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS",\
    "action_land_total_total": 21,\
    "action_land_residence_total": 10,\
    "action_land_commercial_total": 5,\
    "action_land_empty_total": 3,\
    "action_land_strategy_total": 1,\
    "action_land_another_total": 2,\
    "action_address_district": "Centro",\
    "action_address_sector": "Setor 04",\
    "action_deposit_a1_quantity": 4,\
    "action_deposit_a2_quantity": 2,\
    "action_deposit_b_quantity": 5,\
    "action_deposit_c_quantity": 1,\
    "action_deposit_d1_quantity": 0,\
    "action_deposit_d2_quantity": 3,\
    "action_deposit_e_quantity": 0,\
    "action_observation": "Foco encontrado em pneus nos fundos do imovel.",\
    "latitude": -7.123456,\
    "longitude": -34.845678\
  }\
]
```

GET`/api/getmunicipalityblockspublic-2`Público

### Quarteirões cadastrados

Retorna os quarteirões (blocks) cadastrados no município — uma linha por quarteirão, com o polígono, os totais de imóveis por tipo e a média de ações.

**Endpoint novo.** Se você procura as visitas realizadas em quarteirões, use `/api/getmunicipalityblocksvisitpublic`. Por ser um endpoint público, a resposta não inclui o agente responsável pelo quarteirão nem identificadores de usuário/equipe.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Alta%20Floresta" \
  /pt-br/api/getmunicipalityblockspublic-2

curl -G -d "state=MT" \
  /pt-br/api/getmunicipalityblockspublic-2
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "block_id": 118342,\
    "block_group_id": "1",\
    "block_datetime": "Mon, 09 Sep 2024 10:12:41 GMT",\
    "latitude": -9.849042,\
    "longitude": -56.065069,\
    "block_coordinates": "[{\"lat\":-9.849042,\"lng\":-56.065069}, ...]",\
    "block_address_district": "DISTRITO INDUSTRIAL",\
    "block_address_sector": "DISTRITO INDUSTRIAL",\
    "block_municipality_id": 5566,\
    "block_active": 1,\
    "block_actions_mean": 22,\
    "block_land_total": 24,\
    "block_land_residence": 18,\
    "block_land_commercial": 4,\
    "block_land_empty": 2,\
    "block_land_strategy": 0,\
    "block_land_another": 0,\
    "municipality": "Alta Floresta",\
    "municipality_code": "5100250",\
    "state_name": "Mato Grosso",\
    "state_code": "MT"\
  }\
]
```

GET`/api/getmunicipalityedlspublic`Público

### EDLs cadastrados

Retorna os dados dos EDLs (pontos estratégicos que recebem manutenção periódica dos agentes) cadastrados por município.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Vista%20Alegre" \
  /pt-br/api/getmunicipalityedlspublic

curl -G -d "state=MS" \
  /pt-br/api/getmunicipalityedlspublic
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "edl_id": 1832,\
    "edl_group_id": "104",\
    "edl_address_datetime": "2025-02-11 09:15:00",\
    "edl_lat": -7.123456,\
    "edl_lng": -34.845678,\
    "edl_municipality_id": 5007117,\
    "group_id": 12,\
    "user_id": 348,\
    "edl_responsable_agent": "João da Silva",\
    "edl_block_group_id": "12",\
    "edl_responsable_home": "Maria Souza",\
    "edl_date": "2025-02-11",\
    "edl_water_mean": 1.8,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

GET`/api/getmunicipalityedlmaintenancepublic`Público

### Manutenções de EDLs

Retorna os dados das manutenções realizadas nos EDLs, incluindo a observação registrada em cada manutenção.

**Substitui**`/api/getmunicipalityedlvisitspublic`. EDLs recebem manutenções, não visitas — os campos passaram de `edl_visit_*` para `edl_maintenance_*`. A URL antiga continua funcionando e continua devolvendo os nomes antigos, para não quebrar integrações em produção, mas está descontinuada.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Vista%20Alegre" \
  /pt-br/api/getmunicipalityedlmaintenancepublic

curl -G -d "state=MS" \
  /pt-br/api/getmunicipalityedlmaintenancepublic
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "edl_maintenance_id": 9021,\
    "edl_id": 1832,\
    "edl_maintenance_time_week": 7,\
    "edl_maintenance_time_year": 2025,\
    "edl_maintenance_datetime": "2025-02-11 09:20:00",\
    "edl_maintenance_user_id": 348,\
    "edl_maintenance_observation": "Sem foco encontrado no local.",\
    "edl_maintenance_observation_id": 3,\
    "edl_maintenance_water_level": 0.5,\
    "edl_maintenance_lat": -7.123456,\
    "edl_maintenance_lng": -34.845678,\
    "edl_maintenance_municipality_id": 5007117,\
    "edl_maintenance_region_id": 4,\
    "edl_maintenance_state_id": 24,\
    "edl_maintenance_country_id": 1,\
    "edl_maintenance_date": "2025-02-11",\
    "edl_maintenance_observation_name": "Sem foco",\
    "edl_maintenance_observation_number": 3,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

GET`/api/getmunicipalityovitrapspublic`Público

### Ovitrampas cadastradas

Retorna os dados das ovitrampas (pontos de monitoramento de ovos) cadastradas por município.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Vista%20Alegre" \
  /pt-br/api/getmunicipalityovitrapspublic

curl -G -d "state=MS" \
  /pt-br/api/getmunicipalityovitrapspublic
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "ovitrap_id": 4471,\
    "ovitrap_group_id": "97",\
    "ovitrap_datetime": "2025-01-20 14:32:10",\
    "ovitrap_lat": -7.123456,\
    "ovitrap_lng": -34.845678,\
    "ovitrap_lat_lng_error": 0,\
    "ovitrap_municipality_id": 5007117,\
    "group_id": 12,\
    "user_id": 348,\
    "ovitrap_eggs_mean": 12.5,\
    "ovitrap_block_id": 4521,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

GET`/api/getmunicipalityplacespublic`Público

### Imóveis (places)

Retorna os imóveis (pontos estratégicos e imóveis especiais) cadastrados por município.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `state` | string | Código do estado. Exemplo: `state=RJ`. |
| `municipality` | string | Nome do município. Exemplo: `municipality=Ponta Pora` |
| `country` | string | Nome do país. Exemplo: `country=Brasil`. Se omitido, assume "Brasil". |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "municipality=Vista%20Alegre" \
  /pt-br/api/getmunicipalityplacespublic

curl -G -d "state=MS" \
  /pt-br/api/getmunicipalityplacespublic
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "place_id": 771,\
    "user_id": 348,\
    "place_address_district": "Centro",\
    "place_address_sector": "Setor 04",\
    "place_datetime": "2025-02-05 10:00:00",\
    "place_address_lat": -7.123456,\
    "place_address_lng": -34.845678,\
    "place_municipality_id": 5007117,\
    "place_region_id": 4,\
    "place_state_id": 24,\
    "place_country_id": 1,\
    "place_type_id": 2,\
    "place_name": "Ferro-velho Bom Preço",\
    "place_coordinates": "[[-7.123, -34.845], [-7.124, -34.846]]",\
    "place_subtype": 5,\
    "place_area": 320.5,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

## Endpoints Privados

Todos os endpoints abaixo exigem o parâmetro `key` com a sua chave de API.

GET`/api/lastcounting`Privado

### Últimas contagens lançadas

Retorna as últimas contagens lançadas dentro do escopo da chave, com número de ovos, dados da ovitrampa e o usuário responsável.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo das contagens retornadas. |
| `page` | int | Página de paginação (padrão 1, máximo 100). |
| `date_start` | date | Data inicial para filtrar as contagens. Exemplo: `date_start=2025-01-01`. |
| `date_end` | date | Data final para filtrar as contagens. Exemplo: `date_end=2025-12-31`. |

**Respostas específicas:**

- `400` — quando alguma das datas enviadas não está no formato `YYYY-MM-DD`. A resposta traz a lista dos campos inválidos em `invalid_fields`.

#### Exemplo de requisição

Copiar

```
curl -G -d "key=KEY&page=1" \
  /pt-br/api/lastcounting
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "state_name": "Minas Gerais",\
    "state_code": "MG",\
    "municipality": "Ponta Pora",\
    "municipality_code": "5006606",\
    "eggs": 42,\
    "week": 3,\
    "year": 2025,\
    "time": "2025-01-20 14:32:10",\
    "user": "Joao da Silva",\
    "counting_id": 118342,\
    "ovitrap_website_id": 981,\
    "ovitrap_id": "97",\
    "district": "Centro",\
    "street": "Rua das Flores",\
    "number": "123",\
    "complement": "",\
    "loc_inst": "",\
    "sector": "Setor 04",\
    "latitude": -7.000000,\
    "longitude": -8.000000,\
    "date": "2025-01-20",\
    "date_collect": "2025-01-27"\
  }\
]
```

GET`/api/getmunicipalityedls`Privado

### EDLs cadastrados

Retorna os dados dos EDLs (pontos estratégicos visitados periodicamente pelos agentes) dentro do escopo geográfico da chave. O escopo é definido automaticamente pelo plano vinculado à chave — municipal, regional, estadual ou país — não sendo necessário informar município, estado ou país na requisição.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo geográfico dos EDLs retornados. |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "key=KEY&page=1" \
  /pt-br/api/getmunicipalityedls
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "edl_id": 1832,\
    "edl_group_id": "104",\
    "edl_address_datetime": "2025-02-11 09:15:00",\
    "edl_lat": -7.123456,\
    "edl_lng": -34.845678,\
    "edl_municipality_id": 5007117,\
    "group_id": 12,\
    "user_id": 348,\
    "edl_responsable_agent": "João da Silva",\
    "edl_block_group_id": "12",\
    "edl_responsable_home": "Maria Souza",\
    "edl_date": "2025-02-11",\
    "edl_water_mean": 1.8,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

GET`/api/getmunicipalityedlvisits`Privado

### Manutenções de EDLs

Atenção: os campos da resposta deste endpoint privado continuam com o prefixo `edl_visit_*`. Apenas o endpoint público equivalente passou a usar `edl_maintenance_*`.

Retorna os dados das visitas realizadas aos EDLs dentro do escopo geográfico da chave, incluindo a observação registrada em cada visita. O escopo é definido automaticamente pelo plano vinculado à chave — municipal, regional, estadual ou país — não sendo necessário informar município, estado ou país na requisição.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo geográfico das visitas retornadas. |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "key=KEY&page=1" \
  /pt-br/api/getmunicipalityedlvisits
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "edl_visit_id": 9021,\
    "edl_id": 1832,\
    "edl_visit_time_week": 7,\
    "edl_visit_time_year": 2025,\
    "edl_visit_datetime": "2025-02-11 09:20:00",\
    "edl_visit_user_id": 348,\
    "edl_visit_observation": "Sem foco encontrado no local.",\
    "edl_visit_observation_id": 3,\
    "edl_visit_water_level": 0.5,\
    "edl_visit_lat": -7.123456,\
    "edl_visit_lng": -34.845678,\
    "edl_visit_municipality_id": 5007117,\
    "edl_visit_region_id": 4,\
    "edl_visit_state_id": 24,\
    "edl_visit_country_id": 1,\
    "edl_visit_date": "2025-02-11",\
    "edl_visit_observation_name": "Sem foco",\
    "edl_visit_observation_number": 3,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

GET`/api/getmunicipalityblocks`Privado

### Visitas em quarteirões

Retorna os dados das ações (visitas de tratamento) realizadas em quarteirões dentro do escopo geográfico da chave. O escopo é definido automaticamente pelo plano vinculado à chave — municipal, regional, estadual ou país — não sendo necessário informar município, estado ou país na requisição.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo geográfico das ações retornadas. |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "key=KEY&page=1" \
  /pt-br/api/getmunicipalityblocks
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "block_id": 4521,\
    "block_actions_mean": 3.4,\
    "block_coordinates": "[[-7.123, -34.845], [-7.124, -34.846]]",\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS",\
    "action_land_total_total": 21,\
    "action_land_residence_total": 10,\
    "action_land_commercial_total": 5,\
    "action_land_empty_total": 3,\
    "action_land_strategy_total": 1,\
    "action_land_another_total": 2,\
    "action_address_district": "Centro",\
    "action_address_sector": "Setor 04",\
    "action_deposit_a1_quantity": 4,\
    "action_deposit_a2_quantity": 2,\
    "action_deposit_b_quantity": 5,\
    "action_deposit_c_quantity": 1,\
    "action_deposit_d1_quantity": 0,\
    "action_deposit_d2_quantity": 3,\
    "action_deposit_e_quantity": 0,\
    "action_observation": "Foco encontrado em pneus nos fundos do imovel.",\
    "latitude": -7.123456,\
    "longitude": -34.845678\
  }\
]
```

GET`/api/getmunicipalityovitraps`Privado

### Ovitrampas cadastradas

Retorna os dados das ovitrampas (pontos de monitoramento de ovos) dentro do escopo geográfico da chave. O escopo é definido automaticamente pelo plano vinculado à chave — municipal, regional, estadual ou país — não sendo necessário informar município, estado ou país na requisição.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo geográfico das ovitrampas retornadas. |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "key=KEY&page=1" \
  /pt-br/api/getmunicipalityovitraps
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "ovitrap_id": 4471,\
    "ovitrap_group_id": "97",\
    "ovitrap_datetime": "2025-01-20 14:32:10",\
    "ovitrap_lat": -7.123456,\
    "ovitrap_lng": -34.845678,\
    "ovitrap_lat_lng_error": 0,\
    "ovitrap_municipality_id": 5007117,\
    "group_id": 12,\
    "user_id": 348,\
    "ovitrap_eggs_mean": 12.5,\
    "ovitrap_block_id": 4521,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

GET`/api/getmunicipalityplaces`Privado

### Imóveis (places)

Retorna os imóveis (pontos estratégicos e imóveis especiais) dentro do escopo geográfico da chave. O escopo é definido automaticamente pelo plano vinculado à chave — municipal, regional, estadual ou país — não sendo necessário informar município, estado ou país na requisição.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo geográfico dos pontos retornados. |
| `page` | int | Página de paginação (padrão 1, máximo 100). |

#### Exemplo de requisição

Copiar

```
curl -G -d "key=KEY&page=1" \
  /pt-br/api/getmunicipalityplaces
```

#### Exemplo de resposta

Copiar

```
[\
  {\
    "place_id": 771,\
    "user_id": 348,\
    "place_address_district": "Centro",\
    "place_address_sector": "Setor 04",\
    "place_datetime": "2025-02-05 10:00:00",\
    "place_address_lat": -7.123456,\
    "place_address_lng": -34.845678,\
    "place_municipality_id": 5007117,\
    "place_region_id": 4,\
    "place_state_id": 24,\
    "place_country_id": 1,\
    "place_type_id": 2,\
    "place_name": "Ferro-velho Bom Preço",\
    "place_coordinates": "[[-7.123, -34.845], [-7.124, -34.846]]",\
    "place_subtype": 5,\
    "place_area": 320.5,\
    "municipality": "Vista Alegre",\
    "municipality_code": "5007117",\
    "state_name": "Mato Grosso do Sul",\
    "state_code": "MS"\
  }\
]
```

POST`/api/postcounting`Privado

### Envio de leitura

Envia a leitura de uma ovitrampa. É possível enviar dados para uma ovitrampa já existente ou enviar os dados e instalar uma nova ovitrampa ao mesmo tempo.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo do envio. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postcounting?key=KEY"
```

O corpo pode ir como `form-data`, `x-www-form-urlencoded` ou `JSON` — veja [Como enviar o corpo de um POST](https://contaovos.com/pt-br/api/#body-format).

Para o envio padrão, onde não é preciso instalar uma nova ovitrampa, envie os seguintes campos ( **todos obrigatórios**) no corpo da requisição (`form`):

Copiar

```
{
  "ovitrap_group_id": 97,
  "ovitrap_lat": -7.000000,
  "ovitrap_lng": -8.000000,
  "date": "2025-01-20",
  "counting_observation_id": 1,
  "counting_observation": "caso o counting_observation_id seja 9",
  "counting_eggs": 5
}
```

Tabela com os IDs de cada tipo de observação (`counting_observation_id`):

| ID | Significado |
| --- | --- |
| 1 | Sem observações |
| 2 | Intervalo entre instalação e coleta maior que o previsto |
| 3 | Ovitrampa ou paleta desaparecida |
| 4 | Ovitrampa ou paleta quebrada |
| 5 | Ovitrampa ou paleta removida |
| 6 | Ovitrampa seca |
| 7 | Casa fechada |
| 8 | Ovitrampa cheia de água |
| 9 | Ovitrampa com pouca água |
| 10 | Outra observação |

Para instalar uma nova ovitrampa junto do envio, são **obrigatórios** os campos: `ovitrap_lat`, `ovitrap_lng`, `ovitrap_group_id`

Copiar

```
{
  "ovitrap_group_id": 96,
  "ovitrap_address_district": "Distrito",
  "ovitrap_address_street": "Rua",
  "ovitrap_address_number": "Numero",
  "ovitrap_address_complement": "Complemento",
  "ovitrap_address_loc_inst": "",
  "ovitrap_lat": -7.000000,
  "ovitrap_lng": -8.000000,
  "ovitrap_address_sector": "Setor",
  "ovitrap_responsable": "Responsavel",
  "ovitrap_block_id": "Quarteirao",
  "ovitrap_type_id": 1,
  "date": "2025-01-20",
  "counting_date_collect": "2025-01-27",
  "counting_observation_id": 1,
  "counting_observation": "caso o counting_observation_id seja 9",
  "counting_eggs": 5
}
```

Tabela com os IDs de cada tipo de ovitrampa (`ovitrap_type_id`): envie 1 para ovitrampa urbana e 2 para ovitrampa rural. O campo é opcional e, quando não enviado, a ovitrampa é instalada como urbana:

| ID | Significado |
| --- | --- |
| 1 | Ovitrampa urbana (padrão) |
| 2 | Ovitrampa rural |

**Respostas específicas:**

- `400` — quando algum dos campos obrigatórios não é enviado: `ovitrap_lat`, `ovitrap_lng`, `ovitrap_group_id`, `date`
- `400` — quando a coordenada está fora da faixa geográfica: `ovitrap_lat` precisa estar entre -90 e 90, e `ovitrap_lng` entre -180 e 180. O erro mais comum é o ponto decimal se perder na formatação do número — enviar `-23374059` no lugar de `-23.374059`. A resposta traz os valores recebidos em `ovitrap_lat` e `ovitrap_lng`.
- `400` — quando o `ovitrap_type_id` enviado não é 1 nem 2.
- `400` — quando alguma das datas enviadas não está no formato `YYYY-MM-DD`. A resposta traz a lista dos campos inválidos em `invalid_fields`.
- `404` — já existe uma contagem para essa ovitrampa, ano e semana.

POST`/api/postdeletecounting`Privado

### Deletar leitura

Remove a leitura de uma ovitrampa.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. Define o escopo da remoção. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeletecounting?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "ovitrap_group_id": 97,
  "date": "2025-01-20"
}
```

**Respostas específicas:**

- `400` — quando `date` não é enviado.
- `400` — quando alguma das datas enviadas não está no formato `YYYY-MM-DD`. A resposta traz a lista dos campos inválidos em `invalid_fields`.

POST`/api/postdeleteovitrap`Privado

### Deletar ovitrampa

Remove uma ovitrampa.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeleteovitrap?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "ovitrap_group_id": 97
}
```

POST`/api/postaction`Privado

### Inserir visita

Registra uma visita/ação em um quarteirão. Para adicionar a visita a um quarteirão já existente, envie o campo `block_id`. Caso ele não exista, use `block_group_id` — o sistema criará o quarteirão automaticamente. Este endpoint só permite a inserção de quarteirões que estejam dentro do município do solicitante.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postaction?key=KEY"
```

Dados enviados em `form-data`, `x-www-form-urlencoded`, `JSON` ou query parameters, usando `block_id`:

Copiar

```
{
  "block_id": 97,
  "date": "2025-01-20",
  "block_land_residence": 10,
  "action_land_residence_out": 2,
  "action_land_residence_breedings": 1,
  "action_land_residence_treated": 1,

  "block_land_commercial": 5,
  "action_land_commercial_out": 0,
  "action_land_commercial_breedings": 0,
  "action_land_commercial_treated": 0,

  "block_land_empty": 3,
  "action_land_empty_out": 1,
  "action_land_empty_breedings": 2,
  "action_land_empty_treated": 1,

  "block_land_strategy": 1,
  "action_land_strategy_out": 0,
  "action_land_strategy_breedings": 0,
  "action_land_strategy_treated": 0,

  "block_land_special": 0,
  "action_land_special_out": 0,
  "action_land_special_breedings": 0,
  "action_land_special_treated": 0,

  "block_land_another": 2,
  "action_land_another_out": 0,
  "action_land_another_breedings": 0,
  "action_land_another_treated": 0,

  "action_deposit_a1_quantity": 4,
  "action_deposit_a1_eliminated": 2,
  "action_deposit_a1_treated": 1,
  "action_deposit_a1_larvicid": 10,

  "action_deposit_a2_quantity": 2,
  "action_deposit_a2_eliminated": 1,
  "action_deposit_a2_treated": 0,
  "action_deposit_a2_larvicid": 0,

  "action_deposit_b_quantity": 5,
  "action_deposit_b_eliminated": 5,
  "action_deposit_b_treated": 0,
  "action_deposit_b_larvicid": 0,

  "action_deposit_c_quantity": 1,
  "action_deposit_c_eliminated": 0,
  "action_deposit_c_treated": 1,
  "action_deposit_c_larvicid": 5,

  "action_deposit_d1_quantity": 0,
  "action_deposit_d1_eliminated": 0,
  "action_deposit_d1_treated": 0,
  "action_deposit_d1_larvicid": 0,

  "action_deposit_d2_quantity": 3,
  "action_deposit_d2_eliminated": 1,
  "action_deposit_d2_treated": 2,
  "action_deposit_d2_larvicid": 15,

  "action_deposit_e_quantity": 0,
  "action_deposit_e_eliminated": 0,
  "action_deposit_e_treated": 0,
  "action_deposit_e_larvicid": 0,

  "action_observation": "Visita realizada conforme cronograma. Foco encontrado em pneus nos fundos do imovel."
}
```

Optando por `block_group_id` (quarteirão ainda não cadastrado), envie também os dados do próprio quarteirão:

Copiar

```
{
  "block_group_id": 97,
  "date": "2025-01-20",
  "block_address_district": "Centro Historico",
  "block_address_sector": "Setor 04 - Norte",
  "block_coordinates": "[[-7.123, -34.845], [-7.124, -34.846]]",
  "block_lat": -7.123456,
  "block_lng": -34.845678,
  "block_responsable": "Joao da Silva",

  "block_land_residence": 10,
  "action_land_residence_out": 2,
  "action_land_residence_breedings": 1,
  "action_land_residence_treated": 1,

  "block_land_commercial": 5,
  "action_land_commercial_out": 0,
  "action_land_commercial_breedings": 0,
  "action_land_commercial_treated": 0,

  "block_land_empty": 3,
  "action_land_empty_out": 1,
  "action_land_empty_breedings": 2,
  "action_land_empty_treated": 1,

  "block_land_strategy": 1,
  "action_land_strategy_out": 0,
  "action_land_strategy_breedings": 0,
  "action_land_strategy_treated": 0,

  "block_land_special": 0,
  "action_land_special_out": 0,
  "action_land_special_breedings": 0,
  "action_land_special_treated": 0,

  "block_land_another": 2,
  "action_land_another_out": 0,
  "action_land_another_breedings": 0,
  "action_land_another_treated": 0,

  "action_deposit_a1_quantity": 4,
  "action_deposit_a1_eliminated": 2,
  "action_deposit_a1_treated": 1,
  "action_deposit_a1_larvicid": 10,

  "action_deposit_a2_quantity": 2,
  "action_deposit_a2_eliminated": 1,
  "action_deposit_a2_treated": 0,
  "action_deposit_a2_larvicid": 0,

  "action_deposit_b_quantity": 5,
  "action_deposit_b_eliminated": 5,
  "action_deposit_b_treated": 0,
  "action_deposit_b_larvicid": 0,

  "action_deposit_c_quantity": 1,
  "action_deposit_c_eliminated": 0,
  "action_deposit_c_treated": 1,
  "action_deposit_c_larvicid": 5,

  "action_deposit_d1_quantity": 0,
  "action_deposit_d1_eliminated": 0,
  "action_deposit_d1_treated": 0,
  "action_deposit_d1_larvicid": 0,

  "action_deposit_d2_quantity": 3,
  "action_deposit_d2_eliminated": 1,
  "action_deposit_d2_treated": 2,
  "action_deposit_d2_larvicid": 15,

  "action_deposit_e_quantity": 0,
  "action_deposit_e_eliminated": 0,
  "action_deposit_e_treated": 0,
  "action_deposit_e_larvicid": 0,

  "action_observation": "Area com alta densidade de recipientes descartaveis."
}
```

**Respostas específicas:**

- `400` — quando `date` não é enviado ou quando um dos campos numéricos não é um número válido.
- `400` — quando alguma das datas enviadas não está no formato `YYYY-MM-DD`. A resposta traz a lista dos campos inválidos em `invalid_fields`.
- `400` — quando `block_group_id` não é enviado ao criar um novo quarteirão.
- `400` — quando a coordenada está fora da faixa geográfica: `block_lat` precisa estar entre -90 e 90, e `block_lng` entre -180 e 180. O erro mais comum é o ponto decimal se perder na formatação do número — enviar `-23374059` no lugar de `-23.374059`.
- `400` — quando `block_coordinates` passa de 2000 caracteres. Antes o desenho era gravado pela metade, em silêncio, e o quarteirão abria sem mapa; agora a requisição é recusada e a resposta traz o tamanho enviado em `block_coordinates_length`.
- `403` — quando o `block_id` informado não pertence ao município da chave.
- `409` — quando já existe uma visita para esse quarteirão, ano e semana.

POST`/api/postdeleteaction`Privado

### Deletar visita

Remove uma visita de um quarteirão.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeleteaction?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "block_group_id": 97,
  "date": "2025-01-20"
}
```

**Respostas específicas:**

- `400` — quando `date` não é enviado.
- `400` — quando alguma das datas enviadas não está no formato `YYYY-MM-DD`. A resposta traz a lista dos campos inválidos em `invalid_fields`.

POST`/api/postdeleteblock`Privado

### Deletar quarteirão

Remove um quarteirão.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeleteblock?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "block_group_id": 97
}
```

POST`/api/postedl`Privado

### Inserir EDL

Cadastra um EDL (ponto estratégico de vigilância) no município da sua chave. Reenviar o mesmo edl\_group\_id devolve o EDL já existente em vez de duplicar, então é seguro repetir um lote.

O município é sempre o da sua chave — não é possível enviá-lo no corpo.

Obrigatórios: edl\_group\_id, edl\_date (AAAA-MM-DD), edl\_lat e edl\_lng. Os demais campos são opcionais. Devolve o edl\_id.

Se você usa Postman ou Insomnia, não defina o cabeçalho Content-Type à mão: a ferramenta precisa gerá-lo sozinha. Um Content-Type que não corresponde ao corpo faz os campos chegarem vazios.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postedl?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "edl_group_id": "EDL-014",
  "edl_date": "2026-09-01",
  "edl_lat": -23.5505,
  "edl_lng": -46.6333,
  "edl_address_district": "Centro",
  "edl_address_street": "Rua das Palmeiras",
  "edl_address_number": "128",
  "edl_address_complement": "Fundos",
  "edl_address_loc_inst": "Borracharia do Zé",
  "edl_address_sector": "03",
  "edl_responsable_agent": "M. Souza",
  "edl_responsable_home": "J. Pereira",
  "edl_block_group_id": "Q-22"
}
```

POST`/api/postdeleteedl`Privado

### Deletar EDL

Remove um EDL do município da sua chave, pelo mesmo código que você usou para cadastrá-lo.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeleteedl?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "edl_group_id": "EDL-014"
}
```

POST`/api/postedlmaintenance`Privado

### Inserir manutenção de EDL

Registra uma manutenção em um EDL. Um EDL aceita no máximo uma manutenção por data.

O município é sempre o da sua chave — não é possível enviá-lo no corpo.

Obrigatórios: edl\_group\_id e date (AAAA-MM-DD). A data não pode cair em semana epidemiológica futura. Repetir a mesma EDL e data devolve 409.

Os nomes antigos edl\_visit\_observation, edl\_visit\_observation\_id e edl\_visit\_water\_level continuam aceitos.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postedlmaintenance?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "edl_group_id": "EDL-014",
  "date": "2026-09-01",
  "edl_maintenance_observation": "Sem larvas, recipiente lavado",
  "edl_maintenance_observation_id": 1,
  "edl_maintenance_water_level": 2
}
```

POST`/api/postdeleteedlmaintenance`Privado

### Deletar manutenção de EDL

Remove uma manutenção. Ela é identificada pelo EDL mais a data, que juntos são únicos — você não precisa guardar nenhum id interno.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeleteedlmaintenance?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "edl_group_id": "EDL-014",
  "date": "2026-09-01"
}
```

POST`/api/postplace`Privado

### Inserir imóvel

Cadastra um imóvel (Ponto Estratégico ou Imóvel Especial) no município da sua chave.

O município é sempre o da sua chave — não é possível enviá-lo no corpo.

Região, estado e país saem do município da chave e não são aceitos no corpo: as quatro chaves geográficas precisam concordar entre si.

Obrigatórios: place\_name, place\_type\_id, place\_subtype, place\_lat e place\_lng. Devolve o place\_id.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postplace?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "place_name": "Ferro-velho São Jorge",
  "place_type_id": 1,
  "place_subtype": 3,
  "place_lat": -23.5505,
  "place_lng": -46.6333,
  "place_address_district": "Vila Nova",
  "place_address_sector": "07",
  "place_area": 350
}
```

POST`/api/postdeleteplace`Privado

### Deletar imóvel

Remove um imóvel do município da sua chave.

Este é o único endpoint que pede um id interno: a tabela de imóveis não tem um código definido por você, ao contrário de ovitrampa, quarteirão e EDL. O place\_id vem de /api/getmunicipalityplaces.

#### Parâmetros

| Nome | Tipo | Descrição |
| --- | --- | --- |
| `key` | string | Sua chave de API. |

#### Exemplo de requisição

Copiar

```
curl -X POST \
  "/pt-br/api/postdeleteplace?key=KEY"
```

Dados necessários no corpo da requisição (`form-data`, `x-www-form-urlencoded` ou `JSON`):

Copiar

```
{
  "place_id": 142
}
```

