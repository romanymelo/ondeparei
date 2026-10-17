import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Relê o arquivo a cada chamada: cada teste recebe uma cópia nova, livre para alterar."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@dataclass
class FakeClock:
    t: float = 0.0

    def __call__(self) -> float:
        return self.t
