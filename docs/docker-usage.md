# Docker - Guia de Uso

Guia pratico para executar o `gerador-cli` via Docker, sem necessidade de instalar Python ou dependencias no host.

## Pre-requisitos

- [Docker](https://docs.docker.com/get-docker/) e [Docker Compose](https://docs.docker.com/compose/install/) instalados

## Arquitetura

```
+---------------------------------------------------+
|                  Docker Compose                    |
|                                                    |
|  +-------------+         +---------------------+  |
|  |   ollama    |  :11434 |     gerador-cli     |  |
|  |  (servidor) | <-----> | (aplicacao Python)  |  |
|  +-------------+         +---------------------+  |
|        |                          |                |
|   volume:                    volumes:              |
|   ollama_data              /repo (read-only)       |
|   (/root/.ollama)          /app/config.json (ro)   |
|                            /app/output             |
+---------------------------------------------------+
```

Dois containers separados:

| Container | Funcao |
|---|---|
| `ollama` | Servidor LLM (sempre rodando) |
| `gerador-cli` | CLI Python (executa e termina) |

## Inicio Rapido

### 1. Subir o Ollama

```powershell
docker compose up ollama -d
```

### 2. Baixar o modelo (primeira vez)

```powershell
docker compose exec ollama ollama pull qwen2.5:7b
```

Aguarde o download terminar. Verifique com:

```powershell
docker compose exec ollama ollama list
```

### 3. Executar o gerador

```powershell
docker compose run --rm gerador-cli
```

Os arquivos gerados estarao em `./output/`.

## Configuracao

### Variaveis de ambiente

| Variavel | Padrao | Descricao |
|---|---|---|
| `REPO_PATH` | `.` (diretorio atual) | Caminho do repositorio Git a ser analisado |
| `CONFIG_PATH` | `./config.default.json` | Caminho do arquivo de configuracao |
| `OLLAMA_HOST` | `http://ollama:11434` | URL do servidor Ollama (configurado internamente) |

### Analisar outro repositorio

```powershell
$env:REPO_PATH="C:\Users\Davi\outro-repo"
docker compose run --rm gerador-cli
```

### Usar config customizado

```powershell
$env:CONFIG_PATH="./meu-config.json"
docker compose run --rm gerador-cli
```

### Flags da CLI

Os argumentos fixos (`/repo`, `--config`, `--output-dir`) sao definidos no `entrypoint`. O `command` padrao e `--generate both`. Para sobrescrever:

```powershell
# Gerar apenas PR
docker compose run --rm gerador-cli --generate pr

# Gerar com filtro de data
docker compose run --rm gerador-cli --generate both --since 2025-01-01

# Gerar com range de revisao
docker compose run --rm gerador-cli --generate release --range v1.0..v1.1

# Pular LLM (usar assuntos dos commits diretamente)
docker compose run --rm gerador-cli --no-llm
```

## Volumes e Persistencia

| Volume | Caminho no Container | Descricao |
|---|---|---|
| `ollama_data` | `/root/.ollama` | Modelos baixados (~5-10GB por modelo). Persiste entre reinicializacoes |
| bind: `REPO_PATH` | `/repo` (read-only) | Repositorio Git analisado |
| bind: `CONFIG_PATH` | `/app/config.json` (read-only) | Arquivo de configuracao |
| bind: `./output` | `/app/output` | Arquivos gerados (PR.md, release.md) |

## Estrutura de Saida

Apos execucao, os arquivos ficam em:

```
output/
  <nome-do-repo>/
    prs/
      PR.md
    releases/
      release.md
    utils/
      domain_profile.json
      prompts/
```

## Usando Ollama Externo

Se voce ja tem o Ollama rodando no host (fora do Docker), pode apontar o container para ele:

```powershell
# Windows/Mac (Docker Desktop)
docker run --rm `
    -e OLLAMA_HOST=http://host.docker.internal:11434 `
    -v ${PWD}:/repo:ro `
    -v ${PWD}/output:/app/output `
    -v ${PWD}/config.default.json:/app/config.json:ro `
    gerador-cli /repo --config /app/config.json --output-dir /app/output --generate both
```

## GPU (NVIDIA)

Para acelerar a inferencia com GPU, adicione ao `docker-compose.yml` no servico `ollama`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Pre-requisito: [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) instalado no host.

## Comandos Uteis

```powershell
# Ver logs do Ollama
docker compose logs ollama

# Listar modelos disponíveis
docker compose exec ollama ollama list

# Baixar outro modelo
docker compose exec ollama ollama pull llama3:8b

# Remover modelo
docker compose exec ollama ollama rm qwen2.5:7b

# Parar tudo
docker compose down

# Parar e remover volumes (apaga modelos baixados)
docker compose down -v

# Rebuild da imagem (apos alterar codigo)
docker compose build --no-cache gerador-cli
```

## Troubleshooting

### Modelo nao encontrado (404)

```
model 'xxx' not found (status code: 404)
```

O modelo nao foi baixado. Execute:

```powershell
docker compose exec ollama ollama pull <nome-do-modelo>
```

### Output com caminho Windows invalido

```
No such file or directory: '/repo/C:\Users\...'
```

O `output.dir` no config tem um caminho absoluto Windows. O `--output-dir /app/output` do entrypoint tem prioridade, entao isso nao deve ocorrer ao usar o Docker Compose. Se ocorrer, verifique se esta usando o comando correto (sem passar `/repo` manualmente).

### Argumentos duplicados

```
gerador-cli: error: unrecognized arguments: /repo
```

Os argumentos `/repo --config --output-dir` ja estao no `entrypoint`. Nao passe-os novamente. Use apenas:

```powershell
docker compose run --rm gerador-cli --generate both
```
