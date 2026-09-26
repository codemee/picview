# Publishing PicView

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

## Desktop releases

- `desktop.yml` builds a single Windows x64 EXE and an Apple Silicon macOS DMG containing `PicView.app` and an Applications shortcut.
- Publishing a new GitHub Release triggers both the PyPI and desktop workflows. Desktop files and individual SHA-256 checksums are attached to that release after tests and frozen-app smoke checks pass.
- Manually run **Build desktop apps** in GitHub Actions to validate the current branch. Manual runs store downloads as workflow artifacts and do not modify an existing release.
- Download and extract the workflow artifact ZIP to obtain the EXE or DMG; the macOS release download itself is a DMG, not an App ZIP.
- Windows builds run on `windows-latest`; Apple Silicon builds run on `macos-15`. Intel macOS builds are not produced.

### Local builds

Run on Windows x64 or an Apple Silicon Mac using native Python:

```sh
uv sync --locked --group build
uv run --frozen --group build python scripts/build_desktop.py
```

- Deliverables are written to `dist/desktop/release/`.
- PyInstaller bundles Python, Qt, image decoders, and the application icon. Users do not need Python or uv.
- The build checks the actual frozen executable by opening a temporary image, rendering it with Qt, and checking the bundled icon and version.
- macOS builds also verify the bundle's ad-hoc signature and the DMG structure.
- Windows files are unsigned. macOS apps have an ad-hoc signature, not an Apple Developer ID signature or notarization. Public distribution without security prompts requires separately configured signing certificates and, on macOS, notarization credentials.
- The existing `v0.0.1` tag predates desktop packaging. Use a new version and release tag for the first automatic desktop release; do not move the existing tag.
