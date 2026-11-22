# Zirconium HCI upstream synchronization

Zirconium upstream updates are proposed in a pull request, **never merged automatically**.
Merging to `main` remains manual, and only that merge triggers the existing HCI build.

## Ownership policy

- **HCI-owned (never imported from upstream):** `.github/`, `README.md`,
  `renovate.json`, `cosign.pub` (HCI signing identity),
  `build-scripts/hci-*`, `hci-*.conf` / `99-hci*.conf` snippets, and
  `mkosi.extra/usr/lib/systemd/system-preset/00-hci.preset`.
- **Upstream-managed:** the remaining Zirconium files, including shared
  mkosi profiles, package sources and build scripts.
- **Shared changes:** default to three-way patch application. A specialized
  resolver may combine diverging `Packages=` lists **only** if the entire
  surrounding mkosi configuration is identical in the three versions.
  HCI-added packages remain added, HCI-removed packages remain removed.
  Every other conflict is a hard failure requiring manual review.

The `00-hci.preset` file enables HCI-specific Gaze, CUPS, and NordVPN
services without modifying the upstream-owned `01-zirconium.preset`.
Its `00-` prefix takes precedence if upstream later introduces a
preset for one of those units. Upstream changes to other services remain
independent. The preset file is excluded from upstream sync.

The `99-hci-desktop.conf` snippet adds `gvfs-afc` independently from upstream's
`base-desktop.conf`, avoiding the observed conflict with `gutenprint-cups`.
This uses mkosi's additive `Packages=` support. Package removals are not
implicitly reinstalled; do not blindly union upstream and fork package lists.

## Testing and publishing

Pushing changes to the existing `upstream-sync` branch runs a **read-only** dry run
against current upstream and the two managed submodules. Its workflow checks
that custom HCI package choices, local service presets, the signing key and
workflows remain intact.
It cannot push, create PRs or publish an image.

The production sync runs once daily or on manual dispatch. It proposes a
single `upstream-sync` PR and never auto-merges. If any unexpected conflict
arises, it refuses to push partial updates. The accepted-upstream SHA marker
advances only after a proposed sync PR is manually merged to `main`.