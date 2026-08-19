from app.services.catalog_import import CatalogSourceProduct, CatalogYupooScanner
from app.services.imports import FetchedPage


ROOT = "https://rockets-reps.x.yupoo.com/categories/4621053?page=1"


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def get(self, url):
        self.requests.append(url)
        return FetchedPage(url=url, body=self.pages.get(url, category_page([])), content_type="text/html", status_code=200)


class ListingOnlyScanner(CatalogYupooScanner):
    def _open_product(self, candidate, root_url):
        return CatalogSourceProduct(
            source_url=candidate.source_url,
            normalized_source_url=candidate.source_url,
            source_id=candidate.source_url.rsplit("/", 1)[-1].split("?", 1)[0],
            supplier_name=candidate.title,
            description="",
            image_urls=[],
            page_number=candidate.page_number,
            position=candidate.position,
            raw_metadata=candidate.raw_metadata,
        )


def category_page(albums, *, links=()):
    body = ["<html><head><title>Rockets</title></head><body>"]
    for album_id, title, query in albums:
        suffix = f"?{query}" if query else ""
        body.append(f'<a class="album__main" title="{title}" href="/albums/{album_id}{suffix}"><img class="album__img" src="//img.example/{album_id}.jpg"></a>')
    for href in links:
        body.append(f'<a class="pagination__number" href="{href}">next</a>')
    body.append("</body></html>")
    return "".join(body)


def scan_with(pages, *, max_pages=10, max_products=50, start_page=1):
    fetcher = FakeFetcher(pages)
    scanner = ListingOnlyScanner(fetcher=fetcher, max_pages=max_pages, max_products=max_products, start_page=start_page)
    products = scanner.scan(ROOT)
    return scanner, fetcher, products


def test_category_with_two_pages_and_empty_next_stops():
    pages = {
        ROOT: category_page([("100", "A", ""), ("101", "B", "")], links=["/categories/4621053?page=2"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=2": category_page([("102", "C", "")], links=["/categories/4621053?page=3"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=3": category_page([]),
    }

    scanner, fetcher, products = scan_with(pages)

    assert [item.source_id for item in products] == ["100", "101", "102"]
    assert len(fetcher.requests) == 3
    assert scanner.last_scan_stats["scan"]["truncated"] is False


def test_repeated_album_across_pages_is_deduped_by_yupoo_identity():
    pages = {
        ROOT: category_page([("100", "A", "uid=1&referrercate=4621053")], links=["/categories/4621053?page=2"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=2": category_page([("100", "A again", "uid=2&isSubCate=false"), ("101", "B", "")]),
    }

    scanner, _, products = scan_with(pages)

    assert [item.source_id for item in products] == ["100", "101"]
    assert scanner.last_scan_stats["scan"]["raw_items_found"] == 3
    assert scanner.last_scan_stats["scan"]["duplicates_removed"] == 1


def test_max_pages_sets_pagination_truncated():
    pages = {
        ROOT: category_page([("100", "A", "")], links=["/categories/4621053?page=2"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=2": category_page([("101", "B", "")]),
    }

    scanner, fetcher, products = scan_with(pages, max_pages=1)

    assert [item.source_id for item in products] == ["100"]
    assert len(fetcher.requests) == 1
    assert scanner.last_scan_stats["scan"]["pagination_truncated"] is True
    assert scanner.last_scan_stats["scan"]["limit_reason"] == "max_pages"


def test_max_items_sets_truncated_and_keeps_limit():
    pages = {
        ROOT: category_page([("100", "A", ""), ("101", "B", ""), ("102", "C", "")]),
    }

    scanner, _, products = scan_with(pages, max_products=2)

    assert [item.source_id for item in products] == ["100", "101"]
    assert scanner.last_scan_stats["scan"]["truncated"] is True
    assert scanner.last_scan_stats["scan"]["limit_reason"] == "max_items"
    assert scanner.last_scan_stats["scan"]["processed_items"] == 2
    assert scanner.last_scan_stats["scan"]["unique_items_found"] == 3


def test_pagination_loop_is_avoided():
    pages = {
        ROOT: category_page([("100", "A", "")], links=["/categories/4621053?page=1", "/categories/4621053?page=2"]),
        "https://rockets-reps.x.yupoo.com/categories/4621053?page=2": category_page([("101", "B", "")], links=["/categories/4621053?page=1"]),
    }

    scanner, fetcher, products = scan_with(pages)

    assert [item.source_id for item in products] == ["100", "101"]
    assert fetcher.requests.count(ROOT) == 1
    assert len(fetcher.requests) == 3


def test_start_page_begins_from_requested_page():
    page_2 = "https://rockets-reps.x.yupoo.com/categories/4621053?page=2"
    pages = {
        page_2: category_page([("200", "Page 2", "")]),
    }

    _, fetcher, products = scan_with(pages, start_page=2)

    assert fetcher.requests[0] == page_2
    assert [item.source_id for item in products] == ["200"]
