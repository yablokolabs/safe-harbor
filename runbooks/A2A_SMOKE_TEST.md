# Runbook: A2A Smoke Test (Levels 1-6)

The Manager and Specialist communicate over **authenticated private-LAN
A2A**: explicit bind address, bearer authentication, per-peer credentials,
trusted-peer allow-list, firewall boundary, audit trail, approved
capabilities. No public listener, no port forwarding, no unrestricted
remote administration.

A2A is **not** considered working merely because Agent Card discovery
succeeds — the meaningful delegated capability must work.

## Running the harness

On the manager:

```bash
safeharbor a2a-test                 # all levels, all configured peers
safeharbor a2a-test --peer specialist-node
```

On the specialist (for Level 4 reverse direction):

```bash
safeharbor a2a-test --reverse --peer manager-node
```

Configuration: `/etc/safe-harbor/a2a/peers.json`
(template: `config/a2a/peers.example.json`). Tokens live in environment
variables (`token_env`), never in the file.

## The six levels

| Level | What is tested | Passes when |
|-------|----------------|-------------|
| L1 Network | TCP connect manager→specialist | socket connects |
| L2 Protocol | `GET /.well-known/agent-card.json` + auth | 200 JSON Agent Card; bearer auth accepted |
| L3 Manager→Specialist | JSON-RPC `message/send` task | task accepted with taskId |
| L4 Specialist→Manager | JSON-RPC `message/send` task (reverse) | task accepted with taskId |
| L5 Bounded capability | ONE approved Specialist-local capability | task for the approved capability accepted |
| L6 Audit | expected exchanges appear in the audit log | task_ids from L3/L5 found in `a2a_audit.jsonl` |

**L1 alone is a FAIL.** The harness reports it explicitly: "L1 network
success alone is NOT a pass."

## Prerequisite configuration on Hermes

(Verified from the pinned Hermes source: `plugins/platforms/a2a/`.)

| Setting | Mechanism |
|---------|-----------|
| Explicit bind | `A2A_HOST` (refuses non-loopback unless tokens are set) |
| Shared auth | `A2A_BEARER_TOKEN` |
| Per-peer credentials | `A2A_PEER_TOKENS=name:token,name2:token2` |
| Allow-list | `A2A_TRUSTED_PEERS` (or `config.yaml` `a2a.trusted_peers`) |
| Advertised URL | `A2A_PUBLIC_URL` |
| Audit | `$HERMES_HOME/a2a_audit.jsonl` (JSONL: ts, direction, peer, task_id, summary) |

The Specialist side (initial implementation: **Windows**) runs the same
Hermes A2A plugin via the official Windows install
(`%LOCALAPPDATA%\hermes`). Exact Windows enablement steps:
`REQUIRES_WINDOWS_INTEGRATION_TEST`.

## Bounded local capability (L5)

The only capability the Specialist may be asked to run locally is one of
`approved_capabilities` in `peers.json` — for example `get-local-time`.
The Specialist executes it locally (its own tools, no shell access from
the manager) and returns the result through A2A.

If stock Hermes cannot safely express "one approved local capability"
without weakening the boundary, the smallest narrowly scoped solution is
preferred over a wider permission model. That is an integration-lab
decision: `REQUIRES_A2A_INTEGRATION_TEST`.

## Post-restart repetition

Repeat the full test after each of:

1. Hermes process restart
2. Specialist restart
3. Manager restart
4. Specialist machine reboot
5. Manager machine reboot
6. both machines reboot

Each repetition is a separate entry in the operator log. Status after each
step belongs in the README status matrix — never pre-filled.

## Honest status

- Levels 1-2 can be exercised locally against any A2A peer on the LAN.
- Levels 3-6 need the real Hermes pair:
  `REQUIRES_A2A_INTEGRATION_TEST` (manager Ubuntu + specialist Windows).
- The harness, configuration schema, and this runbook are executable and
  locally tested; the peer endpoints are not.