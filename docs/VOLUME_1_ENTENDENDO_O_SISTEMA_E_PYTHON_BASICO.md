# Volume 1 - Entendendo o Sistema Endemias e Python Basico

Material de estudo baseado no Sistema Endemias de Almirante Tamandare-PR.

Este volume foi pensado para quem esta comecando em programacao e quer aprender usando um sistema real, feito em Python, Flask, SQLite, HTML, CSS e JavaScript.

Voce nao precisa decorar tudo. A ideia e aprender a ler o sistema, reconhecer padroes e fazer pequenas mudancas com seguranca.

---

## Sumario

1. Primeiro mapa mental do sistema
2. O que e Python neste sistema
3. Imports: trazendo ferramentas para o arquivo
4. Variaveis
5. Tipos basicos de dados
6. Listas
7. Dicionarios
8. Funcoes
9. Condicionais
10. Repeticoes
11. Tratamento de erros
12. Modulos e organizacao
13. Flask: paginas e APIs
14. Banco de dados com SQLite
15. Criacao do banco
16. Datas no sistema
17. Classes e dataclasses
18. Decorators
19. Caminhos e arquivos
20. Configuracao por variaveis de ambiente
21. Autenticacao e permissoes
22. Templates
23. JavaScript no sistema
24. ETL: processamento de planilhas
25. Testes automatizados
26. Git e seguranca do codigo
27. Como estudar o sistema sem medo
28. Mini glossario
29. Exercicios guiados
30. Roteiro de 7 dias
31. O que voce deve conseguir fazer
32. Proximo volume sugerido

### Para imprimir

Este arquivo esta em Markdown, um formato de texto simples. Voce pode estudar direto por ele, abrir em editores como VS Code ou converter depois para PDF/HTML sem perder a estrutura de capitulos.

---

## Como usar este material

Leia na ordem. Depois de cada capitulo, abra os arquivos citados no seu projeto e tente encontrar os trechos parecidos.

Quando aparecer um exercicio, faca primeiro em pensamento. Depois, se quiser praticar de verdade, crie arquivos de teste ou peca ajuda antes de alterar o sistema principal.

Este volume nao e uma apostila generica de Python. Ele usa o seu sistema como mapa.

### O que voce vai aprender neste volume

- O que e Python e por que ele aparece em tantos arquivos do sistema.
- Como o projeto esta organizado.
- O que sao variaveis, funcoes, listas, dicionarios e modulos.
- Como ler trechos simples de codigo Python.
- Como o Flask liga uma URL a uma funcao Python.
- Como o Python conversa com o banco SQLite.
- Como pensar antes de alterar um sistema real.

### O que fica para volumes futuros

- HTML, CSS e JavaScript em mais profundidade.
- Flask com formularios, APIs e templates.
- SQL mais completo.
- Processamento de planilhas Kobo com Pandas e OpenPyXL.
- Mapas, GeoJSON e Leaflet.
- Testes automatizados.
- Git, commits, branches e GitHub em mais profundidade.
- Como criar novas funcionalidades.

---

## 1. Primeiro mapa mental do sistema

Seu sistema e uma aplicacao web local. Isso significa:

1. Um servidor Python roda no computador.
2. O navegador abre paginas do sistema.
3. O usuario clica, filtra, cadastra, imprime, importa planilhas.
4. O Python recebe essas acoes.
5. O Python consulta ou altera o banco `endemias.db`.
6. O Python devolve HTML, JSON, arquivos ou relatorios.

Uma forma simples de enxergar:

```text
Navegador
   |
   | acessa /registro-geografico ou /api/registro-geografico
   v
Flask em app.py
   |
   | encaminha para um blueprint
   v
blueprints/registro_geografico.py
   |
   | chama regras do sistema
   v
app_core/registro_geografico.py
   |
   | consulta/atualiza
   v
endemias.db
```

O importante aqui e perceber que cada parte tem uma responsabilidade.

### Principais pastas do projeto

No seu projeto, as pastas mais importantes sao:

```text
C:\endemias
  app.py
  criar_banco.py
  etl.py
  config.json
  requirements.txt
  app_core\
  blueprints\
  templates\
  static\
  tests\
  docs\
  scripts\
```

### `app.py`

E a porta de entrada do sistema.

Ele:

- cria o aplicativo Flask;
- configura caminhos de banco, anexos, logs e chaves;
- registra os blueprints;
- ativa protecoes de seguranca;
- inicia o servidor quando voce roda o sistema.

Trecho real simplificado:

```python
def create_app(config_overrides=None):
    flask_app = Flask(__name__, instance_path=INSTANCE_DIR)
    flask_app.config.update(
        DB_PATH=DB_PATH,
        CONFIG_PATH=CONFIG_PATH,
        UPLOAD_TEMP=UPLOAD_TEMP,
    )
    _register_blueprints(flask_app)
    return flask_app
```

Leia assim:

- `def create_app(...)`: define uma funcao.
- `Flask(__name__)`: cria a aplicacao web.
- `config.update(...)`: grava configuracoes.
- `_register_blueprints(...)`: registra as partes do sistema.
- `return flask_app`: devolve o aplicativo pronto.

### `blueprints/`

Cada arquivo em `blueprints/` controla uma area do sistema.

Exemplos:

```text
blueprints/admin.py
blueprints/esporotricose.py
blueprints/registro_geografico.py
blueprints/processar.py
blueprints/mapa.py
```

Um blueprint e como um "departamento" do site.

O arquivo `blueprints/registro_geografico.py`, por exemplo, define rotas como:

```python
@bp.route("/registro-geografico")
@login_required
def page():
    opcoes = rg_core.opcoes(_db_path(), _base_dir())
    return render_template("registro_geografico.html", opcoes=opcoes)
```

Isso significa:

- Quando o navegador abre `/registro-geografico`,
- o Flask chama a funcao `page`,
- a funcao busca opcoes no nucleo `rg_core`,
- e renderiza o HTML `registro_geografico.html`.

### `app_core/`

Aqui ficam as regras principais do sistema.

Exemplos:

```text
app_core/db.py
app_core/auth.py
app_core/backup.py
app_core/registro_geografico.py
app_core/esporotricose.py
app_core/ovitrampas.py
```

Pense assim:

- `blueprints/`: recebe pedido do navegador.
- `app_core/`: faz o trabalho pesado.

Isso e bom porque separa a interface da logica.

### `templates/`

Aqui ficam as paginas HTML.

Exemplos:

```text
templates/base.html
templates/admin_sistema.html
templates/registro_geografico.html
templates/esporotricose.html
```

Esses arquivos misturam HTML com Jinja, que e a linguagem de templates do Flask.

Exemplo:

```html
{% for module in group["items"] %}
  <a href="{{ module.href }}">{{ module.sidebar_title }}</a>
{% endfor %}
```

Isso quer dizer:

- para cada modulo da lista,
- crie um link no HTML.

### `static/`

Arquivos estaticos sao arquivos que o navegador baixa diretamente:

```text
static/css/app.css
static/js/app.js
static/icons/
static/img/
static/quarteiroes.geojson
```

Nessa pasta ficam:

- CSS;
- JavaScript;
- imagens;
- icones;
- arquivos de mapa.

### `tests/`

Aqui ficam os testes automatizados.

O arquivo principal e:

```text
tests/test_security.py
```

Apesar do nome, ele testa varias partes do sistema: login, rotas, backups, Registro Geografico, Esporotricose, APIs e permissoes.

### `scripts/`

Scripts sao comandos auxiliares.

Exemplos:

```text
scripts/backup_banco.py
scripts/backup_completo.py
scripts/limpeza_diaria.py
```

Eles podem ser executados pelo terminal, sem abrir a interface web.

### `endemias.db`

Esse e o banco de dados SQLite.

Ele guarda dados reais:

- usuarios;
- visitas;
- agentes;
- localidades;
- registro geografico;
- esporotricose;
- ovitrampas;
- auditoria;
- e outras tabelas.

Ele nao deve ir para o GitHub.

---

## 2. O que e Python neste sistema

Python e a linguagem principal usada para:

- iniciar o sistema;
- receber pedidos do navegador;
- validar dados;
- consultar o banco;
- processar planilhas;
- gerar relatorios;
- fazer backups;
- criar testes.

Arquivos Python terminam com `.py`.

Exemplos:

```text
app.py
etl.py
criar_banco.py
app_core/db.py
blueprints/admin.py
```

Um arquivo Python normalmente contem:

- imports;
- constantes;
- funcoes;
- classes;
- comandos.

Exemplo real de `app_core/db.py`:

```python
import sqlite3


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
```

Mesmo que voce ainda nao entenda tudo, ja da para reconhecer:

- `import sqlite3`: importa uma ferramenta do Python.
- `def connect(db_path):`: cria uma funcao.
- `conn = ...`: cria uma variavel.
- `conn.execute(...)`: executa comandos no banco.
- `return conn`: devolve uma conexao pronta.

---

## 3. Imports: trazendo ferramentas para o arquivo

Em Python, `import` significa: "quero usar codigo que esta em outro lugar".

Exemplos reais:

```python
import sqlite3
```

Traz o modulo SQLite da biblioteca padrao do Python.

```python
from datetime import date, datetime, timedelta
```

Traz ferramentas para trabalhar com datas.

```python
from flask import Blueprint, current_app, jsonify, render_template, request
```

Traz ferramentas do Flask.

```python
from app_core import db as db_core
```

Traz o arquivo `app_core/db.py`, mas com o apelido `db_core`.

### Como ler um import

```python
from app_core import registro_geografico as rg_core
```

Leia:

"Do pacote `app_core`, importe o modulo `registro_geografico` e chame ele de `rg_core` dentro deste arquivo."

Depois o codigo pode usar:

```python
rg_core.listar(...)
rg_core.quarteirao(...)
rg_core.salvar_quarteirao(...)
```

### Exercicio

Abra `blueprints/registro_geografico.py` e procure:

```python
from app_core import registro_geografico as rg_core
```

Depois encontre onde aparece:

```python
rg_core.opcoes
rg_core.listar
rg_core.quarteirao
```

A ideia e treinar seu olho para seguir o caminho do codigo.

---

## 4. Variaveis

Variavel e um nome que guarda um valor.

Exemplo simples:

```python
nome = "Joao"
idade = 30
ativo = True
```

No seu sistema:

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

Aqui, `BASE_DIR` guarda o caminho da pasta onde esta o `app.py`.

Outro exemplo:

```python
db_path = Path(current_app.config["DB_PATH"])
```

Aqui:

- `current_app.config["DB_PATH"]` pega o caminho do banco configurado no Flask;
- `Path(...)` transforma esse texto em um objeto de caminho;
- `db_path` guarda esse caminho.

### Variaveis com nomes bons

Seu sistema tem muitos bons exemplos:

```python
backup_dir
backup_completo_dir
localidade
quarteiroes
id_animal_doente
data_notificacao
capsulas_total
```

Nomes assim ajudam a entender o codigo.

### Exercicio

Explique com suas palavras o que cada variavel provavelmente guarda:

```python
usuario = bh.usuario_atual()
is_admin = (usuario or {}).get("nivel") == "admin"
backups = backup_core.listar_backups(...)
```

Resposta esperada:

- `usuario`: dados do usuario logado.
- `is_admin`: verdadeiro se o usuario for administrador.
- `backups`: lista de backups encontrados.

---

## 5. Tipos basicos de dados

Python trabalha com varios tipos de valores. Os principais para comecar sao:

### Texto: `str`

```python
nome = "Sede"
status = "Em tratamento"
```

No sistema:

```python
return f"{date.today().year}-01-01"
```

Esse `f"..."` e uma f-string. Ela permite colocar valores dentro do texto.

Exemplo:

```python
ano = 2026
texto = f"{ano}-01-01"
```

Resultado:

```text
2026-01-01
```

### Numeros: `int` e `float`

```python
idade = 30       # int
media = 2.93     # float
```

No sistema:

```python
MEDIA_PESSOAS_POR_RESIDENCIA = 2.93
```

Esse valor e usado para estimar populacao no Registro Geografico.

### Booleanos: `True` e `False`

```python
ativo = True
bloqueado = False
```

No sistema:

```python
return bool(senha) and len(senha) >= PASSWORD_MIN_LENGTH
```

Essa funcao verifica se a senha existe e tem tamanho minimo.

### Valor vazio: `None`

`None` significa "sem valor".

Exemplo:

```python
def data_ano():
    return f"{date.today().year}-01-01"
```

Aqui nao tem `None`, mas em muitos pontos o sistema usa:

```python
return None
```

Isso e comum quando uma informacao nao existe ou nao foi encontrada.

---

## 6. Listas

Lista guarda varios valores em ordem.

```python
localidades = ["Sede", "Cachoeira", "Tamboara"]
```

No sistema, listas aparecem o tempo todo.

Exemplo:

```python
return [dict(r) for r in rows]
```

Esse trecho aparece em `app_core/db.py`.

Ele significa:

- para cada linha `r` em `rows`,
- transforme em dicionario com `dict(r)`,
- devolva uma lista com todos esses dicionarios.

### Acessando itens

```python
localidades[0]
```

Pega o primeiro item.

Em Python, a contagem comeca em zero.

```python
localidades[0]  # Sede
localidades[1]  # Cachoeira
localidades[2]  # Tamboara
```

### Percorrendo uma lista

```python
for localidade in localidades:
    print(localidade)
```

Leia:

"Para cada localidade dentro da lista localidades, imprima a localidade."

### Exercicio

O que este codigo faz?

```python
nomes = ["Ana", "Bruno", "Carla"]
for nome in nomes:
    print(nome)
```

Resposta:

Ele imprime cada nome da lista, um por vez.

---

## 7. Dicionarios

Dicionario guarda pares de chave e valor.

```python
usuario = {
    "nome": "Joao",
    "nivel": "admin",
    "ativo": True,
}
```

No sistema, dicionarios sao essenciais.

Exemplo de `app_core/modules.py`:

```python
LEVEL_ORDER = {
    "visualizador": 1,
    "operador": 2,
    "admin": 3,
}
```

Esse dicionario diz qual nivel vale mais.

### Acessando valor

```python
usuario["nome"]
```

Retorna:

```text
Joao
```

### Usando `.get`

```python
usuario.get("nivel")
```

`.get` e mais seguro porque, se a chave nao existir, ele nao quebra o programa.

Exemplo real:

```python
level = (user or {}).get("nivel") if isinstance(user, dict) else None
```

Esse trecho e mais avancado, mas a ideia e:

- se `user` for um dicionario, pegue o campo `nivel`;
- se nao for, use `None`.

### Dicionarios em APIs

Quando uma API retorna JSON, geralmente ela devolve um dicionario.

Exemplo conceitual:

```json
{
  "ok": true,
  "total": 10,
  "registros": []
}
```

No Python, isso se parece com:

```python
{
    "ok": True,
    "total": 10,
    "registros": [],
}
```

---

## 8. Funcoes

Funcao e um bloco de codigo com nome.

Ela serve para reutilizar uma acao.

Exemplo simples:

```python
def somar(a, b):
    return a + b
```

Uso:

```python
resultado = somar(2, 3)
```

Resultado:

```text
5
```

### Funcao real: `safe_int`

Em `app_core/utils.py`:

```python
def safe_int(value, default=0):
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default
```

Essa funcao tenta transformar um valor em inteiro.

Se der erro, devolve um padrao.

Exemplos:

```python
safe_int("10")       # 10
safe_int(None)       # 0
safe_int("abc")      # 0
safe_int("abc", 99)  # 99
```

### Partes de uma funcao

```python
def safe_int(value, default=0):
```

- `def`: palavra que define funcao.
- `safe_int`: nome da funcao.
- `value`: parametro obrigatorio.
- `default=0`: parametro opcional.

```python
try:
```

Tenta executar algo que pode dar erro.

```python
except (ValueError, TypeError):
```

Se der erro de valor ou tipo, execute este bloco.

```python
return default
```

Devolve o valor padrao.

### Exercicio

Antes de ler a resposta, pense no resultado:

```python
safe_int("25")
safe_int("")
safe_int(None, 7)
```

Resposta:

```text
25
0
7
```

---

## 9. Condicionais: `if`, `elif`, `else`

Condicionais permitem tomar decisoes.

Exemplo:

```python
if idade >= 18:
    print("Maior de idade")
else:
    print("Menor de idade")
```

No sistema:

```python
def senha_valida(senha):
    return bool(senha) and len(senha) >= PASSWORD_MIN_LENGTH
```

Esse exemplo usa uma forma curta.

Outro exemplo, mais visivel:

```python
if not usuario:
    return redirect(url_for("auth.login"))
```

Leia:

"Se nao existir usuario, redirecione para login."

### `if not`

`not` significa "nao".

```python
if not uid:
```

Leia:

"Se nao houver uid..."

No sistema, `uid` e o ID do usuario guardado na sessao.

### `elif`

`elif` significa "senao, se..."

Exemplo:

```python
if nivel == "admin":
    print("Acesso total")
elif nivel == "operador":
    print("Acesso de edicao")
else:
    print("Acesso de leitura")
```

### Exercicio

Complete mentalmente:

```python
nivel = "operador"

if nivel == "admin":
    print("Tudo")
elif nivel == "operador":
    print("Editar")
else:
    print("Ler")
```

O que aparece?

Resposta:

```text
Editar
```

---

## 10. Repeticoes: `for`

`for` percorre itens.

Exemplo:

```python
for item in lista:
    print(item)
```

No sistema:

```python
for group in sidebar_groups:
```

Esse trecho aparece no template `base.html`, em Jinja, mas a ideia e parecida com Python.

Em Python real:

```python
for row in rows:
    backups.append(...)
```

Leia:

"Para cada linha em rows, adicione um item na lista backups."

### `for` com dicionarios

```python
for codigo, cor in AGENDA_TYPE_COLORS.items():
```

Leia:

"Para cada par codigo/cor dentro do dicionario AGENDA_TYPE_COLORS..."

### Exercicio

O que este codigo imprime?

```python
tipos = ["TB", "PE", "TBO"]

for tipo in tipos:
    print("Tipo:", tipo)
```

Resposta:

```text
Tipo: TB
Tipo: PE
Tipo: TBO
```

---

## 11. Tratamento de erros: `try`, `except`, `finally`

Sistemas reais precisam lidar com erros.

Exemplo simples:

```python
try:
    numero = int("abc")
except ValueError:
    numero = 0
```

Como `"abc"` nao vira numero, o Python cai no `except`.

No sistema:

```python
def query(db_path, sql, params=()):
    conn = connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
```

Esse e um trecho excelente.

Ele significa:

1. Abra uma conexao com o banco.
2. Tente executar a consulta.
3. Retorne os resultados.
4. De qualquer forma, feche a conexao.

`finally` sempre roda, mesmo se der erro.

Isso e importante para nao deixar conexoes abertas.

### Em rotas Flask

Exemplo:

```python
try:
    return jsonify(rg_core.listar(...))
except ValueError as exc:
    return jsonify({"erro": str(exc)}), 400
except Exception:
    logging.exception("Erro ao listar Registro Geografico")
    return jsonify({"erro": "Erro interno do servidor."}), 500
```

Leia:

- tente listar;
- se for erro esperado, devolva erro 400;
- se for erro inesperado, registre no log e devolva erro 500.

### Exercicio

Por que o sistema nao deve mostrar todos os detalhes de um erro inesperado para o usuario?

Resposta:

Porque detalhes internos podem expor caminhos, banco, nomes de tabelas ou informacoes sensiveis. O ideal e registrar no log e mostrar uma mensagem simples.

---

## 12. Modulos e organizacao

Um modulo e um arquivo Python.

Exemplo:

```text
app_core/db.py
```

Pode ser importado assim:

```python
from app_core import db as db_core
```

Isso permite usar:

```python
db_core.connect(...)
db_core.query(...)
db_core.query_one(...)
```

### Por que dividir em arquivos?

Porque um sistema grande fica impossivel de manter se tudo ficar em um unico arquivo.

Seu sistema ja tem uma divisao boa:

```text
app.py
  Configura e inicia o Flask

blueprints/
  Rotas e paginas

app_core/
  Regras de negocio e banco

templates/
  HTML

static/
  CSS, JS, imagens, mapas

tests/
  Testes automatizados
```

### Exemplo de caminho de uma funcionalidade

Quando voce abre a pagina Registro Geografico:

```text
Navegador
  -> /registro-geografico
  -> blueprints/registro_geografico.py
  -> app_core/registro_geografico.py
  -> templates/registro_geografico.html
```

Quando voce clica em "Atualizar" na consulta:

```text
JavaScript em templates/registro_geografico.html
  -> chama /api/registro-geografico
  -> blueprints/registro_geografico.py
  -> app_core/registro_geografico.py
  -> banco SQLite
  -> retorna JSON
  -> JavaScript atualiza a tabela
```

Esse mapa mental e uma das coisas mais importantes para aprender a mexer no sistema.

---

## 13. Flask: paginas e APIs

Flask e a ferramenta Python que transforma funcoes em paginas ou APIs.

### Rota de pagina

Exemplo:

```python
@bp.route("/registro-geografico")
@login_required
def page():
    opcoes = rg_core.opcoes(_db_path(), _base_dir())
    return render_template("registro_geografico.html", opcoes=opcoes)
```

Isso cria uma pagina.

Pontos importantes:

- `@bp.route(...)`: define a URL.
- `@login_required`: exige login.
- `def page()`: funcao chamada quando alguem acessa a URL.
- `render_template(...)`: devolve HTML.

### Rota de API

Exemplo:

```python
@bp.route("/api/registro-geografico")
@login_required
def api_listar():
    return jsonify(rg_core.listar(...))
```

Isso cria uma API.

API geralmente devolve JSON, nao uma pagina pronta.

### HTML versus JSON

HTML e pagina:

```html
<h1>Registro Geografico</h1>
```

JSON e dado:

```json
{
  "total": 150,
  "registros": []
}
```

No sistema:

- paginas usam `render_template`;
- APIs usam `jsonify`.

### Exercicio

Classifique:

```python
return render_template("admin_sistema.html", backups=backups)
```

Resposta: pagina HTML.

```python
return jsonify({"ok": True})
```

Resposta: API JSON.

---

## 14. Banco de dados com SQLite

SQLite e o banco usado no sistema.

Ele fica em um arquivo:

```text
endemias.db
```

O Python conversa com ele usando SQL.

### Conexao

Em `app_core/db.py`:

```python
def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
```

Essa funcao prepara uma conexao com o banco.

### Consulta simples

```python
rows = conn.execute("SELECT * FROM usuarios").fetchall()
```

Tradução:

"Busque todas as linhas da tabela usuarios."

### Consulta com parametro

```python
row = conn.execute(
    "SELECT * FROM usuarios WHERE id_usuario=?",
    (uid,),
).fetchone()
```

O `?` e um marcador.

O valor real vem separado em `(uid,)`.

Isso e mais seguro do que montar SQL com texto manualmente.

### Por que usar parametros?

Porque evita problemas de seguranca, como SQL injection.

Ruim:

```python
sql = "SELECT * FROM usuarios WHERE usuario='" + nome + "'"
```

Bom:

```python
sql = "SELECT * FROM usuarios WHERE usuario=?"
params = (nome,)
```

### `fetchone` e `fetchall`

```python
fetchone()
```

Pega uma linha.

```python
fetchall()
```

Pega varias linhas.

### `commit`

Quando altera dados, precisa confirmar:

```python
conn.commit()
```

Sem `commit`, a alteracao pode nao ser gravada.

---

## 15. Criacao do banco

O arquivo `criar_banco.py` cria as tabelas principais.

Ele contem muito SQL.

Exemplo:

```sql
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT    NOT NULL UNIQUE,
    nome        TEXT    NOT NULL,
    senha_hash  TEXT    NOT NULL,
    nivel       TEXT    NOT NULL DEFAULT 'visualizador',
    ativo       INTEGER NOT NULL DEFAULT 1,
    criado_em   TEXT    NOT NULL
);
```

Isso cria a tabela `usuarios`.

### Campos

- `id_usuario`: identificador unico.
- `usuario`: login.
- `nome`: nome da pessoa.
- `senha_hash`: senha protegida.
- `nivel`: permissao.
- `ativo`: se pode acessar.
- `criado_em`: data de criacao.

### `PRIMARY KEY`

Identifica uma linha de forma unica.

### `UNIQUE`

Nao permite repetir.

No exemplo:

```sql
usuario TEXT NOT NULL UNIQUE
```

Nao podem existir dois usuarios com o mesmo login.

### `REFERENCES`

Cria relacionamento entre tabelas.

Exemplo:

```sql
id_localidade INTEGER REFERENCES localidades(id_localidade)
```

Significa:

"Este campo aponta para uma localidade da tabela localidades."

---

## 16. Datas no sistema

O sistema usa muitas datas.

Em `app_core/utils.py`:

```python
from datetime import date, datetime, timedelta
```

### Data de hoje

```python
def hoje():
    return date.today().isoformat()
```

Se hoje fosse 2 de julho de 2026, retornaria:

```text
2026-07-02
```

### Data de N dias atras

```python
def data_n_dias(n=30):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")
```

Se `n=30`, pega a data de 30 dias atras.

### Inicio do ano

```python
def data_ano():
    return f"{date.today().year}-01-01"
```

Se o ano atual for 2026:

```text
2026-01-01
```

### Por que o sistema usa `YYYY-MM-DD`?

Porque esse formato:

```text
2026-07-02
```

e facil de ordenar, comparar e salvar no banco.

---

## 17. Classes e dataclasses

Voce nao precisa dominar classes agora, mas e bom reconhecer.

Em `app_core/modules.py`:

```python
from dataclasses import dataclass, field
```

Depois:

```python
@dataclass(frozen=True)
class AppModule:
    key: str
    title: str
    href: str
    endpoint: str
    icon: str
    nav_section: str
```

Essa classe representa um modulo do sistema.

Exemplo de modulo:

```python
AppModule(
    key="registro_geografico",
    title="Registro Geografico",
    href="/registro-geografico",
    endpoint="registro_geografico.page",
    icon="registro_geografico.svg",
    nav_section="Gestao",
)
```

Isso e usado para montar menus, permissoes e atalhos.

### O que e uma classe?

Classe e um modelo para criar objetos.

`AppModule` e um modelo.

Cada item dentro de `MODULES` e um objeto desse modelo.

### Por que usar isso?

Porque fica organizado.

Em vez de espalhar menu em varios lugares, o sistema centraliza os modulos em uma lista.

---

## 18. Decorators: linhas com `@`

No Python, linhas que comecam com `@` geralmente sao decorators.

Exemplos:

```python
@bp.route("/admin/sistema")
@login_required
@nivel_min("admin")
def admin_sistema():
    ...
```

Leia assim:

- esta funcao responde pela URL `/admin/sistema`;
- precisa estar logado;
- precisa ter nivel minimo `admin`.

Voce nao precisa saber criar decorators agora. Mas precisa reconhecer que eles modificam o comportamento de uma funcao.

### Exemplo importante

```python
@login_required
```

Essa linha protege uma pagina.

Sem login, o usuario e redirecionado.

### Exercicio

Abra `blueprints/admin.py` e procure:

```python
@nivel_min("admin")
```

Pergunta:

Que tipo de paginas essa protecao deve proteger?

Resposta:

Paginas administrativas, como Central do Sistema, usuarios, auditoria e backups.

---

## 19. Caminhos e arquivos

O sistema usa caminhos para encontrar:

- banco;
- anexos;
- configuracoes;
- logs;
- backups.

Em `app.py`:

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

Isso descobre a pasta do sistema.

Tambem aparece:

```python
DB_PATH = PATHS["DB_PATH"]
CONFIG_PATH = PATHS["CONFIG_PATH"]
UPLOAD_TEMP = PATHS["UPLOAD_TEMP"]
```

Essas variaveis guardam caminhos importantes.

### `Path`

Em muitos arquivos aparece:

```python
from pathlib import Path
```

`Path` e uma forma moderna de trabalhar com caminhos.

Exemplo:

```python
db_path = Path(current_app.config["DB_PATH"])
backup_dir = db_path.parent / "backups"
```

Aqui:

- `db_path.parent` pega a pasta onde esta o banco;
- `/ "backups"` adiciona a subpasta `backups`.

### Exercicio

Se:

```python
db_path = Path("C:/endemias/endemias.db")
```

O que e:

```python
db_path.parent
```

Resposta:

```text
C:/endemias
```

---

## 20. Configuracao por variaveis de ambiente

No `app.py`, existe:

```python
def resolve_paths(env=None, base_dir=BASE_DIR):
    env = env or os.environ
```

Isso permite mudar caminhos usando variaveis de ambiente.

Exemplo:

```python
"DB_PATH": os.path.abspath(env.get("ENDEMIAS_DB_PATH", os.path.join(instance_dir, "endemias.db")))
```

Leia:

- procure a variavel `ENDEMIAS_DB_PATH`;
- se ela existir, use esse valor;
- se nao existir, use `endemias.db` dentro da pasta da instancia.

Isso deixa o sistema flexivel.

### Por que isso importa?

Porque em uma instalacao real voce pode querer:

- banco em outro disco;
- anexos em outra pasta;
- backups em outro local;
- logs fora da pasta do codigo.

---

## 21. Autenticacao e permissoes

Autenticacao responde:

"Quem e o usuario?"

Permissao responde:

"O que ele pode fazer?"

No sistema existem niveis:

```python
LEVEL_ORDER = {
    "visualizador": 1,
    "operador": 2,
    "admin": 3,
}
```

### `login_required`

Em `app_core/auth.py`:

```python
def login_required(view):
    @wraps(view)
    def dec(*args, **kwargs):
        uid = session.get("uid")
        if not uid:
            return redirect(url_for("auth.login", next=request.path))
        ...
        return view(*args, **kwargs)
    return dec
```

Esse decorator protege rotas.

Se nao houver `uid` na sessao, manda para login.

### `nivel_min`

```python
@nivel_min("admin")
```

Exige administrador.

```python
@nivel_min("operador")
```

Exige operador ou admin.

### Senhas

O sistema usa hash:

```python
generate_password_hash(...)
check_password_hash(...)
```

Isso e importante porque senha nao deve ser salva em texto puro.

---

## 22. Templates: Python entregando HTML

Quando uma rota usa:

```python
return render_template("registro_geografico.html", opcoes=opcoes)
```

O Flask abre:

```text
templates/registro_geografico.html
```

E envia a variavel `opcoes`.

No template:

```html
{% for loc in opcoes.localidades %}
  <option value="{{ loc.id_localidade }}">{{ loc.nome }}</option>
{% endfor %}
```

Isso cria uma opcao para cada localidade.

### `{{ ... }}`

Mostra um valor.

```html
{{ loc.nome }}
```

### `{% ... %}`

Executa uma instrucao de template.

```html
{% for loc in opcoes.localidades %}
```

### Heranca de template

Muitos templates comecam assim:

```html
{% extends "base.html" %}
```

Isso significa:

"Use o layout principal de `base.html` e preencha partes especificas."

No `base.html` existem blocos:

```html
{% block content %}{% endblock %}
```

Cada pagina coloca seu conteudo nesse bloco.

---

## 23. JavaScript no sistema

JavaScript roda no navegador.

Ele e usado para:

- abrir menu;
- alternar tema claro/escuro;
- mostrar toast;
- buscar dados de APIs;
- atualizar tabelas;
- renderizar graficos;
- trabalhar com mapas.

Exemplo:

```javascript
async function rgCarregar(){
  const resp = await fetch('/api/registro-geografico?' + rgParams());
  const data = await resp.json();
  rgState.registros = data.registros || [];
  rgRenderConsulta();
}
```

Leia:

- chame a API `/api/registro-geografico`;
- transforme a resposta em JSON;
- guarde os registros;
- renderize a consulta.

Voce nao precisa dominar JavaScript neste Volume 1, mas precisa reconhecer que:

- Python roda no servidor;
- JavaScript roda no navegador.

### Fluxo completo com JavaScript

```text
Usuario clica em Atualizar
  -> JavaScript chama fetch('/api/registro-geografico')
  -> Flask recebe a API
  -> Python consulta SQLite
  -> Flask devolve JSON
  -> JavaScript atualiza a tabela
```

---

## 24. ETL: processamento de planilhas

ETL significa:

- Extract: extrair dados;
- Transform: transformar/normalizar;
- Load: carregar no banco.

No seu sistema, o ETL principal esta em:

```text
etl.py
```

Ele usa:

```python
import pandas as pd
```

Pandas e uma biblioteca para trabalhar com planilhas e tabelas.

### Funcoes de normalizacao

Exemplo:

```python
def normalizar_data(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    try:
        return pd.to_datetime(valor).date().isoformat()
    except Exception:
        return None
```

Essa funcao tenta transformar varios formatos de data em um formato padrao:

```text
YYYY-MM-DD
```

### Por que normalizar?

Porque planilhas podem vir com:

- texto;
- data;
- valor vazio;
- `nan`;
- formatos diferentes.

Antes de salvar no banco, o sistema precisa padronizar.

---

## 25. Testes automatizados

Testes sao codigo que verifica se o sistema continua funcionando.

Exemplo real:

```python
def test_pagina_registro_geografico_renderiza(self):
    client = _client_logado()
    resp = client.get("/registro-geografico")

    self.assertEqual(resp.status_code, 200)
    html = resp.data.decode("utf-8")
    self.assertIn("rg-panel-consulta", html)
```

Leia:

- cria um cliente logado;
- acessa `/registro-geografico`;
- confere se a resposta foi `200`;
- confere se o HTML contem um trecho esperado.

### Por que isso e importante?

Porque quando voce muda uma tela, pode quebrar outra coisa sem perceber.

Testes ajudam a pegar isso cedo.

### Rodando testes

Exemplo:

```powershell
python -m unittest tests.test_security.MainApisSmokeTests.test_pagina_registro_geografico_renderiza -v
```

Esse comando roda um teste especifico.

---

## 26. Git e seguranca do codigo

Git controla versoes do codigo.

GitHub guarda uma copia remota.

No seu projeto:

- codigo vai para o GitHub;
- banco real nao vai;
- chaves nao vao;
- arquivos gerados nao vao.

O arquivo `.gitignore` define o que fica fora.

Exemplos:

```text
secret.key
kobo_config.json
*.db
backups/
anexos/
```

Isso e correto.

### Commit

Commit e um ponto salvo na historia do codigo.

### Push

Push envia os commits para o GitHub.

### Cuidado

Nunca coloque no GitHub:

- `endemias.db`;
- `secret.key`;
- `kobo_config.json`;
- backups completos;
- anexos reais.

---

## 27. Como estudar o sistema sem medo

Use esta ordem:

1. Leia o arquivo.
2. Entenda o caminho da funcionalidade.
3. Identifique se e Python, HTML, JavaScript ou SQL.
4. Procure a funcao principal.
5. Leia nomes de variaveis.
6. Ignore detalhes avancados na primeira leitura.
7. Rode testes antes e depois de alterar.
8. Faca commits pequenos.

### Exemplo: entender Registro Geografico

Comece por:

```text
blueprints/registro_geografico.py
```

Pergunte:

- Quais URLs existem?
- Quais funcoes chamam `rg_core`?
- Quais retornam HTML?
- Quais retornam JSON?

Depois abra:

```text
app_core/registro_geografico.py
```

Pergunte:

- Onde cria tabelas?
- Onde lista registros?
- Onde busca quarteiroes?
- Onde salva edicao?

Depois abra:

```text
templates/registro_geografico.html
```

Pergunte:

- Onde estao os filtros?
- Onde esta a tabela?
- Onde o JavaScript chama API?

---

## 28. Mini glossario

### Aplicacao web

Sistema acessado pelo navegador.

### Backend

Parte que roda no servidor. No seu caso, Python e Flask.

### Frontend

Parte que roda no navegador. HTML, CSS e JavaScript.

### Rota

Endereco do sistema, como `/admin/sistema`.

### API

Rota que devolve dados, geralmente JSON.

### Template

Arquivo HTML com variaveis do Flask/Jinja.

### Banco de dados

Lugar onde os dados ficam salvos.

### SQLite

Banco de dados em arquivo.

### Query

Consulta SQL.

### JSON

Formato de dados usado entre navegador e servidor.

### Funcao

Bloco de codigo reutilizavel.

### Modulo

Arquivo Python que pode ser importado.

### Blueprint

Forma do Flask organizar rotas por area.

### Commit

Registro de uma alteracao no Git.

### Teste automatizado

Codigo que verifica se outra parte do sistema funciona.

---

## 29. Exercicios guiados do Volume 1

Estes exercicios sao para estudar. Nao altere o sistema real ainda, a menos que voce queira fazer isso acompanhado.

### Exercicio 1 - Encontre a entrada do sistema

Abra:

```text
app.py
```

Procure:

```python
def create_app
```

Responda:

- Quais configuracoes aparecem dentro de `flask_app.config.update`?
- Onde os blueprints sao registrados?
- Qual variavel representa o banco?

### Exercicio 2 - Leia uma funcao simples

Abra:

```text
app_core/utils.py
```

Leia:

```python
def bounded_int(value, default, minimo=None, maximo=None):
```

Responda:

- O que acontece se o valor for menor que o minimo?
- O que acontece se for maior que o maximo?

### Exercicio 3 - Siga uma rota

Abra:

```text
blueprints/registro_geografico.py
```

Procure:

```python
@bp.route("/api/registro-geografico")
```

Responda:

- Qual funcao essa rota chama?
- Ela devolve HTML ou JSON?
- Qual funcao do `app_core` ela usa?

### Exercicio 4 - Identifique tipos de dados

No trecho:

```python
LEVEL_ORDER = {
    "visualizador": 1,
    "operador": 2,
    "admin": 3,
}
```

Responda:

- Isso e lista ou dicionario?
- As chaves sao textos ou numeros?
- Os valores sao textos ou numeros?

### Exercicio 5 - Entenda uma consulta

Leia:

```python
row = conn.execute(
    "SELECT * FROM usuarios WHERE id_usuario=? AND ativo=1",
    (uid,),
).fetchone()
```

Responda:

- Qual tabela esta sendo consultada?
- Qual campo esta sendo filtrado?
- Por que existe um `?`?

### Exercicio 6 - Diferencie pagina e API

Classifique:

```python
return render_template("admin_sistema.html", backups=backups)
```

```python
return jsonify({"ok": True})
```

### Exercicio 7 - Leia um teste

Abra:

```text
tests/test_security.py
```

Procure um teste que comece com:

```python
def test_pagina_
```

Responda:

- Qual pagina ele abre?
- O que ele espera encontrar no HTML?

---

## 30. Pequeno roteiro de 7 dias

### Dia 1 - Mapa do projeto

Leia os capitulos 1 a 3.

Abra:

```text
app.py
blueprints/
app_core/
templates/
```

Objetivo: saber onde cada coisa mora.

### Dia 2 - Python basico

Leia capitulos 4 a 11.

Abra:

```text
app_core/utils.py
app_core/db.py
```

Objetivo: reconhecer variaveis, funcoes, listas, dicionarios, if, for e try.

### Dia 3 - Flask

Leia capitulos 12 e 13.

Abra:

```text
blueprints/registro_geografico.py
blueprints/admin.py
```

Objetivo: entender rotas, paginas e APIs.

### Dia 4 - Banco SQLite

Leia capitulos 14 e 15.

Abra:

```text
criar_banco.py
app_core/db.py
```

Objetivo: entender tabelas, consultas e conexoes.

### Dia 5 - Templates e JavaScript

Leia capitulos 22 e 23.

Abra:

```text
templates/base.html
templates/registro_geografico.html
static/js/app.js
```

Objetivo: entender como a tela conversa com o Python.

### Dia 6 - ETL e configuracoes

Leia capitulos 20 e 24.

Abra:

```text
etl.py
config.json
app_core/work_types.py
```

Objetivo: entender processamento de planilhas e configuracoes.

### Dia 7 - Testes e revisao

Leia capitulos 25 a 29.

Abra:

```text
tests/test_security.py
```

Objetivo: entender como o sistema se protege contra quebras.

---

## 31. O que voce deve conseguir fazer apos este volume

Ao terminar este volume, voce deve conseguir:

- explicar a diferenca entre `app.py`, `blueprints`, `app_core` e `templates`;
- reconhecer uma funcao Python;
- entender imports simples;
- identificar listas e dicionarios;
- seguir o caminho de uma rota Flask;
- diferenciar HTML de JSON;
- reconhecer uma consulta SQL;
- entender por que o banco nao vai para o GitHub;
- rodar um teste especifico com ajuda;
- ler uma pequena alteracao sem se perder.

Isso ja e muito.

O salto principal nao e "decorar Python". E conseguir abrir um arquivo e nao sentir que ele e uma parede indecifravel.

---

## 32. Proximo volume sugerido

O Volume 2 pode ser:

**Flask, rotas, templates e APIs no Sistema Endemias**

Ele pode ensinar, com mais profundidade:

- como criar uma nova pagina;
- como criar uma nova API;
- como enviar dados do HTML para o Python;
- como validar entrada do usuario;
- como retornar mensagens de erro;
- como usar `fetch` no JavaScript;
- como proteger rotas com login e nivel de acesso.

Depois disso, o Volume 3 pode entrar em:

**Banco de dados, SQL e manutencao segura**

E o Volume 4:

**Planilhas Kobo, ETL, Pandas e importacoes**

---

Fim do Volume 1.
