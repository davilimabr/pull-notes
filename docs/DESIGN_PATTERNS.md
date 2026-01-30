# Padroes de Projeto

Este documento descreve os Design Patterns utilizados no projeto, com exemplos de implementacao.

## Sumario de Padroes

| Padrao | Categoria | Localizacao | Proposito |
|--------|-----------|-------------|-----------|
| Adapter | Estrutural | `adapters/*.py` | Integrar sistemas externos |
| Service Layer | Arquitetural | `domain/services/*.py` | Encapsular logica de negocio |
| Strategy | Comportamental | `aggregation.py` | Classificacao configuravel |
| Template Method | Comportamental | `prompts/__init__.py` | Composicao de prompts |
| Builder | Criacional | `composition.py` | Construir estruturas complexas |
| Factory | Criacional | `config.py` | Criar configuracao validada |
| Repository | Estrutural | `export.py` | Persistir artefatos |

---

## 1. Adapter Pattern

**Proposito:** Converter a interface de uma classe em outra interface esperada pelo cliente.

**Localizacao:** `adapters/*.py`

### Exemplo: Git Adapter

```python
# adapters/subprocess.py

def run_git(repo_dir: Path, args: List[str]) -> str:
    """
    Adapter que converte chamadas de alto nivel em comandos Git.
    Isola o dominio dos detalhes de subprocess.
    """
    result = subprocess.run(
        ['git', '-C', str(repo_dir)] + args,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout
```

### Exemplo: LLM Adapter

```python
# adapters/http.py

def call_ollama(model: str, prompt: str, timeout_seconds: float = None) -> str:
    """
    Adapter que abstrai a comunicacao com Ollama.
    Permite trocar o LLM sem afetar o dominio.
    """
    client = ollama.Client(timeout=httpx.Timeout(timeout_seconds or 10.0))
    response = client.chat(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        options={'temperature': 0.2}
    )
    return response['message']['content'].strip()
```

**Beneficio:** O dominio chama `call_ollama()` sem conhecer detalhes HTTP ou a biblioteca Ollama.

---

## 2. Service Layer Pattern

**Proposito:** Encapsular logica de negocio em servicos coesos e reutilizaveis.

**Localizacao:** `domain/services/*.py`

### Servicos Implementados

```python
# domain/services/data_collection.py
def get_commits(repo_dir, revision_range, since, until, config) -> List[Commit]:
    """Servico de coleta de commits - encapsula toda logica de obtencao"""

# domain/services/aggregation.py
def classify_commit(subject, commit_types) -> Tuple[str, bool]:
    """Servico de classificacao - aplica regras de negocio"""

def compute_importance(commit, config) -> Tuple[float, str]:
    """Servico de scoring - calcula importancia do commit"""

# domain/services/composition.py
def build_pr_fields(summaries, config, model) -> Dict:
    """Servico de composicao - constroi campos do PR"""

# domain/services/export.py
def export_commits(commits, output_dir) -> Path:
    """Servico de exportacao - persiste dados"""
```

**Beneficio:** Cada servico tem responsabilidade unica e pode ser testado/reusado independentemente.

---

## 3. Strategy Pattern

**Proposito:** Definir familia de algoritmos intercambiaveis.

**Localizacao:** `domain/services/aggregation.py`

### Implementacao: Classificacao de Commits

A classificacao usa patterns regex configurados externamente:

```python
def classify_commit(subject: str, commit_types: dict) -> Tuple[str, bool]:
    """
    Strategy: tipo de commit e determinado por patterns configurados.
    Cada tipo define seus proprios patterns de matching.
    """
    lower_subject = subject.lower()

    for type_key, type_config in commit_types.items():
        patterns = type_config.get('patterns', [])
        for pattern in patterns:
            if re.search(pattern, lower_subject, re.IGNORECASE):
                return type_key, True

    return 'other', False
```

**Configuracao (Strategy):**
```json
{
  "commit_types": {
    "feat": {
      "label": "Features",
      "patterns": ["\\bfeat\\b", "\\bfeature\\b", "\\badd\\b"]
    },
    "fix": {
      "label": "Correcoes",
      "patterns": ["\\bfix\\b", "\\bbugfix\\b", "\\bcorrect\\b"]
    }
  }
}
```

**Beneficio:** Novos tipos de commit podem ser adicionados via configuracao, sem alterar codigo.

---

## 4. Template Method Pattern

**Proposito:** Definir esqueleto de algoritmo, delegando passos para subclasses/funcoes.

**Localizacao:** `prompts/__init__.py`

### Implementacao: Carregamento de Prompts

```python
def load_prompt(name: str) -> str:
    """
    Template Method: carrega arquivo de prompt do diretorio prompts/
    """
    prompt_path = Path(__file__).parent / f"{name}.txt"
    return prompt_path.read_text(encoding='utf-8')

def render_prompt_template(template: str, values: dict) -> str:
    """
    Template Method: substitui placeholders no template.
    O algoritmo e fixo, mas os valores variam.
    """
    result = template
    for key, value in values.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result
```

**Uso:**
```python
# Carregar template base
template = load_prompt("commit_group_summary_pr")

# Renderizar com valores especificos
prompt = render_prompt_template(template, {
    "type_label": "Features",
    "commit_blocks": "...",
    "language_hint": "pt-BR"
})
```

**Beneficio:** Prompts sao externalizados e facilmente editaveis sem alterar logica.

---

## 5. Builder Pattern

**Proposito:** Construir objetos complexos passo a passo.

**Localizacao:** `domain/services/composition.py`

### Implementacao: Construcao de Campos

```python
def build_pr_fields(grouped_summaries: List, config: dict, model: str) -> dict:
    """
    Builder: constroi estrutura JSON complexa para PR.

    1. Formata summaries
    2. Carrega prompt template
    3. Renderiza prompt com valores
    4. Chama LLM
    5. Extrai JSON da resposta
    6. Retorna estrutura construida
    """
    # Passo 1: Formatar entrada
    formatted_summaries = _format_grouped_summaries(grouped_summaries)

    # Passo 2: Carregar template
    template = load_prompt("pr_fields")

    # Passo 3: Renderizar
    prompt = render_prompt_template(template, {
        "commit_summaries": formatted_summaries,
        "language_hint": config.get("language", "en")
    })

    # Passo 4: Chamar LLM
    raw_response = call_ollama(model, prompt, config.get("llm_timeout_seconds"))

    # Passo 5: Extrair JSON
    fields = extract_json(raw_response)

    # Passo 6: Retornar
    return fields  # {title, summary, risks, testing}
```

**Beneficio:** Construcao complexa encapsulada, facil de modificar passos individuais.

---

## 6. Factory Pattern

**Proposito:** Criar objetos sem expor logica de criacao.

**Localizacao:** `config.py`

### Implementacao: Factory de Configuracao

```python
def load_config(config_path: Path) -> dict:
    """
    Factory: cria configuracao validada a partir de arquivo.
    Esconde detalhes de parsing e validacao.
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

def validate_config(config: dict, generate: str) -> None:
    """
    Validacao em cadeia (Chain of Responsibility complementar).
    Cada validacao e independente.
    """
    # Validacoes obrigatorias
    _require_keys(config, ['commit_types', 'importance', 'output'])
    _require_non_empty(config, 'commit_types')

    # Validacoes condicionais
    if generate in ('pr', 'both'):
        _require_nested(config, 'templates', 'pr')

    if generate in ('release', 'both'):
        _require_nested(config, 'domain', 'template_path')
```

**Beneficio:** Configuracao e sempre valida quando retornada, cliente nao precisa validar.

---

## 7. Repository Pattern

**Proposito:** Abstrair persistencia de dados.

**Localizacao:** `domain/services/export.py`

### Implementacao: Exportacao de Artefatos

```python
def export_commits(commits: List[Commit], output_dir: Path) -> Path:
    """
    Repository: persiste commits em formato JSON.
    Abstrai detalhes de serializacao e I/O.
    """
    output_path = output_dir / "commits.json"
    data = [asdict(c) for c in commits]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path

def export_text_document(content: str, output_dir: Path, filename: str) -> Path:
    """
    Repository: persiste documento de texto.
    """
    output_path = output_dir / filename
    output_path.write_text(content, encoding='utf-8')
    return output_path
```

**Beneficio:** Mudancas no formato de persistencia nao afetam o dominio.

---

## Diagrama de Interacao dos Padroes

```
+----------------+     +----------------+     +----------------+
|   CLI Input    |---->|    Factory     |---->|    Config      |
+----------------+     | (load_config)  |     |    Object      |
                       +----------------+     +----------------+
                                                     |
                                                     v
+----------------+     +----------------+     +----------------+
|  Git Adapter   |<----|  Service Layer |<----|   Workflow     |
| (subprocess)   |     | (data_collect) |     |   (sync.py)    |
+----------------+     +----------------+     +----------------+
                              |
                              v
+----------------+     +----------------+
|    Strategy    |<----|  Service Layer |
| (classify by   |     | (aggregation)  |
|   patterns)    |     +----------------+
+----------------+            |
                              v
+----------------+     +----------------+
|    Builder     |<----|  Service Layer |
| (build_fields) |     | (composition)  |
+----------------+     +----------------+
       |                      |
       v                      v
+----------------+     +----------------+
|  LLM Adapter   |     |  Repository    |
|  (http.py)     |     |  (export.py)   |
+----------------+     +----------------+
                              |
                              v
                       +----------------+
                       | Output Files   |
                       +----------------+
```

## Padroes Implicitos Adicionais

### Facade
`workflows/sync.py` atua como Facade, escondendo complexidade dos subsistemas.

### Null Object
`--no-llm` flag implementa comportamento "null" para LLM, usando subjects como fallback.

### Chain of Responsibility
Validacao de configuracao em `config.py` usa cadeia de validacoes independentes.

### Singleton (Implicito)
Configuracao carregada uma vez e passada por injecao de dependencia.
