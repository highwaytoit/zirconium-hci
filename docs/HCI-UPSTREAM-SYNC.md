# Zirconium HCI upstream synchronization

Zirconium upstream updates are proposed in a pull request, **never merged automatically**.
Merging to `main` remains manual, and only that merge triggers the existing HCI build.

## Ownership policy

- **HCI-owned (never imported from upstream):** `.github/`, `README.md`,
  `renovate.json`, `cosign.pub` (HCI signing identity),
  `build-scripts/hci-*`, and `hci-*.conf` / `99-hci*.conf` snippets.
- **Upstream-managed:** the remaining Zirconium files, including shared
  mkosi profiles, package sources and build scripts.
- **Shared changes:** default to three-way patch application. A specialized
  resolver may combine diverging `Packages=` lists **only** if the entire
  surrounding mkosi configuration is identical in the three versions.
  HCI-added packages remain added, HCI-removed packages remain removed.
  Every other conflict is a hard failure requiring manual review.

The `99-hci-desktop.conf` snippet adds `gvfs-afc` independently from upstream's
`base-desktop.conf`, avoiding the observed conflict with `gutenprint-cups`.
This uses mkosi's additive `Packages=` support. Package removals are not
implicitly reinstalled; do not blindly union upstream and fork package lists.

## Testing and publishing

The test branch `test/upstream-sync-hardening` runs a **read-only** dry run
against current upstream and the two managed submodules. Its workflow checks
that custom HCI package choices, the signing key and workflows remain intact.
It cannot push, create PRs or publish an image.

The production sync runs once daily or on manual dispatch. It proposes a
single `upstream-sync` PR and never auto-merges. If any unexpected conflict
arises, it refuses to push partial updates. The accepted-upstream SHA marker
advances only after a proposed sync PR is manually merged to `main`.