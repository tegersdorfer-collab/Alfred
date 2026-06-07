"""
Kurzzeitgedächtnis (KZG) – aktiver Gesprächskontext.
In-Memory, geht beim Neustart verloren (gewollt).
"""
from dataclasses import dataclass, field
from datetime import datetime
from llm.base import Message
import config


@dataclass
class Turn:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


class KZG:
    """
    Kurzzeitgedächtnis: Speichert den laufenden Gesprächsverlauf.
    Ältere Turns werden abgeschnitten wenn Limit erreicht.
    """

    def __init__(self, max_turns: int | None = None):
        self.max_turns = max_turns or config.KZG_MAX_TURNS
        self._turns: list[Turn] = []
        self._session_start = datetime.now()

    def add(self, role: str, content: str) -> None:
        self._turns.append(Turn(role=role, content=content))
        # Älteste Turns entfernen wenn über Limit
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def get_messages(self) -> list[Message]:
        return [Message(role=t.role, content=t.content) for t in self._turns]

    def recent_messages(self, max_tokens: int = 3000, min_turns: int = 4) -> list[Message]:
        """
        Jüngste Turns innerhalb eines Token-Budgets (4 Zeichen ≈ 1 Token).
        Passt sich an Nachrichtenlänge an statt hart auf N Turns zu schneiden.
        Ältere Fakten gehen nicht verloren – der Compressor destilliert sie ins LZG,
        von wo die Memory-Suche sie bei Bedarf zurückholt.
        """
        selected: list[Turn] = []
        budget = max_tokens
        for t in reversed(self._turns):
            cost = len(t.content) // 4 + 1
            if selected and budget - cost < 0 and len(selected) >= min_turns:
                break
            selected.append(t)
            budget -= cost
        selected.reverse()
        return [Message(role=t.role, content=t.content) for t in selected]

    def get_turns(self) -> list[Turn]:
        return list(self._turns)

    def clear(self) -> None:
        self._turns = []
        self._session_start = datetime.now()

    def is_empty(self) -> bool:
        return len(self._turns) == 0

    def token_estimate(self) -> int:
        """Grobe Schätzung der Token-Anzahl (4 Zeichen ≈ 1 Token)."""
        total_chars = sum(len(t.content) for t in self._turns)
        return total_chars // 4

    def last_user_message(self) -> str | None:
        for turn in reversed(self._turns):
            if turn.role == "user":
                return turn.content
        return None

    def summary_for_compression(self) -> str:
        """Gibt KZG-Inhalt für LZG-Komprimierung zurück."""
        lines = []
        for t in self._turns:
            prefix = "Timo" if t.role == "user" else "Jarvis"
            lines.append(f"{prefix}: {t.content}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._turns)

    def __repr__(self) -> str:
        return f"KZG({len(self._turns)} turns, ~{self.token_estimate()} tokens)"
