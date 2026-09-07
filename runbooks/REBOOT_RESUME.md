# Runbook: Restart / Reboot / Resume

Gen1 must survive: process restarts, service restarts, full machine
reboots, and (via REPLACEMENT_MACHINE.md) machine replacement.

## 1. Service restart

```bash
sudo systemctl restart restate
sudo systemctl restart jnaapakam
sudo systemctl restart hermes-manager
journalctl -u restate -n 30
journalctl -u jnaapakam -n 30
```

After each restart, the meaningful check is continuity, not process
existence:

```bash
safeharbor doctor
```

## 2. Full machine reboot

```bash
sudo reboot
```

On boot, systemd brings up `restate` and `jnaapakam` (enabled units).
Then:

```bash
safeharbor status          # fast: services + endpoint probes + backup
safeharbor doctor          # deep: state, config, generation, backup integrity
safeharbor a2a-test        # A2A levels 1-6 (see A2A_SMOKE_TEST.md)
```

### What reboot/resume must prove (acceptance criteria)

| Scenario | Criterion |
|----------|-----------|
| Hermes process restart | A2A L3 manager→specialist task still works; audit log continues |
| Specialist restart | A2A L5 bounded capability still works |
| Manager restart | jñāpakaṁ identity (`/agent`) unchanged; Restate durable workflows resume |
| Specialist reboot | Manager reconnects; no re-pairing beyond configured auth |
| Both reboot | A2A L1-L6 all pass again; resident identity identical |

All of these except the purely local manager checks are
`REQUIRES_A2A_INTEGRATION_TEST` until executed on the real pair — nothing
here claims they have passed.

## 3. Durable execution resume (Restate)

Restate replays journals on startup (its design). Safe Harbor's backup
strategy is quiesced copy; after a crash (not a clean stop), do NOT back up
until the node has fully recovered and `GET :9070/health` returns 200.
`restatectl`-driven tooling is `REQUIRES_INTEGRATION_TEST` (see
`integrations/restate.py`).

## 4. Continuity after restart (jñāpakaṁ)

jñāpakaṁ owns continuity semantics. After any restart:

```bash
curl -s http://127.0.0.1:8889/agent            # identity + current generation
curl -s "http://127.0.0.1:8889/search?q=test"  # memory corpus present
```

The `urn:jnaapakam:agent:*` identity is minted once and stable — it does
not change across restarts, reboots, or machine replacement.