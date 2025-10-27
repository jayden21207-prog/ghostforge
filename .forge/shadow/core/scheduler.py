
from pathlib import Path

class Scheduler:
    """Very small placeholder for job submission & sequencing."""
    def __init__(self, root: Path):
        self.root = root
        self.queue = []

    def submit(self, task):
        self.queue.append(task)

    def next(self):
        if self.queue:
            return self.queue.pop(0)
        return None
