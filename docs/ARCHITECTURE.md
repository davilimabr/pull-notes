# Arquitetura do Sistema

Este documento descreve a arquitetura do PullNotes, incluindo os padroes arquiteturais adotados e a organizacao das camadas.

## Padroes Arquiteturais Utilizados

O projeto implementa uma combinacao de tres padroes arquiteturais complementares:

### 1. Arquitetura Hexagonal (Ports & Adapters)

A arquitetura hexagonal separa o nucleo da aplicacao (dominio) das preocupacoes externas atraves de portas e adaptadores.

```
                    +---------------------------+
                    |      CLI Interface        |
                    +---------------------------+
                              |
              +---------------+---------------+
              |                               |
    +---------v---------+           +---------v---------+
    |     ADAPTERS      |           |     ADAPTERS      |
    |   (Ports In)      |           |   (Ports Out)     |
    +-------------------+           +-------------------+
    | - subprocess.py   |           | - llm_structured  |
    | - filesystem.py   |           | - domain_def.py   |
    +-------------------+           | - domain_profile  |
              |                     +-------------------+
              +---------------+---------------+
                              |
                    +---------v---------+
                    |   DOMAIN CORE     |
                    +-------------------+
                    | - models.py       |
                    | - schemas.py      |
                    | - services/       |
                    | - errors.py       |
                    +-------------------+
```

**Adaptadores de Entrada (Driving Adapters):**
- `cli.py` - Interface de linha de comando
- `workflows/sync.py` - Orquestracao de fluxos

**Adaptadores de Saida (Driven Adapters):**
- `adapters/subprocess.py` - Integracao com Git
- `adapters/llm_structured.py` - Integracao com Ollama via LangChain (saida estruturada)
- `adapters/filesystem.py` - Operacoes de I/O
- `adapters/domain_definition.py` - Extracao de contexto do repositorio
- `adapters/domain_profile.py` - Geracao e cache do perfil de dominio

### 2. Clean Architecture (Camadas)

O projeto segue os principios de Clean Architecture com separacao clara de responsabilidades:

```
+-------------------------------------------------------+
|                  Frameworks & Drivers                  |
|  (cli.py, __main__.py, external libraries)            |
+-------------------------------------------------------+
                          |
+-------------------------------------------------------+
|                 Interface Adapters                     |
|  (adapters/*.py, workflows/sync.py)                   |
+-------------------------------------------------------+
                          |
+-------------------------------------------------------+
|                    Use Cases                           |
|  (domain/services/*.py)                               |
+-------------------------------------------------------+
                          |
+-------------------------------------------------------+
|                     Entities                           |
|  (domain/models.py, domain/schemas.py, errors.py)    |
+-------------------------------------------------------+
```

**Camada de Entities:**
- `domain/models.py` - Dataclass `Commit` (entidade central)
- `domain/schemas.py` - Schemas Pydantic para validacao estruturada
- `domain/errors.py` - Excecoes de dominio

**Camada de Use Cases:**
- `domain/services/data_collection.py` - Coleta de commits
- `domain/services/aggregation.py` - Classificacao e scoring
- `domain/services/composition.py` - Composicao de templates
- `domain/services/template_parser.py` - Parsing de templates markdown
- `domain/services/dynamic_fields.py` - Geracao dinamica de schemas Pydantic
- `domain/services/export.py` - Exportacao de artefatos

**Camada de Interface Adapters:**
- `adapters/*.py` - Traducao entre dominio e mundo externo
- `workflows/sync.py` - Orquestracao

**Camada de Frameworks:**
- `cli.py` - Parsing de argumentos
- Bibliotecas externas (pydantic, langchain, ollama)

### 3. Domain-Driven Design (DDD)

Elementos de DDD implementados no projeto:

**Entidade Principal:**
```python
@dataclass
class Commit:
    sha: str              # Identidade unica
    author_name: str
    date: str
    subject: str
    change_type: str      # Contexto de dominio
    importance_score: float
    importance_band: str
    diff_anchors: Optional[DiffAnchors]  # Value object
    # ...
```

**Value Objects (via Pydantic):**
- `DiffAnchors` - Ancoras semanticas extraidas do diff
- `DiffKeyword`, `DiffArtifact` - Componentes das ancoras
- `ProjectProfile`, `Domain`, `DomainAnchors` - Perfil do projeto

**Servicos de Dominio:**
- `aggregation.py` - Logica de classificacao e scoring
- `composition.py` - Logica de construcao de documentos
- `template_parser.py` - Parsing de templates em secoes estruturadas
- `dynamic_fields.py` - Criacao de schemas Pydantic a partir de templates

## Diagrama de Dependencias

```
                        cli.py
                           |
                           v
                      config.py
                           |
                           v
                   workflows/sync.py
                    /      |      \
                   /       |       \
                  v        v        v
          data_collection  aggregation  composition
               |              |             |
               v              v             v
          subprocess.py  llm_structured  filesystem.py
               |              |
               v              v
             [GIT]        [OLLAMA]
                       (via LangChain)
```

**Regra de Dependencia:** As dependencias sempre apontam para dentro, nunca para fora. O dominio nao conhece os adaptadores.

## Estrutura de Diretorios por Camada

```
src/pullnotes/
|
+-- domain/                    # NUCLEO (Clean Architecture Core)
|   +-- models.py              # Entities
|   +-- errors.py              # Domain Exceptions
|   +-- schemas.py             # Pydantic Schemas (Value Objects)
|   +-- services/              # Use Cases
|       +-- data_collection.py
|       +-- aggregation.py
|       +-- composition.py
|       +-- template_parser.py
|       +-- dynamic_fields.py
|       +-- export.py
|
+-- adapters/                  # ADAPTADORES (Hexagonal Ports)
|   +-- subprocess.py          # Git Adapter
|   +-- llm_structured.py      # LLM Adapter (LangChain + Ollama)
|   +-- filesystem.py          # I/O Adapter
|   +-- domain_definition.py   # Context Extraction Adapter
|   +-- domain_profile.py      # Domain Profile Generation Adapter
|   +-- prompt_debug.py        # Debug Adapter (prompts/respostas)
|
+-- workflows/                 # ORQUESTRACAO
|   +-- sync.py                # Main Workflow Coordinator
|
+-- prompts/                   # RECURSOS
|   +-- *.txt                  # Prompt Templates
|
+-- templates/                 # RECURSOS
|   +-- *.md                   # Output Templates
|
+-- cli.py                     # INTERFACE (Driving Adapter)
+-- config.py                  # CONFIGURACAO
+-- __main__.py                # ENTRY POINT
```

## Fluxo de Controle

```
1. Usuario executa CLI
        |
        v
2. cli.py parseia argumentos
        |
        v
3. config.py carrega e valida configuracao
        |
        v
4. workflows/sync.py coordena execucao
        |
        +----> adapters/subprocess.py (Git)
        |             |
        |             v
        |      domain/services/data_collection.py
        |             |
        |             v
        +----> adapters/domain_profile.py (Perfil JSON)
        |             |
        |             v
        +----> domain/services/aggregation.py
        |             |
        |             v
        +----> adapters/llm_structured.py (Ollama/LangChain)
        |             |
        |             v
        +----> domain/services/composition.py
        |      domain/services/template_parser.py
        |      domain/services/dynamic_fields.py
        |             |
        |             v
        +----> domain/services/export.py
                      |
                      v
               Arquivos de saida (prs/, releases/, utils/)
```

## Beneficios da Arquitetura

1. **Testabilidade**: Dominio pode ser testado isoladamente
2. **Flexibilidade**: Adaptadores podem ser substituidos (ex: trocar Ollama por OpenAI)
3. **Manutencao**: Mudancas em uma camada nao afetam outras
4. **Clareza**: Responsabilidades bem definidas por camada
5. **Escalabilidade**: Facil adicionar novos casos de uso ou adaptadores

## Pontos de Extensao

| Extensao | Local | Descricao |
|----------|-------|-----------|
| Novo LLM Provider | `adapters/llm_structured.py` | Implementar novo cliente estruturado |
| Novo Output Format | `domain/services/export.py` | Adicionar exportador |
| Nova Classificacao | `domain/services/aggregation.py` | Adicionar estrategia |
| Novo Template | `templates/` | Criar template markdown |
| Novo Prompt | `prompts/` | Criar prompt para LLM |
