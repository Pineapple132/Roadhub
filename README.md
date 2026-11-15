# Roadhub

Roadhub is a Windows tool for **Euro Truck Simulator 2** (Coaches DLC) with two parts:

- **Bus company simulation.** ETS2 has no bus garages, so Roadhub runs a company next to the game: build garages, buy buses
  from the models in your save, hire drivers, create routes and contracts, and let the buses earn money in fast-forward.
  The company shares one account with ETS2 and writes its changes (money and bus XP) into your newest save game.
- **Save editor.** Change money, XP, skills, truck jobs, bus XP and bus line offers in your save, with an automatic backup before every write.

It also reads live data from the game (speed, distance, real arrival time) and can show a small overlay.
The interface is available in English, German, Russian, Turkish and Polish.

## Installation

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/ and tick *Add Python to PATH*.
2. Download or clone this repository and double-click **`Start.bat`**. On the first run it installs the only dependency (`cryptography`).
3. Optional: **`Build_EXE.bat`** builds a single `Roadhub.exe` in `dist\`.

On the first start you choose your language, then an interactive tutorial walks you through the app.
The *Tutorial* button in the top right restarts it at any time.

Before you use the editor or let the company write into a save:

- **Turn off Steam Cloud for your profile** (in the game: edit profile, untick *Use Steam Cloud*), otherwise Steam overwrites your changes.
- **Close ETS2** (or stay in the main menu) while saving, then load the save again in the game. A running game keeps its old data in memory.
- Roadhub reads plain-text and the usual encrypted saves. If it reports a binary save, set `uset g_save_format "2"` in
  `Documents\Euro Truck Simulator 2\config.cfg`, start the game and save again.

## Live data (telemetry)

Roadhub gets live data from the free [ets2-telemetry-server by Funbit](https://github.com/Funbit/ets2-telemetry-server). It only reads; nothing is written into the running game.

1. Download the latest release of the telemetry server and unpack it.
2. Start the server, choose your ETS2 installation folder if asked and click **Install** (or copy the plugin DLL to `bin/win_x64/plugins` in your ETS2 folder yourself).
3. Start ETS2. When it asks about loading the advanced SDK plugin, confirm it. The server page at `http://localhost:25555` should now show your truck data.
4. In Roadhub open **Live trip**, tick *Follow real trips from ETS2* and press *Test connection*. The default address is `http://127.0.0.1:25555/api/ets2/telemetry`.
5. Optional: tick *Show overlay in game* for a small always-on-top window. It only works if ETS2 runs in windowed or borderless mode.

Without the game you can try the page with *Start demo trip*.

How it behaves:

- The arrival time is a real clock time, calculated from the measured game speed (ETS2 runs at about 19:1) and kept stable like in a navigation app.
- The income of a delivered trip appears in the estimated account straight away (in the game you already have it).
- The telemetry server reports only the planned income of a job. A job that ends within 3 km of the destination counts as delivered.

## The bus company

You need **150,000 €** on your ETS2 account to found a company. Until then only the founding page and the save editor are available.

- **Overview:** fast-forward controls, account, profit chart, events. The company can also run only while `eurotrucks2.exe` is running
  and write its changes into the newest save when you quit the game (*Run along with ETS2*).
- **Garages, buses, drivers:** build garages (small, medium, large), buy buses, assign drivers and routes, service and sell.
  A bus only drives with a driver. Drivers can be trained; training costs money and the bus stands still for two days.
- **Own routes and contracts:** create your own lines and excursions, or accept contracts derived from the line offers in your save.
- **Map:** a schematic map of Europe with your garages and the moving buses.
- **Finances:** income and expenses by category.
- **Settings:** the company name, income per km, working hours ("keep to working hours"), costs, prices, bus XP and more.
- **Write company balance into save game:** writes the money and bus XP of the company into the loaded save (with backup).

One shared account: Roadhub reads your balance from the newest save. Purchases and the profit of the buses are kept as a pending change
and are written into the save when ETS2 exits (or when you press the write button). Income from your own real trips is already in the game and is never paid twice.

The simulation is an estimate. Prices, costs and demand are our own assumptions, not values from the game; tune them on the settings page.

## The save editor

- **Profile:** balance, XP and the truck skills.
- **Truck jobs:** overwrite existing job slots of the companies (destination, cargo, trailer, distance, urgency, validity, ferry).
- **Bus (XP, skills):** bus XP and bus skills.
- **Bus jobs:** overwrite line offers at the bus stops (type, up to five destinations, bus model, departure time, validity).
- Every save creates a backup (`game.sii.backup_<date>`) and also updates the load list entry (`info.sii`).

## Data and files

- Company data: `~/.ets2_save_tool/company.json` (backup `.bak`).
- Language and tutorial state: `~/.ets2_save_tool/ui.json`. Delete `tour_done` and `company_tour_done` there to see the tours again.

## Development

```
python -m pytest
```

Set `ETS2_REAL_SAVE=<path to game.sii>` to run an extra test against a real save.
The GUI smoke tests in `tests/gui_smoke*.py` run under Linux with `xvfb-run` (set `ETS2_SKIP_TUTORIAL=1` to skip the first-start dialogs).

Translations live in `roadhub/i18n_data.py`, generated by `tools/build_i18n.py` from translation tables. The texts in the code are German and serve as the catalog keys.

## Limits

- The company cannot pay into the running game, only into a save while the game is closed.
- The distance of a new truck job can only be calculated if the route already appears in an existing job; otherwise you enter it yourself.
