from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_ENV_PATH = ROOT / ".env.local"


@dataclass(frozen=True)
class LocalConfigStatus:
    path: Path
    found: bool
    loaded_names: tuple[str, ...]
    skipped_existing_names: tuple[str, ...]
    invalid_names: tuple[str, ...]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.found and self.error is None

    def safe_summary_lines(self) -> list[str]:
        if not self.found:
            return [
                "WARN: local config - .env.local was not found; copy .env.local.example to .env.local and restart the console"
            ]
        if self.error:
            return [f"FAIL: local config - .env.local could not be loaded: {self.error}"]
        if not self.loaded_names and not self.skipped_existing_names and not self.invalid_names:
            return [
                "WARN: local config - .env.local was found but no settings were loaded; copy .env.local.example values into it and restart the console"
            ]
        lines = [
            "PASS: local config - .env.local found and parsed; values not displayed",
            f"PASS: local config - loaded {len(self.loaded_names)} setting(s) without overriding OS environment",
        ]
        if self.skipped_existing_names:
            lines.append(
                f"INFO: local config - kept {len(self.skipped_existing_names)} existing OS environment setting(s)"
            )
        if self.invalid_names:
            lines.append(
                f"WARN: local config - ignored {len(self.invalid_names)} empty or invalid setting(s)"
            )
        return lines


def load_local_operator_config(
    path: Path = DEFAULT_LOCAL_ENV_PATH,
    environ: MutableMapping[str, str] | None = None,
) -> LocalConfigStatus:
    target_env = os.environ if environ is None else environ
    if not path.exists():
        return LocalConfigStatus(
            path=path,
            found=False,
            loaded_names=(),
            skipped_existing_names=(),
            invalid_names=(),
        )
    if not path.is_file():
        return LocalConfigStatus(
            path=path,
            found=True,
            loaded_names=(),
            skipped_existing_names=(),
            invalid_names=(),
            error="path is not a file",
        )
    try:
        values = _dotenv_values_with_windows_fallback(path)
    except Exception as exc:
        return LocalConfigStatus(
            path=path,
            found=True,
            loaded_names=(),
            skipped_existing_names=(),
            invalid_names=(),
            error=type(exc).__name__,
        )

    loaded = []
    skipped = []
    invalid = []
    for name, value in values.items():
        if not name or value is None or not str(value).strip():
            invalid.append(str(name))
            continue
        if target_env.get(name):
            skipped.append(name)
            continue
        if environ is None:
            os.environ[name] = str(value).strip()
        else:
            # Tests pass a mutable mapping; production uses os.environ above.
            target_env[name] = str(value).strip()  # type: ignore[index]
        loaded.append(name)

    return LocalConfigStatus(
        path=path,
        found=True,
        loaded_names=tuple(loaded),
        skipped_existing_names=tuple(skipped),
        invalid_names=tuple(invalid),
    )


def _dotenv_values_with_windows_fallback(path: Path) -> dict[str, str | None]:
    try:
        values = dict(dotenv_values(path, encoding="utf-8-sig"))
    except UnicodeError:
        values = {}
    if values:
        return values
    try:
        return dict(dotenv_values(path, encoding="utf-16"))
    except UnicodeError:
        return values
