# Desktop integration

## One shell owner

Use the packaged `dms.service` with the normal `niri-session` login flow. Do not also add `spawn-at-startup "dms" "run"` to Niri. The service follows `graphical-session.target`.

Celeste changes no service definitions. Existing Niri shortcuts keep working. The optional starter calls DMS IPC for launcher, clipboard, notifications, audio, brightness, media, settings, and lock; it uses Niri actions for window management and screenshots.

| Function | Owner |
| --- | --- |
| Workspaces, windows, output geometry | Niri |
| Bar, Island panels, launcher, notification UI | DMS |
| Audio devices | PipeWire/WirePlumber via DMS |
| Network/Bluetooth | Existing system services via DMS |
| Lock authentication and idle policy | Existing working desktop configuration; configure through upstream DMS guidance if starting fresh |
| Polkit authorization | Exactly one working polkit agent |
| Clipboard history | Existing configured backend; the profile only changes the UI |

Do not run Mako/SwayNC beside the DMS notification owner. A wallpaper daemon or Waybar may also overlap DMS surfaces. SwayIdle, SwayLock, SwayOSD, standalone polkit, and clipboard helpers require an ownership check rather than blanket removal: installing an appearance profile is not evidence those services are redundant.

## Optional tools and capabilities

Install Xwayland Satellite if you need X11 applications. Use DMS's dependency diagnostics (`dms doctor`) to check optional network, Bluetooth, brightness, clipboard, and screen-sharing support. A theme cannot supply hardware permissions or missing backends.

The fresh starter does not set a keyboard layout, GPU environment overrides, laptop power policy, display refresh rate, default browser, or external-monitor name. Customize these locally after confirming your hardware and preferred applications.

## Existing generated layout

If your config includes `dms/layout.kdl`, the profile's geometry controls apply through DMS. If it does not, copy the desired layout values from the starter into your existing layout and validate with `niri validate`. Avoid multiple competing layout definitions. Do not paste an include to a missing generated file.

## Shortcuts in the starter

| Shortcut | Action |
| --- | --- |
| Super+Return | Foot terminal |
| Super+Space | Launcher |
| Super+Comma | Settings |
| Super+V | Clipboard |
| Super+N | Notifications |
| Super+B | Control center |
| Super+Y | Wallpaper picker |
| Super+Alt+L | Lock |
| Super+G | Niri overview |
| Super+K | Keybinding help |
| Super+Shift+Escape | Session menu |

New installations must verify lock/unlock and suspend/resume locally before depending on unattended locking. See upstream [DMS authentication guidance](https://danklinux.com/docs/dankmaterialshell/lock-screen) and its current compositor setup documentation.
