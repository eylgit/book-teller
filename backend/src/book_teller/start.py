"""What a container runs when it starts: first the migrations, then the app.

    python -m book_teller.start

With the settings of a database, the migrations run first. A migration that
already ran is skipped. If one fails, the app does not start: new code must
not meet old tables.

Without the settings of a database, the app starts at once, as before.
"""

import os
from collections.abc import Callable, Mapping

from book_teller import migrate


def serve() -> None:
    """Start uvicorn, the server of the app, in the place of this program.

    "exec" does not start a second program: this one becomes uvicorn. So
    the signal that stops a container reaches uvicorn itself.
    """
    os.execvp(
        "uvicorn",
        ["uvicorn", "book_teller.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


def start(
    environment: Mapping[str, str],
    run_migrations: Callable[[], object] = migrate.main,
    serve: Callable[[], object] = serve,
) -> None:
    if environment.get("BOOK_TELLER_DATABASE_HOST", "").strip():
        run_migrations()
    serve()


if __name__ == "__main__":
    start(os.environ)
