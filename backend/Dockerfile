# The recipe for the image: the app and everything it needs.

# Each image is named by its tag and by its digest. The tag is for the reader:
# its owner can move it to another image. The digest, after "@", is the
# fingerprint of one exact image, and it is what Docker follows.
# A test, tests/test_build_files.py, fails when a digest is missing.

# A small Linux with Python 3.14.
FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

# The tool uv, copied from its own image. The same version as in azure-pipelines.yml.
COPY --from=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 /uv /bin/uv

WORKDIR /app

# A user with no special rights. The app runs as this user, not as root.
RUN useradd --create-home --uid 1000 app

# uv also translates each library into bytecode, the form that Python runs.
# So a starting container does not do that work again.
ENV UV_COMPILE_BYTECODE=1

# The libraries, at the exact versions of the lockfile, without the
# development tools. This layer is built again only when one of the two
# copied files changes.
# --no-cache: the downloads are not kept in the image.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

# The code comes last, because it changes most often.
# A change to the code builds only from here.
COPY src ./src

USER app

# Python finds the libraries in .venv and the code in src.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "book_teller.main:app", "--host", "0.0.0.0", "--port", "8000"]
