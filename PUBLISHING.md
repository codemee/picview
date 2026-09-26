# Publishing to PyPI

## One-time setup

Add a [pending publisher](https://pypi.org/manage/account/publishing/) in the PyPI account that will own the project:

| Field | Value |
| --- | --- |
| PyPI project name | `picview` |
| GitHub owner | `codemee` |
| Repository name | `picview` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

For an existing PyPI project, add the same publisher under the project's Publishing settings instead.

## Release

1. Update the version in `pyproject.toml` and `src/picview/__init__.py`, then run `uv lock`.
2. Commit and push the changes.
3. Publish a GitHub Release with a matching tag, such as `v0.0.2`.
4. The `Publish to PyPI` workflow tests the Windows application, builds and validates the distributions, and uploads them using Trusted Publishing.
5. Verify the published command with `uvx --refresh picview --version`.

- For the first PyPI publication of `0.0.1`, manually run `publish.yml` on `main`; the GitHub `v0.0.1` release predates the packaging setup.
- Manual runs publish the version in the selected Git ref. Always use a ref containing the intended release contents.
- PyPI release files cannot be replaced with different contents. Use a new version for subsequent code changes.
- No long-lived PyPI API token is required.
