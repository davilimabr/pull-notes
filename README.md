# PullNotes

Ferramenta local em Python para gerar descricoes de Pull Requests e Release Notes a partir de um repositorio Git, usando LLM local (Ollama) para sumarizacao inteligente.

## Requisitos

- Python 3.10+
- Docker (para o Ollama)
- Git instalado e acessivel no PATH

## Inicio rapido

**1. Instalar a ferramenta**

Abra o PowerShell como administrador e execute:

```powershell
pip install .
```

**2. Subir o Ollama**

```bash
docker compose up -d
```

**3. Executar**

```bash
pullnotes /caminho/para/repo --config config.default.json --generate both
```

Para um intervalo especifico de commits:

```bash
pullnotes /caminho/para/repo --config config.default.json --range v1.0..v1.1 --generate both
```

---

## Instalacao para desenvolvimento

Abra o PowerShell como administrador e execute:

```powershell
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

## Alternativa: Ollama local (sem Docker)

Se preferir rodar o Ollama diretamente na maquina, sem Docker:

**1. Instalar o Ollama**

Baixe e instale em [ollama.com/download](https://ollama.com/download).

**2. Baixar o modelo**

```bash
ollama pull qwen3.5:9b
```

> O modelo padrao usado pelo PullNotes e o `qwen3.5:9b`. O download pode levar alguns minutos dependendo da sua conexao (~4 GB).

**3. Iniciar o servidor Ollama**

```bash
ollama serve
```

O servidor ficara disponivel em `http://localhost:11434`.

**4. Executar o PullNotes normalmente**

```bash
pullnotes /caminho/para/repo --config config.default.json --generate both
```


## Documentacao

Documentacao completa em [docs/](docs/README.md).
