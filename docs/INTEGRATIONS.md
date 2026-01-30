# Integracoes Externas

Este documento descreve as integracoes da ferramenta com sistemas externos.

## Visao Geral

```
+-------------------+     +-------------------+     +-------------------+
|   Gerador CLI     |---->|       Git         |     |      Ollama       |
|                   |     |  (subprocess)     |     |    (HTTP API)     |
|   +----------+    |     +-------------------+     +-------------------+
|   | Adapters |----+---->|      lxml         |
|   +----------+    |     |   (XML/XSD)       |
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

**Exemplo de Saida:**
```
__COMMIT__
abc123def456789...
John Doe
john@example.com
2024-01-15T10:30:00-03:00
feat: add user authentication

5	2	src/auth.py
10	0	src/models/user.py
```

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

## 2. Ollama (LLM)

### Descricao

Ollama e usado para inferencia de LLM local, gerando sumarizacoes e campos dos documentos.

### Adapter

**Arquivo:** `adapters/http.py`

```python
import ollama
import httpx

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
        timeout_seconds: Timeout em segundos

    Returns:
        Resposta do modelo (texto limpo)
    """
    timeout = httpx.Timeout(timeout_seconds or 10.0)
    client = ollama.Client(timeout=timeout)

    response = client.chat(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        options={'temperature': 0.2}
    )

    return response['message']['content'].strip()
```

### Configuracao

**Parametros:**
| Parametro | Valor | Descricao |
|-----------|-------|-----------|
| `temperature` | 0.2 | Baixa temperatura para respostas mais deterministicas |
| `timeout` | configuravel | Padrao 10s, ajustavel via config |

**Modelos Recomendados:**
| Modelo | Tamanho | Uso |
|--------|---------|-----|
| `deepseek-r1:8b` | ~5GB | Padrao, bom balanco |
| `llama2:7b` | ~4GB | Alternativa leve |
| `mistral:7b` | ~4GB | Bom para ingles |
| `codellama:7b` | ~4GB | Melhor para codigo |

### Chamadas LLM no Sistema

| Funcao | Prompt | Output |
|--------|--------|--------|
| `summarize_commit_group()` | commit_group_summary_*.txt | Bullets markdown |
| `build_pr_fields()` | pr_fields.txt | JSON com campos |
| `build_release_fields()` | release_fields.txt | JSON com campos |
| `generate_domain_xml()` | domain_xml.txt | XML preenchido |

### Exemplo de Prompt

```
Voce e um assistente que gera resumos de commits.

Tipo de mudanca: Features
Idioma: pt-BR

Commits:
---
SHA: abc123
Subject: feat: add user login
Body: Implements JWT authentication
Diff:
+def login(user, password):
+    token = generate_jwt(user)
+    return token
---

Gere um resumo em bullets das mudancas, focando no impacto para o usuario.
```

### Extracao de JSON

Respostas LLM podem conter texto extra alem do JSON. A funcao `extract_json()` trata isso:

```python
def extract_json(raw_response: str) -> dict:
    """
    Extrai JSON de resposta LLM.
    Trata casos como:
    - JSON puro
    - JSON em bloco de codigo
    - Texto + JSON
    """
    # Tentar parse direto
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        pass

    # Procurar bloco de codigo
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw_response)
    if match:
        return json.loads(match.group(1))

    # Procurar objeto JSON no texto
    match = re.search(r'\{[\s\S]*\}', raw_response)
    if match:
        return json.loads(match.group(0))

    raise ValueError("No JSON found in response")
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
   ollama pull deepseek-r1:8b
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
| Timeout | Prompt muito longo | Aumentar timeout ou reduzir contexto |
| Out of memory | Modelo muito grande | Usar modelo menor |

---

## 3. lxml (XML/XSD)

### Descricao

A biblioteca lxml e usada para manipulacao de XML e validacao contra schemas XSD.

### Uso no Projeto

**Arquivo:** `adapters/domain_definition.py`

```python
from lxml import etree

def validate_xml(xml_text: str, xsd_path: Path) -> bool:
    """
    Valida XML contra schema XSD.

    Args:
        xml_text: Conteudo XML
        xsd_path: Path do arquivo XSD

    Returns:
        True se valido

    Raises:
        etree.DocumentInvalid: Se invalido
    """
    # Carregar schema
    xsd_doc = etree.parse(str(xsd_path))
    schema = etree.XMLSchema(xsd_doc)

    # Parsear XML
    xml_doc = etree.fromstring(xml_text.encode('utf-8'))

    # Validar
    schema.assertValid(xml_doc)
    return True
```

### Estrutura do XML de Dominio

```xml
<?xml version="1.0" encoding="UTF-8"?>
<domainProfile>
    <repositoryName>gerador-PR-relese-note</repositoryName>

    <domain>
        Ferramenta CLI para geracao automatica de
        documentacao de releases e pull requests.
    </domain>

    <entities>
        <entity name="Commit" description="Representa um commit Git"/>
        <entity name="Config" description="Configuracao da ferramenta"/>
    </entities>

    <domainAnchors>
        <keywords>commit, release, pr, llm, git</keywords>
        <apiEndpoints>/api/ollama/chat</apiEndpoints>
        <sqlTables></sqlTables>
        <events></events>
        <services>DataCollection, Aggregation, Composition</services>
    </domainAnchors>
</domainProfile>
```

### Schema XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="domainProfile">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="repositoryName" type="xs:string"/>
                <xs:element name="domain" type="xs:string"/>
                <xs:element name="entities" minOccurs="0">
                    <xs:complexType>
                        <xs:sequence>
                            <xs:element name="entity" maxOccurs="unbounded">
                                <xs:complexType>
                                    <xs:attribute name="name" type="xs:string"/>
                                    <xs:attribute name="description" type="xs:string"/>
                                </xs:complexType>
                            </xs:element>
                        </xs:sequence>
                    </xs:complexType>
                </xs:element>
                <xs:element name="domainAnchors" minOccurs="0">
                    <!-- ... -->
                </xs:element>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

### Requisitos

- Python package `lxml` instalado
- Arquivos XML/XSD sintaticamente corretos

---

## 4. Filesystem

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
| Escrever XML | domain_definition.py | `Path.write_text()` |

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
    Itera arquivos do repositorio respeitando limites.
    """
    total_bytes = 0

    for path in repo_dir.rglob('*'):
        if any(d in path.parts for d in IGNORE_DIRS):
            continue
        if path.suffix not in INCLUDE_EXTENSIONS:
            continue
        if not path.is_file():
            continue

        size = path.stat().st_size
        if total_bytes + size > max_total_bytes:
            break

        total_bytes += size
        yield path
```

---

## Diagrama de Integracoes

```
                          +------------------+
                          |   Gerador CLI    |
                          +--------+---------+
                                   |
         +-------------------------+-------------------------+
         |                         |                         |
         v                         v                         v
+--------+--------+     +----------+----------+     +--------+--------+
|      GIT        |     |       OLLAMA        |     |    FILESYSTEM   |
|   subprocess    |     |     HTTP/REST       |     |    pathlib      |
+-----------------+     +---------------------+     +-----------------+
| - git log       |     | - /api/chat         |     | - read files    |
| - git show      |     | - model inference   |     | - write files   |
| - git config    |     | - temperature: 0.2  |     | - create dirs   |
+-----------------+     +---------------------+     +-----------------+
         |                         |                         |
         v                         v                         v
+--------+--------+     +----------+----------+     +--------+--------+
|   Repositorio   |     |   Modelo Local      |     |   Config/       |
|      Git        |     |  (deepseek, llama)  |     |   Templates/    |
|                 |     |                     |     |   Output        |
+-----------------+     +---------------------+     +-----------------+
```

## Resumo de Dependencias

| Integracao | Biblioteca | Versao Min | Obrigatorio |
|------------|------------|------------|-------------|
| Git | subprocess (stdlib) | - | Sim |
| Ollama | ollama (pypi) | - | Sim* |
| XML | lxml (pypi) | - | Parcial** |
| Filesystem | pathlib (stdlib) | - | Sim |

\* Pode ser bypassed com `--no-llm`
\** Apenas necessario para `--generate release`
