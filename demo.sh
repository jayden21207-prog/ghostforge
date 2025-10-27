
#!/usr/bin/env bash
set -e

echo "== Agents =="
python3 ghostai.py list || true
echo

# Ensure TVPlotter exists for variety
if [ ! -d "agents/TVPlotter" ]; then
  echo "Spawning TVPlotter..."
  python3 ghostctl.py spawn TVPlotter --kind tv
fi

echo "== Runs =="
python3 ghostai.py run --agent ArcadeFox --goal "design a boss fight loop"
python3 ghostai.py run --agent TVPlotter --goal "season 1 outline: 8 episodes"
python3 ghostai.py run --agent Cyberpunk --goal "world-building: mission beats" || true
echo

echo "== Exports =="
python3 ghostai.py export --agent ArcadeFox --goal "boss fight brief"
python3 ghostai.py export --agent TVPlotter --goal "pilot episode beat sheet"
python3 ghostai.py export --agent Cyberpunk --goal "factions + city districts" || true
echo

echo "== History (last 3) =="
python3 ghostai.py history --agent ArcadeFox --limit 3 || true
python3 ghostai.py history --agent TVPlotter --limit 3 || true
echo

echo "== Pack all agents =="
python3 pack-all.py --version 0.1
echo

echo "== Artifacts =="
echo "-- dist/"
ls -lt dist/ | head -n 20 || true
echo
echo "-- runs/"
ls -lt runs/ | head -n 20 || true
