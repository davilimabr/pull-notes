# Documentacao de Modulos

Este documento descreve cada modulo do projeto, suas funcoes e responsabilidades.

## Indice

1. [Entry Points](#entry-points)
2. [Configuracao](#configuracao)
3. [Domain - Models](#domain---models)
4. [Domain - Services](#domain---services)
5. [Adapters](#adapters)
6. [Workflows](#workflows)
7. [Prompts](#prompts)
8. [Templates](#templates)
9. [XML](#xml)

---

## Entry Points

### `__main__.py`

**Caminho:** `src/gerador_cli/__main__.py`

**Responsabilidade:** Entry point para execucao via `python -m gerador_cli`

```python
def main():
    """Entry point principal"""
    from .cli import run
    sys.exit(run())

if __name__ == "__main__":
    main()
```

### `cli.py`

**Caminho:** `src/gerador_cli/cli.py`

**Responsabilidade:** Interface de linha de comando e parsing de argumentos

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `build_parser()` | Cria ArgumentParser com todas as opcoes |
| `run()` | Parseia argumentos e executa workflow |

**Argumentos Suportados:**
- `repo` - Path do repositorio (padrao: ".")
- `--config` - Arquivo de configuracao JSON
- `--range` - Git revision range
- `--since` / `--until` - Filtro por data
- `--generate` - Tipo de output (pr/release/both)
- `--version` - Label de versao
- `--output-dir` - Diretorio de saida
- `--refresh-domain` - Reconstruir perfil de dominio
- `--model` - Override do modelo LLM
- `--no-llm` - Desabilitar sumarizacao LLM

---

## Configuracao

### `config.py`

**Caminho:** `src/gerador_cli/config.py`

**Responsabilidade:** Carregamento e validacao de configuracao JSON

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `load_config(path)` | Carrega JSON de configuracao |
| `validate_config(config, generate)` | Valida estrutura e campos obrigatorios |

**Validacoes Realizadas:**
- Presenca de keys obrigatorios (commit_types, importance, output)
- Valores nao-vazios
- Estrutura correta de nested objects
- Validacao condicional baseada em `--generate`

**Estrutura Esperada:**
```python
{
    "commit_types": dict,      # Mapeamento tipo -> {label, patterns}
    "importance": dict,        # Pesos e bonus
    "importance_bands": list,  # Faixas de importancia
    "output": dict,            # Diretorio de saida
    "templates": dict,         # Paths dos templates
    "domain": dict,            # Configuracao de dominio (opcional)
    "llm_model": str,          # Modelo Ollama
    "language": str            # Idioma de saida
}
```

---

## Domain - Models

### `domain/models.py`

**Caminho:** `src/gerador_cli/domain/models.py`

**Responsabilidade:** Definicao da entidade central `Commit`

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
    diff: str = ""              # Diff truncado

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
```

### `domain/errors.py`

**Caminho:** `src/gerador_cli/domain/errors.py`

**Responsabilidade:** Excecoes de dominio

```python
class DomainBuildError(Exception):
    """Erro na construcao do perfil de dominio"""
    pass
```

### `domain/domain_profile.py`

**Caminho:** `src/gerador_cli/domain/domain_profile.py`

**Responsabilidade:** Orquestracao da geracao do perfil de dominio

**Classe/Funcao Principal:**

```python
@dataclass
class DomainResult:
    output_path: Path    # Onde XML foi salvo
    xml_text: str        # Conteudo do XML

def build_domain_profile(
    repo_dir: Path,
    template_path: Path,
    xsd_path: Path,
    output_path: Path,
    model: str,
    config: dict
) -> DomainResult:
    """Orquestra extracao de contexto e geracao de XML"""
```

---

## Domain - Services

### `domain/services/data_collection.py`

**Caminho:** `src/gerador_cli/domain/services/data_collection.py`

**Responsabilidade:** Coleta de commits do repositorio Git

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `get_commits(repo_dir, range, since, until, config)` | Funcao principal de coleta |
| `parse_git_log(output)` | Parseia saida do git log |
| `trim_diff(diff, max_lines, max_bytes)` | Trunca diff para limites |
| `_prefix_origin_range(range)` | Fallback para origin/ refs |

**Fluxo:**
```
1. Executar git log com formato customizado
2. Parsear saida em List[Commit]
3. Fetch paralelo de body e diff (ThreadPoolExecutor)
4. Truncar diffs conforme configuracao
5. Retornar commits completos
```

### `domain/services/aggregation.py`

**Caminho:** `src/gerador_cli/domain/services/aggregation.py`

**Responsabilidade:** Classificacao, scoring e sumarizacao de commits

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `classify_commit(subject, types)` | Classifica commit por patterns |
| `compute_importance(commit, config)` | Calcula score de importancia |
| `group_commits_by_type(commits, config)` | Agrupa por tipo de mudanca |
| `summarize_commit_group(type, commits, ...)` | Resume grupo via LLM |
| `summarize_all_groups(grouped, config, model, output_type)` | Resume todos os grupos |
| `build_convention_report(commits)` | Gera relatorio de convencoes |

**Algoritmo de Scoring:**
```python
score = (additions + deletions) * weight_lines
       + len(files) * weight_files
       + keyword_bonus  # breaking, security, perf, hotfix
```

**Faixas de Importancia:**
- `low`: score < 3.0
- `medium`: 3.0 <= score < 6.0
- `high`: 6.0 <= score < 9.0
- `critical`: score >= 9.0

### `domain/services/composition.py`

**Caminho:** `src/gerador_cli/domain/services/composition.py`

**Responsabilidade:** Composicao de templates e geracao de campos via LLM

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `build_version_label(template, range)` | Constroi label de versao |
| `extract_json(raw_response)` | Extrai JSON de resposta LLM |
| `build_pr_fields(summaries, config, model)` | Gera campos do PR |
| `build_release_fields(summaries, domain, config, model, version)` | Gera campos de release |
| `render_template(template, values)` | Renderiza template markdown |
| `render_changes_by_type_from_summaries(summaries, config)` | Formata mudancas agrupadas |

**Campos Gerados para PR:**
```json
{
    "title": "Titulo do PR",
    "summary": "Resumo das mudancas",
    "risks": "Riscos identificados",
    "testing": "Instrucoes de teste"
}
```

**Campos Gerados para Release:**
```json
{
    "executive_summary": "Resumo executivo",
    "highlights": "Destaques da versao",
    "migration_notes": "Notas de migracao",
    "known_issues": "Problemas conhecidos",
    "internal_notes": "Notas internas"
}
```

### `domain/services/export.py`

**Caminho:** `src/gerador_cli/domain/services/export.py`

**Responsabilidade:** Exportacao de artefatos gerados

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `export_commits(commits, output_dir)` | Exporta commits.json |
| `export_convention_report(report, output_dir)` | Exporta conventions.md |
| `export_text_document(content, output_dir, filename)` | Exporta documento texto |

**Arquivos Gerados:**
- `commits.json` - Dados completos dos commits
- `conventions.md` - Relatorio de conventional commits
- `pr.md` - Documento de Pull Request
- `release.md` - Release Notes

---

## Adapters

### `adapters/subprocess.py`

**Caminho:** `src/gerador_cli/adapters/subprocess.py`

**Responsabilidade:** Wrapper para comandos Git

**Funcao Principal:**

```python
def run_git(repo_dir: Path, args: List[str]) -> str:
    """
    Executa comando git no repositorio especificado.

    Args:
        repo_dir: Path do repositorio
        args: Argumentos do comando git

    Returns:
        Saida stdout do comando

    Raises:
        subprocess.CalledProcessError: Se comando falhar
    """
```

**Comandos Utilizados:**
- `git log` - Lista commits
- `git show -s --format=%B` - Corpo do commit
- `git show --unified=3` - Diff do commit
- `git config --get remote.origin.url` - URL do repositorio

### `adapters/http.py`

**Caminho:** `src/gerador_cli/adapters/http.py`

**Responsabilidade:** Cliente para Ollama/LLM

**Funcao Principal:**

```python
def call_ollama(
    model: str,
    prompt: str,
    timeout_seconds: float | None = None
) -> str:
    """
    Chama modelo LLM via Ollama.

    Args:
        model: Nome do modelo (ex: deepseek-r1:8b)
        prompt: Prompt completo
        timeout_seconds: Timeout da requisicao

    Returns:
        Resposta do modelo (texto limpo)
    """
```

**Configuracao:**
- Temperature: 0.2 (deterministico)
- Timeout padrao: 10s (configuravel)

### `adapters/filesystem.py`

**Caminho:** `src/gerador_cli/adapters/filesystem.py`

**Responsabilidade:** Operacoes de I/O e resolucao de paths

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `resolve_path(path)` | Resolve path relativo para absoluto |
| `ensure_dir(path)` | Cria diretorio se nao existir |
| `repository_name(repo_dir)` | Extrai nome do repositorio |
| `sanitize_filename(name)` | Remove caracteres invalidos |

### `adapters/domain_definition.py`

**Caminho:** `src/gerador_cli/adapters/domain_definition.py`

**Responsabilidade:** Extracao de contexto do repositorio e geracao de XML de dominio

**Funcoes Principais:**

| Funcao | Descricao |
|--------|-----------|
| `iter_repo_files(repo_dir, max_total_bytes)` | Itera arquivos do repo |
| `safe_read(path, max_bytes)` | Leitura segura de arquivos |
| `build_repository_index(repo_dir, config)` | Cria indice do repositorio |
| `top_keywords(text, n)` | Extrai keywords principais |
| `extract_anchors(content)` | Detecta APIs, tables, events |
| `fill_domain_anchors(template, anchors)` | Popula template XML |
| `generate_domain_xml(repo_dir, template, xsd, model, config)` | Gera XML completo |
| `call_llm_for_xml(prompt, model, xsd_path)` | Chama LLM com validacao |

**Anchors Extraidos:**
- Keywords (top N palavras)
- API endpoints (REST patterns)
- SQL tables
- Events/handlers
- Services

---

## Workflows

### `workflows/sync.py`

**Caminho:** `src/gerador_cli/workflows/sync.py`

**Responsabilidade:** Orquestracao principal do workflow

**Funcao Principal:**

```python
def run_workflow(args: Namespace) -> int:
    """
    Executa workflow completo de geracao.

    Etapas:
    1. Validacao e setup
    2. Coleta de commits (paralelo)
    3. Preparacao de dominio (se release)
    4. Classificacao de commits
    5. Scoring de importancia
    6. Geracao de relatorios
    7. Sumarizacao via LLM
    8. Composicao de templates
    9. Exportacao de artefatos

    Returns:
        0 se sucesso, 1 se erro
    """
```

**Funcoes Auxiliares:**

| Funcao | Descricao |
|--------|-----------|
| `_classify_commits(commits, config)` | Classifica lista de commits |
| `_score_commits(commits, config)` | Pontua lista de commits |
| `_prepare_domain_text(repo, config, model)` | Prepara XML de dominio |
| `_generate_summaries_for_output(grouped, config, model, type)` | Gera sumarios |

---

## Prompts

### `prompts/__init__.py`

**Caminho:** `src/gerador_cli/prompts/__init__.py`

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
| `commit_summary.txt` | Resumir commit individual |
| `commit_group_summary_pr.txt` | Resumir grupo (tecnico/PR) |
| `commit_group_summary_release.txt` | Resumir grupo (user-facing) |
| `pr_fields.txt` | Gerar campos JSON do PR |
| `release_fields.txt` | Gerar campos JSON de release |
| `domain_xml.txt` | Preencher XML de dominio |

---

## Templates

### `templates/pr.md`

**Proposito:** Template markdown para Pull Request

**Placeholders:**
- `{{title}}` - Titulo do PR
- `{{summary}}` - Resumo das mudancas
- `{{changes_by_type}}` - Mudancas agrupadas por tipo
- `{{risks}}` - Riscos identificados
- `{{testing}}` - Instrucoes de teste

### `templates/release.md`

**Proposito:** Template markdown para Release Notes

**Placeholders:**
- `{{version}}` - Numero da versao
- `{{date}}` - Data de release
- `{{executive_summary}}` - Resumo executivo
- `{{highlights}}` - Destaques
- `{{changes_by_type}}` - Mudancas agrupadas
- `{{migration_notes}}` - Notas de migracao
- `{{known_issues}}` - Problemas conhecidos

---

## XML

### `xml/dominio.xml`

**Proposito:** Template de estrutura de dominio do repositorio

**Estrutura:**
```xml
<domainProfile>
    <repositoryName>{{repo_name}}</repositoryName>
    <domain>{{domain_description}}</domain>
    <entities>
        <entity name="..." description="..."/>
    </entities>
    <domainAnchors>
        <keywords>...</keywords>
        <apiEndpoints>...</apiEndpoints>
        <sqlTables>...</sqlTables>
    </domainAnchors>
</domainProfile>
```

### `xml/XSD_dominio.xml`

**Proposito:** Schema de validacao para o XML de dominio

**Validacoes:**
- Estrutura obrigatoria (repositoryName, domain)
- Tipos de dados
- Elementos opcionais (entities, anchors)
