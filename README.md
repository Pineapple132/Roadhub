# Roadhub

Roadhub: Busfirma-Simulation und Save-Editor für Euro Truck Simulator 2 (Windows, Python/tkinter).

## Aufbau
Links ist das Menü. **Busfirma** ist das Hauptmenü, der **Save-Editor** klappt als Untermenü darunter auf.

### Busfirma (Hauptmenü)
ETS2 hat keine Busgaragen. Darum läuft die Firma als Simulation neben dem Spiel, im Zeitraffer:
- **Übersicht:** Kasse, Zeit, Ruf, Gewinn, 14-Tage-Diagramm, Ereignisse. Start/Pause mit wählbarer
  Geschwindigkeit, „+ 1 / 7 / 30 Tage“, Einnahmen-Faktor (0,1 bis 5) und automatische Wartung.
- **Karte:** Europa mit allen Städten (grau), deinen Garagen (orange), Sehenswürdigkeiten (blau) und den
  Bussen (weiß, wenn sie fahren). Städte anklicken: Garage bauen, ausbauen, Bus kaufen. Bus anklicken:
  Details. Ziehen verschiebt, das Mausrad zoomt. Die Karte ist eine eigene schematische Europakarte
  (Natural Earth, gemeinfrei) mit den ETS2-Städten an ihren echten Orten, nicht die Spielkarte. Die
  Sehenswürdigkeiten liegen teils geschätzt. Die Busse fahren auf der Luftlinie zwischen den Städten.
- **Garagen:** in einer beliebigen Stadt bauen (klein, mittel, groß) und ausbauen.
- **Busse:** Modelle aus deinem Save kaufen, einer Strecke oder Touristenfahrt zuweisen, Fahrer zuweisen,
  warten, verkaufen. Ein Bus fährt nur mit Fahrer.
- **Fahrer:** Jede Spielwoche gibt es neue Bewerber mit Skills (Öko-Fahrweise, Pünktlichkeit,
  Fahrgast-Service, Sicherheit, je 0 bis 5). Einstellen kostet eine Vermittlungsgebühr, bessere Fahrer
  verlangen mehr Lohn. Weiterbildung kostet Geld und dauert 2 Tage, in denen der Bus steht.
- **Eigene Routen:** Eigene Linien mit 2 bis 6 Haltestellen oder Ausflugsfahrten zu Sehenswürdigkeiten
  anlegen (Menü „Eigene Routen“ oder auf der Karte: Stadt anklicken, „Route von hier anlegen“, bzw.
  Sehenswürdigkeit anklicken, „Ausflug dorthin anlegen“). Kilometer und Fahrzeit kommen aus bekannten
  Strecken deines Saves, sonst aus der Luftlinie geschätzt, und sind änderbar. Zugewiesen wird die Route
  auf der Seite „Busse“. Der Bus pendelt hin und zurück.
- **Verträge:** Feste Fahrten wie die Linienaufträge in ETS2, abgeleitet aus den Linienangeboten deines Saves
  (Strecke, Haltestellen, Abfahrtszeit). Jede Spielwoche gibt es neue Angebote ab deinen Garagenstädten. Du
  nimmst einen an und gibst ihm einen Bus mit Fahrer. Der Bus startet dann zur festen Uhrzeit (14 Tage lang),
  fährt die Haltestellen ab und kommt leer zurück. Es gibt einen festen Betrag je Fahrt und 10 % Bonus, wenn
  keine Fahrt ausfällt. Verpasste Fahrten kosten Ruf, ein vorzeitiger Abbruch eine Vertragsstrafe.
- **Touristenfahrten:** Zu Sehenswürdigkeiten (z. B. Geysir, Nordkap, Schönbrunn), mit höherem Fahrpreis, mehr
  Nachfrage am Wochenende und 90 Minuten Aufenthalt vor Ort. Welche Ziele es ab welcher Stadt gibt,
  steht in den Linien deines Saves.
- **Auf ETS2 übertragen:** zahlt Geld (Kasse) und Bus-XP (verdient durch die Fahrten) in deinen Spielstand
  aus. Das geht nur offline, weil ETS2 beim Spielen nichts von außen annimmt: Spiel schließen,
  Steam-Cloud aus, dann überträgt das Tool und legt ein Backup an.
- **Mit ETS2 mitlaufen** (Übersicht, Kasten „Mit ETS2 mitlaufen“): Die Firma verdient nur, solange
  `eurotrucks2.exe` läuft, im gewählten Tempo, auf Wunsch „wie ETS2“ (1 Spielstunde = 1 Firmenstunde, ETS2 läuft etwa 19-mal schneller als die Echtzeit). Mit „automatisch auszahlen“ schreibt das Tool beim Beenden
  von ETS2 einmalig Geld und Bus-XP in den Spielstand mit dem **neuesten Änderungsdatum** (Backup, info.sii
  wird angepasst). Das Konto ist das gemeinsame Konto (siehe unten).
  Das Tool muss dafür schon vor dem Spielstart laufen. Steam-Cloud muss aus sein.
- Strecken, Fahrzeiten und Busmodelle kommen aus den Linienangeboten in deinem Save. Der Firmenstand
  liegt in `~/.ets2_save_tool/company.json` (Backup `.bak`) und wird automatisch gespeichert.

### Save-Editor (Untermenü)
- **Profil:** Kontostand, Erfahrungspunkte (XP) und alle sechs Skills ändern.
- **Truck-Aufträge:** Vorhandene Auftrags-Slots der Firmen überschreiben, auch leere Slots
  („leere Slots anzeigen“): Ziel, Fracht, Anhänger, Entfernung, Dringlichkeit, Gültigkeit, Fähre.
  Fracht und Anhänger kommen aus Kombinationen, die schon in deinem Save vorkommen, damit sie
  zusammenpassen (inklusive passendem Zugwagen für Heavy-/Double-Fracht).
- **Bus (XP, Skills):** Bus-XP und die sechs Bus-Skills ändern, dazu Zahlen aus dem Save zum Nachlesen.
  Die Höchstwerte der Bus-Skills sind unbekannt (erlaubt: 0 bis 6).
- **Bus-Aufträge:** Linienangebote der Haltestellen überschreiben: Typ (Linie/Touristik), bis zu
  5 Ziele, Busmodell, Abfahrtszeit, Gültigkeit. Kilometer und Fahrzeit kommen bei bekannten Etappen aus
  dem Save, bei neuen werden sie aus den Kilometern geschätzt.
- Vor jedem Speichern wird automatisch ein Backup angelegt (`game.sii.backup_<Datum>`).
  Die Anzeige in der Ladeliste (`info.sii`: Geld, XP) wird mit angepasst, ebenfalls mit Backup.
- Dunkles Design mit orangen Akzenten im Stil der ETS2-Menüs.

## Starten
1. Python 3.10 oder neuer installieren (https://www.python.org/downloads/), beim Installieren
   „Add Python to PATH“ ankreuzen.
2. `Start.bat` doppelklicken. Beim ersten Mal wird das Paket `cryptography` installiert.
3. Optional: `Build_EXE.bat` erzeugt eine einzelne `Roadhub.exe` in `dist\`.

## Vor dem Benutzen
- **Steam-Cloud für das Profil ausschalten** (Spiel: Profil bearbeiten → „Steam-Cloud verwenden“ aus),
  sonst überschreibt Steam die Änderungen.
- **Spiel schließen** (oder im Hauptmenü sein), dann speichern und den Spielstand neu laden.
- Das Programm braucht Saves im Textformat bzw. im üblichen verschlüsselten Format. Gibt es eine
  Meldung zum Binärformat, in `Dokumente\Euro Truck Simulator 2\config.cfg` die Zeile
  `uset g_save_format "2"` setzen, Spiel starten und neu speichern.
- Gespeichert wird als Klartext. Das Spiel liest das normal.

## Grenzen
- **Die Simulation ist ein Schätzwerk.** Preise, Kosten und Nachfrage sind eigene Annahmen, keine Werte
  aus dem Spiel. Mit dem Einnahmen-Faktor stellst du ein, wie großzügig die Firma verdient.
- Die Busfirma kann nicht live ins laufende Spiel zahlen, nur offline in den Save.
- Die Entfernung eines neuen Truck-Auftrags kann das Programm nicht berechnen, wenn die Strecke noch
  in keinem vorhandenen Auftrag vorkommt. Dann trägst du sie selbst ein.
- Die deutschen Namen der Bus-Skills sind Übersetzungen, ihre Höchstwerte sind unbekannt.
- Getestet mit nachgebauten Test-Saves und mit der Kopie eines echten Saves (Coaches-DLC,
  Spielversion 1.5x). Ob das Spiel einen bearbeiteten Save fehlerfrei lädt, konnte ich nicht
  ausprobieren. Lege deshalb vor dem ersten Einsatz selbst eine Kopie ab.

## Entwicklung
`python -m pytest` startet die Tests (Entschlüsselung, Profil, Truck- und Bus-Aufträge, Busfirma-Simulation, Backups, info.sii).
Mit `ETS2_REAL_SAVE=<Pfad zu game.sii>` läuft zusätzlich ein Test gegen einen echten Save.
Die Oberfläche testen `tests/gui_smoke.py` und `tests/gui_smoke_company.py`, `tests/gui_smoke_game.py` (unter Linux mit `xvfb-run`).

## Ein gemeinsames Konto

Firma und ETS2 teilen sich ein Konto. Das Tool liest deinen Kontostand beim Start aus dem neuesten Spielstand. Käufe (Garagen, Busse, Fahrer, Weiterbildung) gehen von diesem Geld ab, der Gewinn der Busse kommt dazu. Beim Beenden von ETS2 wird nur die **Änderung durch die Firma** in den neuesten Spielstand geschrieben (Konto plus oder minus diese Änderung, dazu die verdienten Bus-XP).

- Das Spiel bleibt die Quelle: Der Verdienst deiner Fahrten ist ohnehin schon dein Geld und wird nicht noch einmal gezahlt.
- Während ETS2 läuft, ist das angezeigte Konto nur eine Schätzung. Die Telemetrie meldet den Kontostand nicht, nur den Verdienst abgelieferter Fahrten. Tankkosten, Strafen und Ähnliches fehlen in der Anzeige. Beim Schreiben spielt das keine Rolle, denn es wird auf den echten Stand im Save aufgesetzt.
- Reicht das Geld in der Anzeige nicht, lässt das Tool den Kauf nicht zu. Das Konto im Save wird nie unter 0 geschrieben.
- „Mit Spielstand abgleichen“ (Übersicht) liest den Kontostand neu, wenn du außerhalb des Tools Geld geändert hast. Noch nicht geschriebene Firmenänderungen bleiben dabei erhalten.

## Live-Fahrt (Telemetrie)

Unter **Live-Fahrt** siehst du deine echte ETS2-Fahrt (Strecke, Tempo, Restkilometer, Auftragswert) links und die Busfirma rechts.

- **Einrichtung:** den ets2-telemetry-server von Funbit installieren (Plugin-DLL nach `bin/win_x64/plugins` im ETS2-Ordner), dann in der Live-Seite „Echte Fahrten aus ETS2 verfolgen“ einschalten. Das Tool liest nur, ins laufende Spiel wird nie geschrieben. Mit „Demo-Fahrt starten“ kannst du die Ansicht ohne Spiel ausprobieren.
- **Geld:** Der Verdienst einer abgelieferten Fahrt erscheint sofort im geschätzten Konto der Anzeige (im Spiel hast du ihn ohnehin schon).
- **Fahrtbericht:** Nach jeder Lieferung zeigt das Tool Auftrag, Firmenanteil, Firmenverdienst und Ausgaben während der Fahrt und den Kassenstand.
- **Grenzen:** Der Telemetrie-Server meldet bei einem Auftrag nur den geplanten Verdienst. Ein Ende des Auftrags nahe am Ziel (unter 3 km) gilt als Lieferung, sonst als Abbruch (dann gibt es nichts für die Firma). Schäden oder Verspätung ändern den gemeldeten Betrag nicht. Das Zusammenspiel mit dem echten Spiel konnte ich nicht testen, nur mit der Demo-Fahrt.
- **Bus-XP:** 0,3 XP pro km, höchstens 150 XP pro abgeschlossener Fahrt.

- **Overlay:** Auf der Live-Seite „Overlay im Spiel anzeigen“ einschalten. Das Fenster bleibt im Vordergrund, lässt sich mit der Maus verschieben, Rechtsklick schließt es. Es funktioniert nur, wenn ETS2 im Fenster- oder randlosen Modus läuft.
- **Fahrt beenden:** Mit dem Button auf der Live-Seite kannst du eine Fahrt von Hand als abgeliefert verbuchen oder abbrechen.


## Neue Saves und ein Konto
- Das Tool beobachtet den neuesten Spielstand. Sobald ETS2 speichert, wird der Kontostand abgeglichen und der Editor neu geladen (nicht, wenn dort ungespeicherte Änderungen sind). Die Spielstandliste wird zusätzlich alle 5 Minuten neu eingelesen.
- Es gibt nur noch das ETS2-Konto. Noch nicht geschriebene Firmenänderungen stehen unter "Noch nicht im Spielstand".
- Ankunftszeit (Overlay und Live-Fahrt) = echte Uhrzeit, berechnet aus der gemessenen Spielzeit-Geschwindigkeit.
- Jedes geladene (auch automatisch neu geladene) Save setzt die Basis des Kontos in der Firmen-Datei auf den Kontostand des Saves. Was die Firma seit dem letzten Schreiben verdient oder ausgegeben hat (Busfahrten, Käufe), bleibt reserviert und wird beim Beenden von ETS2 in den neuesten Save geschrieben.
- Die Ankunftszeit ist wie bei Navi-Apps stabil: sie wird beim Start berechnet, zählt dann herunter und wandert nur langsam, wenn sie über 2 Min oder 8 % der Restzeit abweicht. Pausen verschieben sie.
- Reiter "Finanzen": Einnahmen und Ausgaben nach Art (Treibstoff, Löhne, Wartung & Maut, Werkstatt, Versicherung, Garagenunterhalt, Käufe, Fahrer, Vertragsstrafen) für heute, gestern, 7 Tage und insgesamt.
- Einnahmen: ein Reisebus mit ca. 50 Sitzen verdient im Schnitt etwa 13 € je gefahrenem km (Linien, Ausflüge und Verträge). Größere Busse mit mehr Sitzen verdienen entsprechend mehr.
- Reiter "Einstellungen": Verdienst je km, Gewinnfaktor, Kosten (Sprit, Lohn, Maut, Versicherung ...), Preise von Garagen und Bussen, Bus-XP, Wartung, Vertragsangebote und Bewerber. Alle Linien, Ausflüge und Verträge (auch laufende) laufen auf dem eingestellten km-Satz.
- Firma gründen kostet 150.000 € vom ETS2-Konto und geht erst, wenn dieser Betrag im geladenen Spielstand da ist. Bis dahin ist nur die Gründungsseite offen (Save-Editor bleibt nutzbar). Die Gründungskosten stehen in den Finanzen und werden beim Beenden von ETS2 vom Konto abgezogen.
- Ohne Firma sind alle Firmenseiten ausgeblendet (nur die Gründungsseite). Die Seite "Garagen" zeigt pro Garage Auslastung, Einnahmen, Kosten, Gewinn (gesamt, je km, je Bus), Fixkosten pro Tag sowie Tabellen der Busse und Fahrer wie die Garagenverwaltung in ETS2.


## Firmenname und Sprachen

- Den Namen der Firma legst du beim Gründen (Übersicht) fest und kannst ihn unter *Einstellungen → Firma* ändern. Er steht in der Kopfzeile.
- Oben rechts wählst du die Sprache: Deutsch, English, Русский, Türkçe, Polski. Nach dem Wechsel startet das Tool neu. Die Auswahl steht in `~/.ets2_save_tool/ui.json`.
- Texte ohne Übersetzung bleiben deutsch. Neue Übersetzungen: Tabellen in `tools/build_i18n.py` einspeisen, die Datei `i18n_data.py` wird erzeugt.

## Ladeanzeige und direktes Schreiben

- Bei jedem Button-Klick zeigt das Fenster den Sanduhr-Cursor und „Bitte warten …“ in der Statuszeile, bis die Aktion fertig ist (`busy.py`). Öffnet der Klick einen Dialog, ist die Anzeige währenddessen aus.
- Mit einer Firma gibt es unten neben „Speichern“ den Button „Firmenstand in Spielstand schreiben …“. Er schreibt Geld und Bus-XP der Firma in den geladenen Spielstand (mit Backup), ETS2 muss dafür geschlossen sein.

## Erster Start und Tutorial

- Beim allerersten Start wählst du zuerst die Sprache. Danach läuft eine interaktive Tour (`tour.py`): Das Tool markiert Elemente orange und erklärt sie in einer Karte daneben. Manche Schritte warten darauf, dass du selbst auf einen Menüpunkt klickst („Weiter“ geht immer).
- Nach der Firmengründung startet einmalig eine zweite Tour durch das Firmenmenü.
- Der Knopf „Tutorial“ oben rechts startet die Touren jederzeit neu. Gemerkt wird, was du schon gesehen hast, in `~/.ets2_save_tool/ui.json`; wer die Touren erneut automatisch sehen will, löscht dort `tour_done` und `company_tour_done`.
- Die Kopfzeile zeigt den Firmennamen in Großbuchstaben (ohne Firma „ROADHUB“).

## Balancing: Arbeitszeiten und Einnahmen der Firma

- Simulierte Fahrten und Verträge bringen standardmäßig 30 % des Tarifs (Einstellungen → Einnahmen → „Einnahmen simulierter Fahrten und Verträge“). Deine eigenen Fahrten im Spiel zählen weiter voll.
- „An Zeiten halten“ (Einstellungen → Betrieb): Ein Fahrer lenkt höchstens 9 Stunden am Tag (einstellbar), danach ruht der Bus bis 05:00 Uhr. Ist die Option aus, fahren die Busse wie früher durch.
- Richtwert mit den Standardwerten: ein Bus bringt etwa 1.500 € Gewinn pro Tag, eine volle mittlere Garage etwa 13.000 € (Test mit 8 Bussen auf Linien ab A Coruña).
