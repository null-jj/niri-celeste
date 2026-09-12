import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "install.py"
spec = importlib.util.spec_from_file_location("celeste_installer", SCRIPT)
installer = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="celeste installer ")
        root = Path(self.tmp.name)
        self.config = root / "config home"
        self.state = root / "state home"
        assets = root / "assets"
        (assets / "profile").mkdir(parents=True)
        (assets / "themes/celeste").mkdir(parents=True)
        (assets / "wallpapers").mkdir()
        (assets / "profile/settings.json").write_text(json.dumps({"themePath": "@THEME@", "managed": 2}))
        (assets / "profile/defaults.json").write_text(json.dumps({"managed": 0}))
        (assets / "themes/celeste/theme.json").write_text('{"name":"celeste"}\n')
        (assets / "wallpapers/celeste.svg").write_text("<svg/>\n")
        self.old = (installer.PROFILE_SETTINGS, installer.PROFILE_DEFAULTS, installer.PROFILE_THEME, installer.PROFILE_WALLPAPER)
        installer.PROFILE_SETTINGS = assets / "profile/settings.json"
        installer.PROFILE_DEFAULTS = assets / "profile/defaults.json"
        installer.PROFILE_THEME = assets / "themes/celeste/theme.json"
        installer.PROFILE_WALLPAPER = assets / "wallpapers/celeste.svg"

    def tearDown(self):
        installer.PROFILE_SETTINGS, installer.PROFILE_DEFAULTS, installer.PROFILE_THEME, installer.PROFILE_WALLPAPER = self.old
        self.tmp.cleanup()

    def settings(self):
        return self.config / "DankMaterialShell/settings.json"

    def test_apply_restore_preserves_unrelated_settings(self):
        self.settings().parent.mkdir(parents=True)
        self.settings().write_text(json.dumps({"unrelated": "keep", "managed": 0}))
        self.assertEqual(installer.apply(self.config, self.state, False), 0)
        applied = json.loads(self.settings().read_text())
        self.assertEqual(applied["unrelated"], "keep")
        self.assertEqual(applied["managed"], 2)
        self.assertEqual(installer.restore(self.config, self.state), 0)
        restored = json.loads(self.settings().read_text())
        self.assertEqual(restored, {"unrelated": "keep", "managed": 0})
        self.assertFalse((self.config / "DankMaterialShell/themes/celeste/theme.json").exists())
        self.assertFalse((self.config / "DankMaterialShell/themes/celeste/wallpaper.svg").exists())

    def test_reapply_is_idempotent_and_does_not_create_backup(self):
        installer.apply(self.config, self.state, False)
        backups = list((self.state / "niri-celeste/backups").iterdir())
        installer.apply(self.config, self.state, False)
        self.assertEqual(list((self.state / "niri-celeste/backups").iterdir()), backups)

    def test_restore_refuses_owned_setting_conflict(self):
        installer.apply(self.config, self.state, False)
        current = json.loads(self.settings().read_text())
        current["managed"] = 3
        self.settings().write_text(json.dumps(current))
        with self.assertRaisesRegex(installer.InstallError, "changed after"):
            installer.restore(self.config, self.state)

    def test_restore_removes_settings_when_it_was_absent(self):
        installer.apply(self.config, self.state, False)
        self.assertTrue(self.settings().exists())
        installer.restore(self.config, self.state)
        self.assertFalse(self.settings().exists())

    def test_restore_rejects_different_config_home(self):
        installer.apply(self.config, self.state, False)
        with self.assertRaisesRegex(installer.InstallError, "different config home"):
            installer.restore(Path(self.tmp.name) / "other config", self.state)

    def test_apply_rebuilds_inputs_after_taking_lock(self):
        real_inputs = installer.installation_inputs
        calls = 0

        def inputs_after_source_changes(home):
            nonlocal calls
            calls += 1
            value = real_inputs(home)
            if calls == 1:
                installer.PROFILE_SETTINGS.write_text(json.dumps({"themePath": "@THEME@", "managed": 9}))
            return value

        installer.installation_inputs = inputs_after_source_changes
        try:
            installer.apply(self.config, self.state, False)
        finally:
            installer.installation_inputs = real_inputs
        self.assertEqual(json.loads(self.settings().read_text())["managed"], 9)
        self.assertGreaterEqual(calls, 2)

    def test_default_omission_restores_using_manifest_snapshot(self):
        installer.PROFILE_SETTINGS.write_text(json.dumps({"managed": 0}))
        installer.apply(self.config, self.state, False)
        self.settings().write_text("{}\n")  # DMS omits values equal to defaults.
        installer.PROFILE_DEFAULTS.write_text(json.dumps({"managed": 99}))
        installer.restore(self.config, self.state)
        self.assertFalse(self.settings().exists())

    def test_failed_backup_activation_rolls_back_files(self):
        real_activate = installer.activate_backup
        installer.activate_backup = lambda state, directory: (_ for _ in ()).throw(OSError("activation failure"))
        try:
            with self.assertRaisesRegex(installer.InstallError, "rolled back"):
                installer.apply(self.config, self.state, False)
        finally:
            installer.activate_backup = real_activate
        self.assertFalse(self.settings().exists())
        self.assertFalse((self.state / "niri-celeste/active.json").exists())

    def test_failed_pointer_cleanup_rolls_back_restore(self):
        theme = self.config / "DankMaterialShell/themes/celeste/theme.json"
        theme.parent.mkdir(parents=True)
        theme.write_text('{"name":"before"}\n')
        installer.apply(self.config, self.state, False)
        active = (self.state / "niri-celeste/active.json").read_bytes()
        applied_theme = theme.read_bytes()
        real_clear = installer.clear_active
        installer.clear_active = lambda state: (_ for _ in ()).throw(OSError("cleanup failure"))
        try:
            with self.assertRaisesRegex(installer.InstallError, "restore failed and changes were rolled back"):
                installer.restore(self.config, self.state)
        finally:
            installer.clear_active = real_clear
        self.assertEqual(theme.read_bytes(), applied_theme)
        self.assertEqual((self.state / "niri-celeste/active.json").read_bytes(), active)

    def test_with_niri_allows_fresh_and_plan_protects_existing_config(self):
        real_validate = installer.validate_niri_example
        installer.validate_niri_example = lambda: b"layout {}\n"
        try:
            installer.apply(self.config, self.state, True)
            self.assertEqual((self.config / "niri/config.kdl").read_bytes(), b"layout {}\n")
            (self.config / "niri/config.kdl").write_text("user config\n")
            with self.assertRaisesRegex(installer.InstallError, "refusing to replace"):
                installer.plan(self.config, True)
        finally:
            installer.validate_niri_example = real_validate

    def test_empty_xdg_environment_uses_home_defaults(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "", "XDG_STATE_HOME": ""}, clear=False), patch.object(Path, "home", return_value=Path("/test-home")):
            args = installer.parse_args([])
        self.assertEqual(args.config_home, Path("/test-home/.config"))
        self.assertEqual(args.state_home, Path("/test-home/.local/state"))

    def test_relative_xdg_environment_uses_home_defaults(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative-config", "XDG_STATE_HOME": "relative-state"}, clear=False), patch.object(Path, "home", return_value=Path("/test-home")):
            args = installer.parse_args([])
        self.assertEqual(args.config_home, Path("/test-home/.config"))
        self.assertEqual(args.state_home, Path("/test-home/.local/state"))

    def test_doctor_fails_when_a_required_command_is_missing(self):
        with patch.object(installer.shutil, "which", return_value=None):
            self.assertEqual(installer.doctor(), 1)

    def test_apply_assets_precede_settings_and_failure_keeps_previous_active(self):
        installer.apply(self.config, self.state, False)
        active = (self.state / "niri-celeste/active.json").read_bytes()
        installer.PROFILE_THEME.write_text('{"name":"new"}\n')
        installer.PROFILE_WALLPAPER.write_text("<svg>new</svg>\n")
        installer.PROFILE_SETTINGS.write_text(json.dumps({"themePath": "@THEME@", "managed": 3}))
        calls = []
        real_write = installer.atomic_write

        def fail_settings(path, data):
            calls.append(path)
            if path == self.settings():
                raise OSError("injected write failure")
            return real_write(path, data)

        installer.atomic_write = fail_settings
        try:
            with self.assertRaisesRegex(installer.InstallError, "rolled back"):
                installer.apply(self.config, self.state, False)
        finally:
            installer.atomic_write = real_write
        self.assertLess(calls.index(self.config / "DankMaterialShell/themes/celeste/theme.json"), calls.index(self.settings()))
        self.assertLess(calls.index(self.config / "DankMaterialShell/themes/celeste/wallpaper.svg"), calls.index(self.settings()))
        self.assertEqual((self.state / "niri-celeste/active.json").read_bytes(), active)

    def test_restore_failure_rolls_back_and_keeps_active_pointer(self):
        theme = self.config / "DankMaterialShell/themes/celeste/theme.json"
        theme.parent.mkdir(parents=True)
        theme.write_text('{"name":"before"}\n')
        (theme.parent / "wallpaper.svg").write_text("<svg>before</svg>\n")
        installer.apply(self.config, self.state, False)
        active = (self.state / "niri-celeste/active.json").read_bytes()
        applied_theme = theme.read_bytes()
        real_write = installer.atomic_write

        def fail_wallpaper(path, data):
            if path.name == "wallpaper.svg":
                raise OSError("injected restore failure")
            return real_write(path, data)

        installer.atomic_write = fail_wallpaper
        try:
            with self.assertRaisesRegex(installer.InstallError, "restore failed and changes were rolled back"):
                installer.restore(self.config, self.state)
        finally:
            installer.atomic_write = real_write
        self.assertEqual(theme.read_bytes(), applied_theme)
        self.assertEqual((self.state / "niri-celeste/active.json").read_bytes(), active)

    def test_malformed_settings_and_symlinks_are_rejected(self):
        self.settings().parent.mkdir(parents=True)
        self.settings().write_text("not json")
        with self.assertRaisesRegex(installer.InstallError, "invalid JSON"):
            installer.apply(self.config, self.state, False)
        self.settings().unlink()
        outside = Path(self.tmp.name) / "outside"
        outside.write_text("{}")
        self.settings().symlink_to(outside)
        with self.assertRaisesRegex(installer.InstallError, "symlink"):
            installer.plan(self.config, False)

    def test_lock_rejects_concurrent_operation(self):
        state = installer.state_path(self.state)
        with installer.Lock(state):
            with self.assertRaisesRegex(installer.InstallError, "another installer"):
                with installer.Lock(state):
                    pass


if __name__ == "__main__":
    unittest.main()
