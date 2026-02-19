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
| FASE 0: SETUP                                                    |
|    - Resolver paths (repo, config, output)                       |
|    - Carregar configuracao JSON                                  |
|    - Validar campos obrigatorios                                 |
|    - Criar estrutura de diretorios de saida                      |
|    - Configurar debug de prompts                                 |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| FASE A: COLETA PARALELA (ThreadPoolExecutor, 2 workers)          |
|    +---------------------------+  +---------------------------+  |
|    | get_commits()             |  | build_domain_profile()    |  |
|    | - git log                 |  | - indexar repositorio     |  |
|    | - parse commits           |  | - extrair anchors         |  |
|    | - fetch body/diff         |  | - chamar LLM (Pydantic)   |  |
|    | - extract_diff_anchors    |  | - cache JSON              |  |
|    +---------------------------+  | (apenas se release)       |  |
|                                   +---------------------------+  |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| FASE B: CLASSIFICACAO E AGRUPAMENTO (sem LLM)                   |
|    - classify_commit() para cada commit                          |
|    - compute_importance() para cada commit                       |
|    - build_convention_report()                                   |
|    - export_commits() -> utils/commit.json                       |
|    - export_convention_report() -> utils/conventions.md          |
|    - group_commits_by_type()                                     |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| FASE C: SUMARIZACAO PARALELA (ThreadPoolExecutor, 2 workers)     |
|    +---------------------------+  +---------------------------+  |
|    | summarize_all_groups()    |  | summarize_all_groups()    |  |
|    | output_type="pr"          |  | output_type="release"     |  |
|    | LLM: CommitGroupSummary   |  | LLM: CommitGroupSummary   |  |
|    +---------------------------+  +---------------------------+  |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| FASE D: PREPARACAO DE DADOS (sem LLM)                           |
|    - render_changes_by_type_from_summaries() (PR e Release)      |
|    - Construir lista de alertas (commits nao-convencionais)       |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| FASE E: CAMPOS VIA LLM PARALELO (ThreadPoolExecutor, 2 workers)  |
|    +---------------------------+  +---------------------------+  |
|    | build_pr_fields()         |  | build_release_fields()    |  |
|    | - parse template pr.md    |  | - parse template          |  |
|    | - gerar schema dinamico   |  |   release.md              |  |
|    | - LLM: secoes dinamicas   |  | - gerar schema dinamico   |  |
|    +---------------------------+  | - LLM: secoes dinamicas   |  |
|                                   +---------------------------+  |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| FASE F: RENDERIZACAO E EXPORTACAO (sem LLM)                     |
|    - render_template(pr) -> prs/pr_{titulo}.md                   |
|    - render_template(release) -> releases/release_{versao}.md    |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| RETORNO                                                          |
|    - return 0 (sucesso) / 1 (erro)                              |
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
- `config`: Configuracao (para limites de diff anchors)

**Fluxo:**
```
1. Construir comando git log
   git log --date=iso-strict --pretty=format:__COMMIT__%n%H%x1f... --numstat

2. Executar via run_git()

3. Parsear saida:
   - Separar por COMMIT_MARKER
   - Extrair campos delimitados por \x1f
   - Extrair numstat (additions, deletions, files)

4. Fetch paralelo para cada commit (ThreadPoolExecutor):
   - git show -s --format=%B <sha>  -> body
   - git show --unified=3 <sha>    -> diff

5. Extrair diff_anchors via extract_diff_anchors()
   - Keywords das linhas +/-
   - Artifacts (endpoints, servicos, etc.)

6. Retornar List[Commit] completos
```

**Saida:** Lista de objetos `Commit` com todos os campos preenchidos

---

### UC2: Classificar Commits

**Servico:** `aggregation.classify_commit()`

**Fluxo:**
```
1. Converter subject para lowercase

2. Para cada tipo em commit_types:
   Para cada pattern do tipo:
     Se re.search(pattern, subject):
       return (tipo, True)  # is_conventional=True

3. Se nenhum match:
   return ("other", False)  # is_conventional=False
```

---

### UC3: Calcular Importancia

**Servico:** `aggregation.compute_importance()`

**Formula:**
```
score = (additions + deletions) * weight_lines
      + len(files) * weight_files
      + keyword_bonus
```

**Faixas Padrao:**
| Score | Band |
|-------|------|
| < 3.0 | low |
| 3.0 - 5.9 | medium |
| 6.0 - 8.9 | high |
| >= 9.0 | critical |

---

### UC4: Agrupar por Tipo

**Servico:** `aggregation.group_commits_by_type()`

**Fluxo:**
```
1. Criar grupos vazios por tipo

2. Para cada commit:
   groups[commit.change_type].append(commit)

3. Para cada grupo:
   Ordenar por importance_score DESC

4. Retornar List[(type, List[Commit])]
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
     - DiffAnchors (keywords, artifacts, files)

2. Carregar prompt apropriado:
   - "pr" -> commit_group_summary_pr.txt
   - "release" -> commit_group_summary_release.txt

3. Renderizar prompt com type_label, commit_blocks, language_hint

4. Chamar LLM via call_llm_structured() -> CommitGroupSummary

5. Retornar lista de summary_points formatados em bullets
```

**Diferenca entre PR e Release:**

| Aspecto | PR | Release |
|---------|----|---------|
| Foco | Tecnico | Usuario final |
| Linguagem | Detalhada | Simplificada |
| Inclui | Detalhes de implementacao | Beneficios para usuario |

---

### UC6: Gerar Campos de PR

**Servico:** `composition.build_pr_fields()`

**Fluxo:**
```
1. Parsear template pr.md -> ParsedTemplate
   (template_parser.parse_template)

2. Para cada secao dinamica:
   - Ler instrucoes da secao
   - Construir schema Pydantic dinamico
   (dynamic_fields.build_dynamic_schema)

3. Construir prompt com:
   - Instrucoes de cada secao
   - Summaries dos grupos de commits
   - Mudancas por tipo
   - Alertas
   - language_hint
   (dynamic_fields.build_dynamic_prompt)

4. Chamar LLM via call_llm_structured() com schema dinamico

5. Retornar campos mapeados por chave de secao
```

---

### UC7: Gerar Campos de Release

**Servico:** `composition.build_release_fields()`

**Entrada:**
- `release_summaries`: Lista de (tipo, resumo)
- `domain_profile`: ProjectProfile do repositorio (JSON)
- `config`: Configuracao
- `model`: Modelo LLM
- `version`: Label de versao

**Fluxo identico ao UC6**, mas usando template `release.md` e incluindo o perfil de dominio no contexto do prompt.

---

### UC8: Renderizar Template

**Servico:** `composition.render_template()`

**Fluxo:**
```
1. Para cada secao do ParsedTemplate:
   - Se is_static: preservar conteudo original (checkboxes)
   - Se chave == "alteracoes" (ou "changes"): injetar changes_by_type
   - Se dinamica: substituir pelo valor gerado pelo LLM

2. Montar markdown final com titulo e secoes

3. Retornar markdown completo
```

---

### UC9: Construir Perfil de Dominio

**Servico:** `adapters/domain_profile.build_domain_profile()`

**Fluxo:**
```
1. Verificar cache (utils/domain_profile_{repo}.json)
   - Se existe e --refresh-domain nao foi passado: retornar cache

2. Indexar repositorio (domain_definition.build_repository_index):
   - Iterar arquivos (.py, .md, .json, .yaml, etc.)
   - Ler conteudo limitado por max_file_bytes
   - Extrair anchors (top_keywords, extract_anchors)

3. Construir prompt com:
   - Snippets de codigo do repositorio
   - Anchors extraidos (keywords, APIs, tabelas, eventos)
   (prompts/domain_profile.txt)

4. Chamar LLM via call_llm_structured() -> ProjectProfile (Pydantic)

5. Salvar ProjectProfile como JSON no cache

6. Retornar ProjectProfile validado
```

---

### UC10: Exportar Artefatos

**Servico:** `export.export_*()`

**Estrutura criada:**
```
{output_dir}/{repo_name}/
├── prs/
│   └── pr_{titulo}.md
├── releases/
│   └── release_{versao}.md
└── utils/
    ├── commit.json
    ├── conventions.md
    ├── domain_profile_{repo}.json
    └── prompts/  (se --debug)
        └── {counter}_{HHMMSS}_{name}.txt
```

---

## Fluxos Alternativos

### Modo --no-llm

Quando `--no-llm` e especificado:

```
1. Coleta de commits (normal)
2. Classificacao e scoring (normal)
3. Exportacao de commits e conventions (normal)
4. Sumarizacao: SKIP LLM
   - Usar subjects dos commits como fallback
5. Geracao de campos: SKIP LLM
   - Usar valores vazios ou placeholder
6. Renderizacao e exportacao (normal, com conteudo minimo)
```

### Modo --refresh-domain

Quando `--refresh-domain` e especificado:

```
1. Ignorar perfil de dominio cacheado (domain_profile_{repo}.json)
2. Re-indexar repositorio completo
3. Re-extrair anchors
4. Re-chamar LLM para gerar novo ProjectProfile
5. Salvar novo perfil no cache
```

### Modo --generate pr

Apenas gera PR, sem release notes:

```
1. Coleta de commits
2. Classificacao e scoring
3. Sumarizacao apenas com output_type="pr"
4. build_pr_fields()
5. render_template(pr.md)
6. Exportar apenas prs/pr_{titulo}.md
```

**Nota:** Perfil de dominio NAO e gerado neste modo.

### Modo --generate release

Apenas gera release notes:

```
1. Coleta de commits
2. Geracao de perfil de dominio (obrigatorio)
3. Classificacao e scoring
4. Sumarizacao apenas com output_type="release"
5. build_release_fields()
6. render_template(release.md)
7. Exportar apenas releases/release_{versao}.md
```

## Diagrama de Sequencia: Geracao de Release

```
Usuario      CLI        Workflow     DataCollection    Aggregation    Composition    Export
   |          |            |              |                |              |            |
   |--run---->|            |              |                |              |            |
   |          |--args----->|              |                |              |            |
   |          |            |==FASE A (paralelo)==          |              |            |
   |          |            |--get_commits->|              |                |            |
   |          |            |--build_domain_profile----------------------->|            |
   |          |            |<-commits-----|              |                |            |
   |          |            |<-domain_profile-------------|                |            |
   |          |            |              |              |                |            |
   |          |            |==FASE B==    |              |                |            |
   |          |            |--classify+score------------>|              |             |
   |          |            |--export_commits+conventions-|-------------->|             |
   |          |            |              |              |                |            |
   |          |            |==FASE C (paralelo)==                                      |
   |          |            |--summarize (pr + release)-->|              |             |
   |          |            |<-summaries------------------|              |             |
   |          |            |              |              |                |            |
   |          |            |==FASE E (paralelo)==                                      |
   |          |            |--build_pr_fields+build_release_fields------>|            |
   |          |            |<-fields------------------------------------|              |
   |          |            |              |              |                |            |
   |          |            |==FASE F==    |              |                |            |
   |          |            |--render_template + export------------------------->|      |
   |          |            |<-paths--------------------------------------------|      |
   |          |<--0--------|              |              |                |            |
   |<-success-|            |              |              |                |            |
```
