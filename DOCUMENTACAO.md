# Documentacao do Gerador de PR e Release Notes

Esta documentacao descreve a ferramenta de geracao automatica de descricoes de Pull Requests e Release Notes, baseada em historico Git e modelos de linguagem locais via Ollama.

## Objetivo
- Reduzir trabalho manual ao compor descricoes de PR e notas de versao.
- Padronizar comunicacao com base em convencoes de commits.
- Manter privacidade: tudo roda localmente, sem envio de codigo a servicos externos.

## Visao geral do fluxo
1) Carrega configuracao (padrao ou via `--config`).
2) Extrai commits do Git conforme `--range`, `--since`, `--until`.
3) Classifica commits por tipo (feat, fix, docs, etc.).
4) Calcula score de importancia e faixa qualitativa.
5) Resume cada commit via LLM (ou fallback com `--no-llm`).
6) Gera relatorio de aderencia a convencoes de commit.
7) Renderiza templates de PR e Release Notes.
8) Para release notes, inclui contexto de dominio gerado pela POC.

## Arquivos principais
- `gerador.py`: CLI principal e orquestracao do pipeline.
- `domain_step.py`: wrapper da POC para gerar o XML de dominio.
- `preencher_dominio.py`: POC original que extrai contexto e chama o Ollama.
- `templates/pr.md`: template de PR.
- `templates/release.md`: template de release.
- `config.default.json`: configuracao base do pipeline.
- `xml/dominio.xml` e `xml/XSD_dominio.xml`: template e schema do dominio.
- `out/`: pasta padrao de saidas.

## CLI e parametros
Exemplo:
```
python gerador.py . --range v1.0..v1.1
```

Opcoes:
- `repo`: caminho do repositorio (padrao `.`).
- `--range`: range Git (ex.: `v1.0..v1.1`).
- `--since` / `--until`: filtro por datas.
- `--config`: caminho de arquivo JSON de configuracao.
- `--generate`: `pr`, `release` ou `both` (padrao `both`).
- `--version`: etiqueta de versao para release.
- `--output-dir`: sobrescreve a pasta de saida.
- `--no-llm`: ignora chamadas de LLM e usa textos base.
- `--refresh-domain`: recalcula o dominio mesmo se ja existir.
- `--model`: sobrescreve o modelo do Ollama para resumos.

## Configuracao
Campos mais relevantes em `config.default.json`:
- `commit_types`: mapa de tipos de commit, labels e regex para classificacao.
- `other_label`: nome da categoria para commits fora da convencao.
- `importance`: pesos do score e bonus por palavras-chave.
- `importance_bands`: faixas de score (low/medium/high/critical).
- `diff`: limites de linhas/bytes para enviar ao LLM.
- `domain`: paths do XML/XSD, saida e modelo de dominio.
- `templates`: caminhos dos templates de PR e release.
- `output`: pasta de saida.
- `language`: idioma sugerido aos prompts.
- `llm_model`: modelo do Ollama para resumos e campos.

## Saidas
- `out/pr.md`: descricao de Pull Request.
- `out/release.md`: release notes.
- `out/commits.json`: metadados enriquecidos de commits.
- `out/conventions.md`: relatorio de convencoes.
- `.gerador/domain.xml`: modelo de dominio preenchido (quando habilitado).

## Etapa de dominio (POC)
A geracao de dominio reaproveita a POC em `preencher_dominio.py`:
- Varre arquivos de texto do repositorio.
- Extrai palavras-chave e artefatos (endpoints, tabelas, eventos, etc.).
- Preenche anchors no XML de dominio.
- Envia o template para o Ollama e valida o retorno com XSD.

O wrapper `domain_step.py` adapta caminhos, valida e salva o resultado.

## Detalhes das funcoes (gerador.py)

### Constantes e estruturas
- `COMMIT_MARKER`: marca usada para separar commits no log do Git.
- `GIT_FORMAT`: formato do `git log` com campos e marcador de commit.
- `DEFAULT_CONFIG`: configuracao padrao embutida no codigo.
- `Commit` (dataclass): estrutura que armazena metadados, classificacao e resumo.

### Funcoes utilitarias
- `deep_merge(base, override)`
  - Mescla dois dicionarios de forma recursiva.
  - Usado para aplicar configuracoes customizadas sobre os defaults.

- `load_config(path)`
  - Carrega o JSON de configuracao e faz merge com `DEFAULT_CONFIG`.
  - Se nao houver path, retorna a configuracao padrao.

- `run_git(repo_dir, args)`
  - Executa `git` com `-C` no repositorio informado.
  - Lanca erro se o comando falhar.

- `parse_git_log(log_text)`
  - Faz parse do output do `git log` usando `COMMIT_MARKER`.
  - Extrai SHA, autor, data, assunto e estatisticas de linhas/arquivos.
  - Retorna lista de `Commit` com campos basicos preenchidos.

- `get_commits(repo_dir, revision_range, since, until)`
  - Monta o comando `git log` com filtros e chama `parse_git_log`.
  - Para cada commit, busca corpo completo e diff via `git show`.

- `trim_diff(diff_text, max_lines, max_bytes)`
  - Reduz o diff para caber nos limites enviados ao LLM.
  - Primeiro corta por linhas, depois por bytes.

- `classify_commit(subject, commit_types)`
  - Aplica regex de tipos de commit ao assunto.
  - Retorna o tipo e um booleano indicando se segue convencao.

- `compute_importance(commit, config)`
  - Calcula score com base em linhas alteradas, numero de arquivos e palavras-chave.
  - Converte o score para uma faixa qualitativa (low/medium/high/critical).

- `call_ollama(model, prompt)`
  - Envia prompt ao Ollama via `ollama.chat`.
  - Retorna apenas o texto de resposta.

- `build_language_hint(language)`
  - Gera uma instrucao curta de idioma para incluir nos prompts.

- `summarize_commit(commit, config, model)`
  - Monta prompt com mensagem, arquivos e diff truncado.
  - Solicita resumo curto e factual (1-2 frases).

- `extract_json(text)`
  - Extrai o primeiro objeto JSON valido de um texto.
  - Usado para interpretar saidas do LLM.

- `build_pr_fields(commits, config, model)`
  - Pede ao LLM um JSON com `title`, `summary`, `risks`, `testing`.
  - Baseia-se apenas nos resumos/mensagens dos commits.

- `build_release_fields(commits, domain_xml, config, model, version)`
  - Pede ao LLM um JSON com campos de release notes.
  - Inclui contexto de dominio (XML) e etiqueta de versao.

- `render_template(template_text, values)`
  - Substitui placeholders `{{chave}}` pelos valores fornecidos.
  - Remove placeholders restantes e adiciona newline final.

- `render_changes_by_type(commits, config)`
  - Agrupa commits por tipo e ordena por importancia.
  - Produz uma secao Markdown por categoria.

- `build_convention_report(commits)`
  - Gera relatorio simples de aderencia a convencoes.
  - Mostra exemplos bons e ruins.

- `ensure_dir(path)`
  - Cria diretorio de saida se nao existir.

- `resolve_repo_path(repo_dir, path_str)`
  - Resolve caminhos relativos ao repositorio.
  - Mantem caminhos absolutos intactos.

### Funcao principal
- `main()`
  - Faz parse de argumentos da CLI.
  - Carrega configuracao e resolve paths.
  - Extrai commits e enriquece com classificacao e importancia.
  - Gera resumos via LLM (ou fallback com `--no-llm`).
  - Escreve `commits.json` e `conventions.md`.
  - Renderiza `pr.md` e/ou `release.md` a partir dos templates.
  - Para release, gera ou reutiliza o XML de dominio via `domain_step.py`.

## Observacoes
- O LLM e orientado a ser factual, mas a ferramenta nao valida semantica do resumo.
- Ajuste `config.default.json` conforme o padrao de commits do seu time.
- O limite de diff e importante para manter custo e tempo do modelo local.
