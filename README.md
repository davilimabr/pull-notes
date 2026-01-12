# Gerador de PR e Release Notes

Ferramenta local em Python para gerar descricoes de Pull Requests e Release Notes a partir de um repositorio Git.

## Requisitos
- Python 3.10+
- Ollama rodando localmente

## Instalacao
```
python -m pip install -e .
```

## Uso rapido
```
python -m gerador_cli /caminho/para/repo --range v1.0..v1.1 --config config.default.json
# compat: python gerador.py /caminho/para/repo --range v1.0..v1.1 --config config.default.json
```

Saidas padrao em `out/`:
- `out/pr.md`
- `out/release.md`
- `out/commits.json`
- `out/conventions.md`

## Configuracao
Use `config.default.json` como base e passe com `--config`.

## Dominio (POC)
A etapa de definicao de dominio reutiliza a POC em `preencher_dominio.py` via `domain_step.py`.

## Estrutura
O codigo foi organizado em camadas sob `src/gerador_cli/`:
- `cli.py`: parsing da CLI.
- `config.py`: carga/validacao de configuracoes.
- `domain/`: modelos, servicos e geracao de perfil de dominio.
- `adapters/`: git, filesystem, llm e POC de dominio.
- `workflows/`: orquestracao principal (`sync.py`).
