# Configuracao de ambiente

Por padrao, o sistema continua usando os caminhos historicos na raiz do projeto:

- `endemias.db`
- `config.json`
- `kobo_config.json`
- `anexos/`
- `uploads_temp/`
- `endemias.log`
- `secret.key`

Para separar dados do codigo em uma instalacao de producao, defina uma pasta de instancia:

```powershell
$env:ENDEMIAS_INSTANCE_DIR = "C:\EndemiasDados"
python app.py
```

Com isso, o sistema passa a procurar/criar nesta pasta:

- `endemias.db`
- `kobo_config.json`
- `anexos/`
- `uploads_temp/`
- `endemias.log`
- `secret.key`

Tambem e possivel sobrescrever caminhos individualmente:

```powershell
$env:ENDEMIAS_DB_PATH = "D:\dados\endemias.db"
$env:ENDEMIAS_CONFIG_PATH = "C:\endemias\config.json"
$env:ENDEMIAS_KOBO_CONFIG_PATH = "D:\dados\kobo_config.json"
$env:ENDEMIAS_ANEXOS_DIR = "D:\dados\anexos"
$env:ENDEMIAS_UPLOAD_TEMP = "D:\dados\uploads_temp"
$env:ENDEMIAS_LOG_PATH = "D:\dados\endemias.log"
$env:ENDEMIAS_SECRET_KEY_PATH = "D:\dados\secret.key"
python app.py
```

Antes de mudar o banco real de lugar, pare o sistema, copie `endemias.db` e os arquivos `*.db-wal`/`*.db-shm` se existirem, e so entao inicie apontando para o novo caminho.

## Backup do banco

Para gerar uma copia consistente do SQLite, use o script de backup. Ele usa a API nativa do SQLite, funciona melhor com WAL do que copiar apenas o arquivo `.db`, valida o resultado com `PRAGMA integrity_check` e grava um `.json` de metadados ao lado do backup.

```powershell
python scripts\backup_banco.py
```

Por padrao, o arquivo sera salvo em `backups/` ao lado do banco configurado. Para escolher origem e destino:

```powershell
python scripts\backup_banco.py --db "D:\dados\endemias.db" --destino "E:\Backups\Endemias"
```

Para manter somente os ultimos 30 backups:

```powershell
python scripts\backup_banco.py --manter 30
```

Boa rotina operacional:

- fazer backup antes de importar planilhas grandes ou rodar migracoes;
- guardar copia em outro disco ou servidor;
- testar restauracao periodicamente em uma pasta separada;
- nunca versionar `backups/`, `anexos/`, `uploads_temp/`, `saida/`, `notificacoes_geradas/`, `*.db`, `*.db-wal`, `*.db-shm`, `*.log`, `secret.key` ou `kobo_config.json`.

## Politica de seguranca de conteudo

O sistema envia `Content-Security-Policy-Report-Only` por padrao. Esse modo registra a politica no navegador sem bloquear telas, porque ainda existem scripts e estilos inline em alguns templates.

Para testar CSP bloqueante em um ambiente controlado, configure:

```python
app = create_app({"CSP_REPORT_ONLY": False})
```

Antes de ativar em producao, valide as telas principais no navegador. A etapa seguinte de endurecimento e mover JavaScript inline para arquivos em `static/js/` e trocar atributos `onclick`/`onchange` por listeners.
