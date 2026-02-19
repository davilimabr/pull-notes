# Configuracao

Este documento descreve todas as opcoes de configuracao disponiveis no arquivo JSON.

## Arquivo de Configuracao

O arquivo de configuracao e um JSON que define comportamentos da ferramenta. Use `--config` para especificar o caminho.

### Estrutura Completa

```json
{
  "commit_types": {
    "feat": {
      "label": "Funcionalidades",
      "patterns": ["\\bfeat\\b", "\\bfeature\\b", "\\badd\\b"]
    },
    "fix": {
      "label": "Ajustes",
      "patterns": ["\\bfix\\b", "\\bbugfix\\b"]
    },
    "docs": {
      "label": "Documentacao",
      "patterns": ["\\bdocs\\b"]
    },
    "refactor": {
      "label": "Refatoracao",
      "patterns": ["\\brefactor\\b"]
    },
    "perf": {
      "label": "Performance",
      "patterns": ["\\bperf\\b"]
    },
    "test": {
      "label": "Testes",
      "patterns": ["\\btest\\b", "\\btests\\b"]
    },
    "build": {
      "label": "Build",
      "patterns": ["\\bbuild\\b"]
    },
    "ci": {
      "label": "CI",
      "patterns": ["\\bci\\b"]
    },
    "style": {
      "label": "Estilo",
      "patterns": ["\\bstyle\\b"]
    },
    "chore": {
      "label": "chore",
      "patterns": ["\\bchore\\b"]
    },
    "revert": {
      "label": "revert",
      "patterns": ["\\brevert\\b"]
    }
  },

  "other_label": "Other",

  "importance": {
    "weight_lines": 0.02,
    "weight_files": 0.6,
    "keyword_bonus": {
      "breaking": 3.0,
      "security": 2.0,
      "hotfix": 2.0,
      "perf": 1.0
    }
  },

  "importance_bands": [
    { "name": "low", "min": 0.0 },
    { "name": "medium", "min": 3.0 },
    { "name": "high", "min": 6.0 },
    { "name": "critical", "min": 9.0 }
  ],

  "diff": {
    "max_anchors_keywords": 10,
    "max_anchors_artifacts": 10
  },

  "domain": {
    "output_path": "domain_profile.json",
    "model": "qwen2.5:7b",
    "max_total_bytes": 400000,
    "max_file_bytes": 40000
  },

  "templates": {
    "pr": "templates/pr.md",
    "release": "templates/release.md"
  },

  "output": {
    "dir": "./output"
  },

  "language": "pt-BR",
  "llm_model": "qwen2.5:7b",
  "llm_timeout_seconds": 600,
  "llm_max_retries": 3,

  "alerts": {
    "none_text": "None."
  },

  "release": {
    "version_template": "{revision_range}",
    "date_format": "%Y-%m-%d"
  }
}
```

---

## Secoes de Configuracao

### commit_types

Define os tipos de commits reconhecidos e seus patterns de matching.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `[key]` | string | Identificador do tipo (feat, fix, etc.) |
| `label` | string | Label de exibicao nos documentos gerados |
| `patterns` | array | Lista de regex patterns para matching |

**Patterns:**
- Regex Python padrao
- Case-insensitive por padrao
- Use `\\b` para word boundaries

---

### other_label

Label usado para commits que nao se encaixam em nenhum tipo definido.

```json
{ "other_label": "Other" }
```

---

### importance

Configura o calculo de score de importancia dos commits.

| Campo | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `weight_lines` | float | 0.02 | Peso por linha alterada (+/-) |
| `weight_files` | float | 0.6 | Peso por arquivo modificado |
| `keyword_bonus` | object | - | Bonus por keyword no subject |

**Formula:**
```
score = (additions + deletions) * weight_lines
      + len(files) * weight_files
      + sum(keyword_bonus[kw] for kw in subject if kw in keyword_bonus)
```

---

### importance_bands

Define as faixas de importancia baseadas no score calculado.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `name` | string | Nome da faixa |
| `min` | float | Score minimo para a faixa |

**Configuracao Padrao:**

| Faixa | Score Minimo |
|-------|-------------|
| low | 0.0 |
| medium | 3.0 |
| high | 6.0 |
| critical | 9.0 |

**Ordem:** Sempre do menor para o maior `min`.

---

### diff

Configuracao para extracao de ancoras semanticas dos diffs.

| Campo | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `max_anchors_keywords` | int | 10 | Maximo de keywords extraidas por diff |
| `max_anchors_artifacts` | int | 10 | Maximo de artifacts detectados por diff |

Em vez de enviar o diff bruto ao LLM, a ferramenta extrai ancoras semanticas (keywords e artifacts) que reduzem significativamente o tamanho dos prompts mantendo o contexto relevante.

---

### domain

Configuracao para geracao do perfil de dominio do projeto (JSON estruturado via LLM).

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `output_path` | string | Nome do arquivo de cache do perfil |
| `model` | string | Modelo LLM para geracao do perfil |
| `max_total_bytes` | int | Limite total de bytes indexados do repositorio |
| `max_file_bytes` | int | Limite de bytes por arquivo indexado |

O perfil e cacheado em `utils/domain_profile_{repo}.json` e reutilizado em execucoes subsequentes. Use `--refresh-domain` para forcar recriacao.

---

### templates

Paths dos templates markdown de saida.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `pr` | string | Template para Pull Request |
| `release` | string | Template para Release Notes |

**Paths:** Relativos ao diretorio do pacote `pullnotes`.

---

### output

Configura o diretorio base de saida dos artefatos gerados.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `dir` | string | Caminho do diretorio base de saida |

**Nota:** Pode ser sobrescrito com `--output-dir` na CLI. Os arquivos sao organizados em `{dir}/{repo_name}/prs/`, `releases/` e `utils/`.

---

### llm_model, llm_timeout_seconds, llm_max_retries

Configuracao do modelo LLM principal.

| Campo | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `llm_model` | string | - | Nome do modelo Ollama |
| `llm_timeout_seconds` | int | 600 | Timeout para chamadas LLM (segundos) |
| `llm_max_retries` | int | 3 | Numero de tentativas em caso de falha |

**Modelos Suportados (Ollama):**
- `qwen2.5:7b` (recomendado, bom para instrucoes estruturadas)
- `llama3:8b`
- `mistral:7b`
- Qualquer modelo disponivel no Ollama local

---

### language

Define o idioma dos outputs gerados.

| Valor | Descricao |
|-------|-----------|
| `pt-BR` | Portugues Brasileiro |
| `en` | Ingles |
| `es` | Espanhol |

Passado como hint para o LLM nos prompts.

---

### alerts

Configuracao para mensagens de alerta nos documentos gerados.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `none_text` | string | Texto quando nao ha alertas (ex: "None.") |

---

### release

Configuracao especifica para release notes.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `version_template` | string | Template para label de versao |
| `date_format` | string | Formato de data (strftime) |

**Version Template Placeholders:**
- `{revision_range}` - Range Git completo
- `{version}` - Versao passada via `--version`

---

## Validacao

O arquivo de configuracao e validado automaticamente. Erros comuns:

| Erro | Causa | Solucao |
|------|-------|---------|
| `Missing key: commit_types` | Secao obrigatoria ausente | Adicionar secao |
| `Empty commit_types` | Nenhum tipo definido | Definir ao menos um tipo |
| `Missing templates.pr` | Template PR nao especificado | Adicionar path (se --generate pr) |

## Exemplo Minimo

Configuracao minima funcional:

```json
{
  "commit_types": {
    "feat": { "label": "Features", "patterns": ["\\bfeat\\b"] },
    "fix": { "label": "Fixes", "patterns": ["\\bfix\\b"] }
  },
  "other_label": "Other",
  "importance": {
    "weight_lines": 0.02,
    "weight_files": 0.6,
    "keyword_bonus": {}
  },
  "importance_bands": [
    { "name": "low", "min": 0.0 },
    { "name": "high", "min": 5.0 }
  ],
  "diff": { "max_anchors_keywords": 10, "max_anchors_artifacts": 10 },
  "output": { "dir": "./output" },
  "llm_model": "qwen2.5:7b",
  "llm_timeout_seconds": 600,
  "llm_max_retries": 3,
  "language": "pt-BR",
  "alerts": { "none_text": "None." },
  "templates": {
    "pr": "templates/pr.md",
    "release": "templates/release.md"
  },
  "release": {
    "version_template": "{revision_range}",
    "date_format": "%Y-%m-%d"
  }
}
```

## Variaveis de Ambiente

A ferramenta nao usa variaveis de ambiente diretamente. Toda configuracao e via arquivo JSON ou argumentos CLI.

Para configurar o Ollama, use as variaveis do proprio Ollama:
- `OLLAMA_HOST` - Host do servidor Ollama (padrao: localhost:11434)
