# sony_projector_adcp — agent instructions

## What this repository is

The **canonical source** for the `sony_projector_adcp` Home Assistant custom
integration — a fork of `Bcukier/sony_projector_adcp` (kept as `upstream`)
adapted to the household's Sony **VPL-VW715ES** (lamp-based; the upstream
targeted the laser XW5000). The copy running in production lives at
`/config/custom_components/sony_projector_adcp/` on the HA Pi and is deployed
**by copying from here** — it is gitignored on the production side and has no
history there.

## Deployment contract

- Deploy over SSH (`jcolellajr@192.168.1.158`, key
  `~/.ssh/id_ed25519_homeassistant`; `sudo` required for `/config`), e.g.
  `cat <file> | ssh … "sudo tee /config/custom_components/sony_projector_adcp/<file>"`.
- The deployed tree must stay **byte-identical** to this repo — verify with
  `sha1sum` after every copy. If they differ, this repo is behind, not ahead:
  reconcile before editing.
- Integration **code changes take effect only on a full HA restart** (no
  reload path exists). Clear the integration's `__pycache__` on the Pi before
  that restart. Read `/config/AGENTS.md` before any production action; take
  the backup it mandates before deploying.
- Bump `manifest.json` `version` with every behavioral change, and deploy the
  bumped manifest together with the code so the running version string always
  identifies what is deployed.

## Hardware truths — do not "correct" from datasheets

- `const.py` comments record behavior **verified against the VW715ES itself**
  (e.g. `light_output_val` answers `err_cmd`; `lamp_control` is the lamp-era
  equivalent; Motionflow and 3D exist on this unit). Keep them authoritative.
- `protocol.py` docstrings record observed device behavior: the projector
  closes idle ADCP sessions after ~60s, and its ADCP daemon can wedge while
  SDCP/HTTP stay up (2026-08-09 incident — fix is toggling ADCP off/on in the
  projector settings; a lamp power cycle does not revive it).

## Git rules

- Work lands on `main`. `origin` is the `jcolellajr` fork; **do not push to
  either remote without explicit instruction.**
- Stage explicit paths only; never bulk-stage.
