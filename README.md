# PullNotes

Ferramenta local em Python para gerar descricoes de Pull Requests e Release Notes a partir de um repositorio Git, usando LLM local (Ollama) para sumarizacao inteligente.

## Requisitos

- Python 3.10+
- Git instalado e acessivel no PATH
- Ollama rodando localmente com o modelo configurado

## Instalacao

```bash
pip install -e .
```

## Uso rapido

```bash
# Gerar PR e Release Notes
pullnotes /caminho/para/repo --config config.default.json --range v1.0..v1.1

# Ou via modulo Python
python -m pullnotes /caminho/para/repo --config config.default.json --range v1.0..v1.1
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

```bash
# Rodar via Docker Compose (com Ollama integrado)
docker-compose --profile run up
```

## Documentacao

Documentacao completa em [docs/](docs/README.md).
