# AGENTS.md

Instructions for automated code-writing agents (Codex/Copilot/etc.).
Follow existing nearby patterns if anything here conflicts with local code.

## Defaults (non-negotiable)

- Python: **3.13+**
- Max line length: **99**
- Indent: 4 spaces
- Encoding: UTF-8

## Typing

- Add type hints for all **public** functions/methods: params + return types.
- Prefer modern syntax:
  - Built-in generics: `list[str]`, `dict[str, int]` (not `typing.List`, `typing.Dict`)
  - Unions: `X | Y` (not `Optional[X]` / `Union[X, Y]`)
- New modules should include `from __future__ import annotations` unless this repo explicitly drops it.
- Import from `typing` only when needed (`Any`, `Callable`, `Sequence`, `Iterable`, `Mapping`,
  `TypedDict`, `Protocol`, `TYPE_CHECKING`, etc.).
- Use small, named type aliases for repeated/complex types.

## Docstrings

- PEP 257 compliant.
- Google-style sections: `Args:`, `Returns:`, `Raises:`
- Public modules/classes/functions: docstring required.
- Private helpers: docstring when non-obvious.

## Imports

- Group imports with blank lines:
  1. standard library
  2. third-party
  3. local imports
- Prefer one import per line.
- Use `TYPE_CHECKING` blocks to avoid runtime cycles.

## Naming

- Functions/vars: `snake_case`
- Classes/exceptions: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

## Code shape

- Aim for ~20–30 lines per function; split complex logic into helpers.
- Single responsibility per function/class.
- Prefer clarity over cleverness.

## Modern Python practices

- f-strings
- `pathlib.Path` over `os.path`
- Context managers (`with`) for resources
- Comprehensions only when they stay readable

## Error handling

- Prefer EAFP.
- Catch specific exceptions.
- Preserve context: `raise NewError(...) from exc`
- Do not silently swallow exceptions without an explicit comment justifying it.

## Repo-specific constraints

- PyQt6 UI: avoid blocking the UI thread; do long work in workers/threads and signal results back.
- Be conservative with network activity; prefer cached/offline-first behavior when applicable.
- Do not add new dependencies unless explicitly requested.

## Checks (run what exists in the repo)

- Smoke test: `fc-token --self-test`
- If configured in this repo:
  - Format: `black --line-length 99 ...`
  - Lint/fix: `ruff check --fix ...`
  - Type check: `mypy --strict ...`

## Change checklist (before finalizing)

1. Keep diffs minimal and consistent with nearby code.
2. Update docstrings + any user-facing text if behavior changes.
3. Run smoke test and any available linters/type checks.
