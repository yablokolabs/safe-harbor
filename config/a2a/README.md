# A2A configuration

`peers.json` (installed to `/etc/safe-harbor/a2a/peers.json`) describes the
A2A peers Safe Harbor may test and talk to. It is **not** a secrets file:
each peer's bearer token is referenced by environment-variable name
(`token_env`) and must exist in the environment of the side that calls the
peer.

Example addresses use documentation placeholders (`192.0.2.0/24`,
`198.51.100.0/24`, `203.0.113.0/24` are reserved for documentation).
Replace them with your LAN addresses on the target.

## Rules enforced by Safe Harbor

- `safeharbor a2a-test` never treats TCP reachability as a pass; the
  meaningful delegated capability (Levels 3-5) must work.
- `approved_capabilities` is the allow-list for the Level 5 bounded local
  capability. Nothing outside it may be requested.
- `safeharbor doctor` flags any peer configured to bind a wildcard address
  (`0.0.0.0` / `::`) as a security failure.
- No public listener, no port forwarding, no unrestricted remote shell.

## Firewall

The Gen1 boundary restricts A2A to the private LAN. With `ufw`:

```bash
sudo ufw allow from <MANAGER_IP> to any port 9900 proto tcp comment 'safeharbor a2a'
sudo ufw allow from <SPECIALIST_IP> to any port 9900 proto tcp comment 'safeharbor a2a'
sudo ufw deny 9900/tcp   # block the rest (after the explicit allows)
```

Restate (8080/9070) and jñāpakaṁ (8889) are loopback-only on the manager;
block them on the LAN interface:

```bash
sudo ufw deny 8080/tcp
sudo ufw deny 9070/tcp
sudo ufw deny 8889/tcp
```

(Exact rules are documented in runbooks/DEPLOYMENT.md.)