from pathlib import Path
from datetime import datetime

def write_bundle(base_dir: str, topic: str, content: str) -> str:
    outdir = Path(base_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe = "".join(c for c in topic if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_")
    fname = f"{ts}_{safe or 'bundle'}.txt"
    path = outdir / fname
    path.write_text(content, encoding="utf-8")
    return str(path)
