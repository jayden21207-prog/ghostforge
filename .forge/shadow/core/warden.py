
import re
from dataclasses import dataclass
from typing import List

@dataclass
class Rule:
    id: str
    pattern: str
    action: str = "block"

class Warden:
    def __init__(self, rules: List[Rule]):
        self.rules = rules

    def scan_text(self, text: str):
        hits = []
        for r in self.rules:
            if re.search(r.pattern, text):
                hits.append(r.id)
        return hits
