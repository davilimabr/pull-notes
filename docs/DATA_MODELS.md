# Modelos de Dados

Este documento descreve as estruturas de dados utilizadas no projeto.

## Entidade Principal: Commit

### Definicao

**Arquivo:** `domain/models.py`

```python
from dataclasses import dataclass, field
from typing import List, Optional

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
    diff: str = ""              # Diff completo do commit
    diff_anchors: Optional[DiffAnchors] = None  # Ancoras semanticas extraidas

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

### Ciclo de Vida

```
1. CRIACAO (parse_git_log)
   +-- sha, author_name, author_email, date, subject
   +-- files, additions, deletions (do numstat)

2. ENRIQUECIMENTO (fetch_commit_details - paralelo)
   +-- body (git show -s --format=%B)
   +-- diff (git show --unified=3)
   +-- diff_anchors (extract_diff_anchors)

3. CLASSIFICACAO (classify_commit)
   +-- change_type
   +-- is_conventional

4. SCORING (compute_importance)
   +-- importance_score
   +-- importance_band

5. SUMARIZACAO (summarize_commit_group)
   +-- summary (via LLM, usando diff_anchors)
```

---

## DiffAnchors (Ancoras Semanticas de Diff)

### Definicao

**Arquivo:** `domain/schemas.py`

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class DiffKeyword(BaseModel):
    """Keyword extraida de linhas do diff."""
    text: str = Field(..., min_length=1)
    change_type: Literal["added", "removed"]

class DiffArtifact(BaseModel):
    """Artefato detectado no diff (endpoint, servico, etc.)."""
    kind: ArtifactKind  # api_endpoint, service, db_table, event, etc.
    name: str = Field(..., min_length=1)
    change_type: Literal["added", "removed"]

class DiffAnchors(BaseModel):
    """Ancoras semanticas extraidas do diff de um commit."""
    files_changed: List[str] = Field(default_factory=list)
    keywords: List[DiffKeyword] = Field(default_factory=list)
    artifacts: List[DiffArtifact] = Field(default_factory=list)
```

### Exemplo JSON

```json
{
  "files_changed": ["src/auth.py", "src/models/user.py"],
  "keywords": [
    {"text": "login", "change_type": "added"},
    {"text": "jwt", "change_type": "added"},
    {"text": "session", "change_type": "removed"}
  ],
  "artifacts": [
    {"kind": "api_endpoint", "name": "POST /api/login", "change_type": "added"},
    {"kind": "service", "name": "AuthService", "change_type": "added"}
  ]
}
```

### Vantagens sobre Diff Bruto

| Aspecto | Diff Bruto | DiffAnchors |
|---------|-----------|-------------|
| Tamanho | Potencialmente grande | ~200-500 bytes |
| Contexto | Codigo bruto | Semanticamente relevante |
| Informacao | Linhas + / - | Keywords + Artifacts tipados |
| LLM | Mais propenso a alucinacao | Contexto preciso e estruturado |

---

## CommitGroupSummary

### Definicao

**Arquivo:** `domain/schemas.py`

```python
class CommitGroupSummary(BaseModel):
    """Resumo de um grupo de commits gerado pelo LLM."""
    summary_points: List[str] = Field(min_length=1)
```

Retornado por cada chamada LLM de sumarizacao de grupo.

---

## ProjectProfile (Perfil de Dominio)

### Definicao

**Arquivo:** `domain/schemas.py`

```python
class ProjectProfile(BaseModel):
    """Perfil completo do projeto gerado por LLM."""
    project: ProjectType
    domain: Domain
    confidence: float = Field(ge=0.0, le=1.0)

class ProjectType(BaseModel):
    kind: ProjectKind  # cli, web_service, library, etc.
    name: str
    description: str

class Domain(BaseModel):
    summary: str
    key_concepts: List[str]
    domain_details: DomainDetails
    domain_anchors: DomainAnchors

class DomainDetails(BaseModel):
    business_rules: List[str]
    integrations: List[str]
    target_users: List[str]

class DomainAnchors(BaseModel):
    keywords: List[Keyword] = []
    artifacts: List[Artifact] = []
```

### Estrutura JSON Cacheada

O perfil e salvo em `utils/domain_profile_{repo}.json`:

```json
{
  "project": {
    "kind": "cli",
    "name": "meu-projeto",
    "description": "Descricao do projeto"
  },
  "domain": {
    "summary": "Descricao do dominio gerada pelo LLM",
    "key_concepts": ["usuario", "pedido", "produto"],
    "domain_details": {
      "business_rules": ["Regra 1", "Regra 2"],
      "integrations": ["Ollama API", "Git CLI"],
      "target_users": ["Desenvolvedores"]
    },
    "domain_anchors": {
      "keywords": [
        {"text": "commit", "source": "README.md"},
        {"text": "release", "source": "src/export.py"}
      ],
      "artifacts": [
        {"kind": "service", "name": "DataCollection"},
        {"kind": "service", "name": "Aggregation"}
      ]
    }
  },
  "confidence": 0.85
}
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
    "commit_types": {
        "feat": {"label": "Funcionalidades", "patterns": [...]},
        "fix": {"label": "Ajustes", "patterns": [...]},
        # ...
    },
    "other_label": "Other",
    "importance": {
        "weight_lines": 0.02,
        "weight_files": 0.6,
        "keyword_bonus": {"breaking": 3.0, ...}
    },
    "importance_bands": [
        {"name": "low", "min": 0.0},
        {"name": "medium", "min": 3.0},
        # ...
    ],
    "diff": {"max_anchors_keywords": 10, "max_anchors_artifacts": 10},
    "domain": {
        "output_path": "domain_profile.json",
        "model": "qwen2.5:7b",
        "max_total_bytes": 400000,
        "max_file_bytes": 40000
    },
    "output": {"dir": "./output"},
    "llm_model": "qwen2.5:7b",
    "llm_timeout_seconds": 600,
    "llm_max_retries": 3,
    "language": "pt-BR",
    "alerts": {"none_text": "None."},
    "templates": {
        "pr": "templates/pr.md",
        "release": "templates/release.md"
    },
    "release": {"version_template": "{revision_range}", "date_format": "%Y-%m-%d"}
}
```

---

## Estruturas de Template Parsing

### TemplateSection e ParsedTemplate

**Arquivo:** `domain/services/template_parser.py`

```python
@dataclass
class TemplateSection:
    heading: str        # Titulo da secao
    key: str            # Chave slugificada (para injecao de valores)
    body: str           # Instrucoes para o LLM preencher
    is_static: bool     # True se contem checkboxes (conteudo estatico)
    level: int          # Nivel do heading (1, 2, 3...)

@dataclass
class ParsedTemplate:
    title_instruction: str
    sections: List[TemplateSection]

    @property
    def dynamic_sections(self) -> List[TemplateSection]:
        """Secoes que o LLM deve preencher"""

    @property
    def static_sections(self) -> List[TemplateSection]:
        """Secoes preservadas como estao (checkboxes)"""
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
        "WIP"
    ]
}
```

---

## Arquivos de Saida

### utils/commit.json

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
    "diff_anchors": {
      "files_changed": ["src/auth.py", "src/models/user.py"],
      "keywords": [
        {"text": "login", "change_type": "added"},
        {"text": "jwt", "change_type": "added"}
      ],
      "artifacts": [
        {"kind": "api_endpoint", "name": "POST /api/login", "change_type": "added"}
      ]
    },
    "change_type": "feat",
    "is_conventional": true,
    "importance_score": 7.5,
    "importance_band": "high",
    "summary": "Nova autenticacao JWT implementada..."
  }
]
```

### prs/pr_{titulo}.md

Arquivo markdown gerado a partir do template `templates/pr.md`, com:
- Titulo gerado pelo LLM
- Secoes dinamicas preenchidas pelo LLM (descricao, riscos, testes, etc.)
- Secao de alteracoes com mudancas agrupadas por tipo de commit
- Secoes estaticas (checkboxes) preservadas do template original

### releases/release_{versao}.md

Arquivo markdown gerado a partir do template `templates/release.md`, com:
- Titulo com versao e data
- Secoes dinamicas preenchidas pelo LLM
- Secao de alteracoes com mudancas agrupadas por tipo
- Secoes estaticas preservadas do template

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
| fetch_details()    |  (paralelo via ThreadPoolExecutor)
| Commit -> Commit   |
| (+body, +diff,     |
|  +diff_anchors)    |
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
| summarize_group()  |  (paralelo: PR + Release)
| Groups -> Summaries|
| CommitGroupSummary |
+--------------------+
     |
     v
+--------------------+
| build_*_fields()   |  (paralelo: PR + Release)
| Summaries -> Fields|
| (schema dinamico)  |
+--------------------+
     |
     v
+--------------------+
| render_template()  |
| Fields -> Markdown |
+--------------------+
     |
     v
OUTPUT FILES
(prs/, releases/, utils/)
```
