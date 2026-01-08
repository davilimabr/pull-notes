"""
Extrai TODAS as mensagens de commits de todos os repositórios listados no arquivo de resultados encontrados pelo SEART - GitHub Search Engine,
varrendo a branch default de cada repositório e salvando em um arquivo CSV.

USO:
  python extract_commit_messages_git.py --input repos.csv --output commits.csv
  # opcional:
  #   --workers 8
  #   --tmpdir /path/para/tmp

ENTRADA:
- CSV com cabeçalho incluindo a coluna "name" no formato "owner/repo" (Resultado obtido pela busca).

SAÍDA:
- CSV com colunas: repos, branch, message
"""

import argparse
import concurrent.futures as futures
import csv
import datetime as dt
import logging
import os
import shutil
import tempfile
from typing import Dict, List, Optional, Tuple

import pygit2


def parse_owner_repo(full_name: str) -> Tuple[str, str]:
    full_name = (full_name or "").strip()
    if "/" not in full_name:
        raise ValueError(f'O valor em "name" precisa ser "owner/repo". Recebido: "{full_name}"')
    owner, repo = full_name.split("/", 1)
    if not owner or not repo:
        raise ValueError(f'Formato inválido em "name": "{full_name}"')
    return owner, repo

def iso8601_from_git_time(t: int, offset_minutes: int) -> str:
    tz = dt.timezone(dt.timedelta(minutes=offset_minutes))
    return dt.datetime.fromtimestamp(t, tz=tz).isoformat()

def get_default_branch_from_origin(repo: pygit2.Repository) -> str:
    ref = repo.references.get("refs/remotes/origin/HEAD")
    if ref is None:
        # fallback: se não existir, tenta head local
        if repo.head_is_unborn:
            raise RuntimeError("Repositório sem HEAD válido e sem origin/HEAD; não foi possível detectar a default.")
        return repo.head.shorthand

    resolved = ref.resolve()  
    name = resolved.name
    if not name.startswith("refs/remotes/origin/"):
        raise RuntimeError(f"origin/HEAD inesperado: {name}")
    return name.split("/")[-1]  # 'main'

def walk_commits_on_default(repo: pygit2.Repository, default_branch: str) -> List[Dict]:
    refname = f"refs/remotes/origin/{default_branch}"
    ref = repo.references.get(refname)
    if ref is None:
        raise RuntimeError(f"Referência {refname} não encontrada no repositório clonado.")

    tip_oid = ref.target
    walker = repo.walk(tip_oid, pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_TIME)

    rows = []
    for commit in walker:
        rows.append({
            "message": (commit.message or "").replace("\r\n", "\n").strip(),
        })
    return rows

def clone_and_extract(full_name: str, base_tmpdir: str) -> Tuple[str, str, List[Dict]]:
    owner, repo = parse_owner_repo(full_name)
    url = f"https://github.com/{owner}/{repo}.git"

    tmpdir = tempfile.mkdtemp(prefix="repo_", dir=base_tmpdir)
    repo_dir = os.path.join(tmpdir, repo)

    logging.debug(f"Clonando {url} em {repo_dir} ...")
    cloned = pygit2.clone_repository(
        url=url,
        path=repo_dir,
        bare=False,
        checkout_branch=None,
    )

    remote = cloned.remotes["origin"]
    remote.fetch()

    default_branch = get_default_branch_from_origin(cloned)
    logging.debug(f"Default branch ({full_name}): {default_branch}")

    rows = walk_commits_on_default(cloned, default_branch)
    for r in rows:
        r["repo"] = full_name
        r["branch"] = default_branch

    # FECHA/REMOVE ANTES DE RETORNAR
    try:
        # fecha handles internos (boa prática, embora o GC do pygit2 já lide)
        del cloned
    except Exception:
        pass

    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:
        logging.warning(f"Falha ao remover diretório temporário {tmpdir}: {e}")

    return full_name, default_branch, rows

def process_repositories_csv(input_csv: str, output_csv: str, workers: Optional[int] = None, tmpdir: Optional[str] = None):
    fields_out = ["repo", "branch", "message"]

    base_tmpdir = tmpdir or tempfile.mkdtemp(prefix="git_min_")
    must_cleanup_base_tmpdir = tmpdir is None

    repos: List[str] = []
    with open(input_csv, newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        for row in reader:
            name = (row.get("name") or "").strip()
            if name:
                repos.append(nameq)

    if not repos:
        raise RuntimeError("Nenhum repositório válido encontrado no CSV de entrada.")

    max_workers = workers or min(32, (os.cpu_count() or 4) * 2) 
    logging.info(f"Processando {len(repos)} repositórios com {max_workers} workers...")

    total_rows = 0
    with open(output_csv, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=fields_out, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        with futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_map = {ex.submit(clone_and_extract, full_name, base_tmpdir): full_name for full_name in repos}

            for fut in futures.as_completed(future_map):
                full_name = future_map[fut]
                try:
                    repo_name, default_branch, rows = fut.result()
                    writer.writerows(rows)
                    total_rows += len(rows)
                    logging.info(f"OK: {repo_name} ({default_branch}) -> {len(rows)} commits")
                except Exception as e:
                    logging.error(f"Falha em {full_name}: {e}")

    if must_cleanup_base_tmpdir:
        try:
            shutil.rmtree(base_tmpdir, ignore_errors=True)
        except Exception as e:
            logging.warning(f"Falha ao remover tmpdir base {base_tmpdir}: {e}")

    logging.info(f"Concluído. Total de commits exportados: {total_rows}")
    print(f"OK: {output_csv} gerado com {total_rows} commits.")


def main():
    parser = argparse.ArgumentParser(description="Extrai mensagens de commit da default branch usando pygit2 (clonagem local).")
    parser.add_argument("--input", "-i", required=True, help="Caminho do CSV de entrada com os repositórios (coluna 'name' no formato owner/repo).")
    parser.add_argument("--output", "-o", required=True, help="Caminho do CSV de saída com as mensagens de commit.")
    parser.add_argument("--workers", "-w", type=int, default=None, help="Número de workers em paralelo (padrão: 2 x CPUs, máx. 32).")
    parser.add_argument("--tmpdir", default=None, help="Diretório base para clones temporários (se omitido, será criado e removido automaticamente).")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"], help="Nível de log (default: INFO).")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")

    try:
        process_repositories_csv(args.input, args.output, workers=args.workers, tmpdir=args.tmpdir)
    except KeyboardInterrupt:
        logging.error("Interrompido pelo usuário.")
    except Exception as e:
        logging.exception(f"Falha: {e}")


if __name__ == "__main__":
    main()
