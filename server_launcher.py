from __future__ import annotations

import json
import csv
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from common import DEFAULT_MAP_ID, MAPS, TRAFFIC_DEFAULT_COUNT
from database import DatabaseConfig, InventoryDatabase, mysql_error_text
from portable_paths import ensure_shared_layout

APP_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG_PATH = APP_DIR / "server_config.csv"
# MySQL/server-control settings are version-independent saved data. Keep them in
# a dedicated shared-data folder rather than inside any game build.
CONFIG_PATH = ensure_shared_layout()["mysql"] / "server_config.csv"
OLD_SHARED_CONFIG_PATH = ensure_shared_layout()["config"] / "server_config.csv"
if not CONFIG_PATH.exists():
    try:
        import shutil
        source = OLD_SHARED_CONFIG_PATH if OLD_SHARED_CONFIG_PATH.exists() else LOCAL_CONFIG_PATH
        if source.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, CONFIG_PATH)
    except OSError:
        pass
if not CONFIG_PATH.exists() and LOCAL_CONFIG_PATH.exists():
    import shutil
    shutil.copy2(LOCAL_CONFIG_PATH, CONFIG_PATH)
LEGACY_CONFIG_PATH = APP_DIR / "server_config.json"
DEFAULT_SERVICE = os.getenv("PYMMO_MYSQL_SERVICE", "MySQL84")

BG = "#151718"
PANEL = "#202326"
PANEL_2 = "#2a2e31"
TEXT = "#eeeeea"
MUTED = "#9fa4a7"
ACCENT = "#e1c65c"
GOOD = "#55c878"
BAD = "#db6262"
WARN = "#d6a84d"


def _load_config() -> dict:
    defaults = {
        "server_name": "Open Night v0.8 / Pass 18",
        "port": 8765,
        "max_players": 128,
        "traffic_cars": TRAFFIC_DEFAULT_COUNT,
        "map_id": DEFAULT_MAP_ID,
        "map_file": "",
        "lan_discovery": True,
        "db_host": os.getenv("PYMMO_DB_HOST", "127.0.0.1"),
        "db_port": int(os.getenv("PYMMO_DB_PORT", "3306")),
        "db_name": os.getenv("PYMMO_DB_NAME", "pymmo"),
        "db_user": os.getenv("PYMMO_DB_USER", "root"),
        "mysql_service": DEFAULT_SERVICE,
        "auto_start_mysql": True,
    }
    converters = {
        "port": int, "max_players": int, "traffic_cars": int, "db_port": int,
        "lan_discovery": lambda v: str(v).strip().lower() in {"1","true","yes","y","on"},
        "auto_start_mysql": lambda v: str(v).strip().lower() in {"1","true","yes","y","on"},
    }
    try:
        with CONFIG_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = str(row.get("key", "")).strip()
                if key not in defaults:
                    continue
                raw = row.get("value", "")
                try:
                    defaults[key] = converters.get(key, str)(raw)
                except (TypeError, ValueError):
                    continue
        return defaults
    except OSError:
        pass

    # One-way compatibility import for an older JSON config if a user copies it
    # beside a newer build. All future saves are CSV.
    try:
        raw = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            defaults.update({k: v for k, v in raw.items() if k in defaults})
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return defaults


def _save_config(config: dict) -> None:
    # Intentionally never persist the MySQL password in plaintext.
    safe = {k: v for k, v in config.items() if k != "db_password"}
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "value"])
        for key in sorted(safe):
            value = safe[key]
            if isinstance(value, bool):
                value = "true" if value else "false"
            writer.writerow([key, value])


def _run_command(args: list[str], timeout: float = 12.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired:
        return 124, "Command timed out."
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def detect_mysql_services() -> list[str]:
    if os.name != "nt":
        return []
    code, output = _run_command(["sc.exe", "query", "type=", "service", "state=", "all"])
    if code not in (0, 1060):
        return []
    services: list[str] = []
    for line in output.splitlines():
        match = re.match(r"\s*SERVICE_NAME:\s*(.+?)\s*$", line, re.IGNORECASE)
        if match and "mysql" in match.group(1).lower():
            services.append(match.group(1).strip())
    return services


def start_windows_service(service_name: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Automatic MySQL service start is implemented for Windows in this prototype."
    name = service_name.strip()
    if not name:
        services = detect_mysql_services()
        if not services:
            return False, "No MySQL Windows service was detected."
        name = services[0]
    code, output = _run_command(["sc.exe", "start", name], timeout=15.0)
    lower = output.lower()
    if code == 0 or "already running" in lower or "an instance of the service is already running" in lower:
        return True, output or f"Started {name}."
    if "access is denied" in lower or "failed 5" in lower:
        return False, f"Windows denied permission to start {name}. Run the launcher as Administrator once, or start the service manually.\n{output}"
    return False, output or f"Could not start service {name} (exit code {code})."


class ServerLauncher:
    def __init__(self) -> None:
        self.config = _load_config()
        self.root = tk.Tk()
        self.root.title("Python MMO - Server Control")
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.server_process: subprocess.Popen[str] | None = None
        self.server_output_queue: queue.Queue[str] = queue.Queue()
        self.db_result_queue: queue.Queue[dict] = queue.Queue()
        self.service_result_queue: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.server_players = 0
        self.server_running = False
        self._closing = False

        self._setup_style()
        self._build_ui()
        self.root.after(120, self._drain_queues)
        self.root.after(500, lambda: self.refresh_database(auto_start_on_fail=True))
        self.root.after(700, self._detect_service_async)
        self.root.after(10000, self._periodic_db_refresh)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Consolas", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Consolas", 10))
        style.configure("Muted.Panel.TLabel", background=PANEL, foreground=MUTED, font=("Consolas", 9))
        style.configure("Header.Panel.TLabel", background=PANEL, foreground=TEXT, font=("Consolas", 16, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Consolas", 23, "bold"))
        style.configure("Accent.TButton", font=("Consolas", 11, "bold"), padding=8)
        style.map("Accent.TButton", background=[("active", "#d6bd57")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("Consolas", 9))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("active", TEXT)])
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT)

    def _entry(self, parent, variable: tk.Variable, width: int = 24, show: str | None = None) -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=variable,
            width=width,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Consolas", 10),
            highlightthickness=1,
            highlightbackground="#4c5154",
            highlightcolor=ACCENT,
            show=show or "",
        )
        return entry

    def _section(self, parent, title: str) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=18)
        ttk.Label(frame, text=title, style="Header.Panel.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        frame.columnconfigure(1, weight=1)
        return frame

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="PYTHON MMO  •  SERVER CONTROL", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="MySQL persistence + authoritative world server", foreground=MUTED).pack(anchor="w", pady=(2, 16))

        top = ttk.Frame(outer)
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        db = self._section(top, "DATABASE")
        db.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        server = self._section(top, "SERVER")
        server.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.db_status_var = tk.StringVar(value="● CHECKING")
        self.db_detail_var = tk.StringVar(value="Waiting for database check...")
        self.db_accounts_var = tk.StringVar(value="—")
        self.db_version_var = tk.StringVar(value="—")

        ttk.Label(db, text="Status", style="Muted.Panel.TLabel").grid(row=1, column=0, sticky="w")
        self.db_status_label = tk.Label(db, textvariable=self.db_status_var, bg=PANEL, fg=WARN, font=("Consolas", 11, "bold"))
        self.db_status_label.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(db, text="Host", style="Muted.Panel.TLabel").grid(row=2, column=0, sticky="w")
        self.db_host_var = tk.StringVar(value=str(self.config["db_host"]))
        self._entry(db, self.db_host_var).grid(row=2, column=1, sticky="ew", pady=3)
        self.db_port_var = tk.StringVar(value=str(self.config["db_port"]))
        self._entry(db, self.db_port_var, width=8).grid(row=2, column=2, sticky="w", padx=(8, 0), pady=3)

        ttk.Label(db, text="Database", style="Muted.Panel.TLabel").grid(row=3, column=0, sticky="w")
        self.db_name_var = tk.StringVar(value=str(self.config["db_name"]))
        self._entry(db, self.db_name_var).grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(db, text="User", style="Muted.Panel.TLabel").grid(row=4, column=0, sticky="w")
        self.db_user_var = tk.StringVar(value=str(self.config["db_user"]))
        self._entry(db, self.db_user_var).grid(row=4, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(db, text="Password", style="Muted.Panel.TLabel").grid(row=5, column=0, sticky="w")
        self.db_password_var = tk.StringVar(value=os.getenv("PYMMO_DB_PASSWORD", ""))
        self._entry(db, self.db_password_var, show="•").grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Label(db, text="Windows service", style="Muted.Panel.TLabel").grid(row=6, column=0, sticky="w")
        self.mysql_service_var = tk.StringVar(value=str(self.config.get("mysql_service", DEFAULT_SERVICE)))
        self._entry(db, self.mysql_service_var).grid(row=6, column=1, columnspan=2, sticky="ew", pady=3)

        self.auto_mysql_var = tk.BooleanVar(value=bool(self.config.get("auto_start_mysql", True)))
        ttk.Checkbutton(db, text="Auto-start MySQL if it is offline", variable=self.auto_mysql_var).grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 2))

        info = ttk.Frame(db, style="Panel.TFrame")
        info.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        ttk.Label(info, text="Accounts", style="Muted.Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(info, textvariable=self.db_accounts_var, style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 22))
        ttk.Label(info, text="MySQL", style="Muted.Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(info, textvariable=self.db_version_var, style="Panel.TLabel").grid(row=0, column=3, sticky="w")

        db_buttons = ttk.Frame(db, style="Panel.TFrame")
        db_buttons.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(db_buttons, text="REFRESH", command=self.refresh_database).pack(side="left")
        ttk.Button(db_buttons, text="START MYSQL", command=self.start_mysql_service).pack(side="left", padx=8)
        ttk.Button(db_buttons, text="CREATE / REPAIR SCHEMA", command=self.initialize_schema).pack(side="left")
        self.db_detail_label = tk.Label(db, textvariable=self.db_detail_var, bg=PANEL, fg=MUTED, font=("Consolas", 8), justify="left", anchor="w", wraplength=470)
        self.db_detail_label.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        self.server_status_var = tk.StringVar(value="● STOPPED")
        self.server_players_var = tk.StringVar(value="0 / 64")
        self.server_name_var = tk.StringVar(value=str(self.config["server_name"]))
        self.server_port_var = tk.StringVar(value=str(self.config["port"]))
        self.max_players_var = tk.StringVar(value=str(self.config["max_players"]))
        self.traffic_cars_var = tk.StringVar(value=str(self.config.get("traffic_cars", TRAFFIC_DEFAULT_COUNT)))
        self.map_id_var = tk.StringVar(value=str(self.config["map_id"]))
        self.map_file_var = tk.StringVar(value=str(self.config.get("map_file", "")))
        self.discovery_var = tk.BooleanVar(value=bool(self.config["lan_discovery"]))

        ttk.Label(server, text="Status", style="Muted.Panel.TLabel").grid(row=1, column=0, sticky="w")
        self.server_status_label = tk.Label(server, textvariable=self.server_status_var, bg=PANEL, fg=MUTED, font=("Consolas", 11, "bold"))
        self.server_status_label.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(server, text="Players", style="Muted.Panel.TLabel").grid(row=1, column=2, sticky="e", padx=(12, 6))
        ttk.Label(server, textvariable=self.server_players_var, style="Panel.TLabel").grid(row=1, column=3, sticky="w")

        ttk.Label(server, text="Name", style="Muted.Panel.TLabel").grid(row=2, column=0, sticky="w")
        self.server_name_entry = self._entry(server, self.server_name_var)
        self.server_name_entry.grid(row=2, column=1, columnspan=3, sticky="ew", pady=3)

        ttk.Label(server, text="Port", style="Muted.Panel.TLabel").grid(row=3, column=0, sticky="w")
        self.server_port_entry = self._entry(server, self.server_port_var, width=10)
        self.server_port_entry.grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(server, text="Max players", style="Muted.Panel.TLabel").grid(row=3, column=2, sticky="e", padx=(12, 6))
        self.max_players_entry = self._entry(server, self.max_players_var, width=8)
        self.max_players_entry.grid(row=3, column=3, sticky="w", pady=3)

        ttk.Label(server, text="Traffic cars", style="Muted.Panel.TLabel").grid(row=4, column=0, sticky="w")
        self.traffic_cars_entry = self._entry(server, self.traffic_cars_var, width=8)
        self.traffic_cars_entry.grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(server, text="server-authoritative AI", style="Muted.Panel.TLabel").grid(row=4, column=2, columnspan=2, sticky="w", padx=(12, 0))

        ttk.Label(server, text="Map", style="Muted.Panel.TLabel").grid(row=5, column=0, sticky="w")
        map_values = list(MAPS.keys())
        self.map_combo = ttk.Combobox(server, values=map_values, textvariable=self.map_id_var, state="readonly")
        self.map_combo.grid(row=5, column=1, columnspan=3, sticky="ew", pady=3)

        ttk.Label(server, text="Portable .map", style="Muted.Panel.TLabel").grid(row=6, column=0, sticky="w")
        self.map_file_entry = self._entry(server, self.map_file_var)
        self.map_file_entry.grid(row=6, column=1, columnspan=2, sticky="ew", pady=3)
        self.map_file_button = ttk.Button(server, text="BROWSE", command=self._browse_map_file)
        self.map_file_button.grid(row=6, column=3, sticky="ew", padx=(6,0), pady=3)

        self.discovery_check = ttk.Checkbutton(server, text="Advertise this server on the LAN", variable=self.discovery_var)
        self.discovery_check.grid(row=7, column=0, columnspan=4, sticky="w", pady=(8, 2))

        self.map_description_var = tk.StringVar()
        self.map_description_label = tk.Label(server, textvariable=self.map_description_var, bg=PANEL, fg=MUTED, font=("Consolas", 8), justify="left", anchor="w", wraplength=470)
        self.map_description_label.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(6, 8))
        self.map_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_map_description())
        self.map_file_var.trace_add("write", lambda *_: self._update_map_description())
        self._update_map_description()

        server_buttons = ttk.Frame(server, style="Panel.TFrame")
        server_buttons.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        self.start_button = ttk.Button(server_buttons, text="START SERVER", style="Accent.TButton", command=self.start_server)
        self.start_button.pack(side="left", fill="x", expand=True)
        self.stop_button = ttk.Button(server_buttons, text="STOP", command=self.stop_server, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))

        log_frame = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        log_frame.pack(fill="both", expand=True, pady=(16, 0))
        ttk.Label(log_frame, text="SERVER LOG", style="Header.Panel.TLabel").pack(anchor="w", pady=(0, 8))
        log_container = ttk.Frame(log_frame, style="Panel.TFrame")
        log_container.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_container,
            bg="#101213",
            fg="#d8dcdd",
            insertbackground=TEXT,
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._log("Server control ready. Database password is kept in memory only and is not written to server_config.csv.")

    def _browse_map_file(self) -> None:
        initial = self.map_file_var.get().strip()
        chosen = filedialog.askopenfilename(parent=self.root, title="Load portable OPEN NIGHT map", initialdir=str(Path(initial).parent) if initial else str(APP_DIR / "dev_tools" / "map_generator" / "exports"), filetypes=[("OPEN NIGHT portable map", "*.map"), ("All files", "*.*")])
        if chosen: self.map_file_var.set(chosen)

    def _update_map_description(self) -> None:
        portable = self.map_file_var.get().strip() if hasattr(self, "map_file_var") else ""
        if portable:
            self.map_description_var.set(f"PORTABLE MAP: {portable}\nServer will validate it and distribute missing map data/textures into each client's local cache.")
            return
        cfg = MAPS.get(self.map_id_var.get(), MAPS[DEFAULT_MAP_ID])
        self.map_description_var.set(f"{cfg['name']}: {cfg['description']}")

    def _log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {text.rstrip()}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _database_config(self) -> DatabaseConfig:
        try:
            port = int(self.db_port_var.get().strip())
        except ValueError as exc:
            raise ValueError("MySQL port must be a whole number.") from exc
        return DatabaseConfig(
            host=self.db_host_var.get().strip() or "127.0.0.1",
            port=port,
            database=self.db_name_var.get().strip() or "pymmo",
            user=self.db_user_var.get().strip() or "root",
            password=self.db_password_var.get(),
        )

    def _collect_config(self) -> dict:
        try:
            port = int(self.server_port_var.get().strip())
            max_players = int(self.max_players_var.get().strip())
            traffic_cars = int(self.traffic_cars_var.get().strip())
            db_port = int(self.db_port_var.get().strip())
        except ValueError as exc:
            raise ValueError("Ports, maximum players, and traffic cars must be whole numbers.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("Game port must be between 1 and 65535.")
        if not 1 <= max_players <= 2000:
            raise ValueError("Maximum players must be between 1 and 2000.")
        if not 0 <= traffic_cars <= 120:
            raise ValueError("Traffic cars must be between 0 and 120.")
        if not 1 <= db_port <= 65535:
            raise ValueError("MySQL port must be between 1 and 65535.")
        map_id = self.map_id_var.get()
        map_file = self.map_file_var.get().strip()
        if map_file:
            mp = Path(map_file).expanduser()
            if mp.suffix.lower() != ".map" or not mp.is_file():
                raise ValueError("Portable map must be an existing .map file.")
            map_file = str(mp.resolve())
        elif map_id not in MAPS:
            raise ValueError("Select a valid map.")
        return {
            "server_name": self.server_name_var.get().strip() or "Python MMO Server",
            "port": port,
            "max_players": max_players,
            "traffic_cars": traffic_cars,
            "map_id": map_id,
            "map_file": map_file,
            "lan_discovery": bool(self.discovery_var.get()),
            "db_host": self.db_host_var.get().strip() or "127.0.0.1",
            "db_port": db_port,
            "db_name": self.db_name_var.get().strip() or "pymmo",
            "db_user": self.db_user_var.get().strip() or "root",
            "db_password": self.db_password_var.get(),
            "mysql_service": self.mysql_service_var.get().strip(),
            "auto_start_mysql": bool(self.auto_mysql_var.get()),
        }

    def refresh_database(self, auto_start_on_fail: bool = False) -> None:
        self.db_status_var.set("● CHECKING")
        self.db_status_label.configure(fg=WARN)
        self.db_detail_var.set("Checking MySQL...")
        try:
            config = self._database_config()
        except ValueError as exc:
            self.db_status_var.set("● CONFIG ERROR")
            self.db_status_label.configure(fg=BAD)
            self.db_detail_var.set(str(exc))
            return

        def worker() -> None:
            db = InventoryDatabase(config)
            try:
                status = db.status()
                status["auto_start_on_fail"] = auto_start_on_fail
                self.db_result_queue.put(status)
            except Exception as exc:
                self.db_result_queue.put({
                    "online": False,
                    "error": mysql_error_text(exc),
                    "errno": getattr(exc, "errno", None),
                    "auto_start_on_fail": auto_start_on_fail,
                })

        threading.Thread(target=worker, daemon=True).start()

    def _periodic_db_refresh(self) -> None:
        if self._closing:
            return
        self.refresh_database(auto_start_on_fail=False)
        self.root.after(10000, self._periodic_db_refresh)

    def initialize_schema(self) -> None:
        try:
            config = self._database_config()
        except ValueError as exc:
            messagebox.showerror("Database configuration", str(exc), parent=self.root)
            return
        self._log("Creating/checking MySQL database schema...")

        def worker() -> None:
            try:
                db = InventoryDatabase(config)
                db.initialize()
                status = db.status()
                status["schema_initialized"] = True
                self.db_result_queue.put(status)
            except Exception as exc:
                self.db_result_queue.put({"online": False, "error": mysql_error_text(exc), "schema_initialized": True})

        threading.Thread(target=worker, daemon=True).start()

    def _detect_service_async(self) -> None:
        if os.name != "nt":
            return

        def worker() -> None:
            services = detect_mysql_services()
            if services:
                self.service_result_queue.put((True, "DETECTED:" + "|".join(services)))

        threading.Thread(target=worker, daemon=True).start()

    def start_mysql_service(self, then_refresh: bool = True) -> None:
        service = self.mysql_service_var.get().strip()
        try:
            db_config = self._database_config()
        except ValueError as exc:
            self.db_detail_var.set(str(exc))
            return
        self._log(f"Attempting to start MySQL Windows service {service or '(auto-detect)'}...")

        def worker() -> None:
            ok, message = start_windows_service(service)
            self.service_result_queue.put((ok, message))
            if ok and then_refresh:
                time.sleep(1.2)
                try:
                    status = InventoryDatabase(db_config).status()
                    self.db_result_queue.put(status)
                except Exception as exc:
                    self.db_result_queue.put({"online": False, "error": mysql_error_text(exc)})

        threading.Thread(target=worker, daemon=True).start()

    def start_server(self) -> None:
        if self.server_process and self.server_process.poll() is None:
            return
        try:
            cfg = self._collect_config()
        except ValueError as exc:
            messagebox.showerror("Server configuration", str(exc), parent=self.root)
            return

        # Ensure schema synchronously in a worker to keep the UI responsive.
        self.start_button.configure(state="disabled")
        self.server_status_var.set("● STARTING")
        self.server_status_label.configure(fg=WARN)
        self._log("Checking database and schema before server launch...")

        def worker() -> None:
            db_cfg = DatabaseConfig(
                host=cfg["db_host"], port=cfg["db_port"], database=cfg["db_name"],
                user=cfg["db_user"], password=cfg["db_password"],
            )
            db = InventoryDatabase(db_cfg)
            try:
                try:
                    db.status()
                except Exception as first_exc:
                    errno = getattr(first_exc, "errno", None)
                    connection_failure = errno in (2002, 2003) or "can't connect" in str(first_exc).lower() or "connection refused" in str(first_exc).lower()
                    if cfg["auto_start_mysql"] and connection_failure:
                        ok, msg = start_windows_service(cfg["mysql_service"])
                        self.server_output_queue.put("[launcher] " + msg)
                        if not ok:
                            raise first_exc
                        time.sleep(1.2)
                    else:
                        raise
                db.initialize()
                self.server_output_queue.put("__LAUNCH_SERVER__" + json.dumps(cfg))
            except Exception as exc:
                self.server_output_queue.put("__LAUNCH_ERROR__" + mysql_error_text(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_server_process(self, cfg: dict) -> None:
        _save_config(cfg)
        self.config.update({k: v for k, v in cfg.items() if k != "db_password"})
        env = os.environ.copy()
        env["PYMMO_DB_PASSWORD"] = cfg["db_password"]
        env["PYTHONUNBUFFERED"] = "1"
        args = [
            sys.executable, "-u", str(APP_DIR / "server.py"),
            "--name", cfg["server_name"],
            "--port", str(cfg["port"]),
            "--max-players", str(cfg["max_players"]),
            "--traffic", str(cfg["traffic_cars"]),
            "--map", cfg["map_id"],
            "--db-host", cfg["db_host"],
            "--db-port", str(cfg["db_port"]),
            "--db-name", cfg["db_name"],
            "--db-user", cfg["db_user"],
        ]
        if cfg.get("map_file"):
            args.extend(["--map-file", cfg["map_file"]])
        if not cfg["lan_discovery"]:
            args.append("--no-discovery")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:
            self.server_process = subprocess.Popen(
                args,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                creationflags=creationflags,
            )
        except Exception as exc:
            self._log(f"Could not launch server: {exc}")
            self.server_status_var.set("● START FAILED")
            self.server_status_label.configure(fg=BAD)
            self.start_button.configure(state="normal")
            return

        self.server_running = True
        self.server_players = 0
        self.server_players_var.set(f"0 / {cfg['max_players']}")
        self.server_status_var.set("● RUNNING")
        self.server_status_label.configure(fg=GOOD)
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._set_server_inputs_enabled(False)
        map_label = Path(cfg["map_file"]).name if cfg.get("map_file") else MAPS[cfg["map_id"]]["name"]
        self._log(f"Launched {cfg['server_name']} on port {cfg['port']} ({map_label}) with {cfg['traffic_cars']} civilian cars.")

        def reader() -> None:
            assert self.server_process is not None
            if self.server_process.stdout is not None:
                for line in self.server_process.stdout:
                    self.server_output_queue.put(line.rstrip("\r\n"))
            code = self.server_process.wait()
            self.server_output_queue.put(f"__PROCESS_EXIT__{code}")

        threading.Thread(target=reader, daemon=True).start()

    def stop_server(self) -> None:
        proc = self.server_process
        if proc is None or proc.poll() is not None:
            self._server_stopped()
            return
        self._log("Stopping game server...")
        try:
            if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        def killer() -> None:
            try:
                proc.wait(timeout=4.0)
            except subprocess.TimeoutExpired:
                proc.kill()

        threading.Thread(target=killer, daemon=True).start()

    def _set_server_inputs_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (self.server_name_entry, self.server_port_entry, self.max_players_entry, self.traffic_cars_entry, self.map_file_entry):
            widget.configure(state=state)
        self.map_combo.configure(state="readonly" if enabled else "disabled")
        self.map_file_button.configure(state="normal" if enabled else "disabled")
        self.discovery_check.configure(state=state)

    def _server_stopped(self) -> None:
        self.server_running = False
        self.server_players = 0
        self.server_status_var.set("● STOPPED")
        self.server_status_label.configure(fg=MUTED)
        max_players = self.max_players_var.get().strip() or "?"
        self.server_players_var.set(f"0 / {max_players}")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._set_server_inputs_enabled(True)

    def _handle_server_line(self, line: str) -> None:
        if line.startswith("__LAUNCH_SERVER__"):
            try:
                cfg = json.loads(line[len("__LAUNCH_SERVER__"):])
            except json.JSONDecodeError as exc:
                self._log(f"Launcher config error: {exc}")
                self.start_button.configure(state="normal")
                return
            self._launch_server_process(cfg)
            return
        if line.startswith("__LAUNCH_ERROR__"):
            error = line[len("__LAUNCH_ERROR__"):]
            self._log("Database startup failed: " + error)
            self.server_status_var.set("● DB OFFLINE")
            self.server_status_label.configure(fg=BAD)
            self.start_button.configure(state="normal")
            messagebox.showerror("Cannot start server", "MySQL/schema check failed:\n\n" + error, parent=self.root)
            return
        if line.startswith("__PROCESS_EXIT__"):
            code = line[len("__PROCESS_EXIT__"):]
            self._log(f"Game server process exited with code {code}.")
            self._server_stopped()
            return
        if line.startswith("@STATUS "):
            try:
                status = json.loads(line[8:])
                players = int(status.get("players", 0))
                maximum = int(status.get("max_players", int(self.max_players_var.get() or 0)))
                self.server_players = players
                self.server_players_var.set(f"{players} / {maximum}")
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            return
        self._log(line)

    def _handle_db_result(self, result: dict) -> None:
        online = bool(result.get("online"))
        if online:
            schema_ready = bool(result.get("schema_ready"))
            self.db_status_var.set("● ONLINE" if schema_ready else "● ONLINE / SCHEMA MISSING")
            self.db_status_label.configure(fg=GOOD if schema_ready else WARN)
            count = result.get("account_count")
            self.db_accounts_var.set(str(count) if count is not None else "—")
            self.db_version_var.set(str(result.get("server_version") or "—"))
            detail = "MySQL is reachable."
            if not schema_ready:
                detail += " Database/tables are not ready; use CREATE / REPAIR SCHEMA or Start Server."
            self.db_detail_var.set(detail)
            if result.get("schema_initialized"):
                self._log("MySQL schema is ready.")
        else:
            self.db_status_var.set("● OFFLINE")
            self.db_status_label.configure(fg=BAD)
            self.db_accounts_var.set("—")
            self.db_version_var.set("—")
            error = str(result.get("error") or "MySQL is not reachable.")
            self.db_detail_var.set(error)
            errno = result.get("errno")
            connection_failure = errno in (2002, 2003) or "can't connect" in error.lower() or "connection refused" in error.lower()
            if result.get("auto_start_on_fail") and self.auto_mysql_var.get() and connection_failure:
                self._log("MySQL is not accepting connections; auto-start is enabled.")
                self.start_mysql_service(then_refresh=True)

    def _drain_queues(self) -> None:
        while True:
            try:
                line = self.server_output_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_server_line(line)

        while True:
            try:
                result = self.db_result_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_db_result(result)

        while True:
            try:
                ok, message = self.service_result_queue.get_nowait()
            except queue.Empty:
                break
            if ok and message.startswith("DETECTED:"):
                services = message[len("DETECTED:"):].split("|")
                current = self.mysql_service_var.get().strip()
                if services and (not current or current == DEFAULT_SERVICE) and current not in services:
                    self.mysql_service_var.set(services[0])
                    self._log(f"Detected MySQL Windows service: {services[0]}")
            else:
                self._log(("MySQL service: " if ok else "MySQL service error: ") + message)

        if self.server_process is not None and self.server_process.poll() is not None and self.server_running:
            self._server_stopped()

        if not self._closing:
            self.root.after(120, self._drain_queues)

    def _on_close(self) -> None:
        self._closing = True
        try:
            cfg = self._collect_config()
            _save_config(cfg)
        except Exception:
            pass
        proc = self.server_process
        if proc is not None and proc.poll() is None:
            if not messagebox.askyesno("Server running", "Stop the game server and close the control panel?", parent=self.root):
                self._closing = False
                self.root.after(120, self._drain_queues)
                return
            try:
                proc.terminate()
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def launch_server_manager() -> None:
    ServerLauncher().run()


if __name__ == "__main__":
    launch_server_manager()
