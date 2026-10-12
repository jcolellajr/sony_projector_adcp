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
  To copy every tracked file in one step with `root:root` 644/755 kept (used
  for 1.3.1):
  `git -c tar.umask=022 archive HEAD custom_components/sony_projector_adcp | ssh … "sudo tar -x -f - -C /config"`.
  In zsh, keep the ssh invocation in a shell function, not a variable: zsh does
  not word-split `$SSH`, so the command never runs.
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
- Deploy every tracked file under `custom_components/sony_projector_adcp/`,
  including `translations/en.json`. HA reads custom-integration UI text from
  `translations/`, not `strings.json`; the two must stay identical, and a test
  enforces that.
- To prove which version loaded after the restart, ask HA for the manifest it
  loaded: the WebSocket command `manifest/get` with
  `{"integration": "sony_projector_adcp"}` returns its `version`. With the
  `hass` wrapper:
  `hass -o json raw ws manifest/get --json '{"integration":"sony_projector_adcp"}'`.
  Verified 2026-10-12: it reported 1.3.1 right after that deploy. Also check
  that `__pycache__` was rebuilt after the restart. HA's loader log line does
  not print the version, and HACS's `update.sony_projector_adcp_update`
  reports GitHub releases, not the deployed manifest, so neither is evidence.
  Config entry flags in `/api/config/config_entries/entry` (e.g.
  `supports_reconfigure`) only help when a release changes them.

## Validation — required before every deploy

The suite runs against a fake ADCP server and is pinned to the production HA
release in `requirements_test.txt`. Bump that pin when production HA moves.

```bash
uv venv .venv --python 3.14 && VIRTUAL_ENV=.venv uv pip install -r requirements_test.txt
.venv/bin/python -m pytest -q
```

The pinned test package needs a recent Python: the 2026.10.1 build needs
**Python ≥ 3.14.2**. uv's default interpreter can be older, and then the
install fails to resolve.

Known environmental failure: `test_identity.py::test_dhcp_keeps_a_hostname`
fails on a machine where `localhost` resolves to `::1` first (the owner's
Mac does), because `pytest-socket` allows only `127.0.0.1`. It fails identically
on 1.3.0 and 1.3.1. Any other failure is real.

Tests cannot show what the real projector answers. Any change to what counts
as success or failure for a command needs one live check per command family
(power, input, picture mode, numeric step) before it is called done.

## Hardware truths — do not "correct" from datasheets

- `const.py` comments record behavior **verified against the VW715ES itself**
  (e.g. `light_output_val` answers `err_cmd`; `lamp_control` is the lamp-era
  equivalent; Motionflow and 3D exist on this unit). Keep them authoritative.
- `protocol.py` docstrings record observed device behavior: the projector
  closes idle ADCP sessions after ~60s, and its ADCP daemon can wedge while
  SDCP/HTTP stay up (2026-08-09 incident — fix is toggling ADCP off/on in the
  projector settings; a lamp power cycle does not revive it).
- Observed 2026-10-06 (projector in standby): ADCP authentication is **off**
  (greeting is `NOKEY`), and a second concurrent TCP connection was accepted
  and greeted while another was open. Only the greetings were checked, not
  commands on two sessions at once, so do not build on concurrent sessions
  without testing them.
- Also observed 2026-10-06 in standby: `serialnum ?` → `"5100123"`,
  `mac_address ?` → `"94-db-56-7b-0d-9d"`, `modelname ?` → `"VPL-VW715ES"`;
  SDCP (TCP 53484) and the web UI (TCP 80) both accept connections. From 1.3.0
  the config entry is keyed by that serial number, and the ADCP lock-up Repair
  relies on those two ports answering while ADCP does not.
- Observed 2026-10-07, in production history: the projector acknowledges
  `power "on"` / `power "off"` **before** its `power_status ?` answer moves.
  It still said `standby` 10 ms after accepting power on, and still said `on`
  245 ms after accepting power off. `POWER_SETTLE` in `coordinator.py`
  exists for this. Do not reintroduce an immediate read-back after a power
  command; that is what 1.3.0 did, and it reversed its own state.
- Also observed 2026-10-07 (one occurrence): `power "on"` sent during
  `cooling2` was answered `ok` and dropped. 1.3.1 still sends it, because
  production theater scripts call `media_player.turn_on` with no
  `continue_on_error` and rely on their own retry. It shows the true cooling
  phase and logs a warning instead. Raising an error here would make those
  scripts abort.

## Git rules

- Work lands on `main`. `origin` is the `jcolellajr` fork; **do not push to
  either remote without explicit instruction.**
- Stage explicit paths only; never bulk-stage.
