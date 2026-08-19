from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib.parse import urlparse

from app.services.yupoo_image_downloader import RawDownloadOptions, YupooRawImageDownloader

YES = {"", "s", "sim", "y", "yes"}
NO = {"n", "nao", "não", "no"}
EXIT_SUCCESS = 0
EXIT_PARTIAL_ERRORS = 2
EXIT_TRUNCATED = 3
EXIT_ABORTED = 20
EXIT_INTERRUPTED = 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Baixa imagens brutas de albuns Yupoo sem criar produtos.")
    parser.add_argument("--url", help="URL da categoria Yupoo.")
    parser.add_argument("--output", default="downloads/yupoo", help="Diretorio base de saida.")
    parser.add_argument("--start-page", type=int, default=1, help="Pagina inicial.")
    parser.add_argument("--max-pages", type=int, help="Maximo de paginas de categoria.")
    parser.add_argument("--max-albums", type=int, help="Maximo de albuns.")
    parser.add_argument("--dry-run", action="store_true", help="Coleta albuns/imagens sem baixar arquivos.")
    parser.add_argument("--verbose", action="store_true", help="Exibe detalhes adicionais.")
    parser.add_argument("--resume", action="store_true", help="Retoma usando manifest existente.")
    parser.add_argument("--run-dir", help="Diretorio de run existente/explicito.")
    parser.add_argument("--resume-run", help="Diretorio de run existente para retomada inteligente.")
    parser.add_argument("--max-retries", type=int, help="Maximo de referencias historicas pendentes a tentar nesta execucao.")
    return parser.parse_args()


def prompt_missing(args: argparse.Namespace) -> argparse.Namespace:
    if args.url or args.resume_run:
        return args
    print("DRIPZONE - YUPOO IMAGE DOWNLOADER")
    print()
    args.url = input("Cole o link da categoria:\n> ").strip()
    destination = input("Destino:\n> ").strip()
    if destination:
        args.output = destination
    answer = input("Iniciar download? [S/n] ").strip().casefold()
    if answer not in YES:
        raise SystemExit(1)
    return args


def format_elapsed(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_mb(bytes_count: int) -> str:
    return f"{bytes_count / (1024 * 1024):.1f} MB"


def progress_bar(done: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = min(width, int(width * done / total))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


class ConsoleProgress:
    def __init__(self, *, verbose: bool = False):
        self.verbose = verbose
        self.started = time.monotonic()
        self.last_status = 0.0
        self.last_image = ""
        self.image_started = 0
        self.resume_mode = False
        self.resume_run = ""
        self.resume_total = 0
        self.resume_pending_total = 0
        self.existing_files = 0
        self.last_activity = ""
        self.last_completion = time.monotonic()

    def __call__(self, event: str, **data) -> None:
        if event == "start":
            host = urlparse(str(data.get("url", ""))).hostname or data.get("url", "")
            self.resume_run = str(data.get("run_dir") or "")
            if not self.resume_mode:
                print(f"Origem: {host}")
                print(f"Run: {self.resume_run}")
                print()
            return
        if event == "page_start":
            print(f"Pagina {data.get('page_index')}: {data.get('page_url')}")
            return
        if event == "page_albums":
            print(f"Albuns encontrados na pagina: {data.get('albums_raw', 0)}")
            return
        if event == "album":
            title = str(data.get("title") or "")
            print(f"[{data.get('album_index')}/{data.get('max_albums')}] Album: {title[:100]}")
            print(f"Imagens encontradas: {data.get('images_found', 0)}")
            return
        if event == "download_plan":
            stats = data.get("stats", {})
            self.resume_mode = bool(stats.get("historical_errors") or stats.get("unique_pending_retries"))
            self.resume_total = int(data.get("images_total", stats.get("images_found", 0)) or 0)
            self.resume_pending_total = int(stats.get("unique_pending_retries", self.resume_total) or 0)
            self.existing_files = int(stats.get("existing_manifest_files", stats.get("physical_files", 0)) or 0)
            if self.resume_mode:
                self.print_resume_start(stats)
            else:
                print()
                print(f"Albuns para processar: {data.get('albums_total', 0)}")
                print(f"Imagens para baixar/reutilizar: {self.resume_total}")
                print()
            return
        if event == "image_download_start":
            self.image_started += 1
            self.last_activity = self.short_text(str(data.get("image_url") or "aguardando imagem"))
            if self.resume_mode and self.image_started == 1:
                print("Primeira requisicao enviada. Aguardando resposta...")
            elif self.verbose and (self.image_started == 1 or self.image_started % 25 == 0):
                print(f"Baixando imagem {self.image_started}: aguardando resposta/retry se necessario...")
            return
        if event in {"image_stored", "image_duplicate"}:
            self.last_completion = time.monotonic()
            self.last_image = str(data.get("file") or self.last_image)
            action = "Recuperada" if event == "image_stored" else "Reutilizada"
            self.last_activity = f"{action}: {self.short_text(self.last_image)}"
            self.render_status(data.get("stats", {}), force=event == "image_duplicate")
            return
        if event == "image_error":
            self.last_completion = time.monotonic()
            error = data.get("error", {})
            self.last_activity = f"Falhou: {error.get('error_type')} {self.short_text(str(error.get('image_url') or ''))}"
            if not self.resume_mode:
                print()
                print(f"Erro em imagem: {error.get('error_type')} - {error.get('message')}")
                print(f"Tentativas/retry: {error.get('attempts')}")
            self.render_status(data.get("stats", {}), force=True)
            return
        if event == "heartbeat":
            elapsed = int(time.monotonic() - self.last_completion)
            print(f"Ainda trabalhando... aguardando resposta/retry DNS ou rede ({elapsed}s)")
            self.render_status(data.get("stats", {}), force=True)
            return
        if event == "host_validation_alert":
            print()
            print("ALERTA: falhas de validacao do host das imagens aumentaram nesta pagina.")
            print(f"Pagina: {data.get('page_index')} | falhas: {data.get('blocked_host_errors')}/{data.get('attempts')}")
            return
        if event == "aborted":
            print()
            print("DOWNLOAD PAUSADO: falha sistemica ao validar o host das imagens. Arquivos ja concluidos foram preservados.")
            print(f"Motivo: {data.get('reason')}")
            print(f"Run: {data.get('run_dir')}")
            return
        if event == "interrupted":
            print()
            if self.resume_mode:
                print("========================================")
                print("RETOMADA INTERROMPIDA")
                print("=====================")
                print("Checkpoint salvo.")
                print("Arquivos concluidos preservados.")
                print("Para continuar execute novamente:")
                print(".\\baixar-yupoo.ps1")
            else:
                print("Download interrompido. Arquivos concluidos foram preservados; arquivos .part foram removidos.")
                print(f"Run: {data.get('run_dir')}")
            return
        if event == "complete":
            print()

    def print_resume_start(self, stats: dict) -> None:
        run_name = Path(self.resume_run).name if self.resume_run else "-"
        print("========================================")
        print("RETOMANDO DOWNLOAD YUPOO")
        print("========================")
        print()
        print(f"Run: {run_name}")
        print()
        print(f"Arquivos existentes: {self.existing_files}")
        print(f"Erros historicos: {stats.get('historical_errors', 0)}")
        print(f"Pendentes para retry: {self.resume_pending_total}")
        if self.resume_total != self.resume_pending_total:
            print(f"Retries nesta execucao: {self.resume_total}")
        print()
        print("Carregando checkpoint...")
        print("Checkpoint carregado: OK")
        print()
        print("> > > RETOMADA INICIADA <<<")
        print()

    def render_status(self, stats: dict, *, force: bool = False) -> None:
        now = time.monotonic()
        if self.resume_mode:
            processed = int(stats.get("retried", 0))
            total = self.resume_total or int(stats.get("images_found", 0))
        else:
            processed = int(stats.get("images_downloaded", 0)) + int(stats.get("reused", 0)) + int(stats.get("errors", 0))
            total = int(stats.get("images_found", 0))
        if not force and now - self.last_status < 2 and processed % 25 != 0:
            return
        self.last_status = now
        percent = (processed / total * 100) if total else 0
        if self.resume_mode:
            elapsed = max(0.001, now - self.started)
            mb = int(stats.get("bytes", 0)) / (1024 * 1024)
            speed = mb / elapsed
            print(
                "Retries: "
                f"{progress_bar(processed, total)} {processed}/{total} ({percent:.1f}%) | "
                f"pendentes totais {self.resume_pending_total} | "
                f"recuperadas {stats.get('recovered', 0)} | "
                f"ainda falharam {stats.get('still_failed', 0)} | "
                f"arquivos {stats.get('physical_files', 0)} | "
                f"dados novos {format_mb(int(stats.get('bytes', 0)))} | "
                f"velocidade {speed:.1f} MB/s | "
                f"tempo {format_elapsed(now - self.started)}"
            )
            if self.last_activity:
                print(f"Ultima atividade: {self.last_activity}")
            return
        print(
            "Imagens: "
            f"{progress_bar(processed, total)} {processed}/{total} ({percent:.1f}%) | "
            f"baixadas {stats.get('images_downloaded', 0)} | "
            f"reutilizadas {stats.get('reused', 0)} | "
            f"duplicadas {stats.get('exact_duplicates', 0)} | "
            f"erros {stats.get('errors', 0)} | "
            f"arquivos {stats.get('physical_files', stats.get('images_downloaded', 0))} | "
            f"dados {format_mb(int(stats.get('bytes', 0)))} | "
            f"tempo {format_elapsed(now - self.started)} | "
            f"ultimo {self.last_image}"
        )

    def short_text(self, value: str, limit: int = 90) -> str:
        value = value.strip()
        return value if len(value) <= limit else value[: limit - 3] + "..."


def print_final_summary(result, elapsed: float) -> None:
    stats = result.stats
    if stats.get("historical_errors") or stats.get("unique_pending_retries"):
        before = int(stats.get("existing_manifest_files", 0) or 0)
        after = int(stats.get("physical_files", 0) or 0)
        print("========================================")
        print("RETOMADA CONCLUIDA")
        print("==================")
        print()
        print(f"Retries tentados: {stats.get('retried', 0)}")
        print(f"Recuperados: {stats.get('recovered', 0)}")
        print(f"Ainda falharam: {stats.get('still_failed', 0)}")
        print(f"Arquivos antes: {before}")
        print(f"Arquivos depois: {after}")
        print(f"Dados novos: {format_mb(int(stats.get('bytes', 0)))}")
        print(f"Tempo: {format_elapsed(elapsed)}")
        print()
        print(f"Run: {result.run_dir}")
        return
    print("========================================")
    print("          DOWNLOAD CONCLUIDO")
    print("========================================")
    print(f"Origem: {urlparse(result.albums[0]['album_url']).hostname if result.albums else '-'}")
    print(f"Paginas: {stats.get('pages_read', 0)}")
    print(f"Albuns: {stats.get('albums_found', 0)}")
    print(f"Imagens encontradas: {stats.get('images_found', 0)}")
    print(f"Arquivos fisicos: {stats.get('physical_files', stats.get('images_downloaded', 0))}")
    print(f"Duplicatas: {stats.get('exact_duplicates', 0)}")
    print(f"Reutilizadas: {stats.get('reused', 0)}")
    print(f"Erros: {stats.get('errors', 0)}")
    print(f"Fim natural da paginacao: {stats.get('pagination_end_reached')}")
    print(f"Truncado: {stats.get('truncated')}")
    print(f"Motivo do limite: {stats.get('limit_reason')}")
    print(f"Motivo de pausa: {stats.get('abort_reason')}")
    print(f"Total baixado: {format_mb(int(stats.get('bytes', 0)))}")
    print(f"Tempo: {format_elapsed(elapsed)}")
    print()
    print(f"Run: {result.run_dir}")


def main() -> int:
    args = prompt_missing(parse_args())
    options = RawDownloadOptions(
        url=args.url,
        output=Path(args.output),
        start_page=max(1, args.start_page),
        max_pages=args.max_pages,
        max_albums=args.max_albums,
        dry_run=args.dry_run,
        verbose=args.verbose,
        resume=args.resume or bool(args.resume_run),
        run_dir=Path(args.resume_run or args.run_dir) if (args.resume_run or args.run_dir) else None,
        max_retries=args.max_retries,
    )
    progress = ConsoleProgress(verbose=args.verbose)
    started = time.monotonic()
    try:
        result = YupooRawImageDownloader(progress=progress).run(options)
    except KeyboardInterrupt:
        print()
        if options.resume:
            print("========================================")
            print("RETOMADA INTERROMPIDA")
            print("=====================")
            print("Checkpoint salvo.")
            print("Arquivos concluidos preservados.")
            print("Para continuar execute novamente:")
            print(".\\baixar-yupoo.ps1")
        else:
            print("Download interrompido. Este run pode ser retomado se manifest/albums foram salvos; caso contrario, use um novo run.")
        return EXIT_INTERRUPTED
    stats = result.stats
    print_final_summary(result, time.monotonic() - started)
    if stats.get("abort_reason"):
        return EXIT_ABORTED
    if stats.get("truncated"):
        return EXIT_TRUNCATED
    if stats.get("errors", 0):
        return EXIT_PARTIAL_ERRORS
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
