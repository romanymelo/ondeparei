from dataclasses import dataclass


@dataclass
class FakeClock:
    t: float = 0.0

    def __call__(self) -> float:
        return self.t
