"""Persistenza dati: un'unica serie di valori (ciascuno nella propria unita',
% oppure $), giorno di reset mensile, tipo di grafico, unita' di
visualizzazione attiva e plafond in $."""

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
    unit: str = "percent"  # unita' nativa in cui e' stato inserito: "percent" oppure "dollar"
    plafond: float = DEFAULT_PLAFOND
    """Plafond in $ vigente al momento dell'inserimento: congelato qui cosi'
    che cambiare il plafond in seguito (Ctrl+B) non alteri retroattivamente
    come questo valore si converte nell'altra unita'."""

    @property
    def datetime(self) -> datetime:
        return datetime.fromisoformat(self.ts)

    def value_in(self, unit: str) -> float:
        """Il valore convertito nell'unita' richiesta, usando il plafond
        congelato al momento dell'inserimento. Nessuna conversione (quindi
        nessun arrotondamento) se l'unita' richiesta e' gia' quella nativa."""
        if unit == self.unit:
            return self.value
        if self.unit == "dollar":
            return self.value / self.plafond * 100.0
        return self.value / 100.0 * self.plafond


@dataclass
class Store:
    reset_day: int = DEFAULT_RESET_DAY
    chart_type: str = "line"  # "line" oppure "bar"
    mode: str = "percent"  # unita' di visualizzazione/inserimento corrente: "percent" oppure "dollar"
    plafond: float = DEFAULT_PLAFOND
    show_plafond_line: bool = True
    show_gap_line: bool = True
    show_gap_history: bool = False
    entries: list[Entry] = field(default_factory=list)

    def target(self) -> float:
        """Valore che rappresenta il 'pieno' nella modalita' corrente: 100 per
        la percentuale, il plafond impostato per i $."""
        return 100.0 if self.mode == "percent" else self.plafond

    @classmethod
    def load(cls) -> "Store":
        if not DATA_FILE.exists():
            return cls()
        raw = json.loads(DATA_FILE.read_text())
        plafond = raw.get("plafond", DEFAULT_PLAFOND)

        if "history" in raw:
            entries = [
                Entry(
                    ts=e["ts"],
                    value=e["value"],
                    unit=e.get("unit", "percent"),
                    plafond=e.get("plafond", plafond),
                )
                for e in raw["history"]
            ]
        else:
            # Formati precedenti: serie % e $ separate (o, ancora prima, una
            # sola serie "entries" sempre in %). Si fondono in un'unica
            # lista, usando il plafond attuale come congelato per tutto lo
            # storico pregresso: non c'e' modo di sapere quale fosse in
            # passato.
            entries = [
                Entry(ts=e["ts"], value=e["value"], unit="percent", plafond=plafond)
                for e in raw.get("entries_percent", raw.get("entries", []))
            ] + [
                Entry(ts=e["ts"], value=e["value"], unit="dollar", plafond=plafond)
                for e in raw.get("entries_dollar", [])
            ]
            entries.sort(key=lambda e: e.ts)

        return cls(
            reset_day=raw.get("reset_day", DEFAULT_RESET_DAY),
            chart_type=raw.get("chart_type", "line"),
            mode=raw.get("mode", "percent"),
            plafond=plafond,
            show_plafond_line=raw.get("show_plafond_line", True),
            show_gap_line=raw.get("show_gap_line", True),
            show_gap_history=raw.get("show_gap_history", False),
            entries=entries,
        )

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "reset_day": self.reset_day,
            "chart_type": self.chart_type,
            "mode": self.mode,
            "plafond": self.plafond,
            "show_plafond_line": self.show_plafond_line,
            "show_gap_line": self.show_gap_line,
            "show_gap_history": self.show_gap_history,
            "history": [
                {"ts": e.ts, "value": e.value, "unit": e.unit, "plafond": e.plafond}
                for e in self.entries
            ],
        }
        DATA_FILE.write_text(json.dumps(payload, indent=2))

    def add_entry(self, value: float) -> None:
        self.entries.append(
            Entry(
                ts=datetime.now().isoformat(timespec="seconds"),
                value=value,
                unit=self.mode,
                plafond=self.plafond,
            )
        )
        self.entries.sort(key=lambda e: e.ts)
        self.save()

    def clear_entries(self) -> None:
        self.entries.clear()
        self.save()

    def update_entry_value(self, index: int, value: float) -> None:
        """Sovrascrive una voce con un nuovo valore, inserito nell'unita' di
        visualizzazione corrente: da questo momento la voce 'nasce' in
        quell'unita' (perde il legame con l'unita'/plafond originali)."""
        self.entries[index] = Entry(
            ts=self.entries[index].ts,
            value=value,
            unit=self.mode,
            plafond=self.plafond,
        )
        self.save()

    def delete_entry(self, index: int) -> None:
        del self.entries[index]
        self.save()

    def set_reset_day(self, day: int) -> None:
        self.reset_day = day
        self.save()

    def toggle_chart_type(self) -> None:
        self.chart_type = "bar" if self.chart_type == "line" else "line"
        self.save()

    def toggle_plafond_line(self) -> None:
        self.show_plafond_line = not self.show_plafond_line
        self.save()

    def toggle_gap_line(self) -> None:
        self.show_gap_line = not self.show_gap_line
        self.save()

    def toggle_gap_history(self) -> None:
        self.show_gap_history = not self.show_gap_history
        self.save()

    def toggle_mode(self) -> None:
        """Cambia solo l'unita' di visualizzazione/inserimento: i valori gia'
        inseriti restano quelli che erano, mostrati convertiti."""
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
