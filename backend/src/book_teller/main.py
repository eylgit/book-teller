"""The web app: one page and one health address."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

STATIC_FOLDER = Path(__file__).parent / "static"

# FastAPI can serve pages that document the API. They are off: they load
# scripts without a checksum, and the app has no API to document yet.
app = FastAPI(title="Book Teller", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
def page() -> FileResponse:
    """The page. The file is read on every request, so a change shows on reload."""
    return FileResponse(STATIC_FOLDER / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    """A machine asks this address to learn whether the app is alive."""
    return {"status": "ok"}
