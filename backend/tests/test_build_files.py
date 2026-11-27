"""Tests of the files that build and ship the app.

First: is every image that is fetched named by its digest? A tag, such as
"python:3.14-slim", is a name that its owner can move to another image. A
digest is the fingerprint of one exact image: "@sha256:" and 64 characters.
With it, every build starts from the same image.

Last: is the image of the app built in one place, and is that one image
tested and pushed?

These tests only read files: the Dockerfile, compose.yaml, the pipeline and
the smoke test. They need no Docker and no network.
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


# ---- The image of the app: built once, tested and pushed by its id. ----
# The pipeline builds the image in a step of its own and reads its id, the
# fingerprint of its content. The smoke test is handed that id, and after a
# merge the push step takes the image by that id. So the image that is
# tested is the image that is deployed.

PIPELINE = Path(__file__).parent.parent.parent / "azure-pipelines.yml"
SMOKE_TEST = Path(__file__).parent.parent.parent / "scripts" / "smoke_test.sh"


def commands_of(script: str) -> str:
    """A shell script without its comments and without its messages.

    A comment and a message may name a command for the reader. Only the
    rest is run.
    """
    kept = []
    for line in script.splitlines():
        words = line.strip()
        if words.startswith("#") or words.startswith(("fail ", "|| fail ")):
            continue
        kept.append(line)
    return "\n".join(kept)


def test_the_smoke_test_does_not_build_the_image_under_test() -> None:
    commands = commands_of(SMOKE_TEST.read_text())

    # No build by Docker itself, in any of its three spellings. Part 2 of
    # the script lets Docker Compose build another image, for the app beside
    # a database; that one is thrown away.
    for build in ("docker build", "docker buildx", "docker image build"):
        assert build not in commands


def test_the_smoke_test_is_told_which_image_to_test() -> None:
    commands = commands_of(SMOKE_TEST.read_text())

    # The image is the first word after the name of the script...
    assert 'IMAGE="${1:-}"' in commands
    # ...and the script has no image of its own to fall back on.
    assert "book-teller:" not in commands


def test_the_finder_of_commands_drops_comments_and_messages() -> None:
    script = """
        # docker build --tag a backend
        docker run a
            || fail "build it first: docker build --tag a backend"
        fail "no image"
    """

    assert commands_of(script).split() == ["docker", "run", "a"]


def test_the_image_that_is_built_is_the_one_that_is_tested_and_pushed() -> None:
    pipeline = PIPELINE.read_text()

    # One build, from the folder "backend".
    built = re.findall(r"docker build --tag (\S+) backend", pipeline)
    assert len(built) == 1
    # The id of that image is read and handed to the later steps.
    assert f"docker image inspect --format '{{{{.Id}}}}' {built[0]}" in pipeline
    assert 'echo "##vso[task.setvariable variable=imageId]$imageId"' in pipeline
    # The smoke test gets that id, and the push step takes the image by it.
    assert 'bash scripts/smoke_test.sh "$(imageId)"' in pipeline
    assert re.findall(r'docker tag (\S+) "\$image"', pipeline) == ['"$(imageId)"']
    # In that order.
    assert (
        pipeline.index("docker build --tag")
        < pipeline.index("bash scripts/smoke_test.sh")
        < pipeline.index("docker tag")
    )
