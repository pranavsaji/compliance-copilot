import os, json, time
from typing import List, Dict, Any
from app.config import settings

class EvidenceBundler:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def bundle(self, topic: str, items: List[Dict[str, Any]]) -> str:
        ts = int(time.time())
        path = os.path.join(self.root, f"{topic.replace(' ','_')}_{ts}.json")
        with open(path, "w") as f:
            json.dump({"topic": topic, "items": items}, f, indent=2)
        return path
