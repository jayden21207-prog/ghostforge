# GhostAI Foundry (Private Alpha)
Spawn niche offline AI agents from your terminal. Policy-guarded and self-repairing (human-in-the-loop escalation).

## Why it’s different
- **Offline-first** demo agents (no API keys).
- **Policy-guarded** repairs (ack file required to escalate).
- **Extensible**: add agents as folders; runtime auto-loads them.
- **Exportable**: clean Markdown outputs.
- **Packable**: ship agents as ZIPs.

## Quickstart
```bash
python3 ghostai.py list
python3 ghostai.py run --agent ArcadeFox --goal "design a boss fight loop"
python3 ghostai.py export --agent ArcadeFox --goal "boss fight brief"
python3 ghostai.py history --agent ArcadeFox --limit 5
python3 ghostctl.py spawn TVPlotter --kind tv
python3 pack-all.py --version 0.1
