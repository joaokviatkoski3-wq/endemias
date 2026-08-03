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

O script seleciona SQLite ou PostgreSQL explicitamente. No SQLite, usa a API
nativa e `PRAGMA integrity_check`. No PostgreSQL, usa `pg_dump` custom,
`pg_restore --list` e SHA-256. Nos dois casos, grava metadados `.json` ao lado
do backup.

```powershell
python scripts\backup_banco.py --backend sqlite
```

Para escolher origem e destino SQLite:

```powershell
python scripts\backup_banco.py --backend sqlite `
  --db "D:\dados\endemias.db" --destino "E:\Backups\Endemias"
```

Para PostgreSQL, informe o banco e use o `pgpass` protegido:

```powershell
python scripts\backup_banco.py --backend postgresql `
  --database endemias `
  --pgpass-file "C:\ProgramData\Endemias\pgpass.conf" `
  --destino "D:\BackupsEndemias\backups_banco" `
  --manter 30
```

O servidor oficial pode registrar as tarefas diaria e semanal executando
`configurar_backup_postgresql.bat` como administrador. A validacao posterior e:

```powershell
Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command "cd C:\endemias; python scripts\verificar_backups_postgresql.py"'
```

No servidor oficial, as pastas de backup ficam restritas a `SYSTEM` e
Administradores porque os arquivos contem dados reais e configuracoes
sensiveis.

Boa rotina operacional:

- fazer backup antes de importar planilhas grandes ou rodar migracoes;
- guardar copia em outro disco ou servidor;
- testar restauracao periodicamente em uma pasta separada;
- manter uma copia externa protegida, pois o backup completo contem dados e
  configuracoes sensiveis;
- nunca versionar `backups/`, `anexos/`, `uploads_temp/`, `saida/`, `notificacoes_geradas/`, `*.db`, `*.db-wal`, `*.db-shm`, `*.log`, `secret.key` ou `kobo_config.json`.

## Politica de seguranca de conteudo

O sistema envia `Content-Security-Policy-Report-Only` por padrao. Esse modo registra a politica no navegador sem bloquear telas, porque ainda existem scripts e estilos inline em alguns templates.

Para testar CSP bloqueante em um ambiente controlado, configure:

```python
app = create_app({"CSP_REPORT_ONLY": False})
```

Antes de ativar em producao, valide as telas principais no navegador. A etapa seguinte de endurecimento e mover JavaScript inline para arquivos em `static/js/` e trocar atributos `onclick`/`onchange` por listeners.
