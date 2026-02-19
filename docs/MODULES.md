# Documentacao de Modulos

Este documento descreve cada modulo do projeto, suas funcoes e responsabilidades.

## Indice

1. [Entry Points](#entry-points)
2. [Configuracao](#configuracao)
3. [Domain - Models e Schemas](#domain---models-e-schemas)
4. [Domain - Services](#domain---services)
5. [Adapters](#adapters)
6. [Workflows](#workflows)
7. [Prompts](#prompts)
8. [Templates](#templates)

---

## Entry Points

### `__main__.py`

**Caminho:** `src/pullnotes/__main__.py`

**Responsabilidade:** Entry point para execucao via `python -m pullnotes`

```python
def main():
    """Entry point principal"""
    from .cli import run
    sys.exit(run())

if __name__ == "__main__":
    main()
```

### `cli.py`

**Caminho:** `src/pullnotes/cli.py`

**Responsabilidade:** Interface de linha de comando e parsing de argumentos

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `build_parser()` | Cria ArgumentParser com todas as opcoes |
| `run()` | Parseia argumentos e executa workflow |

**Argumentos Suportados:**
- `repo` - Path do repositorio (padrao: ".")
- `--config` - Arquivo de configuracao JSON (obrigatorio)
- `--range` - Git revision range
- `--since` / `--until` - Filtro por data
- `--generate` - Tipo de output (pr/release/both)
- `--version` - Label de versao
- `--output-dir` - Diretorio de saida
- `--refresh-domain` - Reconstruir perfil de dominio
- `--model` - Override do modelo LLM
- `--no-llm` - Desabilitar sumarizacao LLM
- `--debug` - Habilitar logging em nivel DEBUG

---

## Configuracao

### `config.py`

**Caminho:** `src/pullnotes/config.py`

**Responsabilidade:** Carregamento e validacao de configuracao JSON

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `load_config(path)` | Carrega JSON de configuracao |
| `validate_config(config, generate)` | Valida estrutura e campos obrigatorios |

**Estrutura Esperada:**
```python
{
    "commit_types": dict,      # Mapeamento tipo -> {label, patterns}
    "importance": dict,        # Pesos e bonus
    "importance_bands": list,  # Faixas de importancia
    "output": dict,            # Diretorio de saida
    "templates": dict,         # Paths dos templates
    "domain": dict,            # Configuracao de dominio (para release)
    "llm_model": str,          # Modelo Ollama
    "llm_timeout_seconds": int,
    "llm_max_retries": int,
    "language": str,           # Idioma de saida (ex: pt-BR)
    "alerts": dict,            # Configuracao de alertas
    "diff": dict,              # Limites de extracao de ancoras
    "release": dict            # Config de versao e data
}
```

---

## Domain - Models e Schemas

### `domain/models.py`

**Caminho:** `src/pullnotes/domain/models.py`

**Responsabilidade:** Definicao da entidade central `Commit` e constantes de formato Git

**Classe Principal:**

```python
@dataclass
class Commit:
    # Identificacao
    sha: str                    # Hash completo

    # Metadados Git
    author_name: str
    author_email: str
    date: str                   # ISO-8601
    subject: str                # Primeira linha
    body: str = ""              # Corpo completo

    # Metricas de mudanca
    files: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    diff: str = ""              # Diff completo
    diff_anchors: Optional[DiffAnchors] = None  # Ancoras semanticas

    # Classificacao
    change_type: str = ""       # feat, fix, docs, etc.
    is_conventional: bool = True

    # Scoring
    importance_score: float = 0.0
    importance_band: str = "low"  # low, medium, high, critical

    # Output
    summary: str = ""           # Resumo LLM

    @property
    def short_sha(self) -> str:
        return self.sha[:7]
```

**Constantes:**
```python
COMMIT_MARKER = "__COMMIT__"
GIT_FORMAT = f"{COMMIT_MARKER}%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s"

SENSITIVE_FILENAMES = {".env"}
SENSITIVE_PREFIXES = (".env.",)

def is_sensitive_file(filename: str) -> bool:
    """Verifica se arquivo e sensivel (.env, .env.*)"""
```

### `domain/errors.py`

**Caminho:** `src/pullnotes/domain/errors.py`

**Responsabilidade:** Excecoes de dominio

```python
class DomainBuildError(Exception):
    """Erro na construcao do perfil de dominio"""
    pass
```

### `domain/schemas.py`

**Caminho:** `src/pullnotes/domain/schemas.py`

**Responsabilidade:** Schemas Pydantic para validacao de dados estruturados

**Schemas Principais:**

| Schema | Descricao |
|--------|-----------|
| `DiffKeyword` | Keyword extraida de diff (texto + tipo added/removed) |
| `DiffArtifact` | Artefato detectado em diff (kind + nome + tipo) |
| `DiffAnchors` | Conjunto de ancoras semanticas de um commit |
| `CommitGroupSummary` | Resumo de grupo de commits (lista de bullets) |
| `ProjectProfile` | Perfil completo do projeto gerado por LLM |
| `ProjectType` | Tipo e descricao do projeto |
| `Domain` | Informacoes de dominio do projeto |
| `DomainAnchors` | Ancoras extraidas do codebase |
| `DomainDetails` | Detalhes de negocio (regras, integracoes, usuarios-alvo) |

**Enums:**

```python
class ProjectKind(str, Enum):
    framework, web_service, web_app, mobile_app, desktop_app,
    data_pipeline, infrastructure, cli, library, package, other

class ArtifactKind(str, Enum):
    db_table, topic, queue, api_endpoint, event, service, file, config
```

---

## Domain - Services

### `domain/services/data_collection.py`

**Caminho:** `src/pullnotes/domain/services/data_collection.py`

**Responsabilidade:** Coleta de commits do repositorio Git

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `get_commits(repo_dir, range, since, until, config)` | Funcao principal de coleta |
| `parse_git_log(output)` | Parseia saida do git log |
| `extract_diff_anchors(diff_text, max_keywords, max_artifacts)` | Extrai ancoras semanticas do diff |

**Fluxo:**
```
1. Executar git log com formato customizado
2. Parsear saida em List[Commit]
3. Fetch paralelo de body e diff (ThreadPoolExecutor)
4. Extrair ancoras semanticas dos diffs (extract_diff_anchors)
5. Retornar commits completos com diff_anchors
```

### `domain/services/aggregation.py`

**Caminho:** `src/pullnotes/domain/services/aggregation.py`

**Responsabilidade:** Classificacao, scoring e sumarizacao de commits

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `classify_commit(subject, types)` | Classifica commit por patterns regex |
| `compute_importance(commit, config)` | Calcula score de importancia |
| `group_commits_by_type(commits, config)` | Agrupa e ordena por tipo |
| `summarize_commit_group(type, commits, ...)` | Resume grupo via LLM |
| `summarize_all_groups(grouped, config, model, output_type)` | Resume todos os grupos em paralelo |
| `build_convention_report(commits)` | Gera relatorio de aderencia a conventional commits |

**Algoritmo de Scoring:**
```python
score = (additions + deletions) * weight_lines
       + len(files) * weight_files
       + keyword_bonus  # breaking, security, perf, hotfix
```

### `domain/services/template_parser.py`

**Caminho:** `src/pullnotes/domain/services/template_parser.py`

**Responsabilidade:** Parsing de templates markdown em secoes estruturadas

**Classes:**

```python
@dataclass
class TemplateSection:
    heading: str        # Titulo da secao
    key: str            # Chave slugificada
    body: str           # Instrucoes para o LLM
    is_static: bool     # True se contem checkboxes
    level: int          # Nivel do heading markdown

@dataclass
class ParsedTemplate:
    title_instruction: str
    sections: List[TemplateSection]

    @property
    def dynamic_sections(self) -> List[TemplateSection]: ...
    @property
    def static_sections(self) -> List[TemplateSection]: ...
```

### `domain/services/dynamic_fields.py`

**Caminho:** `src/pullnotes/domain/services/dynamic_fields.py`

**Responsabilidade:** Geracao dinamica de schemas Pydantic e prompts a partir de templates

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `build_dynamic_schema(sections)` | Gera modelo Pydantic das secoes dinamicas |
| `build_dynamic_prompt(sections, ...)` | Gera prompt LLM para preenchimento |

### `domain/services/composition.py`

**Caminho:** `src/pullnotes/domain/services/composition.py`

**Responsabilidade:** Composicao de templates e geracao de campos via LLM

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `build_version_label(template, range)` | Constroi label de versao |
| `build_pr_fields(summaries, config, model, parsed_template)` | Gera campos do PR via LLM estruturado |
| `build_release_fields(summaries, domain, config, model, version, parsed_template)` | Gera campos de release |
| `render_template(parsed_template, title, fields, changes_by_type, alerts)` | Renderiza markdown final |
| `render_changes_by_type_from_summaries(summaries, config)` | Formata mudancas agrupadas por tipo |

**Nota:** Os campos gerados sao dinamicos e dependem das secoes do template. Secoes com checkboxes sao preservadas como estaticas; demais secoes sao preenchidas pelo LLM.

### `domain/services/export.py`

**Caminho:** `src/pullnotes/domain/services/export.py`

**Responsabilidade:** Exportacao de artefatos gerados

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `create_output_structure(output_dir, repo_name)` | Cria estrutura de subdiretorios |
| `export_commits(commits, utils_dir)` | Exporta commit.json |
| `export_convention_report(report, utils_dir)` | Exporta conventions.md |
| `export_pr(content, prs_dir, title)` | Exporta pr_{titulo}.md |
| `export_release(content, releases_dir, version)` | Exporta release_{versao}.md |

**Estrutura de Saida:**
```
{output_dir}/{repo_name}/
├── prs/
│   └── pr_{titulo}.md
├── releases/
│   └── release_{versao}.md
└── utils/
    ├── commit.json
    ├── conventions.md
    └── domain_profile_{repo}.json
```

---

## Adapters

### `adapters/subprocess.py`

**Caminho:** `src/pullnotes/adapters/subprocess.py`

**Responsabilidade:** Wrapper para comandos Git

**Funcao Principal:**

```python
def run_git(repo_dir: Path, args: List[str]) -> str:
    """
    Executa comando git no repositorio especificado.
    Raises subprocess.CalledProcessError se falhar.
    """
```

**Comandos Utilizados:**
- `git log` - Lista commits
- `git show -s --format=%B` - Corpo do commit
- `git show --unified=3` - Diff do commit
- `git config --get remote.origin.url` - URL do repositorio

### `adapters/llm_structured.py`

**Caminho:** `src/pullnotes/adapters/llm_structured.py`

**Responsabilidade:** Cliente LLM com saida estruturada usando LangChain + Ollama

**Funcao Principal:**

```python
def call_llm_structured(
    model: str,
    prompt: str,
    output_schema: Type[BaseModel],
    timeout_seconds: float = 600,
    max_retries: int = 3
) -> BaseModel:
    """
    Chama LLM via Ollama com saida validada por schema Pydantic.

    Estrategia:
    1. Tenta saida estruturada nativa (tool calling)
    2. Fallback: PydanticOutputParser com retry

    Returns: Instancia do output_schema validada
    """
```

**Configuracao:**
- Temperature: 0.2 (deterministico)
- Timeout: configuravel (padrao 600s)
- Retries: configuravel (padrao 3)

### `adapters/filesystem.py`

**Caminho:** `src/pullnotes/adapters/filesystem.py`

**Responsabilidade:** Operacoes de I/O e resolucao de paths

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `resolve_path(path)` | Resolve path relativo para absoluto |
| `ensure_dir(path)` | Cria diretorio se nao existir |
| `repository_name(repo_dir)` | Extrai nome do repositorio |
| `sanitize_filename(name)` | Remove caracteres invalidos |

### `adapters/domain_definition.py`

**Caminho:** `src/pullnotes/adapters/domain_definition.py`

**Responsabilidade:** Extracao de contexto e ancoras do repositorio

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `iter_repo_files(repo_dir, max_total_bytes)` | Itera arquivos do repo com limite de bytes |
| `safe_read(path, max_bytes)` | Leitura segura de arquivos |
| `build_repository_index(repo_dir, config)` | Cria indice textual do repositorio |
| `top_keywords(text, n)` | Extrai keywords mais frequentes |
| `extract_anchors(content)` | Detecta APIs, tabelas, eventos, servicos |

### `adapters/domain_profile.py`

**Caminho:** `src/pullnotes/adapters/domain_profile.py`

**Responsabilidade:** Geracao e cache do perfil de dominio do projeto via LLM

**Funcao Principal:**

```python
def build_domain_profile(
    repo_dir: Path,
    output_path: Path,
    model: str,
    config: dict,
    refresh: bool = False
) -> ProjectProfile:
    """
    Gera perfil de dominio JSON usando LLM com saida estruturada.

    - Indexa arquivos do repositorio
    - Extrai ancoras (keywords, artifacts)
    - Chama LLM para gerar ProjectProfile Pydantic
    - Cacheia resultado em JSON
    - Retorna ProjectProfile validado
    """
```

### `adapters/prompt_debug.py`

**Caminho:** `src/pullnotes/adapters/prompt_debug.py`

**Responsabilidade:** Salvamento de prompts LLM para debug e analise

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `set_prompt_output_dir(output_dir)` | Configura diretorio de saida para prompts |
| `save_prompt(prompt, name, response)` | Salva prompt e resposta em arquivo |

**Arquivos Gerados em `utils/prompts/`:**
- Formato: `{counter}_{HHMMSS}_{name}.txt`
- Conteudo: Prompt completo + Resposta do LLM

---

## Workflows

### `workflows/sync.py`

**Caminho:** `src/pullnotes/workflows/sync.py`

**Responsabilidade:** Orquestracao principal do workflow em fases paralelas

**Funcao Principal:**

```python
def run_workflow(args: Namespace) -> int:
    """
    Executa workflow completo de geracao.

    Fase 0: Setup (config, paths, output structure)
    Fase A: Paralelo - commits + domain profile
    Fase B: Classificacao, scoring, agrupamento
    Fase C: Paralelo - summaries PR + Release
    Fase D: Campos via LLM (PR + Release em paralelo)
    Fase E: Renderizacao + Exportacao

    Returns: 0 se sucesso, 1 se erro
    """
```

---

## Prompts

### `prompts/__init__.py`

**Caminho:** `src/pullnotes/prompts/__init__.py`

**Responsabilidade:** Carregamento e renderizacao de templates de prompt

**Funcoes:**

```python
def load_prompt(name: str) -> str:
    """Carrega prompt do arquivo {name}.txt"""

def render_prompt_template(template: str, values: dict) -> str:
    """Substitui {{key}} por values[key]"""
```

### Arquivos de Prompt

| Arquivo | Proposito |
|---------|-----------|
| `commit_group_summary_pr.txt` | Resumir grupo de commits (tecnico/PR) |
| `commit_group_summary_release.txt` | Resumir grupo de commits (user-facing/release) |
| `domain_profile.txt` | Gerar perfil de dominio JSON do projeto |
| `dynamic_fields.txt` | Preencher secoes dinamicas de PR e Release |

---

## Templates

### `templates/pr.md`

**Proposito:** Template markdown para Pull Request

Define secoes com instrucoes para o LLM. Secoes com checkboxes sao preservadas como conteudo estatico. A secao "Alteracoes" (ou "Changes") recebe automaticamente as mudancas agrupadas por tipo.

### `templates/release.md`

**Proposito:** Template markdown para Release Notes

Define secoes com instrucoes para o LLM. O titulo inclui automaticamente o label de versao e data.
