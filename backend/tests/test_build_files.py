"""Tests of the Dockerfile: is every image named by its digest?

A tag, such as "python:3.14-slim", is a name that its owner can move to
another image. A digest is the fingerprint of one exact image: "@sha256:"
and 64 characters. With it, every build starts from the same image.

These tests only read the file. They need no Docker and no network.
"""

import re
from pathlib import Path

DOCKERFILE = Path(__file__).parent.parent / "Dockerfile"
# Docker Compose's file, in the top folder of the repository.
COMPOSE_FILE = Path(__file__).parent.parent.parent / "compose.yaml"

# A real digest: the name of the method, then 64 characters from 0-9 and a-f.
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def images_in(dockerfile: str) -> list[str]:
    """Gives every image that a Dockerfile names.

    An image is named in three places: after "FROM", after "COPY --from=",
    and after "from=" inside "RUN --mount=". Docker reads an instruction in
    upper or lower case, and over several lines that end with a backslash.
    """
    # A backslash at the end of a line joins it to the next line.
    joined = re.sub(r"\\[ \t]*\n", " ", dockerfile)

    images: list[str] = []
    for line in joined.splitlines():
        words = line.split()
        if not words:
            continue
        instruction = words[0].upper()
        if instruction == "FROM":
            # Words that start with "--" are settings, not the image.
            names = [word for word in words[1:] if not word.startswith("--")]
            images.append(names[0])
        elif instruction == "COPY":
            for word in words[1:]:
                if word.startswith("--from="):
                    images.append(word.removeprefix("--from="))
        elif instruction == "RUN":
            for word in words[1:]:
                if word.startswith("--mount="):
                    # The settings of a mount are parted by commas.
                    for setting in word.removeprefix("--mount=").split(","):
                        if setting.startswith("from="):
                            images.append(setting.removeprefix("from="))
    return images


def without_digest(images: list[str]) -> list[str]:
    return [image for image in images if not DIGEST.search(image)]


def test_every_image_of_the_dockerfile_has_a_digest() -> None:
    images = images_in(DOCKERFILE.read_text())

    assert without_digest(images) == []


def test_the_dockerfile_names_two_images() -> None:
    # The test above is worth nothing if the finder sees nothing.
    images = images_in(DOCKERFILE.read_text())

    assert len(images) == 2, images


def test_the_finder_catches_a_tag_alone_and_a_short_digest() -> None:
    good = "python:3.14-slim@sha256:" + "a" * 64
    dockerfile = f"""
        FROM python:3.14-slim
        FROM --platform=linux/amd64 {good}
        COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /bin/uv
        COPY --from=example.com/tool:1@sha256:abc123 /tool /bin/tool
        COPY pyproject.toml uv.lock ./
    """
    images = images_in(dockerfile)

    assert images == [
        "python:3.14-slim",
        good,
        "ghcr.io/astral-sh/uv:0.12.6",
        "example.com/tool:1@sha256:abc123",
    ]
    assert without_digest(images) == [
        "python:3.14-slim",
        "ghcr.io/astral-sh/uv:0.12.6",
        "example.com/tool:1@sha256:abc123",
    ]


def test_the_finder_reads_every_way_to_name_an_image() -> None:
    # Three ways that Docker accepts, and that the finder once did not see:
    # lower case, an instruction over two lines, and an image inside a mount.
    dockerfile = """
        from example.com/lower:1
        COPY \\
            --from=example.com/two-lines:1 /tool /bin/tool
        RUN --mount=type=bind,from=example.com/mount:1,target=/bin/tool tool
        # FROM example.com/only-a-comment:1
    """

    assert images_in(dockerfile) == [
        "example.com/lower:1",
        "example.com/two-lines:1",
        "example.com/mount:1",
    ]


# ---- compose.yaml: the images that Docker Compose fetches ready-made. ----


def images_in_compose(compose: str) -> list[str]:
    """Gives every image that a file of Docker Compose names.

    An image is named after "image:". A line that starts with "#" is a
    comment. A service with "build:" and no "image:" names none: its image
    is made from a Dockerfile.
    """
    return re.findall(r"^[ \t]*image:[ \t]*(\S+)", compose, re.MULTILINE)


def test_every_image_of_the_compose_file_has_a_digest() -> None:
    images = images_in_compose(COMPOSE_FILE.read_text())

    assert without_digest(images) == []


def test_the_compose_file_names_one_image() -> None:
    # The test above is worth nothing if the finder sees nothing. The one
    # image is the database.
    images = images_in_compose(COMPOSE_FILE.read_text())

    assert len(images) == 1, images
    assert images[0].startswith("postgres:")


def test_the_finder_of_the_compose_file_catches_a_tag_alone() -> None:
    good = "postgres:18@sha256:" + "a" * 64
    compose = f"""
        services:
          app:
            build: ./backend
          db:
            image: {good}
          cache:
            image:   example.com/cache:7
          # image: example.com/only-a-comment:1
    """
    images = images_in_compose(compose)

    assert images == [good, "example.com/cache:7"]
    assert without_digest(images) == ["example.com/cache:7"]
