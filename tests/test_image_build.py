"""Tests of the image build (`Dockerfile`).

The image build downloads packages only with hash checks: the runtime
dependencies and the build requirements of the app (`build-system.requires`)
are exported from the lock (`uv.lock`), with their hashes, and installed with
uv, as the base image has no pip. Its build context is checked by
`tests/test_dockerignore.py`.
"""

import importlib.util
import os
from pathlib import Path
import re
import shlex
import subprocess
import tomllib
from typing import Any

from packaging.requirements import Requirement
import pytest
from uv import find_uv_bin

ROOT = Path(__file__).parents[1]
DOCKERFILE = ROOT / "Dockerfile"
# Dependency group that locks the build requirements of the app
GROUP = "build-system"


def _export(*args: str) -> str:
    """Export locked requirements with uv, as the image build does.

    Args:
        *args: Arguments that select the requirements (e.g., `--no-dev`).

    Returns:
        The exported requirements file.
    """
    # uv comes with the dev dependencies
    result = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
        [
            find_uv_bin(),
            "export",
            "--frozen",
            "--no-emit-project",
            "--no-header",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "UV_NO_CACHE": "1", "UV_OFFLINE": "1"},
    )
    return result.stdout


def _pinned(requirements: str) -> dict[str, list[str]]:
    """Get the pinned packages of a requirements file, with their hashes.

    Args:
        requirements: Requirements file, as `uv export` writes it.

    Returns:
        Hashes by package name.
    """
    lines = re.sub(r"\\\n\s*", " ", requirements).splitlines()
    packages = {}
    for line in lines:
        if not line or line.lstrip().startswith("#"):
            continue
        # A pin (`<name>==<version>`) or, TEMPORARY while FOCA is pinned to
        # a commit, a direct reference (`<name> @ <URL>`, without hashes)
        match = re.match(r"(?P<name>[A-Za-z0-9._-]+)(?: @ |==)(?P<rest>.*)", line)
        assert match, line
        packages[match["name"]] = re.findall(
            r"--hash=sha256:([0-9a-f]{64})", match["rest"]
        )
    return packages


def _foca_commit(requirements: str) -> str | None:
    """Get the FOCA commit of a temporary direct reference, if any.

    TEMPORARY: used while FOCA is pinned to a commit (see
    `scripts/check_release_pins.py`); remove with the pin's special cases.

    Args:
        requirements: Requirements file, as `uv export` writes it.

    Returns:
        The full commit SHA that FOCA is pinned to, or `None` for a locked
        FOCA release.
    """
    match = re.search(
        r"^foca @ git\+https://github\.com/elixir-cloud-aai/foca@([0-9a-f]{40})$",
        requirements,
        flags=re.MULTILINE,
    )
    return match[1] if match else None


def _locked_versions(requirements: str) -> dict[str, str]:
    """Get the locked versions of a requirements file.

    Args:
        requirements: Requirements file, as `uv export` writes it.

    Returns:
        Versions by package name, of the requirements pinned with `==`.
    """
    return dict(
        re.findall(r"^([A-Za-z0-9._-]+)==([^\s;\\]+)", requirements, flags=re.MULTILINE)
    )


def _runs() -> list[tuple[list[str], list[str]]]:
    """Get the `RUN` instructions of the Dockerfile.

    Continued lines are joined, and comments are left out.

    Returns:
        The options of each instruction (e.g., `--network=none`), and its
        shell commands, one per command of a list or pipeline (separated by
        `&&`, `||`, `;` or `|`).
    """
    lines = [
        line
        for line in DOCKERFILE.read_text().splitlines()
        if not line.lstrip().startswith("#")
    ]
    text = "\n".join(lines).replace("\\\n", " ")
    runs = []
    for run in re.findall(r"^RUN\s+(.+)$", text, flags=re.MULTILINE):
        # Heredocs (`RUN <<EOF`) would hide their commands from the checks
        assert "<<" not in run, run
        match = re.fullmatch(r"((?:--\S+\s+)*)(.*)", run)
        assert match, run
        options, commands = match.groups()
        runs.append(
            (options.split(), [c.strip() for c in re.split(r"&&|\|\||;|\|", commands)])
        )
    return runs


def _run_commands() -> list[str]:
    """Get the shell commands of the `RUN` instructions of the Dockerfile.

    Returns:
        Commands, one per command of a list or pipeline.
    """
    return [command for _, commands in _runs() for command in commands]


def _uv_args(command: str) -> list[str] | None:
    """Get the arguments of uv in a shell command.

    Args:
        command: Shell command (e.g., of a `RUN` instruction).

    Returns:
        The arguments after `uv`, starting with its command (e.g., `pip`), or
        `None` if the command doesn't run uv.
    """
    args = shlex.split(command)
    if args and Path(args[0]).name == "uv":
        return args[1:]
    return None


def _runs_pip(command: str) -> bool:
    """Tell whether a shell command runs pip itself (not `uv pip`).

    Args:
        command: Shell command (e.g., of a `RUN` instruction).

    Returns:
        Whether the command runs `pip`, `pip3`, `pip3.13`, `<venv>/bin/pip`
        or `python -m pip`.
    """
    args = shlex.split(command)
    if _uv_args(command) is not None:
        return False
    return any(re.fullmatch(r"pip(3(\.\d+)?)?", Path(arg).name) for arg in args)


def test_build_requirements_hashed() -> None:
    """The locked build requirements are complete, each with hashes."""
    packages = _pinned(_export("--only-group", GROUP))
    assert {"setuptools", "setuptools-scm"} <= packages.keys()
    for name, hashes in packages.items():
        assert hashes, name


def test_build_requirements_satisfied() -> None:
    """The locked build requirements satisfy `build-system.requires`.

    The image builds the app without build isolation, with the locked build
    requirements, which `uv build` doesn't check against
    `build-system.requires`.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    locked = _locked_versions(_export("--only-group", GROUP))
    for requirement in map(Requirement, pyproject["build-system"]["requires"]):
        assert requirement.specifier.contains(locked[requirement.name]), requirement


def test_locked_foca_is_base_image_foca() -> None:
    """The lock has the FOCA release of the base image.

    The image build fails otherwise (`scripts/image_requirements.py`); this
    test fails earlier, without building the image. A FOCA commit pin
    (temporary) has no locked release, and is checked by
    `scripts/image_requirements.py`.
    """
    locked = _locked_versions(_export("--no-dev"))
    match = re.search(
        r"^FROM elixircloud/foca:(?P<version>[^-@\s]+)-py",
        DOCKERFILE.read_text(),
        flags=re.MULTILINE,
    )
    assert match, "No FOCA base image in the Dockerfile"
    assert locked.get("foca", match["version"]) == match["version"]


def test_dockerfile_exports() -> None:
    """The image build exports the runtime and the build requirements only.

    So the other tests of the exports check what the `Dockerfile` selects (e.g.,
    not `--all-groups`, which would add the build requirements).
    """
    selections = []
    for command in _run_commands():
        args = _uv_args(command)
        if args is None or args[0] != "export":
            continue
        options = args[1:]
        for option in ("--project", "--output-file"):
            del options[options.index(option) : options.index(option) + 2]
        assert {"--frozen", "--no-emit-project"} <= set(options), args
        selections.append(
            [arg for arg in options if arg not in {"--frozen", "--no-emit-project"}]
        )
    assert sorted(selections) == [
        ["--no-dev"],
        ["--only-group", GROUP],
    ]


def test_runtime_requirements_without_build_requirements() -> None:
    """The runtime requirements of the image leave out the build group.

    They have hashes (except a temporary FOCA commit, which the image build
    leaves out), but no dev dependencies (the `dev` extra) and no `yq`, which
    the Helm chart's config Job used.
    """
    exported = _export("--no-dev")
    packages = _pinned(exported)
    assert {"connexion", "foca", "gunicorn"} <= packages.keys()
    assert "yq" not in packages
    assert "setuptools" not in packages
    assert "setuptools-scm" not in packages
    assert "pytest" not in packages
    # TEMPORARY: a FOCA commit has no hashes (see `_foca_commit()`)
    unhashed = {"foca"} if _foca_commit(exported) else set()
    for name, hashes in packages.items():
        assert hashes or name in unhashed, name


def _image_requirements_module() -> Any:
    """Load `scripts/image_requirements.py`, which is not a package.

    Returns:
        The module.
    """
    spec = importlib.util.spec_from_file_location(
        "image_requirements", ROOT / "scripts/image_requirements.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_image_requirements_of_export() -> None:
    """The script keeps the export of the image build as is, with FOCA's release.

    As the base image has the locked FOCA release (see
    `test_locked_foca_is_base_image_foca()`), nothing is left out.
    """
    exported = _export("--no-dev")
    if _foca_commit(exported) is not None:
        pytest.skip("FOCA is pinned to a commit (see the next test)")
    locked = _locked_versions(exported)
    assert (
        _image_requirements_module().image_requirements(exported, locked["foca"])
        == exported
    )


def test_image_requirements_of_export_foca_commit() -> None:
    """The script leaves out a temporary FOCA commit, and keeps the rest.

    TEMPORARY: runs while FOCA is pinned to a commit, which the base image
    has; remove with the pin's special cases.
    """
    exported = _export("--no-dev")
    commit = _foca_commit(exported)
    if commit is None:
        pytest.skip("FOCA is not pinned to a commit")
    # As setuptools-scm sets it for FOCA's development image
    installed = f"0.0.1.dev1+g{commit[:9]}"
    kept = _image_requirements_module().image_requirements(exported, installed)
    reference = (
        f"foca @ git+https://github.com/elixir-cloud-aai/foca@{commit}\n"
        "    # via trs-filer\n"
    )
    assert reference in exported
    assert kept == exported.replace(reference, "")
    assert _pinned(kept).keys() == _pinned(exported).keys() - {"foca"}


def test_downloads_hash_checked() -> None:
    """Each install of the image build checks hashes or downloads nothing.

    uv installs and builds everything; pip isn't run. uv commands that may
    download packages (`uv pip install`) take hash-pinned requirements only
    (`--require-hashes`, `-r`), as wheels (`--only-binary :all:`), without
    resolving anything else (`--no-deps`), or no index at all (`--no-index`,
    `--offline`), and then wheels only. The app is built offline with the
    hash-checked build requirements, not in an isolated build environment,
    which would be filled with unchecked downloads.
    """
    commands = []
    for command in _run_commands():
        assert not _runs_pip(command), command
        uv_args = _uv_args(command)
        if uv_args is not None:
            commands.append(uv_args)
    subcommands = [args[0] for args in commands]
    assert set(subcommands) <= {"export", "venv", "pip", "build"}, subcommands
    # The app is built as a wheel (checked below), not by an install of its
    # sources
    assert subcommands.count("build") == 1, subcommands
    # As nothing is resolved (`--no-deps`), the installed packages are checked
    assert ["pip", "check", "--system"] in commands, commands
    for args in commands:
        if args[:2] == ["pip", "check"]:
            # Checks the installed packages, downloads nothing
            continue
        if args[0] == "pip":
            assert args[1] == "install", args
            if "--no-index" in args:
                assert "--offline" in args, args
                targets = [arg for arg in args[2:] if not arg.startswith("-")]
                assert targets, args
                assert all(target.endswith(".whl") for target in targets), args
            else:
                assert "--require-hashes" in args, args
                assert args[args.index("--only-binary") + 1] == ":all:", args
                assert "-r" in args, args
            assert "--no-deps" in args, args
            # The image has a read-only root file system, so Python can't
            # cache bytecode at runtime; the build environment needs none
            if "--system" in args:
                assert "--compile-bytecode" in args, args
        elif args[0] == "build":
            assert "--offline" in args, args
            assert "--no-build-isolation" in args, args
            assert "--wheel" in args, args
        elif args[0] == "export":
            assert "--frozen" in args, args
        elif args[0] == "venv":
            # `--seed` would download pip without hash checks
            assert "--seed" not in args, args


def _option(args: list[str], name: str) -> str:
    """Get the value of an option of a command.

    Args:
        args: Arguments of the command.
        name: Name of the option (e.g., `-r`).

    Returns:
        The argument after the option.
    """
    return args[args.index(name) + 1]


def test_installs_exported_requirements() -> None:
    """The hash-checked installs read the requirements that the exports write.

    The build requirements are installed from their export; the runtime
    requirements from the output of `scripts/image_requirements.py`, which
    reads their export. So no other (e.g., incomplete) requirements file can
    be installed instead.
    """
    commands = _run_commands()
    exports = {
        _option(args, "--output-file"): args
        for args in map(_uv_args, commands)
        if args is not None and args[0] == "export"
    }
    filtered = {}
    for command in commands:
        match = re.fullmatch(
            r"python \S+/image_requirements\.py (\S+) > (\S+)", command
        )
        if match:
            assert match[1] in exports, command
            assert "--only-group" not in exports[match[1]], command
            filtered[match[2]] = match[1]
    assert len(filtered) == 1, commands
    installed = [
        _option(args, "-r")
        for args in map(_uv_args, commands)
        if args is not None and args[:2] == ["pip", "install"] and "-r" in args
    ]
    assert len(installed) == 2, installed
    (build,) = [path for path in installed if path in exports]
    assert _option(exports[build], "--only-group") == GROUP
    (runtime,) = [path for path in installed if path not in exports]
    assert runtime in filtered, runtime


def test_builds_offline() -> None:
    """The steps that build and install the app have no network.

    So that a download (e.g., of a build requirement missing from the lock)
    fails the image build, instead of only being refused by `--offline`.
    """
    offline = [
        options
        for options, commands in _runs()
        if any("--offline" in (_uv_args(command) or []) for command in commands)
    ]
    # At least the build and the install of the wheel
    assert len(offline) >= 2, offline
    for options in offline:
        assert "--network=none" in options, options


def test_uv_mounted_only() -> None:
    """The uv image is only mounted into the steps that use it, not copied.

    The steps also keep no uv cache (`UV_NO_CACHE=1`) in their layers and
    download no Python (`UV_PYTHON_DOWNLOADS=never`): they use the one of
    the base image.
    """
    text = DOCKERFILE.read_text()
    assert not re.search(r"^COPY\s+--from=uv\b", text, flags=re.MULTILINE)
    uses = [
        (options, commands)
        for options, commands in _runs()
        if any(_uv_args(command) is not None for command in commands)
    ]
    assert uses
    for options, commands in uses:
        assert "--mount=from=uv,source=/uv,target=/usr/local/bin/uv" in options
        assert commands[0] == "export UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never"
