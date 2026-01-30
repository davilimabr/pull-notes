# Interface de Linha de Comando (CLI)

Este documento descreve todos os comandos e opcoes disponiveis na CLI do Gerador de PR e Release Notes.

## Instalacao

Apos clonar o repositorio, instale em modo desenvolvimento:

```bash
pip install -e .
```

Isso disponibiliza o comando `gerador-cli` globalmente.

## Sintaxe

```bash
gerador-cli <repo> [OPTIONS]
```

## Argumentos

### repo (posicional)

**Descricao:** Path para o repositorio Git a ser analisado.

**Padrao:** `.` (diretorio atual)

**Exemplos:**
```bash
gerador-cli .
gerador-cli /home/user/meu-projeto
gerador-cli C:\Users\Dev\projeto
```

## Opcoes

### --config PATH

**Obrigatorio:** Sim

**Descricao:** Caminho para o arquivo de configuracao JSON.

**Exemplo:**
```bash
gerador-cli . --config config.json
gerador-cli . --config /path/to/custom-config.json
```

---

### --range RANGE

**Descricao:** Range de revisoes Git para analisar.

**Formato:** `<ref1>..<ref2>` (sintaxe Git padrao)

**Exemplos:**
```bash
# Entre duas tags
gerador-cli . --config config.json --range v1.0..v1.1

# Entre branch e tag
gerador-cli . --config config.json --range main..release/2.0

# Entre commits
gerador-cli . --config config.json --range abc123..def456

# Desde uma tag ate HEAD
gerador-cli . --config config.json --range v1.0..HEAD
```

**Nota:** Se o range nao funcionar, a ferramenta tenta automaticamente com prefixo `origin/`.

---

### --since DATE

**Descricao:** Data inicial para filtrar commits.

**Formato:** ISO 8601 ou formatos aceitos pelo Git.

**Exemplos:**
```bash
gerador-cli . --config config.json --since 2024-01-01
gerador-cli . --config config.json --since "2024-01-01 00:00:00"
gerador-cli . --config config.json --since "1 month ago"
```

---

### --until DATE

**Descricao:** Data final para filtrar commits.

**Formato:** ISO 8601 ou formatos aceitos pelo Git.

**Exemplos:**
```bash
gerador-cli . --config config.json --until 2024-12-31
gerador-cli . --config config.json --since 2024-01-01 --until 2024-06-30
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
gerador-cli . --config config.json --generate pr
gerador-cli . --config config.json --generate release
gerador-cli . --config config.json --generate both
```

---

### --version LABEL

**Descricao:** Label de versao para o release (sobrescreve template).

**Uso:** Principalmente para release notes.

**Exemplos:**
```bash
gerador-cli . --config config.json --generate release --version "2.0.0"
gerador-cli . --config config.json --version "v1.5.0-beta"
```

---

### --output-dir DIR

**Descricao:** Diretorio onde os arquivos serao gerados (sobrescreve config).

**Exemplos:**
```bash
gerador-cli . --config config.json --output-dir ./docs/releases
gerador-cli . --config config.json --output-dir /tmp/output
```

---

### --refresh-domain

**Descricao:** Forca a recriacao do perfil de dominio XML.

**Comportamento:**
- Sem flag: Reutiliza XML existente se disponivel
- Com flag: Ignora XML existente e regenera

**Uso:** Quando o codigo fonte mudou significativamente.

**Exemplo:**
```bash
gerador-cli . --config config.json --generate release --refresh-domain
```

---

### --model MODEL

**Descricao:** Sobrescreve o modelo LLM configurado.

**Exemplos:**
```bash
gerador-cli . --config config.json --model llama2:7b
gerador-cli . --config config.json --model mistral:7b
gerador-cli . --config config.json --model deepseek-r1:14b
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
gerador-cli . --config config.json --no-llm
```

---

## Exemplos Completos

### Geracao Basica

```bash
# PR e Release Notes para commits entre tags
gerador-cli /path/to/repo --config config.json --range v1.0..v1.1
```

### Apenas Pull Request

```bash
# PR para commits do ultimo mes
gerador-cli . --config config.json --generate pr --since "1 month ago"
```

### Release Notes Completo

```bash
# Release com versao customizada e refresh de dominio
gerador-cli . \
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
gerador-cli . --config config.json --no-llm --output-dir ./debug
```

### Modelo Alternativo

```bash
# Usar modelo diferente para melhor qualidade
gerador-cli . \
  --config config.json \
  --model deepseek-r1:14b \
  --generate both
```

---

## Arquivos de Saida

Apos execucao, os seguintes arquivos sao gerados no diretorio de saida:

| Arquivo | Condicao | Descricao |
|---------|----------|-----------|
| `pr.md` | --generate pr ou both | Documento de Pull Request |
| `release.md` | --generate release ou both | Release Notes |
| `commits.json` | Sempre | Dados completos dos commits |
| `conventions.md` | Sempre | Relatorio de conventional commits |
| `dominio.xml` | --generate release | Perfil de dominio extraido |

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
3. Baixar modelo: `ollama pull deepseek-r1:8b`

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
from gerador_cli.workflows.sync import run_workflow
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
    no_llm=False
)

exit_code = run_workflow(args)
```
