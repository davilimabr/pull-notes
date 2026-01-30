# Workflows e Casos de Uso

Este documento descreve os fluxos principais da aplicacao e os casos de uso implementados.

## Fluxo Principal: Geracao Completa

O workflow principal e executado por `workflows/sync.py:run_workflow()`.

```
+------------------------------------------------------------------+
|                     WORKFLOW PRINCIPAL                            |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 1. VALIDACAO E SETUP                                             |
|    - Resolver paths (repo, config, output)                       |
|    - Carregar configuracao JSON                                  |
|    - Validar campos obrigatorios                                 |
|    - Criar diretorio de saida                                    |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 2. COLETA PARALELA (ThreadPoolExecutor)                          |
|    +---------------------------+  +---------------------------+  |
|    | get_commits()             |  | _prepare_domain_text()    |  |
|    | - git log                 |  | - build_domain_profile()  |  |
|    | - parse commits           |  | - generate_domain_xml()   |  |
|    | - fetch body/diff         |  | (apenas se release)       |  |
|    +---------------------------+  +---------------------------+  |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 3. CLASSIFICACAO                                                 |
|    - Para cada commit:                                           |
|      - classify_commit(subject, patterns)                        |
|      - Atribuir change_type (feat, fix, docs, etc.)             |
|      - Marcar is_conventional                                    |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 4. SCORING                                                       |
|    - Para cada commit:                                           |
|      - compute_importance(commit, weights)                       |
|      - Calcular importance_score                                 |
|      - Atribuir importance_band                                  |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 5. GERACAO DE RELATORIOS BASE                                    |
|    - build_convention_report(commits)                            |
|    - export_convention_report() -> conventions.md                |
|    - export_commits() -> commits.json                            |
|    - group_commits_by_type()                                     |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 6. GERACAO CONDICIONAL                                           |
|    +---------------------------+  +---------------------------+  |
|    | SE generate="pr" ou       |  | SE generate="release" ou  |  |
|    |    generate="both":       |  |    generate="both":       |  |
|    |                           |  |                           |  |
|    | - summarize_all_groups    |  | - summarize_all_groups    |  |
|    |   (output_type="pr")      |  |   (output_type="release") |  |
|    | - render_changes_by_type  |  | - render_changes_by_type  |  |
|    | - build_pr_fields()       |  | - build_release_fields()  |  |
|    | - render_template(pr.md)  |  | - render_template         |  |
|    | - export -> pr.md         |  |   (release.md)            |  |
|    +---------------------------+  | - export -> release.md    |  |
|                                   +---------------------------+  |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 7. RETORNO                                                       |
|    - return 0 (sucesso)                                          |
+------------------------------------------------------------------+
```

## Casos de Uso Detalhados

### UC1: Coletar Commits

**Servico:** `data_collection.get_commits()`

**Entrada:**
- `repo_dir`: Path do repositorio
- `revision_range`: Range Git (ex: v1.0..v1.1)
- `since`: Data inicial (opcional)
- `until`: Data final (opcional)
- `config`: Configuracao (para limites de diff)

**Fluxo:**
```
1. Construir comando git log
   git log --date=iso-strict --pretty=format:__COMMIT__%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s --numstat

2. Executar via run_git()

3. Parsear saida:
   - Separar por COMMIT_MARKER
   - Extrair campos delimitados por \x1f
   - Extrair numstat (additions, deletions, files)

4. Fetch paralelo para cada commit:
   - git show -s --format=%B <sha>  -> body
   - git show --unified=3 <sha>    -> diff

5. Truncar diffs conforme config.diff.max_bytes/max_lines

6. Retornar List[Commit]
```

**Saida:** Lista de objetos Commit com todos os campos preenchidos

---

### UC2: Classificar Commits

**Servico:** `aggregation.classify_commit()`

**Entrada:**
- `subject`: Subject do commit
- `commit_types`: Dicionario de tipos e patterns

**Fluxo:**
```
1. Converter subject para lowercase

2. Para cada tipo em commit_types:
   Para cada pattern do tipo:
     Se re.search(pattern, subject):
       return (tipo, True)

3. Se nenhum match:
   return ("other", False)
```

**Configuracao de Patterns:**
```json
{
  "feat": {"patterns": ["\\bfeat\\b", "\\bfeature\\b", "\\badd\\b"]},
  "fix": {"patterns": ["\\bfix\\b", "\\bbugfix\\b", "\\bcorrect\\b"]},
  "docs": {"patterns": ["\\bdocs\\b", "\\bdocument\\b"]},
  "refactor": {"patterns": ["\\brefactor\\b", "\\breorganize\\b"]},
  "test": {"patterns": ["\\btest\\b", "\\bspec\\b"]},
  "chore": {"patterns": ["\\bchore\\b", "\\bbuild\\b", "\\bci\\b"]}
}
```

---

### UC3: Calcular Importancia

**Servico:** `aggregation.compute_importance()`

**Entrada:**
- `commit`: Objeto Commit
- `config`: Configuracao com pesos

**Formula:**
```
score = (additions + deletions) * weight_lines
      + len(files) * weight_files
      + keyword_bonus
```

**Keyword Bonuses:**
| Keyword | Bonus |
|---------|-------|
| breaking | 3.0 |
| security | 2.0 |
| hotfix | 2.0 |
| perf | 1.0 |

**Mapeamento para Bands:**
| Score | Band |
|-------|------|
| < 3.0 | low |
| 3.0 - 5.9 | medium |
| 6.0 - 8.9 | high |
| >= 9.0 | critical |

---

### UC4: Agrupar por Tipo

**Servico:** `aggregation.group_commits_by_type()`

**Entrada:**
- `commits`: Lista de commits classificados
- `config`: Configuracao com tipos

**Fluxo:**
```
1. Criar dicionario vazio por tipo

2. Para cada commit:
   groups[commit.change_type].append(commit)

3. Para cada grupo:
   Ordenar por importance_score DESC

4. Ordenar grupos por ordem definida em config

5. Retornar List[(type, List[Commit])]
```

**Saida:**
```python
[
    ("feat", [commit1, commit2]),
    ("fix", [commit3]),
    ("docs", [commit4, commit5]),
]
```

---

### UC5: Resumir Grupo de Commits

**Servico:** `aggregation.summarize_commit_group()`

**Entrada:**
- `type_key`: Tipo do grupo (feat, fix, etc.)
- `commits`: Lista de commits do grupo
- `config`: Configuracao
- `model`: Modelo LLM
- `output_type`: "pr" ou "release"

**Fluxo:**
```
1. Formatar commits em blocos:
   Para cada commit:
     - SHA curto
     - Subject
     - Body (se houver)
     - Diff truncado

2. Carregar prompt apropriado:
   - "pr" -> commit_group_summary_pr.txt
   - "release" -> commit_group_summary_release.txt

3. Renderizar prompt com:
   - type_label
   - commit_blocks
   - language_hint

4. Chamar LLM via call_ollama()

5. Retornar resposta formatada em bullets
```

**Diferenca entre PR e Release:**

| Aspecto | PR | Release |
|---------|----|---------
| Foco | Tecnico | Usuario final |
| Linguagem | Detalhada | Simplificada |
| Inclui | Detalhes de implementacao | Beneficios para usuario |

---

### UC6: Gerar Campos de PR

**Servico:** `composition.build_pr_fields()`

**Entrada:**
- `grouped_summaries`: Lista de (tipo, resumo)
- `config`: Configuracao
- `model`: Modelo LLM

**Fluxo:**
```
1. Formatar summaries em markdown

2. Carregar prompt pr_fields.txt

3. Renderizar com:
   - commit_summaries formatados
   - language_hint

4. Chamar LLM

5. Extrair JSON da resposta

6. Retornar campos:
   {
     "title": "...",
     "summary": "...",
     "risks": "...",
     "testing": "..."
   }
```

---

### UC7: Gerar Campos de Release

**Servico:** `composition.build_release_fields()`

**Entrada:**
- `release_summaries`: Lista de (tipo, resumo)
- `domain_xml`: XML de dominio do repositorio
- `config`: Configuracao
- `model`: Modelo LLM
- `version`: Label de versao

**Fluxo:**
```
1. Formatar summaries

2. Truncar domain_xml (max 6000 chars)

3. Carregar prompt release_fields.txt

4. Renderizar com:
   - release_version
   - domain_xml
   - commit_summaries
   - language_hint

5. Chamar LLM

6. Extrair JSON

7. Retornar campos:
   {
     "executive_summary": "...",
     "highlights": "...",
     "migration_notes": "...",
     "known_issues": "...",
     "internal_notes": "..."
   }
```

---

### UC8: Renderizar Template

**Servico:** `composition.render_template()`

**Entrada:**
- `template_text`: Conteudo do template markdown
- `values`: Dicionario de valores

**Fluxo:**
```
1. Para cada key em values:
   Substituir {{key}} por values[key]

2. Limpar placeholders nao-usados:
   Remover linhas com {{...}} restantes

3. Retornar markdown final
```

---

### UC9: Construir Perfil de Dominio

**Servico:** `domain_profile.build_domain_profile()`

**Entrada:**
- `repo_dir`: Path do repositorio
- `template_path`: Template XML
- `xsd_path`: Schema de validacao
- `model`: Modelo LLM
- `config`: Configuracao

**Fluxo:**
```
1. Indexar repositorio:
   - Iterar arquivos (.py, .md, .json, .yaml)
   - Ler conteudo (limitado por max_file_bytes)
   - Extrair anchors (keywords, APIs, tables)

2. Preencher template com anchors extraidos

3. Construir prompt com:
   - Contexto do repositorio (snippets de codigo)
   - Template XML pre-preenchido

4. Chamar LLM para completar XML:
   - Preencher <domain>
   - Preencher <entities>
   - Ajustar descricoes

5. Validar XML contra XSD

6. Salvar e retornar DomainResult
```

---

### UC10: Exportar Artefatos

**Servico:** `export.export_*()`

**Funcoes:**

1. **export_commits(commits, output_dir)**
   - Serializa List[Commit] para JSON
   - Salva em commits.json

2. **export_convention_report(report, output_dir)**
   - Formata relatorio de convencoes em markdown
   - Salva em conventions.md

3. **export_text_document(content, output_dir, filename)**
   - Salva conteudo texto
   - Usado para pr.md e release.md

---

## Fluxos Alternativos

### Modo --no-llm

Quando `--no-llm` e especificado:

```
1. Coleta de commits (normal)
2. Classificacao (normal)
3. Scoring (normal)
4. Sumarizacao: SKIP LLM
   - Usar subjects como fallback
   - Agrupar por tipo sem resumir
5. Composicao: SKIP field generation
   - Usar placeholders ou valores vazios
6. Exportacao (normal)
```

### Modo --refresh-domain

Quando `--refresh-domain` e especificado:

```
1. Ignorar XML de dominio existente
2. Recriar perfil completo:
   - Re-indexar repositorio
   - Re-extrair anchors
   - Re-chamar LLM
   - Re-validar contra XSD
3. Salvar novo XML
```

### Modo --generate pr

Apenas gera PR, sem release notes:

```
1. Coleta de commits
2. Classificacao e scoring
3. Sumarizacao com output_type="pr"
4. build_pr_fields()
5. render_template(pr.md)
6. Exportar apenas pr.md
```

### Modo --generate release

Apenas gera release notes:

```
1. Coleta de commits
2. Preparacao de dominio (obrigatorio)
3. Classificacao e scoring
4. Sumarizacao com output_type="release"
5. build_release_fields()
6. render_template(release.md)
7. Exportar apenas release.md
```

## Diagrama de Sequencia: Geracao de Release

```
Usuario      CLI        Workflow     DataCollection    Aggregation    Composition    Export
   |          |            |              |                |              |            |
   |--run---->|            |              |                |              |            |
   |          |--args----->|              |                |              |            |
   |          |            |--get_commits->|              |                |            |
   |          |            |              |--git log---->|                |            |
   |          |            |              |<--commits----|                |            |
   |          |            |<-commits-----|              |                |            |
   |          |            |              |              |                |            |
   |          |            |--classify------------------->|              |            |
   |          |            |<-classified------------------|              |            |
   |          |            |              |              |                |            |
   |          |            |--score------------------------->|            |            |
   |          |            |<-scored-------------------------|            |            |
   |          |            |              |              |                |            |
   |          |            |--summarize--------------------->|            |            |
   |          |            |              |              |--LLM call----->|            |
   |          |            |<-summaries----------------------|            |            |
   |          |            |              |              |                |            |
   |          |            |--build_release_fields---------->|            |            |
   |          |            |              |              |--LLM call----->|            |
   |          |            |<-fields-------------------------|            |            |
   |          |            |              |              |                |            |
   |          |            |--render_template--------------->|            |            |
   |          |            |<-markdown-----------------------|            |            |
   |          |            |              |              |                |            |
   |          |            |--export---------------------------------------->|         |
   |          |            |<-path------------------------------------------|         |
   |          |<--0--------|              |              |                |            |
   |<-success-|            |              |              |                |            |
```
