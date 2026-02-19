# Integracoes Externas

Este documento descreve as integracoes da ferramenta com sistemas externos.

## Visao Geral

```
+-------------------+     +-------------------+     +-------------------+
|    PullNotes      |---->|       Git         |     |      Ollama       |
|                   |     |  (subprocess)     |     |  (LangChain API)  |
|   +----------+    |     +-------------------+     +-------------------+
|   | Adapters |----+---->|    Filesystem     |
|   +----------+    |     |   (pathlib)       |
+-------------------+     +-------------------+
```

---

## 1. Git

### Descricao

O Git e usado para coletar informacoes de commits do repositorio.

### Adapter

**Arquivo:** `adapters/subprocess.py`

```python
def run_git(repo_dir: Path, args: List[str]) -> str:
    """
    Executa comando git no repositorio.

    Args:
        repo_dir: Path do repositorio
        args: Lista de argumentos git

    Returns:
        Saida stdout do comando
    """
    result = subprocess.run(
        ['git', '-C', str(repo_dir)] + args,
        capture_output=True,
        text=True,
        check=True,
        encoding='utf-8'
    )
    return result.stdout
```

### Comandos Utilizados

| Comando | Proposito | Modulo |
|---------|-----------|--------|
| `git log` | Listar commits com metadata | data_collection.py |
| `git show -s --format=%B <sha>` | Obter corpo do commit | data_collection.py |
| `git show --unified=3 <sha>` | Obter diff do commit | data_collection.py |
| `git config --get remote.origin.url` | Nome do repositorio | filesystem.py |

### Formato do Git Log

```bash
git log --date=iso-strict \
        --pretty=format:"__COMMIT__%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s" \
        --numstat \
        [range]
```

**Campos:**
- `%H` - Hash completo
- `%an` - Nome do autor
- `%ae` - Email do autor
- `%ad` - Data (ISO-8601)
- `%s` - Subject (primeira linha)
- `--numstat` - Estatisticas de linhas (+/-)

### Tratamento de Erros

```python
try:
    output = run_git(repo_dir, ['log', range])
except subprocess.CalledProcessError:
    # Tentar com prefixo origin/
    prefixed_range = _prefix_origin_range(range)
    output = run_git(repo_dir, ['log', prefixed_range])
```

### Requisitos

- Git instalado e acessivel no PATH
- Repositorio valido com historico de commits
- Permissao de leitura no repositorio

---

## 2. Ollama (LLM via LangChain)

### Descricao

Ollama e usado para inferencia de LLM local. A integracao utiliza **LangChain** com suporte a **saida estruturada** (Pydantic), garantindo respostas validas e tipadas.

### Adapter

**Arquivo:** `adapters/llm_structured.py`

```python
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import PydanticOutputParser

def call_llm_structured(
    model: str,
    prompt: str,
    output_schema: Type[BaseModel],
    timeout_seconds: float = 600,
    max_retries: int = 3
) -> BaseModel:
    """
    Chama LLM via Ollama com saida validada por schema Pydantic.

    Estrategia de duas etapas:
    1. Tenta saida estruturada nativa (tool calling do modelo)
    2. Fallback: PydanticOutputParser com instrucoes de formato

    Args:
        model: Nome do modelo (ex: qwen2.5:7b)
        prompt: Prompt completo
        output_schema: Classe Pydantic para validacao da resposta
        timeout_seconds: Timeout da requisicao
        max_retries: Tentativas em caso de falha

    Returns:
        Instancia do output_schema validada
    """
```

### Configuracao

| Parametro | Valor | Descricao |
|-----------|-------|-----------|
| `temperature` | 0.2 | Baixa temperatura para respostas mais deterministicas |
| `timeout` | configuravel | Padrao 600s (ajustavel via config) |
| `max_retries` | configuravel | Padrao 3 (ajustavel via config) |

**Modelos Recomendados:**
| Modelo | Tamanho | Uso |
|--------|---------|-----|
| `qwen2.5:7b` | ~5GB | Padrao, excelente para instrucoes estruturadas |
| `llama3:8b` | ~5GB | Alternativa, bom desempenho geral |
| `mistral:7b` | ~4GB | Bom para ingles |

### Chamadas LLM no Sistema

| Servico | Prompt | Schema de Saida |
|---------|--------|-----------------|
| `summarize_commit_group()` | `commit_group_summary_pr.txt` | `CommitGroupSummary` |
| `summarize_commit_group()` | `commit_group_summary_release.txt` | `CommitGroupSummary` |
| `build_*_fields()` | `dynamic_fields.txt` | Schema dinamico por template |
| `build_domain_profile()` | `domain_profile.txt` | `ProjectProfile` |

### Saida Estruturada

Todas as chamadas LLM retornam objetos Pydantic validados, eliminando a necessidade de parsing manual de JSON:

```python
# Exemplo de schema usado para sumarizacao
class CommitGroupSummary(BaseModel):
    summary_points: List[str] = Field(min_length=1)

# Exemplo de schema para perfil de dominio
class ProjectProfile(BaseModel):
    project: ProjectType
    domain: Domain
    confidence: float = Field(ge=0.0, le=1.0)
```

### Requisitos

1. **Ollama instalado:**
   ```bash
   # Linux/Mac
   curl -fsSL https://ollama.ai/install.sh | sh

   # Windows
   # Baixar instalador de https://ollama.ai
   ```

2. **Servidor rodando:**
   ```bash
   ollama serve
   ```

3. **Modelo baixado:**
   ```bash
   ollama pull qwen2.5:7b
   ```

4. **Verificar:**
   ```bash
   ollama list
   # Deve mostrar o modelo instalado
   ```

### Troubleshooting Ollama

| Problema | Causa | Solucao |
|----------|-------|---------|
| Connection refused | Servidor parado | `ollama serve` |
| Model not found | Modelo nao baixado | `ollama pull <model>` |
| Timeout | Prompt muito longo | Aumentar `llm_timeout_seconds` no config |
| Out of memory | Modelo muito grande | Usar modelo menor |
| Structured output falha | Modelo sem suporte a tool calling | Fallback automatico para PydanticOutputParser |

---

## 3. Filesystem

### Descricao

Operacoes de leitura e escrita no sistema de arquivos local.

### Adapter

**Arquivo:** `adapters/filesystem.py`

### Funcoes Principais

```python
def resolve_path(path: str | Path) -> Path:
    """Resolve path relativo para absoluto"""
    return Path(path).resolve()

def ensure_dir(path: Path) -> None:
    """Cria diretorio se nao existir"""
    path.mkdir(parents=True, exist_ok=True)

def repository_name(repo_dir: Path) -> str:
    """Extrai nome do repositorio da URL origin"""
    url = run_git(repo_dir, ['config', '--get', 'remote.origin.url'])
    # Parse URL para extrair nome
    ...

def sanitize_filename(name: str) -> str:
    """Remove caracteres invalidos para nome de arquivo"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)
```

### Operacoes de I/O

| Operacao | Modulo | Descricao |
|----------|--------|-----------|
| Ler config JSON | config.py | `json.load()` |
| Ler prompts | prompts/__init__.py | `Path.read_text()` |
| Ler templates | composition.py | `Path.read_text()` |
| Escrever JSON | export.py | `json.dump()` |
| Escrever MD | export.py | `Path.write_text()` |

### Indexacao de Repositorio

Para extracao de dominio, o sistema indexa arquivos do repositorio:

```python
IGNORE_DIRS = {
    '.git', '__pycache__', 'node_modules',
    'venv', '.venv', 'dist', 'build'
}

INCLUDE_EXTENSIONS = {
    '.py', '.md', '.json', '.yaml', '.yml',
    '.txt', '.xml', '.html', '.css', '.js'
}

def iter_repo_files(repo_dir: Path, max_total_bytes: int):
    """
    Itera arquivos do repositorio respeitando limites de bytes.
    """
```

---

## Diagrama de Integracoes

```
                          +------------------+
                          |    PullNotes     |
                          +--------+---------+
                                   |
         +-------------------------+-------------------------+
         |                         |                         |
         v                         v                         v
+--------+--------+     +----------+----------+     +--------+--------+
|      GIT        |     |       OLLAMA        |     |    FILESYSTEM   |
|   subprocess    |     |   LangChain API     |     |    pathlib      |
+-----------------+     +---------------------+     +-----------------+
| - git log       |     | - ChatOllama        |     | - read files    |
| - git show      |     | - structured output |     | - write files   |
| - git config    |     | - temperature: 0.2  |     | - create dirs   |
+-----------------+     +---------------------+     +-----------------+
         |                         |                         |
         v                         v                         v
+--------+--------+     +----------+----------+     +--------+--------+
|   Repositorio   |     |   Modelo Local      |     |   Config/       |
|      Git        |     |  (qwen2.5, llama3)  |     |   Templates/    |
|                 |     |  Pydantic schemas   |     |   Output        |
+-----------------+     +---------------------+     +-----------------+
```

## Resumo de Dependencias

| Integracao | Biblioteca | Obrigatorio |
|------------|------------|-------------|
| Git | subprocess (stdlib) | Sim |
| Ollama | langchain-ollama, langchain-core | Sim* |
| Filesystem | pathlib (stdlib) | Sim |

\* Pode ser bypassed com `--no-llm`
