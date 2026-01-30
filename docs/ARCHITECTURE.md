# Arquitetura do Sistema

Este documento descreve a arquitetura do Gerador de PR e Release Notes, incluindo os padroes arquiteturais adotados e a organizacao das camadas.

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
    | - subprocess.py   |           | - http.py         |
    | - filesystem.py   |           | - domain_def.py   |
    +-------------------+           +-------------------+
              |                               |
              +---------------+---------------+
                              |
                    +---------v---------+
                    |   DOMAIN CORE     |
                    +-------------------+
                    | - models.py       |
                    | - services/       |
                    | - errors.py       |
                    +-------------------+
```

**Adaptadores de Entrada (Driving Adapters):**
- `cli.py` - Interface de linha de comando
- `workflows/sync.py` - Orquestracao de fluxos

**Adaptadores de Saida (Driven Adapters):**
- `adapters/subprocess.py` - Integracao com Git
- `adapters/http.py` - Integracao com Ollama/LLM
- `adapters/filesystem.py` - Operacoes de I/O
- `adapters/domain_definition.py` - Extracao de contexto

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
|  (domain/models.py, domain/errors.py)                 |
+-------------------------------------------------------+
```

**Camada de Entities:**
- `domain/models.py` - Dataclass `Commit` (entidade central)
- `domain/errors.py` - Excecoes de dominio

**Camada de Use Cases:**
- `domain/services/data_collection.py` - Coleta de commits
- `domain/services/aggregation.py` - Classificacao e scoring
- `domain/services/composition.py` - Composicao de templates
- `domain/services/export.py` - Exportacao de artefatos

**Camada de Interface Adapters:**
- `adapters/*.py` - Traducao entre dominio e mundo externo
- `workflows/sync.py` - Orquestracao

**Camada de Frameworks:**
- `cli.py` - Parsing de argumentos
- Bibliotecas externas (lxml, ollama)

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
    # ...
```

**Servicos de Dominio:**
- `aggregation.py` - Logica de classificacao e scoring
- `composition.py` - Logica de construcao de documentos

**Value Objects (implicitos):**
- Campos compostos do Commit (files, additions, deletions)

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
          subprocess.py   http.py    filesystem.py
               |              |
               v              v
             [GIT]        [OLLAMA]
```

**Regra de Dependencia:** As dependencias sempre apontam para dentro, nunca para fora. O dominio nao conhece os adaptadores.

## Estrutura de Diretorios por Camada

```
src/gerador_cli/
|
+-- domain/                    # NUCLEO (Clean Architecture Core)
|   +-- models.py              # Entities
|   +-- errors.py              # Domain Exceptions
|   +-- domain_profile.py      # Domain Service
|   +-- services/              # Use Cases
|       +-- data_collection.py
|       +-- aggregation.py
|       +-- composition.py
|       +-- export.py
|
+-- adapters/                  # ADAPTADORES (Hexagonal Ports)
|   +-- subprocess.py          # Git Adapter
|   +-- http.py                # LLM Adapter
|   +-- filesystem.py          # I/O Adapter
|   +-- domain_definition.py   # Context Extraction Adapter
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
+-- xml/                       # RECURSOS
|   +-- dominio.xml            # Domain XML Template
|   +-- XSD_dominio.xml        # XML Schema
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
        +----> domain/services/aggregation.py
        |             |
        |             v
        +----> adapters/http.py (Ollama)
        |             |
        |             v
        +----> domain/services/composition.py
        |             |
        |             v
        +----> domain/services/export.py
                      |
                      v
               Arquivos de saida
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
| Novo LLM Provider | `adapters/http.py` | Implementar novo cliente |
| Novo Output Format | `domain/services/export.py` | Adicionar exportador |
| Nova Classificacao | `domain/services/aggregation.py` | Adicionar estrategia |
| Novo Template | `templates/` | Criar template markdown |
| Novo Prompt | `prompts/` | Criar prompt para LLM |
