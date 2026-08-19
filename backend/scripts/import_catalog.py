import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import or_

from app.database import SessionLocal
from app.exceptions import ApiError
from app.models import Brand
from app.services.catalog_import import CatalogBrand, CatalogImporter
from app.services.imports import validate_source_url
from app.utils.slug import make_slug

CANCEL_WORDS = {"q", "quit", "sair", "cancelar"}
YES_WORDS = {"", "s", "sim", "y", "yes"}
NO_WORDS = {"n", "nao", "não", "no"}


class UserCancelled(Exception):
    pass


class Console:
    COLORS = {
        "title": "\033[1;36m",
        "success": "\033[32m",
        "warning": "\033[33m",
        "error": "\033[31m",
        "info": "\033[36m",
        "reset": "\033[0m",
    }

    def __init__(self, stream=None, *, no_color: bool | None = None):
        self.stream = stream or sys.stdout
        supports_color = hasattr(self.stream, "isatty") and self.stream.isatty()
        self.use_color = supports_color and "NO_COLOR" not in os.environ if no_color is None else not no_color

    def color(self, text: str, kind: str) -> str:
        if not self.use_color:
            return text
        return f"{self.COLORS.get(kind, '')}{text}{self.COLORS['reset']}"

    def print(self, text: str = "", *, kind: str | None = None) -> None:
        print(self.color(text, kind) if kind else text, file=self.stream)


def parse_args():
    parser = argparse.ArgumentParser(description="Importa uma pasta/album Yupoo para o catalogo local do DripZone.")
    parser.add_argument("--brand", help="Nome ou slug de uma marca cadastrada.")
    parser.add_argument("--url", help="URL da pasta ou album Yupoo.")
    parser.add_argument("--catalog-path", default="catalog", help="Pasta do catalogo local. Padrao: backend/catalog.")
    parser.add_argument("--dry-run", action="store_true", help="Analisa sem baixar imagens nem escrever arquivos permanentes.")
    parser.add_argument("--force", action="store_true", help="Reprocessa produtos existentes sem duplicar pastas.")
    parser.add_argument("--skip-ai", action="store_true", help="Usa apenas fallback deterministico nesta versao.")
    parser.add_argument("--max-products", type=int, help="Limita a quantidade de produtos processados.")
    parser.add_argument("--max-pages", type=int, help="Limita a quantidade de paginas da categoria a varrer.")
    parser.add_argument("--start-page", type=int, default=1, help="Pagina inicial da categoria Yupoo. Padrao: 1.")
    parser.add_argument("--concurrency", type=int, default=1, help="Reservado para downloads concorrentes futuros.")
    parser.add_argument("--verbose", action="store_true", help="Exibe detalhes adicionais de diagnostico.")
    return parser.parse_args()


def is_cancel(value: str) -> bool:
    return value.strip().casefold() in CANCEL_WORDS


def print_header(console: Console) -> None:
    console.print("+==============================================+", kind="title")
    console.print("|       DRIPZONE - IMPORTADOR DE CATALOGO      |", kind="title")
    console.print("+==============================================+", kind="title")
    console.print()


def dedupe_and_sort_brands(brands) -> list:
    by_slug = {}
    for brand in brands:
        if getattr(brand, "slug", None) and brand.slug not in by_slug:
            by_slug[brand.slug] = brand
    return sorted(by_slug.values(), key=lambda item: item.name.casefold())


def available_brands(db) -> list:
    brands = db.query(Brand).filter(Brand.is_active.is_(True)).all()
    return dedupe_and_sort_brands(brands)


def resolve_brand_from_value(brands, value: str) -> CatalogBrand | None:
    answer = value.strip()
    if answer.isdigit():
        index = int(answer)
        if 1 <= index <= len(brands):
            brand = brands[index - 1]
            return CatalogBrand(brand.name, brand.slug)
    slug = make_slug(answer)
    for brand in brands:
        if brand.slug == slug or brand.name.casefold() == answer.casefold():
            return CatalogBrand(brand.name, brand.slug)
    return None


def resolve_brand_argument(db, value: str) -> CatalogBrand:
    slug = make_slug(value.strip())
    brand = db.query(Brand).filter(or_(Brand.slug == slug, Brand.name.ilike(value.strip()))).first()
    if not brand:
        raise SystemExit("Marca nao cadastrada. Confira o nome/slug antes de importar.")
    return CatalogBrand(brand.name, brand.slug)


def choose_brand(db, value: str | None, *, console: Console | None = None, input_func=input) -> CatalogBrand:
    console = console or Console()
    if value:
        return resolve_brand_argument(db, value)
    brands = available_brands(db)
    if not brands:
        raise SystemExit("Nenhuma marca cadastrada encontrada.")
    console.print("Escolha a marca:")
    console.print()
    for index, brand in enumerate(brands, start=1):
        console.print(f"  [{index}] {brand.name}")
    while True:
        answer = input_func("\nDigite o numero ou o nome da marca: ").strip()
        if is_cancel(answer):
            raise UserCancelled()
        selected = resolve_brand_from_value(brands, answer)
        if selected:
            console.print()
            console.print(f"[OK] Marca selecionada: {selected.name}", kind="success")
            return selected
        console.print("Marca nao encontrada. Escolha um numero ou nome apresentado na lista.", kind="error")


def request_url(value: str | None, *, console: Console | None = None, input_func=input) -> str:
    console = console or Console()
    if value:
        return validate_catalog_url(value.strip())
    while True:
        console.print()
        answer = input_func("Cole o link da pasta do Yupoo:\n> ").strip()
        if is_cancel(answer):
            raise UserCancelled()
        if not answer:
            console.print("O link nao pode ficar vazio. Tente novamente.", kind="error")
            continue
        try:
            return validate_catalog_url(answer)
        except ApiError as exc:
            console.print(f"{friendly_url_error(exc)} Tente novamente.", kind="error")


def validate_catalog_url(value: str) -> str:
    if not value:
        raise ApiError(422, "IMPORT_INVALID_URL", "Informe uma URL HTTP ou HTTPS valida.")
    return validate_source_url(value)


def friendly_url_error(exc: ApiError) -> str:
    messages = {
        "IMPORT_INVALID_URL": "O link informado nao e uma URL valida.",
        "IMPORT_HOST_NOT_ALLOWED": "O host do link nao esta permitido para importacao.",
        "IMPORT_SSRF_BLOCKED": "O link aponta para uma origem local ou privada e foi bloqueado.",
        "IMPORT_HOST_NOT_RESOLVED": "Nao foi possivel validar o host informado.",
        "IMPORT_TLS_VERIFICATION_FAILED": "Nao foi possivel validar o certificado HTTPS da origem. Verifique os certificados confiaveis do Windows, o ambiente virtual ou configure DRIPZONE_CA_BUNDLE.",
    }
    return messages.get(exc.code, exc.message or "Nao foi possivel validar o link informado.")


def resolve_catalog_path(value: str) -> Path:
    catalog_path = Path(value)
    if not catalog_path.is_absolute():
        catalog_path = ROOT / catalog_path
    return catalog_path


def print_import_summary(args, brand: CatalogBrand, url: str, catalog_path: Path, *, console: Console) -> None:
    console.print()
    console.print("Resumo da importacao:", kind="info")
    console.print()
    console.print(f"  Marca: {brand.name}")
    console.print(f"  Origem: {url}")
    console.print(f"  Destino: {Path(args.catalog_path) / brand.slug}")
    console.print(f"  Limite: {args.max_products if args.max_products else 'padrao do ambiente'}")
    console.print(f"  Limite produtos: {args.max_products if args.max_products else 'padrao do ambiente'}")
    max_pages = getattr(args, "max_pages", None)
    start_page = getattr(args, "start_page", 1)
    console.print(f"  Limite paginas: {max_pages if max_pages else 'padrao do ambiente'}")
    console.print(f"  Pagina inicial: {start_page}")
    console.print(f"  IA: {'desativada' if args.skip_ai else 'fallback deterministico'}")
    console.print(f"  Modo: {'dry-run' if args.dry_run else 'importacao real'}")


def confirm_start(*, console: Console | None = None, input_func=input) -> bool:
    console = console or Console()
    while True:
        answer = input_func("\nDeseja iniciar a importacao? [S/n]: ").strip().casefold()
        if is_cancel(answer):
            raise UserCancelled()
        if answer in YES_WORDS:
            return True
        if answer in NO_WORDS:
            return False
        console.print("Resposta nao reconhecida. Digite s para iniciar ou n para cancelar.", kind="warning")


def print_manifest(manifest: dict, catalog_path: Path, *, dry_run: bool, console: Console) -> None:
    scan = manifest.get("scan") or {}
    if scan:
        console.print()
        console.print(f"Albuns encontrados antes da deduplicacao: {scan.get('albums_found_before_dedupe', 0)}")
        console.print(f"Albuns validos: {scan.get('albums_valid', 0)}")
        console.print(f"Duplicados removidos: {scan.get('albums_duplicates_removed', 0)}")
        console.print(f"Produtos que serao processados: {scan.get('products_to_process', manifest['products_found'])}")
        scan_detail = scan.get("scan") or {}
        if scan_detail:
            console.print(f"Paginas lidas: {scan_detail.get('pages_read', 0)}")
            console.print(f"Albuns brutos: {scan_detail.get('raw_items_found', 0)}")
            console.print(f"Albuns unicos: {scan_detail.get('unique_items_found', 0)}")
            console.print(f"Total processado: {scan_detail.get('processed_items', 0)}")
            console.print(f"Truncado: {scan_detail.get('truncated', False)}")
            console.print(f"Paginacao truncada: {scan_detail.get('pagination_truncated', False)}")
            if scan_detail.get("limit_reason"):
                console.print(f"Motivo do limite: {scan_detail['limit_reason']}")
    for index, item in enumerate(manifest["items"], start=1):
        console.print(f"\n[{index}/{manifest['products_found']}]")
        if item.get("source_url"):
            console.print(f"  Origem: {item['source_url']}")
        console.print()
        console.print("  Nome original:")
        console.print(f"  {item['supplier_name']}")
        if item.get("final_name"):
            console.print()
            console.print("  Nome sugerido:")
            console.print(f"  {item['final_name']}")
        if item.get("supplier_code"):
            console.print()
            console.print("  Codigo do fornecedor:")
            console.print(f"  {item['supplier_code']}")
        if item.get("category"):
            category = item["category"]
            console.print()
            console.print(f"  Categoria: {category.get('name')} ({int(float(category.get('confidence', 0)) * 100)}%)")
        if dry_run:
            console.print()
            console.print(f"  Imagens encontradas: {item.get('source_images', 0)}")
            console.print("  Imagens baixadas: nao aplicavel (dry-run)")
        elif item.get("images") is not None:
            console.print(f"  Imagens: {item.get('images', 0)}/{item.get('source_images', item.get('images', 0))}")
        import_info = item.get("import") or {}
        errors = import_info.get("errors") or []
        if errors:
            console.print()
            console.print("  Importacao:")
            console.print(f"  Falhas de imagem: {import_info.get('images_failed', len(errors))}")
            first = errors[0]
            console.print(f"  Motivo: {first.get('error_type')} ({first.get('message')})")
        review = item.get("review") or {}
        notes = review.get("notes") or []
        if notes:
            console.print()
            console.print("  Revisao:")
            console.print(f"  {'; '.join(notes)}")
        console.print(f"  Resultado: {item['result']}")
        console.print(f"  Destino: {item['destination']}")
        if item.get("error"):
            console.print(f"  Erro: {item['error']}", kind="error")
    if "possible_brand_divergence" in (manifest.get("warnings") or []):
        console.print()
        console.print("Aviso: a origem parece conter produtos que podem nao pertencer exclusivamente a marca selecionada.", kind="warning")
    console.print("\nResumo:\n")
    console.print(f"Produtos encontrados: {manifest['products_found']}")
    console.print(f"Criados: {manifest['products_created']}")
    console.print(f"Atualizados: {manifest['products_updated']}")
    console.print(f"Parciais: {manifest.get('products_partial', 0)}")
    console.print(f"Ignorados: {manifest['products_skipped']}")
    console.print(f"Com erro: {manifest.get('products_with_error', manifest['products_failed'])}")
    console.print(f"Imagens encontradas: {manifest.get('images_found', 0)}")
    console.print(f"Imagens baixadas: {manifest['downloaded_images']}")
    console.print(f"Falhas de imagem: {manifest['failed_images']}")
    console.print(f"Desconhecidos: {manifest['unknown_products']}")
    console.print(f"Revisao de nome: {manifest['name_review_products']}")
    if not dry_run:
        console.print(f"\nManifesto: {catalog_path / '_runs' / (manifest['run_id'] + '.json')}")


def run_with_args(args, *, console: Console | None = None, input_func=input, importer_factory=CatalogImporter) -> int:
    console = console or Console()
    print_header(console)
    fully_non_interactive = bool(args.brand and args.url)
    with SessionLocal() as db:
        brand = choose_brand(db, args.brand, console=console, input_func=input_func)
    url = request_url(args.url, console=console, input_func=input_func)
    catalog_path = Path(args.catalog_path)
    catalog_path = resolve_catalog_path(args.catalog_path)
    print_import_summary(args, brand, url, catalog_path, console=console)
    if not fully_non_interactive and not confirm_start(console=console, input_func=input_func):
        console.print("Importacao cancelada. Nenhum arquivo foi alterado.", kind="warning")
        return 1
    console.print()
    console.print("Iniciando importacao...", kind="info")
    importer = importer_factory(catalog_path=catalog_path)
    manifest = importer.run(brand=brand, folder_url=url, dry_run=args.dry_run, force=args.force, max_products=args.max_products, max_pages=getattr(args, "max_pages", None), start_page=getattr(args, "start_page", 1))
    print_manifest(manifest, catalog_path, dry_run=args.dry_run, console=console)
    return 0 if not manifest.get("products_with_error", manifest["products_failed"]) else 1


def main() -> int:
    args = parse_args()
    console = Console()
    try:
        return run_with_args(args, console=console)
    except UserCancelled:
        console.print("Importacao cancelada. Nenhum arquivo foi alterado.", kind="warning")
        return 1
    except KeyboardInterrupt:
        console.print()
        console.print("Importacao interrompida pelo usuario.", kind="warning")
        return 130
    except ApiError as exc:
        console.print(friendly_url_error(exc), kind="error")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
