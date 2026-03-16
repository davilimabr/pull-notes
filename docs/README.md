# PullNotes - Documentacao

Ferramenta CLI para geracao automatica de Pull Requests e Release Notes a partir de commits Git, utilizando LLM local (Ollama) para sumarizacao inteligente.

## Indice da Documentacao

| Documento | Descricao |
|-----------|-----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitetura do sistema (Hexagonal, Clean Architecture, DDD) |
| [DESIGN_PATTERNS.md](DESIGN_PATTERNS.md) | Padroes de projeto utilizados |
| [MODULES.md](MODULES.md) | Documentacao detalhada de cada modulo |
| [WORKFLOWS.md](WORKFLOWS.md) | Fluxos principais e casos de uso |
| [CONFIGURATION.md](CONFIGURATION.md) | Configuracao e variaveis |
| [CLI.md](CLI.md) | Interface de linha de comando |
| [INTEGRATIONS.md](INTEGRATIONS.md) | Integracoes externas (Git, Ollama) |
| [ollama-gpu-cuda.md](ollama-gpu-cuda.md) | Configurar Ollama local para usar GPU NVIDIA (CUDA) |
| [DATA_MODELS.md](DATA_MODELS.md) | Modelos de dados e estruturas |

## Visao Geral

O **PullNotes** e uma ferramenta que automatiza a criacao de documentacao de releases e pull requests atraves de:

1. **Coleta de Commits**: Extrai commits do repositorio Git com metadados completos
2. **Classificacao**: Categoriza commits usando Conventional Commits (feat, fix, docs, etc.)
3. **Scoring de Importancia**: Calcula relevancia baseado em linhas alteradas, arquivos e keywords
4. **Sumarizacao via LLM**: Gera resumos inteligentes usando Ollama local (saida estruturada via LangChain)
5. **Geracao de Documentos**: Produz PR e Release Notes formatados a partir de templates markdown dinamicos

## Arquitetura em Alto Nivel

```
                    [CLI Interface]
                          |
    [CONFIG] --> [WORKFLOW ORCHESTRATION] <-- [TEMPLATES]
                          |
    +---------------------+---------------------+
    |                     |                     |
[ADAPTERS]          [DOMAIN SERVICES]    [COMPOSITION]
    |                     |                     |
+--subprocess       +--data_collection   +--template_parser
+--filesystem       +--aggregation       +--dynamic_fields
+--llm_structured   +--composition       +--export
+--domain_def       +--export
+--domain_profile
```

## Estrutura de Diretorios

```
pull-notes/
+-- src/pullnotes/
|   +-- __main__.py              # Entry point
|   +-- cli.py                   # Interface CLI
|   +-- config.py                # Carregamento de configuracao
|   +-- domain/                  # Camada de Dominio
|   |   +-- models.py            # Entidades (Commit)
|   |   +-- errors.py            # Excecoes de dominio
|   |   +-- schemas.py           # Schemas Pydantic (validacao)
|   |   +-- services/            # Servicos de negocio
|   |       +-- data_collection.py
|   |       +-- aggregation.py
|   |       +-- composition.py
|   |       +-- export.py
|   |       +-- template_parser.py
|   |       +-- dynamic_fields.py
|   +-- adapters/                # Adaptadores externos
|   |   +-- subprocess.py        # Integracao Git
|   |   +-- llm_structured.py    # Integracao Ollama/LangChain
|   |   +-- filesystem.py        # I/O e resolucao de paths
|   |   +-- domain_definition.py # Extracao de contexto do repo
|   |   +-- domain_profile.py    # Geracao de perfil de dominio
|   |   +-- prompt_debug.py      # Debug de prompts LLM
|   +-- workflows/               # Orquestracao
|   |   +-- sync.py              # Workflow principal
|   +-- prompts/                 # Templates de prompts LLM
|   +-- templates/               # Templates Markdown de saida
+-- config.default.json          # Configuracao padrao
+-- pyproject.toml               # Build e dependencias
+-- Dockerfile                   # Build Docker multi-stage
+-- docker-compose.yml           # Ollama + PullNotes
+-- docs/                        # Esta documentacao
```

## Requisitos

- **Python**: 3.10+
- **Git**: Instalado e acessivel no PATH
- **Ollama**: Daemon local rodando com modelo configurado

### Dependencias Python

```
pydantic>=2.0       # Validacao de dados e schemas estruturados
langchain>=0.3.0    # Framework LLM
langchain-ollama>=0.2.0  # Integracao Ollama via LangChain
langchain-core>=0.3.0    # Abstrações core do LangChain
ollama              # Cliente Python para Ollama
lxml                # XML parsing (dependencia legada)
```

## Instalacao Rapida

```bash
# Clonar repositorio
git clone <repo-url>
cd pull-notes

# Instalar em modo desenvolvimento
pip install -e .

# Configurar Ollama (se ainda nao configurado)
ollama pull qwen2.5:7b
```

## Uso Basico

```bash
# Gerar PR e Release Notes
pullnotes /path/to/repo --config config.default.json --range v1.0..v1.1

# Apenas PR
pullnotes /path/to/repo --config config.default.json --generate pr

# Sem LLM (fallback para subjects)
pullnotes /path/to/repo --config config.default.json --no-llm
```

## Saidas Geradas

Os arquivos sao organizados por repositorio dentro do diretorio de saida:

```
{output_dir}/{repo_name}/
├── prs/
│   └── pr_{titulo}.md          # Documento de Pull Request formatado
├── releases/
│   └── release_{versao}.md     # Release Notes
└── utils/
    ├── commit.json             # Dados completos dos commits
    ├── conventions.md          # Relatorio de conventional commits
    └── domain_profile_{repo}.json  # Perfil de dominio cacheado
```

## Fluxo de Dados

```
Git Repository
      |
      v
[Subprocess Adapter] --> git log, git show
      |
      v
[Data Collection] --> List[Commit]
      |
      v
[Aggregation] --> classify, score, group
      |
      v
[LLM Summarization] --> Ollama (via LangChain)
      |
      v
[Composition] --> render templates (template_parser + dynamic_fields)
      |
      v
[Export] --> prs/pr_*.md, releases/release_*.md, utils/
```

## Proximos Passos

Para entender cada aspecto do projeto em detalhes, consulte os documentos especificos listados no indice acima.
