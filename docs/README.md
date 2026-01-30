# Gerador de PR e Release Notes - Documentacao

Ferramenta CLI para geracao automatica de Pull Requests e Release Notes a partir de commits Git, utilizando LLM (Ollama) para sumarizacao inteligente.

## Indice da Documentacao

| Documento | Descricao |
|-----------|-----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitetura do sistema (Hexagonal, Clean Architecture, DDD) |
| [DESIGN_PATTERNS.md](DESIGN_PATTERNS.md) | Padroes de projeto utilizados |
| [MODULES.md](MODULES.md) | Documentacao detalhada de cada modulo |
| [WORKFLOWS.md](WORKFLOWS.md) | Fluxos principais e casos de uso |
| [CONFIGURATION.md](CONFIGURATION.md) | Configuracao e variaveis |
| [CLI.md](CLI.md) | Interface de linha de comando |
| [INTEGRATIONS.md](INTEGRATIONS.md) | Integracoes externas (Git, Ollama, XML) |
| [DATA_MODELS.md](DATA_MODELS.md) | Modelos de dados e estruturas |

## Visao Geral

O **Gerador de PR e Release Notes** e uma ferramenta que automatiza a criacao de documentacao de releases e pull requests atraves de:

1. **Coleta de Commits**: Extrai commits do repositorio Git com metadados completos
2. **Classificacao**: Categoriza commits usando Conventional Commits (feat, fix, docs, etc.)
3. **Scoring de Importancia**: Calcula relevancia baseado em linhas alteradas, arquivos e keywords
4. **Sumarizacao via LLM**: Gera resumos inteligentes usando Ollama local
5. **Geracao de Documentos**: Produz PR.md e Release Notes formatados

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
+--subprocess       +--data_collection   +--template rendering
+--filesystem       +--aggregation       +--field building
+--http (LLM)       +--composition       +--export
+--domain_def       +--export
```

## Estrutura de Diretorios

```
gerador-PR-relese-note/
+-- src/gerador_cli/
|   +-- __main__.py          # Entry point
|   +-- cli.py               # Interface CLI
|   +-- config.py            # Carregamento de configuracao
|   +-- domain/              # Camada de Dominio
|   |   +-- models.py        # Entidades (Commit)
|   |   +-- errors.py        # Excecoes
|   |   +-- domain_profile.py
|   |   +-- services/        # Servicos de negocio
|   +-- adapters/            # Adaptadores externos
|   +-- workflows/           # Orquestracao
|   +-- prompts/             # Templates de prompts LLM
|   +-- templates/           # Templates Markdown
|   +-- xml/                 # Schemas XML de dominio
+-- config.default.json      # Configuracao padrao
+-- pyproject.toml           # Build e dependencias
+-- docs/                    # Esta documentacao
```

## Requisitos

- **Python**: 3.10+
- **Git**: Instalado e acessivel no PATH
- **Ollama**: Daemon local rodando com modelo configurado

### Dependencias Python

```
lxml      # XML parsing e validacao XSD
ollama    # Cliente Python para Ollama
```

## Instalacao Rapida

```bash
# Clonar repositorio
git clone <repo-url>
cd gerador-PR-relese-note

# Instalar em modo desenvolvimento
pip install -e .

# Configurar Ollama (se ainda nao configurado)
ollama pull deepseek-r1:8b
```

## Uso Basico

```bash
# Gerar PR e Release Notes
gerador-cli /path/to/repo --config config.json --range v1.0..v1.1

# Apenas PR
gerador-cli /path/to/repo --config config.json --generate pr

# Sem LLM (fallback para subjects)
gerador-cli /path/to/repo --config config.json --no-llm
```

## Saidas Geradas

| Arquivo | Descricao |
|---------|-----------|
| `pr.md` | Documento de Pull Request formatado |
| `release.md` | Release Notes com sumario executivo |
| `commits.json` | Dados completos dos commits em JSON |
| `conventions.md` | Relatorio de aderencia a conventional commits |
| `dominio.xml` | Perfil de dominio extraido (para releases) |

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
[LLM Summarization] --> Ollama
      |
      v
[Composition] --> render templates
      |
      v
[Export] --> pr.md, release.md, commits.json
```

## Proximos Passos

Para entender cada aspecto do projeto em detalhes, consulte os documentos especificos listados no indice acima.
