#!/usr/bin/env python3
"""Portable, reversible installer for the Celeste DMS profile."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


PROJECT = Path(__file__).resolve().parents[1]
PROFILE_SETTINGS = PROJECT / "profile" / "settings.json"
PROFILE_THEME = PROJECT / "themes" / "celeste" / "theme.json"
PROFILE_WALLPAPER = PROJECT / "wallpapers" / "celeste.svg"
PROFILE_DEFAULTS = PROJECT / "profile" / "defaults.json"
NIRI_EXAMPLE = PROJECT / "examples" / "niri" / "config.kdl"
SETTINGS_REL = Path("DankMaterialShell/settings.json")
THEME_REL = Path("DankMaterialShell/themes/celeste/theme.json")
WALLPAPER_REL = Path("DankMaterialShell/themes/celeste/wallpaper.svg")
NIRI_REL = Path("niri/config.kdl")
ACTIVE_NAME = "active.json"


class InstallError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_regular(path: Path, label: str) -> bytes | None:
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise InstallError(f"refusing unsafe {label}: {path}")
    return path.read_bytes()


def validate_json(data: bytes, label: str) -> object:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid JSON in {label}: {exc}") from exc


def reject_symlink_components(path: Path, label: str) -> None:
    """Reject existing symlinks on the route to a file, including the file."""
    path = path.absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise InstallError(f"refusing symlink in {label} path: {current}")


def safe_target(home: Path, relative: Path, label: str) -> Path:
    home = home.absolute()
    if home.is_symlink():
        raise InstallError(f"refusing symlink {label} home: {home}")
    target = home / relative
    if target.parent == target or ".." in relative.parts or not target.is_relative_to(home):
        raise InstallError(f"unsafe {label} target")
    reject_symlink_components(target, label)
    return target


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    reject_symlink_components(path, "write")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def replace_theme_token(value: object, theme_path: Path) -> object:
    if isinstance(value, str):
        return str(theme_path) if value == "@THEME@" else value
    if isinstance(value, list):
        return [replace_theme_token(item, theme_path) for item in value]
    if isinstance(value, dict):
        return {key: replace_theme_token(item, theme_path) for key, item in value.items()}
    return value


def installation_inputs(config_home: Path) -> tuple[bytes, bytes, bytes, dict[str, object], dict[str, object]]:
    overrides_bytes = read_regular(PROFILE_SETTINGS, "profile settings")
    theme_bytes = read_regular(PROFILE_THEME, "profile theme")
    wallpaper_bytes = read_regular(PROFILE_WALLPAPER, "profile wallpaper")
    if overrides_bytes is None or theme_bytes is None or wallpaper_bytes is None:
        raise InstallError("profile/settings.json, theme.json, and wallpapers/celeste.svg must exist")
    overrides = validate_json(overrides_bytes, str(PROFILE_SETTINGS))
    validate_json(theme_bytes, str(PROFILE_THEME))
    if not isinstance(overrides, dict):
        raise InstallError("profile/settings.json must contain a JSON object")
    defaults_bytes = read_regular(PROFILE_DEFAULTS, "profile defaults")
    defaults: dict[str, object] = {}
    if defaults_bytes is not None:
        parsed_defaults = validate_json(defaults_bytes, str(PROFILE_DEFAULTS))
        if not isinstance(parsed_defaults, dict):
            raise InstallError("profile/defaults.json must contain a JSON object")
        defaults = parsed_defaults
    settings_target = safe_target(config_home, SETTINGS_REL, "settings")
    existing = read_regular(settings_target, "settings")
    base: dict[str, object] = {}
    if existing is not None:
        decoded = validate_json(existing, str(settings_target))
        if not isinstance(decoded, dict):
            raise InstallError("existing settings.json must contain a JSON object")
        base = decoded
    resolved_overrides = replace_theme_token(overrides, safe_target(config_home, THEME_REL, "theme"))
    assert isinstance(resolved_overrides, dict)
    base.update(resolved_overrides)
    return (json.dumps(base, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n", theme_bytes, wallpaper_bytes, resolved_overrides, defaults)


def target_paths(config_home: Path, with_niri: bool = False) -> dict[str, Path]:
    paths = {
        "settings": safe_target(config_home, SETTINGS_REL, "settings"),
        "theme": safe_target(config_home, THEME_REL, "theme"),
        "wallpaper": safe_target(config_home, WALLPAPER_REL, "wallpaper"),
    }
    if with_niri:
        paths["niri"] = safe_target(config_home, NIRI_REL, "niri")
    return paths


def state_path(state_home: Path) -> Path:
    result = state_home.absolute() / "niri-celeste"
    reject_symlink_components(result, "state")
    return result


class Lock:
    def __init__(self, state: Path):
        self.state = state
        self.file = None

    def __enter__(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        reject_symlink_components(self.state / "install.lock", "lock")
        self.file = open(self.state / "install.lock", "a+b")
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.file.close()
            raise InstallError("another installer operation is in progress") from exc

    def __exit__(self, *unused: object) -> None:
        if self.file:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()


def backup(state: Path, originals: dict[str, bytes | None], installed: dict[str, bytes], owned: dict[str, object], defaults: dict[str, object], with_niri: bool, config_home: Path) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = state / "backups" / f"{stamp}-{uuid.uuid4().hex}"
    directory.mkdir(parents=True, mode=0o700)
    entries: dict[str, dict[str, str | bool | None]] = {}
    for name, contents in originals.items():
        stored = None
        if contents is not None:
            stored = f"{name}.original"
            atomic_write(directory / stored, contents)
        entries[name] = {
            "present": contents is not None,
            "original_sha256": digest(contents) if contents is not None else None,
            "installed_sha256": digest(installed[name]),
            "backup": stored,
        }
    # Settings are restored key by key, because DMS may rewrite its JSON while
    # Celeste is active. Keep the exact original bytes too for audit/recovery.
    settings_before = validate_json(originals["settings"], "original settings") if originals["settings"] else {}
    if not isinstance(settings_before, dict):
        raise InstallError("existing settings.json must contain a JSON object")
    entries["settings"]["owned"] = {
        key: {"present": key in settings_before, "original": settings_before.get(key), "installed": value}
        for key, value in owned.items()
    }
    manifest = {
        "version": 1,
        "entries": entries,
        "with_niri": with_niri,
        "config_home": str(config_home.absolute()),
        "defaults": defaults,
    }
    atomic_write(directory / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")
    return directory


def activate_backup(state: Path, directory: Path) -> None:
    atomic_write(state / ACTIVE_NAME, json.dumps({"backup": directory.name}, sort_keys=True).encode() + b"\n")


def clear_active(state: Path) -> None:
    (state / ACTIVE_NAME).unlink()


def restore_original(path: Path, content: bytes | None) -> None:
    reject_symlink_components(path, "restore")
    if content is None:
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise InstallError(f"refusing unsafe restore target: {path}")
            path.unlink()
        return
    atomic_write(path, content)


def validate_niri_example() -> bytes:
    contents = read_regular(NIRI_EXAMPLE, "niri example")
    if contents is None:
        raise InstallError("examples/niri/config.kdl must exist for --with-niri")
    executable = shutil.which("niri")
    if not executable:
        raise InstallError("--with-niri requires the niri command for validation")
    import subprocess
    result = subprocess.run([executable, "validate", "-c", str(NIRI_EXAMPLE)], text=True, capture_output=True, check=False)
    if result.returncode:
        raise InstallError("niri example validation failed: " + (result.stderr.strip() or result.stdout.strip()))
    return contents


def apply(config_home: Path, state_home: Path, with_niri: bool) -> int:
    targets = target_paths(config_home, with_niri)
    def build_desired() -> tuple[dict[str, bytes], dict[str, object], dict[str, object]]:
        desired_settings, desired_theme, desired_wallpaper, owned, defaults = installation_inputs(config_home)
        desired = {"settings": desired_settings, "theme": desired_theme, "wallpaper": desired_wallpaper}
        if with_niri:
            desired["niri"] = validate_niri_example()
        return desired, owned, defaults

    def settings_matches(content: bytes | None, owned: dict[str, object], defaults: dict[str, object]) -> bool:
        if content is None:
            return False
        parsed = validate_json(content, "settings")
        absent = object()
        return isinstance(parsed, dict) and all(parsed.get(key, defaults.get(key, absent)) == value for key, value in owned.items())
    def matches(name: str, content: bytes | None, desired: dict[str, bytes], owned: dict[str, object], defaults: dict[str, object]) -> bool:
        return settings_matches(content, owned, defaults) if name == "settings" else content == desired[name]

    desired, owned, defaults = build_desired()
    originals = {name: read_regular(path, name) for name, path in targets.items()}
    if with_niri and originals["niri"] is not None and originals["niri"] != desired["niri"]:
        raise InstallError("refusing to replace an existing niri/config.kdl")
    if all(matches(name, originals[name], desired, owned, defaults) for name in targets):
        print("Celeste is already applied; unchanged.")
        return 0
    state = state_path(state_home)
    with Lock(state):
        # Rebuild after locking: settings may have changed while waiting.
        desired, owned, defaults = build_desired()
        originals = {name: read_regular(path, name) for name, path in targets.items()}
        if with_niri and originals["niri"] is not None and originals["niri"] != desired["niri"]:
            raise InstallError("refusing to replace an existing niri/config.kdl")
        if all(matches(name, originals[name], desired, owned, defaults) for name in targets):
            print("Celeste is already applied; unchanged.")
            return 0
        backup_dir = backup(state, originals, desired, owned, defaults, with_niri, config_home)
        changed: list[str] = []
        try:
            for name in ("niri", "theme", "wallpaper", "settings"):
                if name in targets and not matches(name, originals[name], desired, owned, defaults):
                    path = targets[name]
                    atomic_write(path, desired[name])
                    changed.append(name)
            activate_backup(state, backup_dir)
        except BaseException as exc:
            rollback_errors = []
            for name in reversed(changed):
                try:
                    restore_original(targets[name], originals[name])
                except BaseException as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            message = f"apply failed and changes were rolled back: {exc}"
            if rollback_errors:
                message += "; rollback errors: " + "; ".join(rollback_errors)
            raise InstallError(message) from exc
    print(f"Applied Celeste. Backup: {backup_dir}")
    return 0


def load_active(state: Path) -> tuple[Path, dict[str, object]]:
    active_bytes = read_regular(state / ACTIVE_NAME, "active manifest pointer")
    if active_bytes is None:
        raise InstallError("no active Celeste apply to restore")
    pointer = validate_json(active_bytes, "active manifest pointer")
    if not isinstance(pointer, dict) or not isinstance(pointer.get("backup"), str):
        raise InstallError("unsafe active manifest pointer")
    name = pointer["backup"]
    if Path(name).name != name or not name or name in {".", ".."}:
        raise InstallError("unsafe backup name")
    directory = state / "backups" / name
    reject_symlink_components(directory, "backup")
    manifest_bytes = read_regular(directory / "manifest.json", "backup manifest")
    if manifest_bytes is None:
        raise InstallError("backup manifest is missing")
    manifest = validate_json(manifest_bytes, "backup manifest")
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or not isinstance(manifest.get("entries"), dict):
        raise InstallError("unsafe backup manifest")
    return directory, manifest


def restore(config_home: Path, state_home: Path) -> int:
    state = state_path(state_home)
    with Lock(state):
        directory, manifest = load_active(state)
        entries = manifest["entries"]
        if manifest.get("config_home") != str(config_home.absolute()):
            raise InstallError("backup belongs to a different config home")
        targets = target_paths(config_home, manifest.get("with_niri") is True)
        if set(entries) != set(targets):
            raise InstallError("unsafe backup manifest entries")
        originals: dict[str, bytes | None] = {}
        before_restore: dict[str, bytes | None] = {}
        for name, path in targets.items():
            entry = entries[name]
            if not isinstance(entry, dict) or not isinstance(entry.get("present"), bool) or not isinstance(entry.get("installed_sha256"), str):
                raise InstallError("unsafe backup manifest entry")
            current = read_regular(path, name)
            before_restore[name] = current
            if name == "settings":
                if current is None:
                    raise InstallError("restore refused: settings is missing")
                parsed = validate_json(current, "settings")
                owned = entry.get("owned")
                if not isinstance(parsed, dict) or not isinstance(owned, dict):
                    raise InstallError("unsafe settings backup entry")
                defaults = manifest.get("defaults")
                if not isinstance(defaults, dict):
                    raise InstallError("unsafe backup defaults")
                absent = object()
                for key, values in owned.items():
                    if not isinstance(key, str) or not isinstance(values, dict) or values.get("installed") != parsed.get(key, defaults.get(key, absent)):
                        raise InstallError(f"restore refused: settings key {key!r} changed after Celeste was applied")
            elif current is None or digest(current) != entry["installed_sha256"]:
                raise InstallError(f"restore refused: {name} changed after Celeste was applied")
            if entry["present"]:
                filename = entry.get("backup")
                expected = entry.get("original_sha256")
                if filename != f"{name}.original" or not isinstance(expected, str):
                    raise InstallError("unsafe backup filename")
                content = read_regular(directory / filename, "backup file")
                if content is None or digest(content) != expected:
                    raise InstallError("backup file hash does not match manifest")
                originals[name] = content
            else:
                if entry.get("backup") is not None or entry.get("original_sha256") is not None:
                    raise InstallError("unsafe absent-state entry")
                originals[name] = None
        # Validate every target before changing either one.
        # Settings are merged so unrelated values DMS or the user added remain.
        settings_entry = entries["settings"]
        current_settings = validate_json(read_regular(targets["settings"], "settings") or b"", "settings")
        assert isinstance(current_settings, dict)
        for key, values in settings_entry["owned"].items():
            if values["present"]:
                current_settings[key] = values["original"]
            else:
                current_settings.pop(key, None)
        if not settings_entry["present"] and not current_settings:
            originals["settings"] = None
        else:
            originals["settings"] = json.dumps(current_settings, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for name, path in targets.items():
            reject_symlink_components(path, f"restore {name}")
        changed: list[str] = []
        try:
            # Keep settings last so DMS does not see a profile that refers to
            # assets which have not yet been restored.
            for name in ("niri", "theme", "wallpaper", "settings"):
                if name in targets:
                    restore_original(targets[name], originals[name])
                    changed.append(name)
            clear_active(state)
        except BaseException as exc:
            rollback_errors = []
            for name in reversed(changed):
                try:
                    restore_original(targets[name], before_restore[name])
                except BaseException as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            message = f"restore failed and changes were rolled back: {exc}"
            if rollback_errors:
                message += "; rollback errors: " + "; ".join(rollback_errors)
            raise InstallError(message) from exc
    print("Restored the files from the latest Celeste apply.")
    return 0


def plan(config_home: Path, with_niri: bool) -> int:
    targets = target_paths(config_home, with_niri)
    settings, theme, wallpaper, owned, defaults = installation_inputs(config_home)
    desired = {"settings": settings, "theme": theme, "wallpaper": wallpaper}
    if with_niri:
        desired["niri"] = validate_niri_example()
        current_niri = read_regular(targets["niri"], "niri")
        if current_niri is not None and current_niri != desired["niri"]:
            raise InstallError("refusing to replace an existing niri/config.kdl")
    for name, path in targets.items():
        current = read_regular(path, name)
        if name == "settings" and current is not None:
            parsed = validate_json(current, "settings")
            absent = object()
            unchanged = isinstance(parsed, dict) and all(parsed.get(key, defaults.get(key, absent)) == value for key, value in owned.items())
        else:
            unchanged = current == desired[name]
        status = "unchanged" if unchanged else "would update"
        print(f"{name}: {status} ({path})")
    return 0


def version(command: str, flag: str = "--version") -> str:
    executable = shutil.which(command)
    if not executable:
        return "missing"
    try:
        import subprocess
        result = subprocess.run([executable, flag], text=True, capture_output=True, timeout=3, check=False)
        return (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr) else executable
    except Exception:
        return executable


def doctor() -> int:
    missing = False
    for command, flag in (("niri", "--version"), ("dms", "version"), ("python3", "--version")):
        if not shutil.which(command):
            print(f"{command}: missing")
            missing = True
        else:
            print(f"{command}: {version(command, flag)}")
    return 1 if missing else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "restore", "doctor"), nargs="?", default="plan")
    home = Path.home()
    config_env = Path(os.environ["XDG_CONFIG_HOME"]) if os.environ.get("XDG_CONFIG_HOME") else None
    state_env = Path(os.environ["XDG_STATE_HOME"]) if os.environ.get("XDG_STATE_HOME") else None
    config_default = config_env if config_env and config_env.is_absolute() else home / ".config"
    state_default = state_env if state_env and state_env.is_absolute() else home / ".local/state"
    parser.add_argument("--config-home", type=Path, default=config_default)
    parser.add_argument("--state-home", type=Path, default=state_default)
    parser.add_argument("--with-niri", action="store_true", help="also install the example niri config when no config exists")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if args.command == "plan":
            return plan(args.config_home, args.with_niri)
        if args.command == "apply":
            return apply(args.config_home, args.state_home, args.with_niri)
        if args.command == "restore":
            return restore(args.config_home, args.state_home)
        return doctor()
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
