# Architecture and ownership

Celeste is a configuration distribution. It owns visual choices and installation; upstream DMS owns the shell implementation and its compositor/service integrations. The dependency direction is profile → DMS public settings/IPC → Niri and desktop services. No local compositor adapter or parallel notification daemon is needed.

| Location | Responsibility |
| --- | --- |
| `profile/settings.json` | Top-level DMS overrides; nested objects and arrays intentionally replace their corresponding setting |
| `profile/defaults.json` | Upstream v1.6.1 defaults for sparse-settings comparison |
| `themes/celeste/theme.json` | Complete dark and light palettes |
| `wallpapers/celeste.svg` | Original scalable wallpaper |
| `examples/niri/config.kdl` | Optional self-contained starter; hardware auto-detection and generic shell shortcuts |
| `scripts/install.py` | Local file transaction, backup, plan, conflict detection, restore, doctor |
| `tests/` | Isolated transaction and asset checks |

The installer does not copy a user's entire DMS directory. Session data, output serial numbers, location, clipboard, plugin state, and app history remain local. Backups are outside the repository in XDG state.

## Settings contract

The profile targets DMS 1.6.1, configuration schema 18. Settings are based on upstream [SettingsSpec.js](https://github.com/AvengeMedia/DankMaterialShell/blob/v1.6.1/quickshell/Common/settings/SettingsSpec.js) and [SettingsData.qml](https://github.com/AvengeMedia/DankMaterialShell/blob/v1.6.1/quickshell/Common/SettingsData.qml).

Position `0` is top; `island: true` selects the animated Island renderer per bar. The profile uses one bar definition with `screenPreferences: ["all"]`; DMS creates the appropriate surfaces per display. Output modes, scaling, arrangement, and workspace semantics belong to Niri.

DMS omits settings equal to defaults when it saves JSON. Installer equality and rollback therefore compare effective values for owned keys instead of whole-file byte hashes. Original bytes are retained for manual recovery. Theme and wallpaper assets use exact content checks.

Changing `cornerRadius` and `niriLayout*` can make DMS regenerate `niri/dms/layout.kdl` on an existing DMS integration. That generated file belongs to DMS; never edit it as the profile source. The fresh starter has its own explicit geometry and no generated includes, so its first login does not depend on files that do not exist yet.

## Deliberate boundaries

- No Hyprland or Caelestia binaries, socket shims, or compositor forks.
- No new PAM, lock, idle, suspend, network, or polkit implementation.
- No automatic package transaction, session restart, service enablement, or remote install script.
- No global app-theme generation: both DMS and user Matugen template runs are disabled by the profile.
- Wallpaper selection stays in the DMS session, separate from the appearance transaction.

These boundaries keep a profile update and its undo proportional. Exact Caelestia panel shapes would require a separate QML implementation and are outside this configuration distribution.
