"""TokenCounter: TUI colorata per tracciare il consumo di token, in % o in $."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import erf, sqrt

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from textual_plotext import PlotextPlot

from . import __version__
from .cycle import (
    CONFIDENCE_Z,
    HALF_LIFE_DAYS,
    WINDOW_DAYS,
    current_cycle,
    max_value_to_stay_on_pace,
    projected_exhaustion,
    trend_confidence_interval,
    trend_regression,
)

from .storage import DemoStore, Entry, Store

SECONDS_PER_DAY = 86400.0
CONFIDENCE_PERCENT = round(erf(CONFIDENCE_Z / sqrt(2)) * 100)

_NUMBER_CHARS = set("0123456789.+-eE_")

DEMO_INTERVAL_SECONDS = 5.0

# (giorno del ciclo demo, valore %): parte piano, poi accelera abbastanza da
# mandare la retta di tendenza fuori budget, poi rallenta/scende.
DEMO_POINTS = [
    (0, 3),
    (2, 6),
    (4, 9),
    (6, 12),
    (8, 17),
    (10, 30),
    (12, 48),
    (14, 68),
    (16, 90),
    (18, 97),
    (20, 90),
    (23, 82),
    (26, 80),
    (28, 79),
]


class ValueInput(Input):
    """Input numerico che non 'ruba' ai binding globali (es. q, t) le lettere
    che non potrebbe comunque accettare come valore."""

    def check_consume_key(self, key: str, character: str | None) -> bool:
        return character is not None and character in _NUMBER_CHARS


class ResetDayScreen(ModalScreen[int | None]):
    """Modale per impostare il giorno del mese in cui i token si azzerano."""

    DEFAULT_CSS = """
    ResetDayScreen {
        align: center middle;
    }
    #dialog {
        width: 46;
        height: auto;
        padding: 1 2;
        border: thick $warning;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    """

    def __init__(self, current_day: int) -> None:
        super().__init__()
        self._current_day = current_day

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Giorno del mese di reset (attuale: {self._current_day})")
            yield Input(placeholder="1-31", type="integer", id="day_input")

    def on_mount(self) -> None:
        self.query_one("#day_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if raw.isdigit() and 1 <= int(raw) <= 31:
            self.dismiss(int(raw))
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class PlafondScreen(ModalScreen[float | None]):
    """Modale per impostare il plafond in $ che si resetta col ciclo."""

    DEFAULT_CSS = """
    PlafondScreen {
        align: center middle;
    }
    #dialog {
        width: 46;
        height: auto;
        padding: 1 2;
        border: thick $warning;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    """

    def __init__(self, current_plafond: float) -> None:
        super().__init__()
        self._current_plafond = current_plafond

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Plafond in $ per ciclo (attuale: {self._current_plafond:.2f})")
            yield Input(placeholder="es. 500", type="number", id="plafond_input")

    def on_mount(self) -> None:
        self.query_one("#plafond_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        try:
            value = float(raw)
        except ValueError:
            self.dismiss(None)
            return
        self.dismiss(value if value > 0 else None)

    def key_escape(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Modale di conferma per azzerare i dati."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        border: thick $error;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    #buttons {
        align: center middle;
        height: auto;
    }
    #buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, question: str, confirm_label: str = "Si, azzera") -> None:
        super().__init__()
        self._question = question
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._question)
            with Horizontal(id="buttons"):
                yield Button(self._confirm_label, id="yes", variant="error")
                yield Button("Annulla", id="no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def key_escape(self) -> None:
        self.dismiss(False)


class EditValueScreen(ModalScreen[float | None]):
    """Modale per modificare il valore di una voce gia' inserita."""

    DEFAULT_CSS = """
    EditValueScreen {
        align: center middle;
    }
    #dialog {
        width: 46;
        height: auto;
        padding: 1 2;
        border: thick $warning;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    """

    def __init__(self, current_value: float, unit: str) -> None:
        super().__init__()
        self._current_value = current_value
        self._unit = unit

    def compose(self) -> ComposeResult:
        prefill = (
            f"{self._current_value:.2f}" if self._unit == "$" else f"{self._current_value:.1f}"
        )
        with Vertical(id="dialog"):
            yield Label(f"Nuovo valore ({self._unit})")
            yield Input(value=prefill, type="number", id="edit_input")

    def on_mount(self) -> None:
        input_widget = self.query_one("#edit_input", Input)
        input_widget.focus()
        input_widget.action_select_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        try:
            value = float(raw)
        except ValueError:
            self.dismiss(None)
            return
        self.dismiss(max(0.0, value))

    def key_escape(self) -> None:
        self.dismiss(None)


class InfoScreen(ModalScreen[None]):
    """Modale informativa su come vengono calcolati tendenza e intervallo."""

    DEFAULT_CSS = """
    InfoScreen {
        align: center middle;
    }
    #dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(
                "[b]Come viene calcolata la tendenza (linea gialla)[/b]\n\n"
                "Regressione lineare pesata sui valori inseriti, non una media "
                f"grezza di tutto lo storico:\n\n"
                f"- [b]finestra[/b]: usa solo gli ultimi {WINDOW_DAYS:.0f} giorni\n"
                f"- [b]recenza[/b]: i punti piu' recenti pesano di piu', il peso "
                f"si dimezza ogni {HALF_LIFE_DAYS:.0f} giorni\n"
                "- [b]outlier[/b]: un valore anomalo isolato (es. inserito per "
                "errore) viene automaticamente scartato dal calcolo\n\n"
                "[b]Intervallo di confidenza (linea magenta a fine ciclo)[/b]\n\n"
                f"Mostra un range (~{CONFIDENCE_PERCENT}% di probabilita') attorno al "
                "valore finale previsto, calcolato dalla dispersione dei punti "
                "intorno alla retta di tendenza: piu' i valori inseriti sono "
                "irregolari, piu' il range e' ampio. Con pochi dati, o dati "
                "troppo allineati, l'intervallo non viene mostrato.\n\n"
                "La stessa tendenza alimenta anche l'avviso di rischio "
                "esaurimento e il \"max oggi senza sforare\" in barra di stato.\n\n"
                "Esc per chiudere."
            )

    def key_escape(self) -> None:
        self.dismiss(None)


class EntriesScreen(ModalScreen[None]):
    """Modale con la lista dei valori inseriti nella modalita' corrente:
    permette di modificarli o eliminarli."""

    DEFAULT_CSS = """
    EntriesScreen {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: 24;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #dialog Label {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("e", "edit_selected", "Modifica"),
        Binding("d", "delete_selected", "Elimina"),
    ]

    def __init__(self, store: Store, unit: str) -> None:
        super().__init__()
        self._store = store
        self._unit = unit

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Valori inseriti - e modifica, d elimina, Esc chiude")
            yield DataTable(id="table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Data/ora", "Valore")
        self._reload_table()
        table.focus()

    def _reload_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for entry in self._store.entries:
            value_text = (
                f"{entry.value:.2f}{self._unit}"
                if self._unit == "$"
                else f"{entry.value:.1f}{self._unit}"
            )
            table.add_row(entry.datetime.strftime("%d/%m/%Y %H:%M"), value_text)

    @work
    async def action_edit_selected(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        index = table.cursor_row
        current = self._store.entries[index].value
        result = await self.app.push_screen_wait(EditValueScreen(current, self._unit))
        if result is not None:
            self._store.update_entry_value(index, result)
            self._reload_table()

    @work
    async def action_delete_selected(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        index = table.cursor_row
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen("Eliminare questo valore?", confirm_label="Si, elimina")
        )
        if confirmed:
            self._store.delete_entry(index)
            self._reload_table()

    def key_escape(self) -> None:
        self.dismiss(None)


class TokenCounterApp(App):
    """App principale: prompt per inserire il consumo (% o $) + grafico."""

    TITLE = "TokenCounter"
    SUB_TITLE = f"v{__version__}"

    CSS = """
    Screen {
        background: $background;
    }
    #status {
        height: auto;
        padding: 0 1;
        background: $panel;
        border-bottom: solid $primary;
    }
    PlotextPlot {
        border: round $primary;
    }
    #value_input {
        dock: bottom;
        border: heavy $accent;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Esci", priority=True),
        Binding("ctrl+r", "set_reset_day", "Giorno reset", priority=True),
        Binding("ctrl+x", "clear_data", "Azzera dati", priority=True),
        Binding("t", "toggle_chart", "Linea/barre", priority=True),
        Binding("ctrl+d", "toggle_demo", "Demo", priority=True),
        Binding("ctrl+m", "toggle_mode", "Modalita' %/$", priority=True),
        Binding("ctrl+b", "set_plafond", "Plafond $", priority=True),
        Binding("ctrl+l", "show_entries", "Lista/modifica", priority=True),
        Binding("question_mark", "show_info", "Info", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.store = Store.load()
        self._real_store = self.store
        self._demo_store: DemoStore | None = None
        self._demo_index = 0
        self._demo_timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="status")
        yield PlotextPlot(id="plot")
        yield ValueInput(
            placeholder="",
            type="number",
            id="value_input",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#value_input", Input).focus()
        self.redraw()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "value_input":
            return
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return
        try:
            value = float(raw)
        except ValueError:
            return
        if self.store.mode == "dollar":
            value = max(0.0, value)
        else:
            value = max(0.0, min(100.0, value))
        self.store.add_entry(value)
        self.redraw()

    @work
    async def action_set_reset_day(self) -> None:
        result = await self.push_screen_wait(ResetDayScreen(self.store.reset_day))
        if result is not None:
            self.store.set_reset_day(result)
            self.redraw()
        self.query_one("#value_input", Input).focus()

    @work
    async def action_show_info(self) -> None:
        await self.push_screen_wait(InfoScreen())
        self.query_one("#value_input", Input).focus()

    def action_toggle_chart(self) -> None:
        self.store.toggle_chart_type()
        self.redraw()

    def action_toggle_mode(self) -> None:
        self.store.toggle_mode()
        self.redraw()

    @work
    async def action_set_plafond(self) -> None:
        result = await self.push_screen_wait(PlafondScreen(self.store.plafond))
        if result is not None:
            self.store.set_plafond(result)
            self.redraw()
        self.query_one("#value_input", Input).focus()

    @work
    async def action_show_entries(self) -> None:
        unit = "$" if self.store.mode == "dollar" else "%"
        await self.push_screen_wait(EntriesScreen(self.store, unit))
        self.redraw()
        self.query_one("#value_input", Input).focus()

    def action_toggle_demo(self) -> None:
        if self._demo_store is None:
            self._demo_store = DemoStore(
                reset_day=datetime.now().day,
                mode=self._real_store.mode,
                plafond=self._real_store.plafond,
            )
            self.store = self._demo_store
            self._demo_index = 0
            self._demo_timer = self.set_interval(DEMO_INTERVAL_SECONDS, self._demo_step)
            self._demo_step()
        else:
            if self._demo_timer is not None:
                self._demo_timer.stop()
                self._demo_timer = None
            self._demo_store = None
            self.store = self._real_store
            self.redraw()

    def _demo_step(self) -> None:
        if self._demo_store is None or self.store is not self._demo_store:
            return
        if self._demo_index >= len(DEMO_POINTS):
            if self._demo_timer is not None:
                self._demo_timer.stop()
                self._demo_timer = None
            return
        cycle = current_cycle(self._demo_store.reset_day)
        offset_days, raw_value = DEMO_POINTS[self._demo_index]
        value = raw_value * (self._demo_store.target() / 100.0)
        self._demo_index += 1
        ts = datetime.combine(cycle.start, datetime.min.time()) + timedelta(
            days=offset_days, hours=10
        )
        self._demo_store.entries.append(Entry(ts=ts.isoformat(timespec="seconds"), value=value))
        self._demo_store.entries.sort(key=lambda e: e.ts)
        self.redraw()

    @work
    async def action_clear_data(self) -> None:
        confirmed = await self.push_screen_wait(
            ConfirmScreen("Azzerare tutti i valori inseriti? L'operazione non e' reversibile.")
        )
        if confirmed:
            self.store.clear_entries()
            self.redraw()
        self.query_one("#value_input", Input).focus()

    def redraw(self) -> None:
        self._draw_plot()
        self._update_status()

    def _entries_in_cycle(self, start_dt: datetime, end_dt: datetime) -> list[Entry]:
        """Voci della modalita' attiva che ricadono nel ciclo [start_dt, end_dt).
        Lo storico completo resta salvato: e' solo il grafico/le statistiche a
        limitarsi al ciclo corrente, cosi' cambiare il giorno di reset o lasciar
        passare un reset non mescola dati di cicli diversi."""
        return [e for e in self.store.entries if start_dt <= e.datetime < end_dt]

    def _draw_plot(self) -> None:
        plot_widget = self.query_one("#plot", PlotextPlot)
        plt = plot_widget.plt
        plt.clf()

        cycle = current_cycle(self.store.reset_day)
        start_dt = datetime.combine(cycle.start, datetime.min.time())
        end_dt = datetime.combine(cycle.end, datetime.min.time())

        def days_since_start(dt: datetime) -> float:
            return (dt - start_dt).total_seconds() / 86400.0

        cycle_len = days_since_start(end_dt)
        target = self.store.target()
        unit = "$" if self.store.mode == "dollar" else "%"

        plt.plot(
            [0.0, cycle_len],
            [0, target],
            marker="braille",
            color="orange",
            label="budget ideale",
        )

        entries = self._entries_in_cycle(start_dt, end_dt)
        if entries:
            xs = [days_since_start(e.datetime) for e in entries]
            ys = [e.value for e in entries]
            now_days = days_since_start(datetime.now())
            reg = trend_regression(xs, ys, now_days)

            if reg is not None:
                slope, intercept = reg
                t0, t1 = xs[0], cycle_len
                trend_y = [slope * t0 + intercept, slope * t1 + intercept]
                plt.plot([t0, t1], trend_y, marker="braille", color="yellow", label="tendenza")

            ci = trend_confidence_interval(xs, ys, now_days, cycle_len)
            if ci is not None:
                _predicted, lower, upper = ci
                plt.plot(
                    [cycle_len, cycle_len],
                    [lower, upper],
                    marker="braille",
                    color="magenta",
                    label="intervallo",
                )

            if self.store.chart_type == "bar":
                plt.bar(xs, ys, color="cyan+", width=0.6, reset_ticks=False, label="consumo")
            else:
                plt.plot(xs, ys, marker="braille", color="cyan", label="consumo")
                plt.scatter(xs, ys, marker="dot", color="cyan+")

        tick_count = 6
        tick_x = [cycle_len * i / (tick_count - 1) for i in range(tick_count)]
        tick_labels = [(start_dt + timedelta(days=t)).strftime("%d/%m") for t in tick_x]
        plt.xticks(tick_x, tick_labels)

        plt.title(f"Consumo token ({unit})")
        plt.xlabel("data")
        plt.ylabel(f"{unit} consumati")
        plt.ylim(0, target * 1.1)
        plot_widget.refresh()

    def _update_status(self) -> None:
        cycle = current_cycle(self.store.reset_day)
        start_dt = datetime.combine(cycle.start, datetime.min.time())
        end_dt = datetime.combine(cycle.end, datetime.min.time())
        today = datetime.now().date()
        days_left = cycle.days_left(today)
        entries = self._entries_in_cycle(start_dt, end_dt)
        target = self.store.target()
        unit = "$" if self.store.mode == "dollar" else "%"

        def fmt(value: float) -> str:
            return f"{value:.2f}{unit}" if unit == "$" else f"{value:.1f}{unit}"

        if days_left > 7:
            days_color = "green"
        elif days_left > 2:
            days_color = "yellow"
        else:
            days_color = "red"

        last_value = fmt(entries[-1].value) if entries else "n/d"

        cycle_end_ts = end_dt.timestamp()

        warning = ""
        max_today_text = "n/d"
        if entries:
            xs_num = [e.datetime.timestamp() for e in entries]
            ys = [e.value for e in entries]

            now_ts = datetime.now().timestamp()

            if len(entries) >= 2:
                reg = trend_regression(xs_num, ys, now_ts, day_length=SECONDS_PER_DAY)
                if reg is not None:
                    slope, intercept = reg
                    exhaustion_ts = projected_exhaustion(slope, intercept, target=target)
                    if exhaustion_ts is not None and exhaustion_ts < cycle_end_ts:
                        exhaustion_date = datetime.fromtimestamp(exhaustion_ts)
                        warning = (
                            f"  [b red]! rischio esaurimento entro il "
                            f"{exhaustion_date.strftime('%d/%m %H:%M')}[/]"
                        )

            max_today = max_value_to_stay_on_pace(
                xs_num, ys, now_ts, cycle_end_ts, target=target, day_length=SECONDS_PER_DAY
            )
            if max_today is None:
                max_today_text = "n/d"
            elif max_today <= 0:
                max_today_text = f"[b red]0{unit} (gia' oltre la tendenza)[/]"
            elif max_today >= target:
                max_today_text = f"[b green]{fmt(target)}+ (ampio margine)[/]"
            else:
                max_today_text = fmt(max_today)

        status = self.query_one("#status", Static)
        chart_label = "barre" if self.store.chart_type == "bar" else "linea"
        mode_label = "$" if self.store.mode == "dollar" else "%"
        plafond_info = f"  [b]plafond:[/b] {self.store.plafond:.2f}$" if self.store.mode == "dollar" else ""

        demo_tag = ""
        if self.store is self._demo_store:
            progress = f"{min(self._demo_index, len(DEMO_POINTS))}/{len(DEMO_POINTS)}"
            demo_tag = f"[b black on yellow] DEMO {progress} [/]  "

        status.update(
            f"{demo_tag}"
            f"[b]modalita':[/b] {mode_label}{plafond_info}  "
            f"[b]reset:[/b] giorno {self.store.reset_day} del mese  "
            f"[b]ciclo:[/b] {cycle.start.strftime('%d/%m/%Y')} -> {cycle.end.strftime('%d/%m/%Y')}  "
            f"[b {days_color}]giorni rimanenti: {days_left}[/]  "
            f"[b]ultimo valore:[/b] {last_value}  "
            f"[b]max oggi senza sforare:[/b] {max_today_text}  "
            f"[b]grafico:[/b] {chart_label} (t per cambiare)"
            f"{warning}"
        )

        placeholder = (
            "Inserisci $ consumati (es. 42.50) e premi Invio..."
            if self.store.mode == "dollar"
            else "Inserisci % di token consumati (0-100) e premi Invio..."
        )
        self.query_one("#value_input", Input).placeholder = placeholder


def main() -> None:
    TokenCounterApp().run()


if __name__ == "__main__":
    main()
