"""Check the listening socket without connecting to the single-client endpoint."""
from pathlib import Path

rows = Path('/proc/net/tcp').read_text().splitlines()[1:]
listening = any(row.split()[1].endswith(':2710') and row.split()[3] == '0A'
                for row in rows)
raise SystemExit(0 if listening else 1)
