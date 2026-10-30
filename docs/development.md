# Development

See [Contributing](contributing.md) for how to contribute; this page
describes the development setup, the checks, the documentation and the
versions.

To set up a development environment (e.g., in a virtual environment, with
Python 3.13) and run the checks that CI runs:

```bash
pip install -e ".[dev]"  # the app, with the dev dependencies
pre-commit install  # run the checks on every commit
pre-commit run --all-files  # ruff, mypy, semgrep, ast-grep, actionlint
pre-commit run --all-files --hook-stage manual gitleaks-all  # secrets
coverage run -m pytest --ignore tests/integration_tests.py  # unit tests
coverage report
```

The unit tests need no database: they create the app from the base config
(`trs_filer/config.yaml`) with an in-memory database
([mongomock](https://github.com/mongomock/mongomock)), see
`tests/conftest.py`. Coverage is measured for `trs_filer` and `scripts`, and
CI reports it to [Codecov](https://about.codecov.io/); add tests that fail
without your change.

The integration tests (`tests/integration_tests.py`) send requests to the
app running with Docker Compose, as CI does:

```bash
docker compose up -d --build --wait
pytest tests/integration_tests.py
docker compose down --volumes
```

To try changes in the running app, rebuild it with
`docker compose up --build -d`. `python -m trs_filer.app` runs the app with
Flask's development server instead of Gunicorn (see
[Server](configuration.md#server)); it needs a MongoDB at `db.host` of the
config (e.g., set `MONGO_HOST=localhost` for a MongoDB published on the
host).

Run `pre-commit` in the environment with the dev dependencies: the mypy and
ast-grep hooks use the installed packages. The first run sets up the other
hooks, which takes a few minutes.

The checks are configured in
[`.pre-commit-config.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/.pre-commit-config.yaml)
and
[`pyproject.toml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/pyproject.toml).
Project-specific rules are in `.semgrep/` (security) and `.ast-grep/`
(anti-patterns such as HTTP status codes as strings, `print()` calls or
calls of the root logger), each with tests.
[actionlint](https://github.com/rhysd/actionlint) checks the workflows in
`.github/workflows/`, and their shell scripts with
[ShellCheck](https://www.shellcheck.net/) if it is installed (as on
GitHub-hosted runners, so CI may find more than a local run without it). To
suppress a false positive, add a comment with the reason to the line:
`# noqa: <code>` (ruff), `# type: ignore[<code>]` (mypy),
`# nosemgrep: <rule-id>`, `# ast-grep-ignore: <rule-id>` or
`# gitleaks:allow`.

## Helm chart

The [Helm chart](deployment.md) is in `deployment/`. Check changes with
[Helm](https://helm.sh/docs/intro/install/), e.g.:

```bash
helm lint deployment --set host_name=trs.example.org
helm template trs-filer deployment --set host_name=trs.example.org
```

## Documentation

This documentation is built with [MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), from
`docs/` and
[`mkdocs.yml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/mkdocs.yml),
by Read the Docs (configured in
[`.readthedocs.yaml`](https://github.com/elixir-cloud-aai/trs-filer/blob/dev/.readthedocs.yaml))
and in CI; warnings, e.g., of broken links, fail the build. The [API
reference](reference.md) is generated from the docstrings with
[mkdocstrings](https://mkdocstrings.github.io/). To build it locally, or serve
it with live reloading:

```bash
pip install -e ".[docs]"
mkdocs build --strict  # into `site/`, ignored by Git
mkdocs serve
```

Parts of the docs are kept elsewhere, so that they are written only once: the
introduction, the known deployments and the quick start of the home and
getting started pages are sections of `README.md` (between
`--8<-- [start:<name>]` and `--8<-- [end:<name>]` comments), and the
[deployment page](deployment.md) is the README of the Helm chart
(`deployment/README.md`), which `docs/hooks.py` includes, with its links to
pages of the docs and to files of the repository adapted (tested in
`tests/test_docs_hooks.py`). Links in the chart's README must be absolute (to
`https://trs-filer.readthedocs.io/en/latest/` and to files on branch `dev` on
GitHub), as they must also work in the packaged chart.

## Versioning

The project adopts the [semantic versioning](https://semver.org/) scheme for
versioning. Currently the service is in beta stage, so the API may change
without further notice.

The version is only stored in Git tags (`vX.Y.Z`): the package version is
derived from them (via
[setuptools-scm](https://setuptools-scm.readthedocs.io/)), and the service
info reports it. Builds without Git metadata, such as local Docker builds
(e.g., with Docker Compose), report `0.0.0.dev0`; pass the version to the
image build as the build argument `SETUPTOOLS_SCM_PRETEND_VERSION`, as the
CI workflow does.

To test unreleased changes of FOCA, `pyproject.toml` may pin a FOCA commit
(`foca @ git+https://github.com/elixir-cloud-aai/foca@<sha>`), with FOCA's
development image of that commit as the base image (tagged by date, e.g.,
`elixircloud/foca:20261023-py3.13`, pinned by digest, as the tag moves with
later commits of that day). The `Dockerfile` records the commit as
`## FOCA commit: <sha>`, which the tests check (`tests/test_config.py`); the
image build doesn't reinstall FOCA, but fails unless the base image has FOCA
of that commit (`scripts/image_requirements.py`). Such pins are temporary:
CI fails for release tags while a requirement is a direct reference or
names a pre-release or a local version, or a FOCA image has no release tag
(`scripts/check_release_pins.py`, tested in
`tests/test_check_release_pins.py`), so replace them by the released versions
before tagging.
