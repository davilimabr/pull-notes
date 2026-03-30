# PullNotes

Ferramenta local em Python para gerar descricoes de Pull Requests e Release Notes a partir de um repositorio Git, usando LLM local (Ollama) para sumarizacao inteligente.

## Requisitos

- Python 3.10+
- Git instalado e acessivel no PATH
- Ollama (local ou via Docker)

## Setup rapido

Escolha **uma** das opcoes abaixo. Os scripts instalam o Ollama, baixam o modelo configurado e instalam o pacote Python automaticamente.

### Opcao A: Ollama local (sem Docker)

```bash
bash setup-local.sh
```

Instala o Ollama na maquina, baixa o modelo definido em `config.default.json` e instala o pacote `pullnotes`.

### Opcao B: Ollama via Docker

```bash
bash setup-docker.sh
```

Sobe o Ollama via Docker Compose, baixa o modelo definido em `config.default.json` e instala o pacote `pullnotes`.

> Requer [Docker](https://docs.docker.com/get-docker/) instalado.

### Executar

Apos o setup, use normalmente:

```bash
pullnotes /caminho/para/repo --config config.default.json --generate both
```

Para um intervalo especifico de commits:

```bash
pullnotes /caminho/para/repo --config config.default.json --range v1.0..v1.1 --generate both
```

---

## Instalacao manual

Se preferir instalar sem os scripts:

**1. Instalar o pacote**

```bash
pip install .
```

**2. Subir o Ollama** (Docker ou local)

```bash
# Docker
docker compose up -d

# Ou local (requer Ollama instalado: https://ollama.com/download)
ollama pull qwen2.5:14b
```

## Instalacao para desenvolvimento

```bash
pip install -e .
```

## Saidas

Os arquivos sao gerados em `{output_dir}/{nome_repo}/`:

```
{output_dir}/{repo}/
├── prs/
│   └── pr_{titulo}.md
├── releases/
│   └── release_{versao}.md
└── utils/
    ├── commit.json
    ├── conventions.md
    └── domain_profile_{repo}.json
```

## Configuracao

Use `config.default.json` como base e passe com `--config`:

```bash
pullnotes . --config config.default.json --range main..HEAD
```

## Estrutura

O codigo esta organizado em camadas sob `src/pullnotes/`:

- `cli.py`: parsing da CLI
- `config.py`: carga e validacao de configuracoes
- `domain/`: entidades, servicos e schemas
- `adapters/`: git, filesystem, llm e perfil de dominio
- `workflows/`: orquestracao principal (`sync.py`)
- `prompts/`: templates de prompt para o LLM
- `templates/`: templates markdown de saida (pr.md, release.md)

## Docker

O Docker e usado apenas para subir o Ollama:

```bash
docker compose up -d
```

## Documentacao

Documentacao completa em [docs/](docs/README.md).
