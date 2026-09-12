# Verification

## Automated checks

Run `python3 -m unittest discover -s tests -v`, then `niri validate -c examples/niri/config.kdl`. Tests must use temporary config/state directories and must not start a compositor, DMS instance, or development server.

The installer must demonstrate apply, repeat apply without a new backup, restoration of prior values/absent files, preservation of unrelated settings, conflict refusal, malformed JSON rejection, symlink refusal, and recovery from interrupted file transactions.

## Native desktop checks

Use a running Niri/DMS session. Web browser automation cannot verify QML layer-shell surfaces; use Niri/DMS IPC plus native screenshots.

1. Record `niri validate`, `dms version`, DMS service status, active workspace IDs, and the previous wallpaper path.
2. Save a private screenshot outside the repository before applying.
3. Run plan/apply. Query effective theme, bar configuration, and font with `dms ipc call settings get KEY`.
4. Check that one bar/Island is present per display and that the reserved area leaves tiled windows unobscured.
5. Open and close launcher, control center, and notifications. Confirm panels fit the smaller display and focus returns to applications.
6. Check workspaces and Niri overview, media and audio status, light/dark palette, wallpaper rendering, and service logs.
7. For repository screenshots, switch briefly to an empty workspace and close private popups. Keep screenshots containing app titles, accounts, notifications, or user files outside the repository.
8. Exercise restore in an isolated directory first. For a live restore, reselect the previous wallpaper before removing the installed asset.
9. Test hotplug, fractional scaling, authentication, and suspend/resume on representative hardware before calling those verified. A successful IPC call or lock demo does not prove authentication.

## Results

Verified locally on Arch Linux, Niri 26.04, DMS 1.6.1, Quickshell 0.3.1, and Python 3.14.7 on 2026-09-12:

- All 20 automated installer/profile tests pass, including injected transaction failures, XDG fallbacks, and sparse-settings restoration.
- Starter Niri config and existing live Niri config validate.
- Real installer plan/apply/reapply/restore succeeds in isolated directories with spaces in their paths, including fresh `--with-niri` installation and removal.
- Live restore returns the previous theme; reapply restores Celeste. Repeat apply reports unchanged after DMS has loaded and normalized the settings.
- Theme and Noto Sans font are confirmed through DMS IPC. Both template-generation switches remain disabled.
- Native screenshots confirm wallpaper and Island surfaces on 3440×1440 and 1920×1080 displays at scale 1.
- Launcher, control center, and notifications open and close on the 1920×1080 display without clipping. Closing them removes exclusive shell keyboard focus. Workspace switching was exercised and the original active workspaces were restored.
- Dark and light shell palettes render. Both palettes' main text pairs meet the automated 4.5:1 contrast threshold.
- DMS remains active; its journal had no warning-or-higher entries during the final verification window.

Not verified: a fresh physical-machine login, authentication/lock-unlock, suspend/resume, monitor hotplug, fractional scaling, hardware control changes, or CI on GitHub. These are upstream/hardware integration checks; no custom implementation of those systems is bundled. Existing lock/idle service ownership was preserved.

Private before/panel screenshots and full desktop baselines remain in local XDG state. Only a reviewed empty-workspace screenshot is included in the repository.
