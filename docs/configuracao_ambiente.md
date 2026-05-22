# Configuracao de ambiente

Por padrao, o sistema continua usando os caminhos historicos na raiz do projeto:

- `endemias.db`
- `config.json`
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
- `uploads_temp/`
- `endemias.log`
- `secret.key`

Tambem e possivel sobrescrever caminhos individualmente:

```powershell
$env:ENDEMIAS_DB_PATH = "D:\dados\endemias.db"
$env:ENDEMIAS_CONFIG_PATH = "C:\endemias\config.json"
$env:ENDEMIAS_UPLOAD_TEMP = "D:\dados\uploads_temp"
$env:ENDEMIAS_LOG_PATH = "D:\dados\endemias.log"
$env:ENDEMIAS_SECRET_KEY_PATH = "D:\dados\secret.key"
python app.py
```

Antes de mudar o banco real de lugar, pare o sistema, copie `endemias.db` e os arquivos `*.db-wal`/`*.db-shm` se existirem, e so entao inicie apontando para o novo caminho.
