"""Tests of the skeleton: the page and the health address.

They call the app in memory. No server is started, and no network is used.
"""

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from book_teller.main import app

client = TestClient(app)


class ResourceFinder(HTMLParser):
    """Reads a page and keeps every script or style that has no checksum.

    The checksum is the attribute "integrity". With it, the browser refuses
    a file that was changed after the page was written. A real checksum
    starts with the name of its method, such as "sha384-".
    """

    METHODS = ("sha384-", "sha512-")

    def __init__(self) -> None:
        super().__init__()
        self.without_checksum: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        address: str | None = None
        if tag == "script":
            address = values.get("src")
        elif tag == "link" and "stylesheet" in (values.get("rel") or "").split():
            address = values.get("href")
        checksum = values.get("integrity") or ""
        if address and not checksum.startswith(self.METHODS):
            self.without_checksum.append(address)


def test_health_answers_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_page_is_html_and_names_the_product() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Book Teller" in response.text


def test_the_page_loads_nothing_without_a_checksum() -> None:
    response = client.get("/")
    finder = ResourceFinder()
    finder.feed(response.text)

    assert response.status_code == 200
    assert finder.without_checksum == []


def test_the_finder_catches_a_missing_or_a_false_checksum() -> None:
    # The test above is worth nothing if the finder sees nothing.
    bad_page = """
        <link rel="stylesheet" href="https://example.com/no-checksum.css">
        <link rel="stylesheet" href="https://example.com/false.css" integrity="x">
        <script src="https://example.com/no-checksum.js"></script>
        <script src="https://example.com/good.js" integrity="sha384-abc"></script>
    """
    finder = ResourceFinder()
    finder.feed(bad_page)

    assert finder.without_checksum == [
        "https://example.com/no-checksum.css",
        "https://example.com/false.css",
        "https://example.com/no-checksum.js",
    ]


def test_the_pages_that_document_the_api_are_off() -> None:
    # FastAPI can serve these by itself. They load scripts without a checksum.
    for address in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(address).status_code == 404, address


def test_an_unknown_address_answers_404() -> None:
    response = client.get("/no-such-page")

    assert response.status_code == 404


def test_health_takes_only_get() -> None:
    response = client.post("/health")

    assert response.status_code == 405
