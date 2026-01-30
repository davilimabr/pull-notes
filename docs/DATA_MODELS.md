# Modelos de Dados

Este documento descreve as estruturas de dados utilizadas no projeto.

## Entidade Principal: Commit

### Definicao

**Arquivo:** `domain/models.py`

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Commit:
    """
    Representa um commit Git com metadados e analise.
    Entidade central do dominio.
    """

    # === Identificacao ===
    sha: str                    # Hash completo (40 chars)

    # === Metadados Git ===
    author_name: str            # Nome do autor
    author_email: str           # Email do autor
    date: str                   # Data ISO-8601 (ex: 2024-01-15T10:30:00-03:00)
    subject: str                # Primeira linha do commit (titulo)
    body: str = ""              # Corpo completo (apos primeira linha)

    # === Metricas de Mudanca ===
    files: List[str] = field(default_factory=list)  # Arquivos modificados
    additions: int = 0          # Total de linhas adicionadas
    deletions: int = 0          # Total de linhas removidas
    diff: str = ""              # Diff truncado do commit

    # === Classificacao ===
    change_type: str = ""       # Tipo: feat, fix, docs, refactor, etc.
    is_conventional: bool = True  # Segue conventional commits?

    # === Scoring ===
    importance_score: float = 0.0   # Score numerico calculado
    importance_band: str = "low"    # Faixa: low, medium, high, critical

    # === Output ===
    summary: str = ""           # Resumo gerado por LLM

    @property
    def short_sha(self) -> str:
        """Retorna SHA abreviado (7 chars)"""
        return self.sha[:7]
```

### Diagrama de Campos

```
+------------------------------------------------------------------+
|                            Commit                                 |
+------------------------------------------------------------------+
| IDENTIFICACAO                                                     |
|   sha: str              "abc123def456789..."                     |
|   short_sha: str        "abc123d" (property)                     |
+------------------------------------------------------------------+
| METADADOS GIT                                                     |
|   author_name: str      "John Doe"                               |
|   author_email: str     "john@example.com"                       |
|   date: str             "2024-01-15T10:30:00-03:00"             |
|   subject: str          "feat: add user authentication"          |
|   body: str             "Detailed description..."                |
+------------------------------------------------------------------+
| METRICAS DE MUDANCA                                               |
|   files: List[str]      ["src/auth.py", "src/models/user.py"]   |
|   additions: int        150                                      |
|   deletions: int        30                                       |
|   diff: str             "+def login(): ..."                      |
+------------------------------------------------------------------+
| CLASSIFICACAO                                                     |
|   change_type: str      "feat"                                   |
|   is_conventional: bool  True                                    |
+------------------------------------------------------------------+
| SCORING                                                           |
|   importance_score: float  7.5                                   |
|   importance_band: str     "high"                                |
+------------------------------------------------------------------+
| OUTPUT                                                            |
|   summary: str          "Nova autenticacao JWT implementada..."  |
+------------------------------------------------------------------+
```

### Ciclo de Vida

```
1. CRIACAO (parse_git_log)
   +-- sha, author_name, author_email, date, subject
   +-- files, additions, deletions (do numstat)

2. ENRIQUECIMENTO (fetch_commit_details)
   +-- body (git show -s --format=%B)
   +-- diff (git show --unified=3)

3. CLASSIFICACAO (classify_commit)
   +-- change_type
   +-- is_conventional

4. SCORING (compute_importance)
   +-- importance_score
   +-- importance_band

5. SUMARIZACAO (summarize_commit_group)
   +-- summary (via LLM)
```

---

## Constantes de Formato

### GIT_FORMAT

**Arquivo:** `domain/models.py`

```python
COMMIT_MARKER = "__COMMIT__"
GIT_FORMAT = f"{COMMIT_MARKER}%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s"
```

**Placeholders Git:**
| Placeholder | Significado |
|-------------|-------------|
| `%H` | Hash completo |
| `%an` | Author name |
| `%ae` | Author email |
| `%ad` | Author date |
| `%s` | Subject |
| `%B` | Body completo |
| `%x1f` | Separador (unit separator) |
| `%n` | Newline |

---

## Estruturas de Configuracao

### Config (dicionario)

```python
config = {
    # Tipos de commit
    "commit_types": {
        "feat": {"label": "Features", "patterns": [...]},
        "fix": {"label": "Correcoes", "patterns": [...]},
        # ...
    },

    # Pesos de importancia
    "importance": {
        "weight_lines": 0.02,
        "weight_files": 0.6,
        "keyword_bonus": {"breaking": 3.0, ...}
    },

    # Faixas de importancia
    "importance_bands": [
        {"name": "low", "min": 0.0},
        {"name": "medium", "min": 3.0},
        # ...
    ],

    # Dominio (para releases)
    "domain": {
        "template_path": "xml/dominio.xml",
        "xsd_path": "xml/XSD_dominio.xml",
        # ...
    },

    # Output
    "output": {"dir": "./output"},

    # LLM
    "llm_model": "deepseek-r1:8b",
    "llm_timeout_seconds": 600,

    # Templates
    "templates": {
        "pr": "templates/pr.md",
        "release": "templates/release.md"
    },

    # Outros
    "language": "pt-BR",
    "diff": {"max_bytes": 1000, "max_lines": 50},
    "release": {"version_template": "{revision_range}", "date_format": "%Y-%m-%d"}
}
```

---

## Estruturas de Saida

### PR Fields

```python
pr_fields = {
    "title": "feat: Implementacao de autenticacao de usuarios",
    "summary": "Este PR adiciona sistema completo de autenticacao...",
    "risks": "- Mudanca no schema do banco de dados\n- Necessita migracao",
    "testing": "1. Testar login com credenciais validas\n2. Testar logout..."
}
```

### Release Fields

```python
release_fields = {
    "executive_summary": "Esta versao traz melhorias significativas...",
    "highlights": "- Nova dashboard de metricas\n- Suporte a exportacao PDF",
    "migration_notes": "Execute `python migrate.py` antes de atualizar",
    "known_issues": "- Bug #123 em dispositivos iOS antigos",
    "internal_notes": "Revisar performance do endpoint /api/reports"
}
```

### Grouped Commits

```python
grouped_commits = [
    ("feat", [commit1, commit2, commit3]),
    ("fix", [commit4, commit5]),
    ("docs", [commit6]),
]
```

### Grouped Summaries

```python
grouped_summaries = [
    ("feat", "- Nova funcionalidade X\n- Melhoria em Y"),
    ("fix", "- Correcao do bug Z\n- Ajuste no calculo de W"),
]
```

---

## DomainResult

### Definicao

**Arquivo:** `domain/domain_profile.py`

```python
@dataclass
class DomainResult:
    """Resultado da geracao do perfil de dominio"""
    output_path: Path    # Onde o XML foi salvo
    xml_text: str        # Conteudo do XML gerado
```

### Estrutura do XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<domainProfile>
    <repositoryName>meu-projeto</repositoryName>

    <domain>
        Descricao do dominio do projeto gerada pelo LLM
        com base no codigo fonte analisado.
    </domain>

    <entities>
        <entity name="User" description="Representa um usuario do sistema"/>
        <entity name="Order" description="Pedido de compra"/>
        <entity name="Product" description="Produto do catalogo"/>
    </entities>

    <domainAnchors>
        <keywords>usuario, pedido, produto, carrinho, pagamento</keywords>
        <apiEndpoints>/api/users, /api/orders, /api/products</apiEndpoints>
        <sqlTables>users, orders, products, order_items</sqlTables>
        <events>UserCreated, OrderPlaced, PaymentProcessed</events>
        <services>UserService, OrderService, PaymentGateway</services>
    </domainAnchors>
</domainProfile>
```

---

## Convention Report

### Estrutura

```python
convention_report = {
    "total_commits": 50,
    "conventional_commits": 45,
    "non_conventional_commits": 5,
    "adherence_rate": 90.0,
    "by_type": {
        "feat": 20,
        "fix": 15,
        "docs": 5,
        "refactor": 3,
        "test": 2,
        "other": 5
    },
    "non_conventional_examples": [
        "Update readme",
        "Minor changes",
        "WIP",
        "Fix stuff",
        "..."
    ]
}
```

### Markdown Gerado

```markdown
# Relatorio de Conventional Commits

## Resumo
- Total de commits: 50
- Commits convencionais: 45 (90.0%)
- Commits nao-convencionais: 5 (10.0%)

## Distribuicao por Tipo
| Tipo | Quantidade |
|------|------------|
| feat | 20 |
| fix | 15 |
| docs | 5 |
| refactor | 3 |
| test | 2 |
| other | 5 |

## Commits Nao-Convencionais
- Update readme
- Minor changes
- WIP
- Fix stuff
- ...
```

---

## Arquivos de Saida

### commits.json

```json
[
  {
    "sha": "abc123def456...",
    "author_name": "John Doe",
    "author_email": "john@example.com",
    "date": "2024-01-15T10:30:00-03:00",
    "subject": "feat: add user authentication",
    "body": "Implements JWT authentication...",
    "files": ["src/auth.py", "src/models/user.py"],
    "additions": 150,
    "deletions": 30,
    "diff": "+def login():\n+    ...",
    "change_type": "feat",
    "is_conventional": true,
    "importance_score": 7.5,
    "importance_band": "high",
    "summary": "Nova autenticacao JWT implementada..."
  }
]
```

### pr.md

```markdown
# {{title}}

## Resumo
{{summary}}

## Mudancas por Tipo

### Features
- Nova funcionalidade X
- Melhoria em Y

### Correcoes
- Correcao do bug Z

## Riscos
{{risks}}

## Plano de Testes
{{testing}}
```

### release.md

```markdown
# Release Notes v{{version}}

**Data:** {{date}}

## Resumo Executivo
{{executive_summary}}

## Destaques
{{highlights}}

## Mudancas

### Features
- Nova funcionalidade X
- Melhoria em Y

### Correcoes
- Correcao do bug Z

## Notas de Migracao
{{migration_notes}}

## Problemas Conhecidos
{{known_issues}}

---
*Notas Internas:*
{{internal_notes}}
```

---

## Fluxo de Transformacao de Dados

```
GIT LOG OUTPUT
     |
     v
+--------------------+
| parse_git_log()    |
| String -> Commit[] |
+--------------------+
     |
     v
+--------------------+
| classify_commit()  |
| Commit -> Commit   |
| (+change_type)     |
+--------------------+
     |
     v
+--------------------+
| compute_importance |
| Commit -> Commit   |
| (+score, +band)    |
+--------------------+
     |
     v
+--------------------+
| group_by_type()    |
| Commit[] -> Groups |
+--------------------+
     |
     v
+--------------------+
| summarize_group()  |
| Groups -> Summaries|
+--------------------+
     |
     v
+--------------------+
| build_*_fields()   |
| Summaries -> JSON  |
+--------------------+
     |
     v
+--------------------+
| render_template()  |
| JSON -> Markdown   |
+--------------------+
     |
     v
OUTPUT FILES
```
