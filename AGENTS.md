# Celeste project guidance

This is a portable DMS appearance profile, not a shell fork. Match the DMS version documented in README and use its public settings/IPC. Keep new implementation proportional to a configuration distribution.

- Never copy a user's entire configuration or session directory into the repository. Keep snapshots, notification/app history, locations, output serials, and personal paths in XDG state.
- Installer tests use temporary config/state directories. Run `python3 -m unittest discover -s tests -v` and `niri validate -c examples/niri/config.kdl` for relevant changes.
- Changes to installation must verify rollback, failure handling, defaults omitted by DMS, repeat application, and preservation of unrelated user settings. Do not replace dotfile symlinks.
- Additions to profile settings may require matching entries in `profile/defaults.json`. Source defaults from the documented DMS version; do not guess enum values.
- Native Niri/DMS IPC and screenshots verify this QML desktop. Do not start a compositor, shell instance, dev server, or preview server for tests. Use an existing user session only when desktop changes are authorized.
- Keep optional starter configuration generic: no host-specific display modes, usernames, app preferences beyond the documented terminal, or GPU workarounds.
- Never write to DMS-generated compositor files as the source of a feature. Use public settings or a documented Niri configuration boundary.
- Commit, push, and GitHub publication require an explicit request. Package installation and service enablement are documented user setup steps, not hidden installer behavior.
