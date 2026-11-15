"""Interactive tour: highlights elements of the interface and explains them in a card next to them.
A step can first open a page ("before") or wait for a click by the user ("wait_page")."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from . import i18n, theme

CARD_W = 370
PAD = 5          # distance of the frame to the element
EDGE = 3         # frame thickness


@dataclass
class Step:
    title: str
    text: str
    target: Callable | None = None          # app -> widget, list of widgets or None (card in the middle)
    before: Callable | None = None          # app -> None, runs before showing
    wait_page: str = ""                     # continues as soon as the user opens this page
    hint: str = ""


# --------------------------------------------------------------------- Steps
def intro_steps() -> list[Step]:
    return [
        Step("Willkommen!",
             "Dieses Tool hat zwei Teile: eine Busfirma, die im Zeitraffer für dich Geld verdient, und einen "
             "Save-Editor für Truck und Bus. Ich zeige dir kurz das Wichtigste. Mit „Überspringen“ kannst du "
             "jederzeit abbrechen.",
             before=lambda a: a.show_page("overview")),
        Step("Sprache",
             "Hier wechselst du die Sprache. Nach dem Umschalten startet das Tool neu.",
             lambda a: a.lang_cell),
        Step("Dein Spielstand",
             "Wähle hier den Spielstand, mit dem du arbeiten willst, und klicke auf „Laden“. Das Tool findet "
             "deine ETS2-Spielstände selbst; mit „Datei wählen …“ geht es auch von Hand. Neue Spielstände "
             "werden automatisch erkannt.",
             lambda a: a.save_bar),
        Step("Dein Konto",
             "Oben stehen dein ETS2-Konto, deine XP und die Bus-XP aus dem geladenen Spielstand. Mit einer "
             "Firma zeigt das Konto auch Änderungen, die noch nicht im Spielstand stehen.",
             lambda a: a.stat_cells),
        Step("Busfirma gründen",
             "Mit 150.000 € auf deinem ETS2-Konto kannst du hier eine Firma gründen und ihr einen Namen geben. "
             "Erst danach erscheinen Garagen, Busse, Fahrer und die anderen Firmenseiten.",
             lambda a: a.overview.empty,
             before=lambda a: a.show_page("overview")),
        Step("Save-Editor",
             "Im Save-Editor änderst du Konto, XP, Skills und Aufträge deines Spielstands.",
             lambda a: a.nav_buttons["profile"],
             before=lambda a: a._toggle_editor(True),
             wait_page="profile",
             hint="Klicke jetzt auf „Profil“ (oder auf „Weiter“)."),
        Step("Profil",
             "Hier stellst du Kontostand und Erfahrungspunkte ein, darunter die Truck-Skills. Die Änderungen "
             "gelten erst, wenn du speicherst.",
             lambda a: a.field_widgets["money_account"].master,
             before=lambda a: a.show_page("profile")),
        Step("Speichern",
             "„Speichern (mit Backup)“ schreibt deine Änderungen in den Spielstand und legt vorher ein Backup "
             "an. Lade den Spielstand danach im Spiel über das Hauptmenü neu. Ein bereits laufendes Spiel "
             "überschreibt die Änderung sonst wieder.",
             lambda a: a.save_btn),
        Step("Los geht's",
             "Das war's. Sobald du 150.000 € auf dem Konto hast und eine Firma gründest, zeige ich dir das "
             "Firmenmenü. Über den Knopf „Tutorial“ oben rechts startest du eine Tour jederzeit neu.",
             before=lambda a: a.show_page("overview")),
    ]


def company_steps() -> list[Step]:
    return [
        Step("Deine Firma",
             "Glückwunsch zur Firmengründung! Jetzt zeige ich dir das Firmenmenü. Ihr Name steht oben in der "
             "Kopfzeile.",
             before=lambda a: a.show_page("overview")),
        Step("Zeitraffer",
             "Hier läuft die Firma im Zeitraffer: Start und Stopp, Geschwindigkeit, +1, +7 und +30 Tage und der "
             "Einnahmen-Faktor. Die Gewinne bleiben zuerst in der Firma.",
             lambda a: a.overview.ctrl_frame,
             before=lambda a: a.show_page("overview")),
        Step("Mit ETS2 mitlaufen",
             "Die Firma kann nur verdienen, solange ETS2 läuft. Beim Beenden von ETS2 kann sie ihre Änderungen "
             "selbst in den neuesten Spielstand schreiben.",
             lambda a: a.overview.game_frame),
        Step("Garagen",
             "Alles beginnt mit einer Garage. Dort baust du Garagen in Städten und siehst, wie wirtschaftlich "
             "sie sind, welche Busse und Fahrer darin stehen.",
             lambda a: a.nav_buttons["garages"],
             wait_page="garages",
             hint="Klicke jetzt auf „Garagen“ (oder auf „Weiter“)."),
        Step("Garage bauen",
             "Baue zuerst eine Garage. Größere Garagen fassen mehr Busse und Fahrer, kosten aber mehr Unterhalt.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("garages")),
        Step("Busse",
             "Hier kaufst du Busse, weist ihnen eine Linie und einen Fahrer zu und schickst sie zur Wartung.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("buses")),
        Step("Fahrer",
             "Ohne Fahrer fährt kein Bus. Stelle Fahrer ein, weise sie Bussen zu und schicke sie in die "
             "Weiterbildung, damit sie besser werden.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("drivers")),
        Step("Eigene Routen",
             "Lege eigene Linien und Ausflüge an. Die Tabelle zeigt dir den geschätzten Gewinn pro Fahrt.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("routes")),
        Step("Verträge",
             "Nimm Verträge an: Ein Bus fährt dann feste Fahrten für festen Lohn. Ein Abbruch kostet Strafe.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("contracts")),
        Step("Finanzen",
             "Alle Einnahmen und Ausgaben der Firma, sortiert nach Kategorie und Zeitraum.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("finance")),
        Step("Einstellungen",
             "Firmenname, Preise, Kosten, Bus-XP und viele weitere Werte stellst du hier ein.",
             lambda a: a.tabs,
             before=lambda a: a.show_page("settings")),
        Step("Live-Fahrt und Karte",
             "Mit dem Telemetrie-Server von Funbit zeigt die Live-Fahrt deine echte Fahrt samt Ankunftszeit. "
             "Die Karte zeigt deine Garagen und Strecken.",
             lambda a: a.nav_buttons["live"],
             before=lambda a: a.show_page("live")),
        Step("In den Spielstand schreiben",
             "Mit diesem Knopf schreibst du Geld und Bus-XP der Firma direkt in den geladenen Spielstand. "
             "Davor wird ein Backup angelegt. ETS2 sollte dabei geschlossen sein.",
             lambda a: a.payout_btn,
             before=lambda a: a.show_page("overview")),
        Step("Viel Spaß!",
             "Das war die Tour durch das Firmenmenü. Über den Knopf „Tutorial“ oben rechts startest du sie "
             "jederzeit neu."),
    ]


# --------------------------------------------------------------------- Tour
class Tour:
    def __init__(self, app: tk.Tk, steps: list[Step], on_close: Callable[[bool], None] | None = None) -> None:
        self.app = app
        self.steps = steps
        self.on_close = on_close
        self.index = -1
        self.active = False
        self._place_job = None
        self._frames: list[tk.Frame] = []
        self.card: tk.Frame | None = None

        style = ttk.Style(app)
        style.configure("TourTitle.TLabel", background=theme.PANEL, foreground=theme.ACCENT,
                        font=app.fonts["head"])
        style.configure("TourText.TLabel", background=theme.PANEL, foreground=theme.TEXT, font=app.fonts["base"])
        style.configure("TourHint.TLabel", background=theme.PANEL, foreground=theme.ACCENT, font=app.fonts["bold"])

    # ---- Build ----
    def start(self) -> None:
        self.active = True
        self._bind = self.app.bind("<Configure>", self._on_configure, add="+")
        self._show(0)

    def _build_card(self, step: Step, number: int) -> tk.Frame:
        card = tk.Frame(self.app, bg=theme.PANEL, highlightthickness=2, highlightbackground=theme.ACCENT)
        inner = ttk.Frame(card, style="Panel.TFrame", padding=(16, 12, 16, 12))
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=f"Schritt {number} von {len(self.steps)}", style="PanelMuted.TLabel").pack(anchor="w")
        ttk.Label(inner, text=step.title, style="TourTitle.TLabel").pack(anchor="w", pady=(4, 6))
        ttk.Label(inner, text=step.text, style="TourText.TLabel", wraplength=CARD_W - 40, justify="left").pack(anchor="w")
        if step.hint:
            ttk.Label(inner, text=step.hint, style="TourHint.TLabel", wraplength=CARD_W - 40,
                      justify="left").pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(inner, style="Panel.TFrame")
        row.pack(fill="x", pady=(14, 0))
        last = number == len(self.steps)
        if not last:
            ttk.Button(row, text="Überspringen", style="Small.TButton", command=lambda: self._close(False)).pack(side="left")
        ttk.Button(row, text="Fertig" if last else "Weiter", style="Accent.TButton",
                   command=(lambda: self._close(True)) if last else self.next).pack(side="right")
        if number > 1:
            ttk.Button(row, text="Zurück", command=self.back).pack(side="right", padx=8)
        return card

    def _show(self, index: int) -> None:
        self.index = index
        step = self.steps[index]
        self._clear()
        try:
            if step.before:
                step.before(self.app)
        except Exception:                                       # noqa: BLE001 - a step must never break the tour
            pass
        self.app.update_idletasks()
        self.card = self._build_card(step, index + 1)
        self.card.place(x=0, y=0)
        self.app.update_idletasks()
        self._place()
        self.app.after(120, self._place)                         # once more after the page has been built

    def _clear(self) -> None:
        for fr in self._frames:
            fr.destroy()
        self._frames = []
        if self.card is not None:
            self.card.destroy()
            self.card = None

    # ---- Geometry ----
    def _target_rect(self, step: Step):
        if step.target is None:
            return None
        try:
            widgets = step.target(self.app)
        except Exception:                                       # noqa: BLE001
            return None
        if widgets is None:
            return None
        if not isinstance(widgets, (list, tuple)):
            widgets = [widgets]
        rects = []
        for w in widgets:
            try:
                if not w.winfo_ismapped() or w.winfo_width() < 4:
                    continue
                x = w.winfo_rootx() - self.app.winfo_rootx()
                y = w.winfo_rooty() - self.app.winfo_rooty()
                rects.append((x, y, x + w.winfo_width(), y + w.winfo_height()))
            except tk.TclError:
                continue
        if not rects:
            return None
        return (min(r[0] for r in rects), min(r[1] for r in rects),
                max(r[2] for r in rects), max(r[3] for r in rects))

    def _place(self) -> None:
        if not self.active or self.card is None or not self.card.winfo_exists():
            return
        step = self.steps[self.index]
        rect = self._target_rect(step)
        W, H = self.app.winfo_width(), self.app.winfo_height()
        self.card.update_idletasks()
        cw, ch = max(CARD_W, self.card.winfo_reqwidth()), self.card.winfo_reqheight()
        for fr in self._frames:
            fr.destroy()
        self._frames = []
        if rect is None:
            x, y = (W - cw) // 2, (H - ch) // 2
        else:
            x0, y0, x1, y1 = rect[0] - PAD, rect[1] - PAD, rect[2] + PAD, rect[3] + PAD
            for (fx, fy, fw, fh) in ((x0, y0, x1 - x0, EDGE), (x0, y1 - EDGE, x1 - x0, EDGE),
                                     (x0, y0, EDGE, y1 - y0), (x1 - EDGE, y0, EDGE, y1 - y0)):
                fr = tk.Frame(self.app, bg=theme.ACCENT)
                fr.place(x=fx, y=fy, width=fw, height=fh)
                self._frames.append(fr)
            gap = 14
            candidates = [
                (x1 + gap, y0),                      # right
                (x0, y1 + gap),                      # below
                (x0 - cw - gap, y0),                 # left
                (x0, y0 - ch - gap),                 # above
            ]
            x = y = None
            for cx, cy in candidates:
                cx = min(max(cx, 8), W - cw - 8)
                cy = min(max(cy, 8), H - ch - 8)
                overlap = not (cx + cw <= x0 or cx >= x1 or cy + ch <= y0 or cy >= y1)
                if not overlap:
                    x, y = cx, cy
                    break
            if x is None:                            # element is large: place the card over it at the bottom right
                x, y = W - cw - 24, H - ch - 70
        self.card.place(x=int(x), y=int(y), width=cw)
        self.card.lift()
        for fr in self._frames:
            fr.lift()
        self.card.lift()

    def _on_configure(self, event) -> None:
        if event.widget is not self.app or not self.active:
            return
        if self._place_job is not None:
            self.app.after_cancel(self._place_job)
        self._place_job = self.app.after(80, self._place)

    # ---- Control ----
    def next(self) -> None:
        if self.index + 1 >= len(self.steps):
            self._close(True)
        else:
            self._show(self.index + 1)

    def back(self) -> None:
        if self.index > 0:
            self._show(self.index - 1)

    def page_shown(self, key: str) -> None:
        """Called by the app when a page has been opened (also by the tour itself)."""
        if not self.active or self.index < 0:
            return
        if self.steps[self.index].wait_page == key:
            self.app.after(250, self._advance_if_still, self.index)

    def _advance_if_still(self, index: int) -> None:
        if self.active and self.index == index:
            self.next()

    def _close(self, finished: bool) -> None:
        if not self.active:
            return
        self.active = False
        self._clear()
        try:
            self.app.unbind("<Configure>", self._bind)
        except tk.TclError:
            pass
        if self.on_close:
            self.on_close(finished)


# --------------------------------------------------------------------- first language choice
def choose_first_language(root: tk.Tk) -> str | None:
    """Shows the language selection before the first start. Returns the language code (None: window closed)."""
    result: list[str | None] = [None]
    win = tk.Toplevel(root)
    win.title("Roadhub")
    win.configure(bg=theme.BG)
    win.resizable(False, False)
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    box = ttk.Frame(win, padding=28)
    box.pack()
    ttk.Label(box, text="ROADHUB", style="Title.TLabel", background=theme.BG).pack()
    ttk.Label(box, text="Choose your language  ·  Sprache wählen", style="Head.TLabel").pack(pady=(14, 14))

    def pick(code: str) -> None:
        result[0] = code
        win.destroy()

    for code, name in i18n.LANGUAGES:
        ttk.Button(box, text=name, style="Accent.TButton", width=24, command=lambda c=code: pick(c)).pack(pady=4)
    win.update_idletasks()
    x = root.winfo_screenwidth() // 2 - win.winfo_reqwidth() // 2
    y = root.winfo_screenheight() // 2 - win.winfo_reqheight() // 2
    win.geometry(f"+{x}+{y}")
    win.lift()
    win.focus_force()
    win.grab_set()
    root.wait_window(win)
    return result[0]
