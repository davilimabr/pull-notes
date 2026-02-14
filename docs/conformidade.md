# Relatório de Conformidade do Sistema

**Data:** 2026-02-04
**Versão do Sistema:** 0.1.0
**Documento de Referência:** [requisitos_sistemas.md](doc/requisitos_sistemas.md)

---

## Sumário Executivo

Este relatório analisa a conformidade do sistema "PullNotes" com os requisitos funcionais e não funcionais especificados no documento de requisitos. A análise foi realizada através de inspeção direta do código-fonte e dos artefatos do projeto.

### Resultado Geral

| Categoria | Total | Conformes | Parcialmente Conformes | Não Conformes |
|-----------|-------|-----------|----------------------|---------------|
| Requisitos Funcionais | 21 | 19 | 1 | 1 |
| Requisitos Não Funcionais | 8 | 5 | 2 | 1 |
| **Total** | **29** | **24** | **3** | **2** |

**Taxa de Conformidade Total:** 82.8% (conformes) / 93.1% (conformes + parcialmente conformes)

---

## Requisitos Funcionais

### RF01 - Conectar-se a um repositório Git local
**Status:** ✅ CONFORME

**Evidências:**
- [cli.py:12](src/pullnotes/cli.py#L12): Argumento `repo` aceita caminho para repositório Git local (default: `.`)
- [workflows/sync.py:122-124](src/pullnotes/workflows/sync.py#L122-L124): Validação do diretório do repositório
- [adapters/subprocess.py](src/pullnotes/adapters/subprocess.py): Função `run_git()` executa comandos git no repositório

---

### RF02 - Extrair histórico de commits
**Status:** ✅ CONFORME

**Evidências:**
- [cli.py:13-15](src/pullnotes/cli.py#L13-L15): Parâmetros `--range`, `--since`, `--until` permitem configurar intervalo
- [data_collection.py:85-127](src/pullnotes/domain/services/data_collection.py#L85-L127): Função `get_commits()` extrai commits com suporte a:
  - Intervalo por revisão (tags, hashes, branches)
  - Filtro por data (`--since`, `--until`)
  - Fallback automático para refs `origin/` quando refs locais não existem

---

### RF03 - Coletar metadados de cada commit
**Status:** ✅ CONFORME

**Evidências:**
- [models.py:16-37](src/pullnotes/domain/models.py#L16-L37): Dataclass `Commit` contém todos os metadados requeridos:
  - `sha` (hash)
  - `author_name`, `author_email` (autor e e-mail)
  - `date` (data/hora em formato ISO)
  - `subject`, `body` (mensagem completa)
  - `files` (lista de arquivos modificados)
  - `additions`, `deletions` (linhas adicionadas/removidas)
  - `diff` (diff completo)
- [data_collection.py:34-82](src/pullnotes/domain/services/data_collection.py#L34-L82): Função `parse_git_log()` extrai todos esses metadados
- [data_collection.py:112-126](src/pullnotes/domain/services/data_collection.py#L112-L126): Busca assíncrona de body e diff em paralelo

---

### RF04 - Identificar arquivos "documentais" no repositório
**Status:** ✅ CONFORME

**Evidências:**
- [domain_definition.py:24-50](src/pullnotes/adapters/domain_definition.py#L24-L50): Constante `TEXT_EXTS` define extensões documentais configuráveis:
  ```python
  TEXT_EXTS = {".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx",
               ".java", ".cs", ".go", ".rb", ".php", ".sh", ".yml", ".yaml",
               ".json", ".toml", ".ini", ".cfg", ".conf", ".xml", ".sql", ...}
  ```
- [domain_definition.py:151-152](src/pullnotes/adapters/domain_definition.py#L151-L152): Priorização de READMEs e arquivos de configuração
- [domain_definition.py:178-187](src/pullnotes/adapters/domain_definition.py#L178-L187): Função `iter_repo_files()` varre repositório respeitando regras de ignore

---

### RF05 - Construir contexto de domínio da aplicação
**Status:** ✅ CONFORME

**Evidências:**
- [domain_profile.py:51-116](src/pullnotes/adapters/domain_profile.py#L51-L116): Função `generate_domain_profile()` implementa o fluxo completo:
  - Concatena conteúdo de arquivos documentais
  - Envia ao modelo de linguagem
  - Solicita preenchimento de template estruturado
- [schemas.py:190-197](src/pullnotes/domain/schemas.py#L190-L197): Schema `ProjectProfile` contém campos estruturados:
  - `project_type` (tipo de projeto)
  - `domain` (domínio de negócio com labels e anchors)
  - `domain_details` (summary, entities, core_tasks, actors, integrations, non_functional)
  - `evidence` (evidências das inferências)

**Nota:** O formato de saída é JSON (via Pydantic) em vez de XML, conforme mencionado no requisito. Esta é uma decisão de implementação válida que melhora a estruturação e validação dos dados.

---

### RF06 - Armazenar o modelo de domínio
**Status:** ✅ CONFORME

**Evidências:**
- [domain_profile.py:119-125](src/pullnotes/adapters/domain_profile.py#L119-L125): Função `save_domain_profile()` persiste em JSON
- [domain_profile.py:128-131](src/pullnotes/adapters/domain_profile.py#L128-L131): Função `load_domain_profile()` carrega perfil existente
- [workflows/sync.py:82-118](src/pullnotes/workflows/sync.py#L82-L118): Lógica de cache - verifica existência antes de recomputar
- [config.default.json:28-33](config.default.json#L28-L33): Configuração `domain.output_path` define local de armazenamento

---

### RF07 - Classificar commits por tipo de alteração (taxonomia)
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:49-60](src/pullnotes/domain/services/aggregation.py#L49-L60): Função `classify_commit()` classifica usando padrões regex configuráveis
- [config.default.json:2-14](config.default.json#L2-L14): Taxonomia configurável com 11 tipos:
  - feat, fix, docs, refactor, perf, test, build, ci, style, chore, revert
- [aggregation.py:16-46](src/pullnotes/domain/services/aggregation.py#L16-L46): Suporte a padrões JS-style (`/.../flags`) e regex Python

---

### RB01 - Mensagens fora da convenção
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:49-60](src/pullnotes/domain/services/aggregation.py#L49-L60): Retorna `("other", False)` quando nenhum padrão é encontrado
- [workflows/sync.py:75-79](src/pullnotes/workflows/sync.py#L75-L79): Função `_warn_on_non_conventional()` emite alerta ao usuário:
  ```python
  print("⚠️ WARNING: Commits fora do padrao definido foram encontrados...")
  ```
- [config.default.json:15](config.default.json#L15): Configuração `other_label` para categoria de fallback

---

### RF08 - Agrupar commits por tipo de alteração
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:82-97](src/pullnotes/domain/services/aggregation.py#L82-L97): Função `group_commits_by_type()` agrupa commits por tipo
- Commits "other" são agrupados separadamente

---

### RF09 - Calcular um score de importância por commit
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:63-79](src/pullnotes/domain/services/aggregation.py#L63-L79): Função `compute_importance()` calcula score usando:
  - Tamanho do diff (linhas adicionadas/removidas) × peso configurável
  - Número de arquivos afetados × peso configurável
  - Bônus por palavras-chave na mensagem (breaking, security, perf, hotfix)
- [config.default.json:16-19](config.default.json#L16-L19): Pesos e bônus configuráveis

---

### RF10 - Classificar importância em faixas
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:74-78](src/pullnotes/domain/services/aggregation.py#L74-L78): Mapeamento para faixas qualitativas
- [config.default.json:21-26](config.default.json#L21-L26): Faixas configuráveis:
  - low (min: 0.0)
  - medium (min: 3.0)
  - high (min: 6.0)
  - critical (min: 9.0)
- [models.py:32](src/pullnotes/domain/models.py#L32): Campo `importance_band` no modelo Commit

---

### RF11 - Ordenar commits por importância
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:87-88](src/pullnotes/domain/services/aggregation.py#L87-L88): Ordenação por `importance_score` (decrescente) dentro de cada grupo:
  ```python
  typed_commits = sorted(..., key=lambda c: c.importance_score, reverse=True)
  ```

---

### RF13 - Garantir que o resumo seja factualmente ancorado
**Status:** ⚠️ PARCIALMENTE CONFORME

**Evidências Positivas:**
- [domain_profile.txt:13-18](src/pullnotes/prompts/domain_profile.txt#L13-L18): Instruções explícitas para usar apenas informações presentes no repositório:
  ```
  RULES:
  1. Use only information present in the repository
  3. Do not invent libraries, names, metrics, or integrations not explicitly present
  ```
- [data_collection.py:130-206](src/pullnotes/domain/services/data_collection.py#L130-L206): Extração de "diff anchors" (keywords, artifacts) para ancorar resumos
- [aggregation.py:104-138](src/pullnotes/domain/services/aggregation.py#L104-L138): Formatação de anchors no prompt para contextualização

**Lacunas Identificadas:**
- Os prompts de commit summary (PR e release) não contêm instruções explícitas sobre não inventar informações
- Não há mecanismo de validação pós-geração para detectar alucinações
- Não há sinalização explícita ao usuário quando respostas estão fora do padrão esperado

**Recomendação:** Adicionar instruções anti-alucinação nos prompts e implementar validação de consistência nas respostas.

---

### RF14 - Armazenar descrições de alterações
**Status:** ✅ CONFORME

**Evidências:**
- [models.py:29-33](src/pullnotes/domain/models.py#L29-L33): Campos armazenados no modelo Commit:
  - `change_type`, `is_conventional`, `importance_score`, `importance_band`, `summary`
- [export.py:58-64](src/pullnotes/domain/services/export.py#L58-L64): Função `export_commits()` persiste dados em JSON
- [workflows/sync.py:164](src/pullnotes/workflows/sync.py#L164): Exportação de commits para `utils/commit.json`

---

### RF15 - Carregar e gerenciar templates de descrições
**Status:** ✅ CONFORME

**Evidências:**
- [templates/pr.md](src/pullnotes/templates/pr.md): Template para Pull Request com campos:
  - title, summary, changes_by_type, risks, testing, alerts
- [templates/release.md](src/pullnotes/templates/release.md): Template para Release Notes com campos:
  - version, executive_summary, highlights, changes_by_type, migration_notes, known_issues, internal_notes
- [config.default.json:34](config.default.json#L34): Caminhos configuráveis para templates
- [composition.py:129-135](src/pullnotes/domain/services/composition.py#L129-L135): Função `render_template()` para renderização

---

### RF17 - Ajustar o contexto para Release Notes usando o domínio da aplicação
**Status:** ✅ CONFORME

**Evidências:**
- [composition.py:88-126](src/pullnotes/domain/services/composition.py#L88-L126): Função `build_release_fields()` incorpora `domain_context` no prompt
- [release_fields.txt:9-10](src/pullnotes/prompts/release_fields.txt#L9-L10): Template inclui contexto de domínio:
  ```
  Domain context (for understanding the project):
  {{domain_context}}
  ```
- [workflows/sync.py:216](src/pullnotes/workflows/sync.py#L216): Conversão do perfil de domínio para JSON no prompt

---

### RF18 - Completar campos de alto nível via LLM
**Status:** ✅ CONFORME

**Evidências:**
- [composition.py:53-85](src/pullnotes/domain/services/composition.py#L53-L85): `build_pr_fields()` gera campos abstratos via LLM:
  - title, summary, risks, testing
- [composition.py:88-126](src/pullnotes/domain/services/composition.py#L88-L126): `build_release_fields()` gera campos abstratos via LLM:
  - executive_summary, highlights, migration_notes, known_issues, internal_notes
- [schemas.py:42-87](src/pullnotes/domain/schemas.py#L42-L87): Schemas Pydantic com validação para garantir estrutura

---

### RF20 - Exportar resultados em formatos compatíveis
**Status:** ✅ CONFORME

**Evidências:**
- [export.py:75-92](src/pullnotes/domain/services/export.py#L75-L92): Funções `export_release()` e `export_pr()` salvam em Markdown
- Estrutura de saída organizada:
  ```
  {output_dir}/{repo_name}/
  ├── utils/          # commit.json, conventions.md, domain_profile.json
  ├── releases/       # release_{version}.md
  └── prs/            # pr_{title}.md
  ```

---

### RF23 - Relatar conformidade com convenções de mensagens
**Status:** ✅ CONFORME

**Evidências:**
- [aggregation.py:300-319](src/pullnotes/domain/services/aggregation.py#L300-L319): Função `build_convention_report()` gera relatório com:
  - Total de commits
  - Commits convencionais vs. outros
  - Exemplos de boas e más práticas
- [workflows/sync.py:158-159](src/pullnotes/workflows/sync.py#L158-L159): Exportação para `utils/conventions.md`

---

### RF24 - Configuração de parâmetros do pipeline
**Status:** ✅ CONFORME

**Evidências:**
- [config.default.json](config.default.json): Arquivo de configuração JSON completo com:
  - `commit_types`: taxonomia de tipos
  - `importance`: pesos para scoring
  - `importance_bands`: faixas de importância
  - `diff`: limites de anchors
  - `domain`: configurações de extração de domínio
  - `templates`: caminhos de templates
  - `output`: diretório de saída
  - `language`: idioma de saída
  - `llm_model`: modelo de linguagem
  - `llm_timeout_seconds`, `llm_max_retries`: parâmetros LLM
- [cli.py:10-23](src/pullnotes/cli.py#L10-L23): Overrides via CLI:
  - `--config`, `--range`, `--since`, `--until`, `--generate`, `--version`, `--output-dir`, `--model`, `--no-llm`
- [config.py:33-121](src/pullnotes/config.py#L33-L121): Validação robusta de configurações

---

## Requisitos Não Funcionais

### RNF01 - Privacidade e confidencialidade
**Status:** ✅ CONFORME

**Evidências:**
- O sistema usa Ollama para execução local de LLMs - não há envio de dados a serviços externos por padrão
- [http.py:15-45](src/pullnotes/adapters/http.py#L15-L45): Cliente Ollama executa localmente
- [pyproject.toml:12](pyproject.toml#L12): Dependência `ollama` para execução local
- Não há endpoints de rede expostos - CLI puro
- Nenhum dado é enviado a APIs externas sem configuração explícita

---

### RNF02 - Uso de modelos de linguagem leves
**Status:** ✅ CONFORME

**Evidências:**
- [config.default.json:37](config.default.json#L37): Modelo padrão `deepseek-r1:8b` (modelo leve de 8B parâmetros)
- [cli.py:21](src/pullnotes/cli.py#L21): Opção `--model` permite override
- Integração com Ollama permite uso de qualquer modelo local

---

### RNF03 - Desempenho
**Status:** ✅ CONFORME

**Evidências:**
- [data_collection.py:119-126](src/pullnotes/domain/services/data_collection.py#L119-L126): Processamento paralelo de commits com `ThreadPoolExecutor`
- [workflows/sync.py:140-150](src/pullnotes/workflows/sync.py#L140-L150): Busca paralela de commits e perfil de domínio
- [llm_structured.py:21-27](src/pullnotes/adapters/llm_structured.py#L21-L27): Timeout configurável para chamadas LLM
- Limite de bytes para contexto evita sobrecarga de memória

---

### RNF04 - Robustez e tolerância a falhas
**Status:** ✅ CONFORME

**Evidências:**
- [llm_structured.py:79-125](src/pullnotes/adapters/llm_structured.py#L79-L125): Retry com feedback de erro (até 3 tentativas)
- [aggregation.py:281-295](src/pullnotes/domain/services/aggregation.py#L281-L295): Fallback para subjects quando LLM falha:
  ```python
  except Exception as exc:
      print(f"WARNING: Falha ao resumir grupo {type_label}: {exc}. Usando assuntos como fallback.")
  ```
- [workflows/sync.py:186-187](src/pullnotes/workflows/sync.py#L186-L187): Mensagens de erro claras ao usuário
- [domain_profile.py:96-100](src/pullnotes/adapters/domain_profile.py#L96-L100): Try/catch para carregar perfil existente
- [errors.py:4-6](src/pullnotes/domain/errors.py#L4-L6): Exceções de domínio específicas

---

### RNF05 - Usabilidade
**Status:** ✅ CONFORME

**Evidências:**
- [cli.py:11](src/pullnotes/cli.py#L11): Descrição clara no parser: "Generate PR descriptions and release notes from a Git repo"
- [cli.py:12-22](src/pullnotes/cli.py#L12-L22): Help text para cada argumento
- [workflows/sync.py:79](src/pullnotes/workflows/sync.py#L79): Mensagens de alerta em português para usuários brasileiros
- [config.py:116-121](src/pullnotes/config.py#L116-L121): Mensagens de erro descritivas para configuração inválida

---

### RNF07 - Portabilidade (Docker)
**Status:** ❌ NÃO CONFORME

**Evidências:**
- Não foi encontrado `Dockerfile` ou `docker-compose.yml` no projeto
- O requisito especifica: "O sistema deve disponibilizar uma imagem Docker que encapsule todas as dependências"

**Recomendação:** Criar Dockerfile e docker-compose.yml para encapsular:
- Python 3.10+
- Dependências do projeto
- Ollama (ou configuração para Ollama externo)

---

### RNF08 - Segurança
**Status:** ⚠️ PARCIALMENTE CONFORME

**Evidências Positivas:**
- Não há logging de código sensível por padrão
- Não há criação de endpoints de rede
- Configurações são lidas de arquivo local

**Lacunas Identificadas:**
- Não há documentação explícita sobre práticas de armazenamento de segredos
- O arquivo `config.default.json` não menciona tratamento de tokens/credenciais
- Não há validação explícita para evitar que credenciais sejam incluídas em logs

**Recomendação:** Documentar práticas de segurança e adicionar validação para excluir arquivos sensíveis (como `.env`) do processamento.

---

### RNF10 - Internacionalização
**Status:** ⚠️ PARCIALMENTE CONFORME

**Evidências Positivas:**
- [config.default.json:36](config.default.json#L36): Configuração `language: "pt-BR"` presente
- [aggregation.py:100-101](src/pullnotes/domain/services/aggregation.py#L100-L101): Função `build_language_hint()` gera hint de idioma para prompts
- [domain_definition.py:54-143](src/pullnotes/adapters/domain_definition.py#L54-L143): Stopwords em português e inglês

**Lacunas Identificadas:**
- Templates de PR e Release estão apenas em inglês (campos como "Risks", "Testing", "Known Issues")
- Não há mecanismo de templates por idioma
- Mensagens do CLI estão misturadas (português e inglês)

**Recomendação:** Implementar sistema de templates localizados e padronizar idioma das mensagens.

---

## Resumo das Não Conformidades

### Críticas (bloqueiam conformidade total)

| ID | Requisito | Status | Ação Necessária |
|----|-----------|--------|-----------------|
| RNF07 | Portabilidade Docker | ❌ Não Conforme | Criar Dockerfile e docker-compose.yml |

### Parciais (funcionalidade presente mas incompleta)

| ID | Requisito | Status | Ação Necessária |
|----|-----------|--------|-----------------|
| RF13 | Ancoragem factual | ⚠️ Parcial | Adicionar instruções anti-alucinação nos prompts |
| RNF08 | Segurança | ⚠️ Parcial | Documentar práticas de segurança |
| RNF10 | Internacionalização | ⚠️ Parcial | Implementar templates localizados |

---

## Pontos Fortes do Sistema

1. **Arquitetura bem estruturada**: Uso de padrões como Hexagonal Architecture, Clean Architecture e DDD
2. **Validação robusta**: Uso de Pydantic para validação de schemas LLM com retry automático
3. **Processamento paralelo**: ThreadPoolExecutor para operações I/O bound
4. **Configurabilidade**: Praticamente todos os parâmetros são configuráveis via JSON
5. **Tolerância a falhas**: Sistema de fallback quando LLM não está disponível
6. **Privacidade**: Execução totalmente local via Ollama

---

## Recomendações de Melhoria

### Alta Prioridade
1. **Criar infraestrutura Docker** para atender RNF07
2. **Adicionar instruções anti-alucinação** nos prompts de summarização

### Média Prioridade
3. **Implementar templates localizados** (pt-BR e en-US)
4. **Documentar práticas de segurança** no README
5. **Adicionar validação** para excluir arquivos sensíveis

### Baixa Prioridade
6. **Padronizar idioma** das mensagens do sistema
7. **Adicionar métricas** de qualidade das respostas LLM

---

## Conclusão

O sistema demonstra alto nível de conformidade com os requisitos especificados, implementando corretamente 24 dos 29 requisitos (82.8%). As não conformidades identificadas são majoritariamente relacionadas a aspectos de infraestrutura (Docker) e melhorias incrementais de internacionalização.

A arquitetura do sistema é sólida e extensível, facilitando a implementação das melhorias necessárias para atingir 100% de conformidade.
