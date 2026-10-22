# Smart Sugarcane Irrigation Advisory System
OOP-PY lab project (SY B.Tech IT, Sem III): 12 agriculture scenarios built with experiments 1 to 8.

## How to run
```
python main.py
```
* You only need **Python 3.8 or newer**. It uses only the standard library (tkinter, sqlite3, threading, collections, functools, abc), so you don't have to pip install anything.
* The first run creates `sugarcane.db` with demo data: farmer Ramesh Patil, 6 plots and 7 days of sensor history.
  Delete `sugarcane.db` if you want to start fresh.
* Linux only: if tkinter is missing, run `sudo apt install python3-tk`.

## Files
| File | What it contains | Experiment |
|---|---|---|
| `models.py` | `Person → Farmer`, `Plot → DripPlot / FurrowPlot / FloodPlot`, `Farm`, `SensorReading` | Exp 1, 2, 3 |
| `exceptions.py` | Custom exception hierarchy (`IrrigationError`, `InvalidPlotDataError`, `SensorError` …) and input parsers | Exp 5 |
| `advisors.py` | Abstract class `Advisor` and 7 subclasses (one per scenario), plus `PumpScheduler` | Exp 4 |
| `analytics.py` | `deque`, `defaultdict`, `Counter`, `namedtuple`, `OrderedDict`, `map/filter/reduce/lambda`, higher-order function | Exp 6 |
| `weather.py` | 7-day forecast, Hargreaves ET0, thread `Lock` | Exp 5, 6 |
| `services.py` | `SensorSimulator` thread, `NotificationService` thread (producer/consumer with `queue`), English/Hindi/Marathi templates | Exp 5 |
| `database.py` | SQLite: 7 tables, CRUD, JOIN, GROUP BY, parameterised queries | Exp 8 |
| `charts.py` | Line, bar and Gantt charts drawn on a Tkinter Canvas | Exp 7 |
| `pages.py` | One page per scenario. All pages inherit from the abstract `BasePage` | Exp 7 (+4) |
| `app.py` | Main window, sidebar, header controls, thread to GUI event loop | Exp 7 |
| `lab/` (package) | **My own Exp 1–5 code**: `exp1_classes.py`, `exp2_records.py`, `exp3_inheritance.py`, `exp4_abstract.py`, and Exp 5's `sensor.py` + `recommendation.py` + `exp5_threads.py` | Exp 1–5 |
| `lab_logic.py` | **My own lab code reused**: Exp 6 advisory (same collections, map/filter/reduce, thresholds and output), Exp 7 recommendation rule, Exp 8 water amounts | Exp 6, 7, 8 |
| `main.py` | Entry point (also shows **modules**: the project is split into importable modules) | Exp 5 |

## Experiment → where to show it in the viva
1. **Classes & objects**: `Farmer`, `Plot`, `Farm` objects are created from the DB rows in `Database.load_farm()`.
2. **Constructors & lists**: every `__init__` validates its data; `Plot.readings` and `Farm.plots` are lists with add / remove / search methods.
3. **String handling & inheritance**: `Person.__init__` cleans names (`" ramesh   PATIL "` becomes `"Ramesh Patil"`); `masked_phone`, `initials`, `Plot.describe()` (ljust); `Farmer(Person)` with `super()`; `DripPlot(Plot)` overrides class attributes.
4. **Abstract classes & polymorphism**: `Advisor(ABC)` has the abstract methods `analyze()` and `headline()`. `WeatherAwareAdvisor` overrides `IrrigationAdvisor.analyze()` and calls `super()`. On page 12, a list of different advisors is handled through one call: `advisor.summary()`.
5. **Exception handling, modules, multithreading**: enter "abc" as the area on page 1, or a duplicate plot name, to trigger the custom errors. Two background threads send their results through a `queue.Queue`, and the GUI picks them up with `after()`.
6. **Collections & functional programming**: see `analytics.py`. It is used by pages 1, 2, 5, 7 and 12.
7. **GUI dashboard**: Tkinter + ttk with 12 pages, live charts, forms, Treeviews and a status bar.
8. **SQLite**: plot CRUD (page 1), sensor readings, irrigation log + `GROUP BY` report (page 8), alerts with `JOIN` (page 7), notifications (page 10).

## Where my own lab programs appear in the GUI
Sidebar item **13. My Lab Programs 1-8** runs every one of my lab programs and shows the same output as in my write-ups (Exp 5 prints its sensor lines in thread order, so the order can change from run to run). It also says where that code is used in the scenarios:

| My experiment | Where to find it in the app |
|---|---|
| **Exp 1**: `IrrigationSystem` (class variable, constructor, instance / class / static methods) | Page 1: select a plot. *Plot details* creates an `IrrigationSystem` object from that plot's live moisture and temperature, then shows `crop_info()`, `sensor_status()` and `irrigation_advice()`. |
| **Exp 2**: `IrrigationRecord` + list of 30 days | Page 2, **"30-day log (Exp 2)"** tab: my 30 records with buttons for `append()`, update (`list[i].attribute = value`), `remove()`, `pop()`, search, and reset. |
| **Exp 3**: string handling + 5 kinds of inheritance | Page 6: column **"SmartFarm (Exp 3)"** uses `SmartFarm(WeatherData, SoilData)` (multiple inheritance). Page 7: every stress tile shows `CropHealthAnalyzer` (multilevel). The 10 string operations run on page 13. |
| **Exp 4**: `IrrigationAdvisory(ABC)` → `AIAdvisory` / `SensorAdvisory` | Page 12 plot report: a list with both objects, `get_advisory()` called on each (runtime polymorphism). |
| **Exp 5**: modules `sensor.py` + `recommendation.py`, 3 threads, `ValueError` handling | Page 5: **"Read selected plot with 3 threads (Exp 5)"** reads soil moisture, temperature and humidity in 3 threads with `read_sensor()`, then shows `recommend()`'s answer. |
| **Exp 6**: Irrigation advisory with list / tuple / dict / set + map / filter / reduce / lambda | Page 2, **"Reading analysis (Exp 6)"** tab. With the default input (FARM101; 28, 32, 25, 30, 26; 36 °C; 48 %; 2 mm) it prints exactly my Exp 6 output: average 28.20 %, low readings [28, 25, 30, 26], IRRIGATION RECOMMENDED. *Load plot readings* runs the same code on a live plot's last 5 readings. |
| **Exp 7**: Tkinter Canvas logo (oval sun, line stem and leaves, polygon water drop, text, rectangle) and the sensor input form | The **start-up screen** draws my full logo; the **header** shows a smaller copy. Page 5 has my **"Generate Irrigation Recommendation"** form (same rule: below 40 % required, below 60 % recommended soon, same "Please enter valid numeric values." message). |
| **Exp 8**: `irrigation_advisory.db`-style tables `Sensor_Data` and `Irrigation_Advisory` with 50 records, and the SQL queries | Same two tables (same columns) and the same 50 sensor records are created in `sugarcane.db`. Page 2, **"Sensor records - SQLite (Exp 8)"** tab: queries 1-7 are my Exp 8 queries (all data, moisture < 40, temperature > 30, ORDER BY moisture, COUNT = 50, AVG = 50.07, 'Irrigation Required' list); 8-15 add GROUP BY, MIN/MAX, BETWEEN, LIMIT, DISTINCT, LIKE, HAVING and JOIN from the theory table. You can edit the SQL (SELECT only) and add new sensor records, which are written to both tables. |

## The 12 scenarios (sidebar)
| # | Scenario | What you can do |
|---|---|---|
| 1 | Farm & Plot Monitoring | KPIs, plot table, plot details, add / edit / delete plots |
| 2 | Multi-Plot Soil Moisture | Live gauge tiles per plot + live chart; Exp 8 SQLite sensor records and query console; Exp 6 reading analysis |
| 3 | Crop Water Requirement | ET0 × Kc = ETc, litres per day per plot, Kc season curve |
| 4 | Next Irrigation Date | Day-by-day soil water simulation, 10-day projection chart |
| 5 | Smart Recommendation | Priority list, step-by-step calculation, start the pump, Exp 7 quick-check form |
| 6 | Weather-Aware Advisory | 7-day forecast, edit rain to test "what if", basic vs weather-aware advice |
| 7 | Water Stress Alerts | Coloured stress tiles, alert log saved in SQLite, level filter |
| 8 | Pump Scheduling | Greedy multi-pump timetable (Gantt), start pumps, irrigation history |
| 9 | Fertigation | Weekly N-P-K and Urea / 12:61:00 / MOP per plot, send to farmer |
| 10 | Farmer Advisory & SMS | Messages in English / Hindi / Marathi, "Ask Krishi Mitra" Q&A, notification log |
| 11 | Yield Prediction | FAO-33 (Ky = 1.2) yield, sugar, revenue at the FRP |
| 12 | Integrated Dashboard | Everything together, every advisor's report per plot, export a .txt report |

**Simulation controls** (header): *Pause sensors*, *Sim hours/tick* (raise it so plots dry faster during a demo) and **↺ Reset demo**, which gives every plot a fresh, different moisture level (some dry, some fine), and clears alerts, SMS, pumps and history.

## Formulas used
* ET0 (Hargreaves) = 0.0023 × Ra × (Tmean + 17.8) × √(Tmax − Tmin)
* ETc = ET0 × Kc (sugarcane Kc: 0.45 / 0.80 / 1.25 / 0.75 by stage)
* Net depth = (Field capacity − current moisture) × root depth; Gross = Net ÷ efficiency (Drip 90%, Furrow 60%, Flood 50%)
* Pump hours = Volume ÷ pump flow
* Yield: 1 − Ya/Ym = Ky (1 − water index), Ky = 1.2

The sensor data and weather are simulated. In a real system they would come from IoT soil sensors and a weather API.
