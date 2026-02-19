# Interface de Linha de Comando (CLI)

Este documento descreve todos os comandos e opcoes disponiveis na CLI do PullNotes.

## Instalacao

Apos clonar o repositorio, instale em modo desenvolvimento:

```bash
pip install -e .
```

Isso disponibiliza o comando `pullnotes` globalmente.

## Sintaxe

```bash
pullnotes <repo> [OPTIONS]
```

## Argumentos

### repo (posicional)

**Descricao:** Path para o repositorio Git a ser analisado.

**Padrao:** `.` (diretorio atual)

**Exemplos:**
```bash
pullnotes .
pullnotes /home/user/meu-projeto
pullnotes C:\Users\Dev\projeto
```

## Opcoes

### --config PATH

**Obrigatorio:** Sim

**Descricao:** Caminho para o arquivo de configuracao JSON.

**Exemplo:**
```bash
pullnotes . --config config.default.json
pullnotes . --config /path/to/custom-config.json
```

---

### --range RANGE

**Descricao:** Range de revisoes Git para analisar.

**Formato:** `<ref1>..<ref2>` (sintaxe Git padrao)

**Exemplos:**
```bash
# Entre duas tags
pullnotes . --config config.json --range v1.0..v1.1

# Entre branch e tag
pullnotes . --config config.json --range main..release/2.0

# Entre commits
pullnotes . --config config.json --range abc123..def456

# Desde uma tag ate HEAD
pullnotes . --config config.json --range v1.0..HEAD
```

**Nota:** Se o range nao funcionar, a ferramenta tenta automaticamente com prefixo `origin/`.

---

### --since DATE

**Descricao:** Data inicial para filtrar commits.

**Formato:** ISO 8601 ou formatos aceitos pelo Git.

**Exemplos:**
```bash
pullnotes . --config config.json --since 2024-01-01
pullnotes . --config config.json --since "2024-01-01 00:00:00"
pullnotes . --config config.json --since "1 month ago"
```

---

### --until DATE

**Descricao:** Data final para filtrar commits.

**Formato:** ISO 8601 ou formatos aceitos pelo Git.

**Exemplos:**
```bash
pullnotes . --config config.json --until 2024-12-31
pullnotes . --config config.json --since 2024-01-01 --until 2024-06-30
```

---

### --generate {pr|release|both}

**Descricao:** Tipo de documento a ser gerado.

**Padrao:** `both`

**Opcoes:**
| Valor | Descricao |
|-------|-----------|
| `pr` | Gera apenas documento de Pull Request |
| `release` | Gera apenas Release Notes |
| `both` | Gera ambos os documentos |

**Exemplos:**
```bash
pullnotes . --config config.json --generate pr
pullnotes . --config config.json --generate release
pullnotes . --config config.json --generate both
```

---

### --version LABEL

**Descricao:** Label de versao para o release (sobrescreve template de versao do config).

**Uso:** Principalmente para release notes.

**Exemplos:**
```bash
pullnotes . --config config.json --generate release --version "2.0.0"
pullnotes . --config config.json --version "v1.5.0-beta"
```

---

### --output-dir DIR

**Descricao:** Diretorio base onde os arquivos serao gerados (sobrescreve config).

**Exemplos:**
```bash
pullnotes . --config config.json --output-dir ./docs/releases
pullnotes . --config config.json --output-dir /tmp/output
```

---

### --refresh-domain

**Descricao:** Forca a recriacao do perfil de dominio do projeto.

**Comportamento:**
- Sem flag: Reutiliza perfil JSON existente se disponivel
- Com flag: Ignora cache e regenera o perfil via LLM

**Uso:** Quando o codigo fonte mudou significativamente e o perfil cacheado esta desatualizado.

**Exemplo:**
```bash
pullnotes . --config config.json --generate release --refresh-domain
```

---

### --model MODEL

**Descricao:** Sobrescreve o modelo LLM configurado no arquivo de config.

**Exemplos:**
```bash
pullnotes . --config config.json --model llama3:8b
pullnotes . --config config.json --model mistral:7b
pullnotes . --config config.json --model qwen2.5:14b
```

---

### --no-llm

**Descricao:** Desabilita chamadas ao LLM.

**Comportamento:**
- Sumarizacao usa subjects dos commits como fallback
- Campos de PR/release usam placeholders ou ficam vazios
- Util para debug ou quando LLM nao esta disponivel

**Exemplo:**
```bash
pullnotes . --config config.json --no-llm
```

---

### --debug

**Descricao:** Habilita logging em nivel DEBUG.

**Comportamento:**
- Sem flag: Logging em nivel WARNING
- Com flag: Logging detalhado (DEBUG) para todos os modulos

**Exemplo:**
```bash
pullnotes . --config config.json --debug
```

---

## Exemplos Completos

### Geracao Basica

```bash
# PR e Release Notes para commits entre tags
pullnotes /path/to/repo --config config.default.json --range v1.0..v1.1
```

### Apenas Pull Request

```bash
# PR para commits do ultimo mes
pullnotes . --config config.json --generate pr --since "1 month ago"
```

### Release Notes Completo

```bash
# Release com versao customizada e refresh de dominio
pullnotes . \
  --config config.json \
  --generate release \
  --range v2.0..v2.1 \
  --version "2.1.0" \
  --refresh-domain \
  --output-dir ./releases/2.1.0
```

### Debug sem LLM

```bash
# Testar coleta e classificacao sem chamar LLM
pullnotes . --config config.json --no-llm --debug --output-dir ./debug
```

### Modelo Alternativo

```bash
# Usar modelo diferente para melhor qualidade
pullnotes . \
  --config config.json \
  --model qwen2.5:14b \
  --generate both
```

---

## Arquivos de Saida

Apos execucao, os arquivos sao gerados em `{output_dir}/{repo_name}/`:

| Caminho | Condicao | Descricao |
|---------|----------|-----------|
| `prs/pr_{titulo}.md` | `--generate pr` ou `both` | Documento de Pull Request |
| `releases/release_{versao}.md` | `--generate release` ou `both` | Release Notes |
| `utils/commit.json` | Sempre | Dados completos dos commits |
| `utils/conventions.md` | Sempre | Relatorio de conventional commits |
| `utils/domain_profile_{repo}.json` | `--generate release` ou `both` | Perfil de dominio cacheado |
| `utils/prompts/` | Com `--debug` | Prompts e respostas LLM salvos |

---

## Codigos de Retorno

| Codigo | Significado |
|--------|-------------|
| 0 | Sucesso |
| 1 | Erro (configuracao, Git, LLM, etc.) |

---

## Troubleshooting

### Erro: "Config file not found"

**Causa:** Arquivo de configuracao nao existe no path especificado.

**Solucao:** Verificar path e existencia do arquivo.

### Erro: "Invalid revision range"

**Causa:** Range Git invalido ou refs nao existem.

**Solucao:**
1. Verificar se as tags/branches existem: `git tag -l`, `git branch -a`
2. Usar format correto: `ref1..ref2`

### Erro: "Ollama connection failed"

**Causa:** Servidor Ollama nao esta rodando.

**Solucao:**
1. Iniciar Ollama: `ollama serve`
2. Verificar modelo: `ollama list`
3. Baixar modelo: `ollama pull qwen2.5:7b`

### Erro: "No commits found"

**Causa:** Range nao contem commits ou filtros muito restritivos.

**Solucao:**
1. Verificar range: `git log ref1..ref2 --oneline`
2. Ajustar datas --since/--until

### Timeout em chamadas LLM

**Causa:** Modelo muito grande ou prompt complexo.

**Solucao:**
1. Aumentar `llm_timeout_seconds` na config
2. Usar modelo menor
3. Reduzir quantidade de commits por range

---

## Uso Programatico

Alem da CLI, o pacote pode ser importado:

```python
from pullnotes.workflows.sync import run_workflow
from argparse import Namespace

args = Namespace(
    repo="/path/to/repo",
    config="/path/to/config.json",
    range="v1.0..v1.1",
    since=None,
    until=None,
    generate="both",
    version=None,
    output_dir=None,
    refresh_domain=False,
    model=None,
    no_llm=False,
    debug=False
)

exit_code = run_workflow(args)
```
