# Configuracao

Este documento descreve todas as opcoes de configuracao disponiveis no arquivo JSON.

## Arquivo de Configuracao

O arquivo de configuracao e um JSON que define comportamentos da ferramenta. Use `--config` para especificar o caminho.

### Estrutura Completa

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
    },
    "docs": {
      "label": "Documentacao",
      "patterns": ["\\bdocs\\b", "\\bdocument\\b"]
    },
    "refactor": {
      "label": "Refatoracao",
      "patterns": ["\\brefactor\\b", "\\breorganize\\b"]
    },
    "test": {
      "label": "Testes",
      "patterns": ["\\btest\\b", "\\bspec\\b"]
    },
    "chore": {
      "label": "Manutencao",
      "patterns": ["\\bchore\\b", "\\bbuild\\b", "\\bci\\b"]
    },
    "perf": {
      "label": "Performance",
      "patterns": ["\\bperf\\b", "\\boptimize\\b"]
    },
    "style": {
      "label": "Estilo",
      "patterns": ["\\bstyle\\b", "\\bformat\\b"]
    }
  },

  "importance": {
    "weight_lines": 0.02,
    "weight_files": 0.6,
    "keyword_bonus": {
      "breaking": 3.0,
      "security": 2.0,
      "hotfix": 2.0,
      "perf": 1.0,
      "critical": 2.5
    }
  },

  "importance_bands": [
    { "name": "low", "min": 0.0 },
    { "name": "medium", "min": 3.0 },
    { "name": "high", "min": 6.0 },
    { "name": "critical", "min": 9.0 }
  ],

  "domain": {
    "template_path": "xml/dominio.xml",
    "xsd_path": "xml/XSD_dominio.xml",
    "output_path": "dominio.xml",
    "model": "deepseek-r1:8b",
    "max_total_bytes": 400000,
    "max_file_bytes": 40000
  },

  "output": {
    "dir": "./output"
  },

  "llm_model": "deepseek-r1:8b",
  "llm_timeout_seconds": 600,
  "language": "pt-BR",

  "templates": {
    "pr": "templates/pr.md",
    "release": "templates/release.md"
  },

  "diff": {
    "max_anchors_keywords": 10,
    "max_anchors_artifacts": 10
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
| `label` | string | Label de exibicao |
| `patterns` | array | Lista de regex patterns |

**Patterns:**
- Regex Python padrao
- Case-insensitive por padrao
- Use `\\b` para word boundaries

**Exemplo Customizado:**
```json
{
  "commit_types": {
    "feature": {
      "label": "Novas Funcionalidades",
      "patterns": ["\\bfeat\\b", "\\bnew\\b", "\\badd\\b", "\\bimplement\\b"]
    },
    "bugfix": {
      "label": "Correcoes de Bugs",
      "patterns": ["\\bfix\\b", "\\bbug\\b", "\\bresolve\\b", "\\bcorrect\\b"]
    }
  }
}
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

**Exemplo de Keyword Bonus:**
```json
{
  "importance": {
    "keyword_bonus": {
      "breaking": 3.0,    // BREAKING CHANGE
      "security": 2.0,    // Correcoes de seguranca
      "hotfix": 2.0,      // Correcoes urgentes
      "perf": 1.0,        // Melhorias de performance
      "critical": 2.5,    // Mudancas criticas
      "urgent": 1.5       // Mudancas urgentes
    }
  }
}
```

---

### importance_bands

Define as faixas de importancia baseadas no score calculado.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `name` | string | Nome da faixa |
| `min` | float | Score minimo para a faixa |

**Configuracao Padrao:**
```json
{
  "importance_bands": [
    { "name": "low", "min": 0.0 },
    { "name": "medium", "min": 3.0 },
    { "name": "high", "min": 6.0 },
    { "name": "critical", "min": 9.0 }
  ]
}
```

**Ordem:** Sempre do menor para o maior `min`.

---

### domain

Configuracao para extracao de perfil de dominio (usado em release notes).

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `template_path` | string | Path do template XML |
| `xsd_path` | string | Path do schema XSD |
| `output_path` | string | Nome do arquivo de saida |
| `model` | string | Modelo LLM para geracao |
| `max_total_bytes` | int | Limite total de bytes indexados |
| `max_file_bytes` | int | Limite por arquivo |

**Exemplo:**
```json
{
  "domain": {
    "template_path": "xml/dominio.xml",
    "xsd_path": "xml/XSD_dominio.xml",
    "output_path": "dominio.xml",
    "model": "deepseek-r1:8b",
    "max_total_bytes": 400000,
    "max_file_bytes": 40000
  }
}
```

---

### output

Configura o diretorio de saida dos artefatos gerados.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `dir` | string | Caminho do diretorio de saida |

**Nota:** Pode ser sobrescrito com `--output-dir` na CLI.

---

### llm_model e llm_timeout_seconds

Configuracao do modelo LLM principal.

| Campo | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `llm_model` | string | - | Nome do modelo Ollama |
| `llm_timeout_seconds` | int | 600 | Timeout para chamadas LLM |

**Modelos Suportados (Ollama):**
- `deepseek-r1:8b` (recomendado)
- `llama2:7b`
- `mistral:7b`
- `codellama:7b`
- Qualquer modelo disponivel no Ollama local

---

### language

Define o idioma dos outputs gerados.

| Valor | Descricao |
|-------|-----------|
| `pt-BR` | Portugues Brasileiro |
| `en` | Ingles |
| `es` | Espanhol |

**Uso:** Passado como hint para o LLM nos prompts.

---

### templates

Paths dos templates markdown de saida.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `pr` | string | Template para Pull Request |
| `release` | string | Template para Release Notes |

**Paths:** Relativos ao diretorio do pacote `pullnotes`.

---

### diff

Configuracao para extracao de ancoras semanticas dos diffs.

| Campo | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `max_anchors_keywords` | int | 10 | Maximo de keywords extraidas por diff |
| `max_anchors_artifacts` | int | 10 | Maximo de artifacts detectados por diff |

**Nota:** Em vez de truncar diffs brutos, a ferramenta agora extrai ancoras semanticas (keywords e artifacts) que sao mais informativas para o LLM e reduzem significativamente o tamanho dos prompts.

**Ancoras Extraidas:**
- **Keywords:** Palavras-chave das linhas adicionadas/removidas (excluindo stopwords)
- **Artifacts:** Padroes detectados como endpoints API, eventos e servicos

---

### release

Configuracao especifica para release notes.

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `version_template` | string | Template para label de versao |
| `date_format` | string | Formato de data (strftime) |

**Version Template Placeholders:**
- `{revision_range}` - Range Git completo
- `{version}` - Versao passada via CLI

**Exemplo:**
```json
{
  "release": {
    "version_template": "v{version}",
    "date_format": "%d/%m/%Y"
  }
}
```

---

## Validacao

O arquivo de configuracao e validado automaticamente. Erros comuns:

| Erro | Causa | Solucao |
|------|-------|---------|
| `Missing key: commit_types` | Secao obrigatoria ausente | Adicionar secao |
| `Empty commit_types` | Nenhum tipo definido | Definir ao menos um tipo |
| `Missing templates.pr` | Template PR nao especificado | Adicionar path (se --generate pr) |
| `Missing domain config` | Config de dominio ausente | Adicionar (se --generate release) |

## Exemplo Minimo

Configuracao minima funcional:

```json
{
  "commit_types": {
    "feat": { "label": "Features", "patterns": ["\\bfeat\\b"] },
    "fix": { "label": "Fixes", "patterns": ["\\bfix\\b"] }
  },
  "importance": {
    "weight_lines": 0.02,
    "weight_files": 0.6,
    "keyword_bonus": {}
  },
  "importance_bands": [
    { "name": "low", "min": 0.0 },
    { "name": "high", "min": 5.0 }
  ],
  "output": { "dir": "./output" },
  "llm_model": "deepseek-r1:8b",
  "language": "pt-BR",
  "templates": {
    "pr": "templates/pr.md",
    "release": "templates/release.md"
  }
}
```

## Variaveis de Ambiente

A ferramenta nao usa variaveis de ambiente diretamente. Toda configuracao e via arquivo JSON ou argumentos CLI.

Para configurar o Ollama, use as variaveis do proprio Ollama:
- `OLLAMA_HOST` - Host do servidor Ollama (padrao: localhost:11434)
