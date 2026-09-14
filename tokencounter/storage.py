"""Persistenza dati: due serie di valori (percentuale e $), giorno di reset
mensile, tipo di grafico, modalita' attiva e plafond in $."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DATA_DIR = Path.home() / ".config" / "tokencounter"
DATA_FILE = DATA_DIR / "data.json"

DEFAULT_RESET_DAY = 1
DEFAULT_PLAFOND = 500.0


@dataclass
class Entry:
    ts: str  # ISO 8601
    value: float

    @property
    def datetime(self) -> datetime:
        return datetime.fromisoformat(self.ts)


@dataclass
class Store:
    reset_day: int = DEFAULT_RESET_DAY
    chart_type: str = "line"  # "line" oppure "bar"
    mode: str = "percent"  # "percent" oppure "dollar"
    plafond: float = DEFAULT_PLAFOND
    entries_percent: list[Entry] = field(default_factory=list)
    entries_dollar: list[Entry] = field(default_factory=list)

    @property
    def entries(self) -> list[Entry]:
        """Serie attiva in base alla modalita' corrente."""
        return self.entries_dollar if self.mode == "dollar" else self.entries_percent

    def target(self) -> float:
        """Valore che rappresenta il 'pieno' nella modalita' corrente: 100 per
        la percentuale, il plafond impostato per i $."""
        return 100.0 if self.mode == "percent" else self.plafond

    @classmethod
    def load(cls) -> "Store":
        if not DATA_FILE.exists():
            return cls()
        raw = json.loads(DATA_FILE.read_text())
        if "entries_percent" in raw:
            entries_percent = [Entry(**e) for e in raw.get("entries_percent", [])]
        else:
            # formato precedente: un'unica serie, era sempre la percentuale.
            entries_percent = [Entry(**e) for e in raw.get("entries", [])]
        entries_dollar = [Entry(**e) for e in raw.get("entries_dollar", [])]
        return cls(
            reset_day=raw.get("reset_day", DEFAULT_RESET_DAY),
            chart_type=raw.get("chart_type", "line"),
            mode=raw.get("mode", "percent"),
            plafond=raw.get("plafond", DEFAULT_PLAFOND),
            entries_percent=entries_percent,
            entries_dollar=entries_dollar,
        )

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "reset_day": self.reset_day,
            "chart_type": self.chart_type,
            "mode": self.mode,
            "plafond": self.plafond,
            "entries_percent": [{"ts": e.ts, "value": e.value} for e in self.entries_percent],
            "entries_dollar": [{"ts": e.ts, "value": e.value} for e in self.entries_dollar],
        }
        DATA_FILE.write_text(json.dumps(payload, indent=2))

    def add_entry(self, value: float) -> None:
        self.entries.append(Entry(ts=datetime.now().isoformat(timespec="seconds"), value=value))
        self.entries.sort(key=lambda e: e.ts)
        self.save()

    def clear_entries(self) -> None:
        """Azzera solo la serie della modalita' attiva."""
        self.entries.clear()
        self.save()

    def update_entry_value(self, index: int, value: float) -> None:
        """Modifica il valore di una voce (stessa data/ora) nella serie attiva."""
        self.entries[index].value = value
        self.save()

    def delete_entry(self, index: int) -> None:
        """Elimina una voce dalla serie attiva."""
        del self.entries[index]
        self.save()

    def set_reset_day(self, day: int) -> None:
        self.reset_day = day
        self.save()

    def toggle_chart_type(self) -> None:
        self.chart_type = "bar" if self.chart_type == "line" else "line"
        self.save()

    def toggle_mode(self) -> None:
        self.mode = "dollar" if self.mode == "percent" else "percent"
        self.save()

    def set_plafond(self, value: float) -> None:
        self.plafond = value
        self.save()


class DemoStore(Store):
    """Store usato dalla modalita' demo: vive solo in memoria, non tocca mai
    il file dei dati reali."""

    def save(self) -> None:
        pass
