# The recipe for the image: the app and everything it needs.

# A small Linux with Python 3.14.
FROM python:3.14-slim

# The tool uv, copied from its own image, at the version that wrote the lockfile.
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /bin/uv

WORKDIR /app

# A user with no special rights. The app runs as this user, not as root.
RUN useradd --create-home --uid 1000 app

# uv also translates each library into bytecode, the form that Python runs.
# So a starting container does not do that work again.
ENV UV_COMPILE_BYTECODE=1

# The libraries, at the exact versions of the lockfile, without the
# development tools. This layer is built again only when the lockfile changes.
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
