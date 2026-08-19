import argparse
import io
from types import SimpleNamespace

import pytest

from scripts import import_catalog


def brand(name, slug):
    return SimpleNamespace(name=name, slug=slug)


class FakeDb:
    pass


class FakeSession:
    def __enter__(self):
        return FakeDb()

    def __exit__(self, exc_type, exc, tb):
        return False


class InputSequence:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def __call__(self, prompt=""):
        self.calls += 1
        if not self.values:
            raise AssertionError(f"input inesperado: {prompt}")
        return self.values.pop(0)


class FakeImporter:
    calls = []

    def __init__(self, catalog_path):
        self.catalog_path = catalog_path

    def run(self, **kwargs):
        self.__class__.calls.append(kwargs)
        return {
            "run_id": "run-1",
            "products_found": 1,
            "products_created": 1,
            "products_updated": 0,
            "products_skipped": 0,
            "products_failed": 0,
            "downloaded_images": 1,
            "failed_images": 0,
            "unknown_products": 0,
            "name_review_products": 0,
            "items": [
                {
                    "supplier_name": "Nike Tee",
                    "final_name": "Nike Tee",
                    "category": {"name": "Camisetas", "confidence": 0.91},
                    "images": 1,
                    "source_images": 1,
                    "result": "created",
                    "destination": "nike/camisetas/nike-tee-abc123",
                }
            ],
        }


@pytest.fixture()
def console():
    return import_catalog.Console(io.StringIO(), no_color=True)


@pytest.fixture()
def brands(monkeypatch):
    items = [brand("Nike", "nike"), brand("Adidas", "adidas"), brand("Chrome Hearts", "chrome-hearts")]
    monkeypatch.setattr(import_catalog, "available_brands", lambda db: items)
    return items


def test_brand_selection_by_number_name_slug_case_and_trim(console, brands):
    assert import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence(["1"])).name == "Nike"
    assert import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence(["Adidas"])).slug == "adidas"
    assert import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence(["chrome-hearts"])).name == "Chrome Hearts"
    assert import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence([" NIKE "])).slug == "nike"


def test_invalid_brand_retries(console, brands):
    selected = import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence(["Puma", "2"]))
    assert selected.name == "Adidas"
    assert "Marca nao encontrada" in console.stream.getvalue()


def test_cancel_on_brand_selection(console, brands):
    with pytest.raises(import_catalog.UserCancelled):
        import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence(["sair"]))


def test_no_available_brands(monkeypatch, console):
    monkeypatch.setattr(import_catalog, "available_brands", lambda db: [])
    with pytest.raises(SystemExit, match="Nenhuma marca"):
        import_catalog.choose_brand(FakeDb(), None, console=console, input_func=InputSequence([]))


def test_url_empty_invalid_retry_and_cancel(monkeypatch, console):
    calls = []

    def fake_validate(value):
        calls.append(value)
        if value == "notaurl":
            raise import_catalog.ApiError(422, "IMPORT_INVALID_URL", "invalida")
        return "https://example.com/folder"

    monkeypatch.setattr(import_catalog, "validate_catalog_url", fake_validate)
    assert import_catalog.request_url(None, console=console, input_func=InputSequence(["", "notaurl", " https://example.com/folder "])) == "https://example.com/folder"
    assert calls == ["notaurl", "https://example.com/folder"]
    with pytest.raises(import_catalog.UserCancelled):
        import_catalog.request_url(None, console=console, input_func=InputSequence(["cancelar"]))


def test_confirmation_accepts_enter_and_s_and_retries_invalid_and_cancels(console):
    assert import_catalog.confirm_start(console=console, input_func=InputSequence([""])) is True
    assert import_catalog.confirm_start(console=console, input_func=InputSequence(["s"])) is True
    assert import_catalog.confirm_start(console=console, input_func=InputSequence(["talvez", "n"])) is False
    assert "Resposta nao reconhecida" in console.stream.getvalue()


def test_summary_shows_dry_run_max_products_and_skip_ai(console):
    args = argparse.Namespace(catalog_path="catalog", max_products=2, skip_ai=True, dry_run=True)
    import_catalog.print_import_summary(args, import_catalog.CatalogBrand("Nike", "nike"), "https://example.com/folder", import_catalog.Path("catalog"), console=console)
    output = console.stream.getvalue()
    assert "dry-run" in output
    assert "Limite: 2" in output
    assert "IA: desativada" in output


def args(**overrides):
    base = {
        "brand": None,
        "url": None,
        "catalog_path": "catalog",
        "dry_run": True,
        "force": False,
        "skip_ai": True,
        "max_products": None,
        "concurrency": 1,
        "verbose": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def setup_run(monkeypatch, brand_arg=None):
    FakeImporter.calls = []
    monkeypatch.setattr(import_catalog, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(import_catalog, "resolve_brand_argument", lambda db, value: import_catalog.CatalogBrand("Nike", "nike"))
    monkeypatch.setattr(import_catalog, "validate_catalog_url", lambda value: "https://example.com/folder")


def test_brand_argument_skips_brand_prompt_and_asks_only_url(monkeypatch, console):
    setup_run(monkeypatch)
    input_func = InputSequence(["https://example.com/folder", "s"])
    code = import_catalog.run_with_args(args(brand="Nike"), console=console, input_func=input_func, importer_factory=FakeImporter)
    assert code == 0
    assert input_func.calls == 2


def test_url_argument_skips_url_prompt_and_asks_only_brand(monkeypatch, console, brands):
    setup_run(monkeypatch)
    input_func = InputSequence(["1", "s"])
    code = import_catalog.run_with_args(args(url="https://example.com/folder"), console=console, input_func=input_func, importer_factory=FakeImporter)
    assert code == 0
    assert input_func.calls == 2


def test_full_non_interactive_does_not_confirm(monkeypatch, console):
    setup_run(monkeypatch)
    input_func = InputSequence([])
    code = import_catalog.run_with_args(args(brand="Nike", url="https://example.com/folder"), console=console, input_func=input_func, importer_factory=FakeImporter)
    assert code == 0
    assert input_func.calls == 0


def test_interactive_cancel_with_n_does_not_run_pipeline(monkeypatch, console, brands):
    setup_run(monkeypatch)
    code = import_catalog.run_with_args(args(), console=console, input_func=InputSequence(["1", "https://example.com/folder", "n"]), importer_factory=FakeImporter)
    assert code == 1
    assert FakeImporter.calls == []


def test_main_handles_keyboard_interrupt(monkeypatch):
    stream = io.StringIO()
    original_console = import_catalog.Console
    monkeypatch.setattr(import_catalog, "parse_args", lambda: args())
    monkeypatch.setattr(import_catalog, "Console", lambda: original_console(stream, no_color=True))
    monkeypatch.setattr(import_catalog, "run_with_args", lambda parsed, console: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert import_catalog.main() == 130
    assert "interrompida pelo usuario" in stream.getvalue()


def test_console_omits_ansi_when_no_color_or_not_tty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    console = import_catalog.Console(stream)
    console.print("Erro", kind="error")
    assert "\033[" not in stream.getvalue()
