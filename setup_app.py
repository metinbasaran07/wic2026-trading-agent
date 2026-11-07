#!/usr/bin/env python3
"""
WIC 2026 Trading Agent - Setup App
Single window, fill in the blanks, click Save.
Supports: OpenRouter, Anthropic, OpenAI, Azure, Gemini, Ollama, Team Key
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT_DIR = Path(__file__).parent.resolve()

# Provider configurations
PROVIDERS = [
    ("openrouter", "OpenRouter (recommended)", "https://openrouter.ai/keys"),
    ("anthropic", "Anthropic (Claude direct)", "https://console.anthropic.com/"),
    ("openai", "OpenAI (GPT direct)", "https://platform.openai.com/"),
    ("azure", "Azure OpenAI", "https://azure.microsoft.com/"),
    ("gemini", "Google Gemini", "https://aistudio.google.com/"),
    ("ollama", "Ollama (local)", "https://ollama.ai/"),
    ("team_key", "Team Key (competition)", "Provided by organizers"),
    ("mock", "Mock (testing only)", "No API needed"),
]

PROVIDER_FIELDS = {
    "openrouter": ["api_key", "model"],
    "anthropic": ["api_key", "model"],
    "openai": ["api_key", "base_url", "model"],
    "azure": ["api_key", "endpoint", "api_version", "deployment"],
    "gemini": ["api_key", "model"],
    "ollama": ["base_url", "model"],
    "team_key": ["api_key", "base_url", "model"],
    "mock": [],
}

FIELD_LABELS = {
    "api_key": "API Key",
    "model": "Model",
    "base_url": "Base URL",
    "endpoint": "Endpoint",
    "api_version": "API Version",
    "deployment": "Deployment Name",
}


class SetupApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("WIC 2026 Trading Agent - Setup")
        self.root.geometry("580x750")
        self.root.resizable(False, False)
        self.root.minsize(580, 750)

        self.center_window()

        # Variables - core
        self.vars = {
            "mode": tk.StringVar(value="dev"),
            "llm_provider": tk.StringVar(value="openrouter"),
            "ib_user": tk.StringVar(),
            "ib_password": tk.StringVar(),
            "ib_mode": tk.StringVar(value="paper"),
            "symbols": tk.StringVar(value="SPY,QQQ,AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,BAC,GS,MS"),
            "max_position": tk.DoubleVar(value=10.0),
            "risk_per_trade": tk.DoubleVar(value=1.0),
            "max_drawdown": tk.DoubleVar(value=5.0),
            "review_interval": tk.IntVar(value=60),
            "dashboard_port": tk.IntVar(value=8080),
        }

        # Provider-specific variables (created dynamically)
        self.provider_vars = {}

        self.status_var = tk.StringVar(value="Select LLM provider, fill in fields, then click Save")
        self.saving = False

        self.setup_styles()
        self.create_widgets()
        self.load_existing_config()
        self.on_provider_change()  # Initialize provider fields

    def center_window(self):
        self.root.update_idletasks()
        w, h = 580, 750
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # macOS: aggressive window focus
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.focus_force()
        self.root.after(50, lambda: self.root.attributes('-topmost', False))
        self.root.after(100, lambda: self.root.lift())
        self.root.after(150, lambda: self.root.focus_force())

        # Also try macOS-specific
        try:
            import subprocess
            subprocess.run(['osascript', '-e', 'tell application "System Events" to set frontmost of process "Python" to true'], capture_output=True)
        except:
            pass

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("aqua")

        style.configure("Title.TLabel", font=("SF Pro Display", 16, "bold"))
        style.configure("Section.TLabel", font=("SF Pro Display", 12, "bold"))
        style.configure("Hint.TLabel", font=("SF Pro", 9), foreground="gray")
        style.configure("Accent.TButton", font=("SF Pro", 11, "bold"))
        style.configure("Card.TFrame", background="#f5f5f7")
        style.configure("Provider.TCombobox", font=("SF Pro", 10))

    def create_widgets(self):
        # Main container with padding
        container = ttk.Frame(self.root, style="Card.TFrame")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        # Scrollable canvas
        canvas = tk.Canvas(container, highlightthickness=0, bg="#f5f5f7")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.content = ttk.Frame(canvas, style="Card.TFrame")

        self.content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Also bind to content frame for scrolling
        self.content.bind("<MouseWheel>", _on_mousewheel)

        main = self.content
        main.columnconfigure(1, weight=1)

        row = 0

        # Header
        header = ttk.Frame(main)
        header.grid(row=row, column=0, columnspan=2, pady=(0, 20))
        ttk.Label(header, text="🏆 WIC 2026 Trading Agent", style="Title.TLabel").pack()
        ttk.Label(header, text="World Investment Competition - AI Agent Division", style="Hint.TLabel").pack()
        row += 1

        # --- Operating Mode ---
        row = self.add_section(main, row, "Operating Mode", [
            ("Development", "mode", "dev"),
            ("Competition Trial", "mode", "trial"),
            ("Competition Live", "mode", "live"),
        ], radio=True)

        # --- LLM Provider ---
        row = self.add_section(main, row, "LLM Provider", [
            ("Provider", "llm_provider", {"type": "combo", "values": [p[0] for p in PROVIDERS], "width": 35}),
        ], hint="Choose your LLM provider. OpenRouter recommended for development.")
        row += 1

        # Provider-specific fields container (dynamic)
        self.provider_frame = ttk.Frame(main)
        self.provider_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10)
        self.provider_frame.columnconfigure(1, weight=1)
        row += 1

        # --- Interactive Brokers ---
        row = self.add_section(main, row, "Interactive Brokers (Required)", [
            ("Username", "ib_user", {"width": 38}),
            ("Password", "ib_password", {"show": "•", "width": 38}),
            ("Mode", "ib_mode", {"type": "combo", "values": ["paper", "live"], "width": 36}),
        ], hint="Paper trading uses port 4002, Live uses 4001")

        # --- Trading Symbols ---
        row = self.add_section(main, row, "Trading Symbols", [
            ("Symbols (comma-separated)", "symbols", {"width": 48}),
        ])

        # --- Risk Management ---
        row = self.add_section(main, row, "Risk Management", [
            ("Max Position Size", "max_position", {"type": "scale", "from": 1, "to": 50, "suffix": "%"}),
            ("Risk Per Trade", "risk_per_trade", {"type": "scale", "from": 0.5, "to": 5, "step": 0.5, "suffix": "%"}),
            ("Max Daily Drawdown", "max_drawdown", {"type": "scale", "from": 1, "to": 20, "suffix": "%"}),
        ])

        # --- LLM Review ---
        row = self.add_section(main, row, "LLM Review Schedule", [
            ("Review Interval", "review_interval", {"type": "combo", "values": [15, 30, 60, 120, 240], "suffix": " min", "width": 36}),
        ])

        # Spacer
        ttk.Frame(main, height=20).grid(row=row, column=0, columnspan=2)
        row += 1

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=10, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.save_btn = ttk.Button(btn_frame, text="💾  Save Configuration", command=self.save_config, style="Accent.TButton")
        self.save_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5), ipady=8)

        self.start_btn = ttk.Button(btn_frame, text="▶️  Start Trading Agent", command=self.start_agent)
        self.start_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0), ipady=8)

        row += 1

        # Secondary buttons
        btn_frame2 = ttk.Frame(main)
        btn_frame2.grid(row=row, column=0, columnspan=2, pady=5, sticky="ew")
        btn_frame2.columnconfigure(0, weight=1)
        btn_frame2.columnconfigure(1, weight=1)
        btn_frame2.columnconfigure(2, weight=1)

        ttk.Button(btn_frame2, text="🌐 Open Dashboard", command=self.open_dashboard).grid(row=0, column=0, sticky="ew", padx=2, ipady=6)
        ttk.Button(btn_frame2, text="📊 Run Backtest", command=self.run_backtest).grid(row=0, column=1, sticky="ew", padx=2, ipady=6)
        ttk.Button(btn_frame2, text="📄 Generate Report", command=self.generate_report).grid(row=0, column=2, sticky="ew", padx=2, ipady=6)

        row += 1

        # Status bar
        status_frame = ttk.Frame(main)
        status_frame.grid(row=row, column=0, columnspan=2, pady=15, sticky="ew")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, style="Hint.TLabel", wraplength=540, justify="center")
        self.status_label.pack()

    def add_section(self, parent, row, title, fields, radio=False, hint=None):
        if row > 0:
            ttk.Separator(parent).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
            row += 1

        ttk.Label(parent, text=title, style="Section.TLabel").grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(row=row, column=1, sticky="w", pady=(0, 8))
            row += 1

        if radio:
            for label, var_name, value in fields:
                rb = ttk.Radiobutton(parent, text=label, variable=self.vars[var_name], value=value)
                rb.grid(row=row, column=1, sticky="w", pady=2)
                row += 1
        else:
            for field in fields:
                label_text, var_name, opts = field
                field_type = opts.get("type", "entry")
                width = opts.get("width", 38)

                ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)

                if field_type == "entry":
                    widget = ttk.Entry(parent, textvariable=self.vars[var_name], width=width, **{k: v for k, v in opts.items() if k not in ("type", "width")})
                elif field_type == "combo":
                    widget = ttk.Combobox(parent, textvariable=self.vars[var_name], values=opts.get("values", []), width=width, state="readonly", style="Provider.TCombobox")
                elif field_type == "scale":
                    frame = ttk.Frame(parent)
                    frame.grid(row=row, column=1, sticky="ew", pady=6)
                    frame.columnconfigure(0, weight=1)

                    var = self.vars[var_name]
                    scale = ttk.Scale(frame, variable=var, from_=opts.get("from", 0), to=opts.get("to", 100), orient="horizontal")
                    scale.grid(row=0, column=0, sticky="ew", padx=(0, 8))

                    val_label = ttk.Label(frame, text="", width=6, font=("SF Pro", 10, "bold"))
                    val_label.grid(row=0, column=1)

                    step = opts.get("step", 1)
                    suffix = opts.get("suffix", "")

                    def make_updater(v=var, lbl=val_label, s=step, suf=suffix):
                        def update(*_):
                            val = round(v.get() / s) * s
                            lbl.config(text=f"{val:g}{suf}")
                        return update

                    var.trace_add("write", make_updater())
                    make_updater()()
                    row += 1
                    continue

                widget.grid(row=row, column=1, sticky="ew", pady=6)
                row += 1

        return row

    def on_provider_change(self, *args):
        """Update provider-specific fields when provider changes."""
        provider = self.vars["llm_provider"].get()

        # Clear existing provider fields
        for widget in self.provider_frame.winfo_children():
            widget.destroy()

        # Get fields for this provider
        fields = PROVIDER_FIELDS.get(provider, [])

        if not fields:
            ttk.Label(self.provider_frame, text="No additional configuration needed", style="Hint.TLabel").grid(row=0, column=0, columnspan=2, pady=10)
            return

        # Create provider-specific variables
        for field in fields:
            var_name = f"{provider}_{field}"
            if field in ("api_key",):
                self.provider_vars[var_name] = tk.StringVar()
            elif field in ("model", "base_url", "endpoint", "api_version", "deployment"):
                # Set defaults
                defaults = {
                    "openrouter_model": "anthropic/claude-3.5-sonnet",
                    "anthropic_model": "claude-3-5-sonnet-20241022",
                    "openai_model": "gpt-4o",
                    "openai_base_url": "https://api.openai.com/v1",
                    "azure_api_version": "2024-02-15-preview",
                    "gemini_model": "gemini-1.5-pro",
                    "ollama_base_url": "http://localhost:11434/v1",
                    "ollama_model": "llama3.1:70b",
                    "team_key_model": "",
                }
                default = defaults.get(var_name, "")
                self.provider_vars[var_name] = tk.StringVar(value=default)
            else:
                self.provider_vars[var_name] = tk.StringVar()

        # Create UI fields
        for i, field in enumerate(fields):
            var_name = f"{provider}_{field}"
            label = FIELD_LABELS.get(field, field.replace("_", " ").title())

            ttk.Label(self.provider_frame, text=label).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=6)

            var = self.provider_vars[var_name]
            if field in ("api_key",):
                widget = ttk.Entry(self.provider_frame, textvariable=var, width=40, show="•")
            else:
                widget = ttk.Entry(self.provider_frame, textvariable=var, width=40)

            widget.grid(row=i, column=1, sticky="ew", pady=6)

            # Add hint for URL fields
            if field in ("base_url", "endpoint"):
                ttk.Label(self.provider_frame, text=f"Default: {var.get()}", style="Hint.TLabel").grid(row=i, column=2, sticky="w", padx=5)

    def load_existing_config(self):
        env_path = PROJECT_DIR / ".env"
        if not env_path.exists():
            return

        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")

                    key_map = {
                        "MODE": "mode",
                        "LLM_PROVIDER": "llm_provider",
                        "IB_USER": "ib_user",
                        "IB_PASSWORD": "ib_password",
                        "IB_TRADING_MODE": "ib_mode",
                        "DEFAULT_SYMBOLS": "symbols",
                        "MAX_POSITION_SIZE": "max_position",
                        "RISK_PER_TRADE": "risk_per_trade",
                        "MAX_DRAWDOWN": "max_drawdown",
                        "REVIEW_INTERVAL_MINUTES": "review_interval",
                        "DASHBOARD_PORT": "dashboard_port",
                    }

                    if key in key_map:
                        var_name = key_map[key]
                        if var_name in self.vars:
                            if var_name in ("max_position", "risk_per_trade", "max_drawdown"):
                                try:
                                    self.vars[var_name].set(float(val) * 100)
                                except:
                                    pass
                            else:
                                try:
                                    if isinstance(self.vars[var_name], tk.IntVar):
                                        self.vars[var_name].set(int(val))
                                    elif isinstance(self.vars[var_name], tk.DoubleVar):
                                        self.vars[var_name].set(float(val))
                                    else:
                                        self.vars[var_name].set(val)
                                except:
                                    pass

                    # Provider-specific fields
                    provider = self.vars.get("llm_provider", tk.StringVar(value="openrouter")).get()
                    prefix = f"{provider}_"
                    if key.startswith(prefix):
                        field = key[len(prefix):].lower()
                        var_name = f"{provider}_{field}"
                        if var_name in self.provider_vars:
                            self.provider_vars[var_name].set(val)

            self.status_var.set("✅ Loaded existing configuration")
            self.on_provider_change()  # Refresh UI with loaded values
        except Exception as e:
            self.status_var.set(f"⚠ Could not load config: {e}")

    def save_config(self):
        if self.saving:
            return

        self.saving = True
        self.save_btn.config(state="disabled", text="Saving...")
        self.status_var.set("Saving configuration...")

        def do_save():
            try:
                template_path = PROJECT_DIR / ".env.example"
                template = template_path.read_text() if template_path.exists() else ""

                lines = []
                for line in template.splitlines():
                    if line.strip() and not line.startswith("#"):
                        key = line.split("=")[0].strip()
                        val = self.get_env_value(key)
                        if val is not None:
                            lines.append(f"{key}={val}")
                        else:
                            lines.append(line)
                    else:
                        lines.append(line)

                (PROJECT_DIR / ".env").write_text("\n".join(lines))

                self.root.after(0, self.on_save_success)
            except Exception as e:
                self.root.after(0, lambda: self.on_save_error(str(e)))

        threading.Thread(target=do_save, daemon=True).start()

    def get_env_value(self, key):
        """Get value for env key from our vars"""
        # Core vars
        core_mapping = {
            "MODE": ("mode", str),
            "LLM_PROVIDER": ("llm_provider", str),
            "IB_USER": ("ib_user", str),
            "IB_PASSWORD": ("ib_password", str),
            "IB_TRADING_MODE": ("ib_mode", str),
            "DEFAULT_SYMBOLS": ("symbols", str),
            "MAX_POSITION_SIZE": ("max_position", lambda v: v / 100),
            "RISK_PER_TRADE": ("risk_per_trade", lambda v: v / 100),
            "MAX_DRAWDOWN": ("max_drawdown", lambda v: v / 100),
            "REVIEW_INTERVAL_MINUTES": ("review_interval", int),
            "DASHBOARD_PORT": ("dashboard_port", int),
        }

        if key in core_mapping:
            var_name, converter = core_mapping[key]
            if var_name in self.vars:
                raw = self.vars[var_name].get()
                if raw == "":
                    return None
                try:
                    return converter(raw)
                except:
                    return None

        # Provider-specific fields
        provider = self.vars["llm_provider"].get()
        prefix = f"{provider}_"
        if key.startswith(prefix):
            field = key[len(prefix):].lower()
            var_name = f"{provider}_{field}"
            if var_name in self.provider_vars:
                raw = self.provider_vars[var_name].get()
                if raw == "":
                    return None
                return raw

        return None

    def on_save_success(self):
        self.saving = False
        self.save_btn.config(state="normal", text="💾  Save Configuration")
        self.status_var.set("✅ Configuration saved! You can now start the agent.")
        messagebox.showinfo("Saved", "Configuration saved to .env\n\nYou can now click 'Start Trading Agent'")

    def on_save_error(self, error):
        self.saving = False
        self.save_btn.config(state="normal", text="💾  Save Configuration")
        self.status_var.set(f"❌ Save failed: {error}")
        messagebox.showerror("Error", f"Failed to save: {error}")

    def start_agent(self):
        env_path = PROJECT_DIR / ".env"
        if not env_path.exists():
            messagebox.showwarning("Not Configured", "Please save configuration first!")
            return

        if not messagebox.askyesno("Start Agent", "Start the trading agent?\n\nMake sure IB Gateway is running on port 4002 (paper) or 4001 (live)."):
            return

        self.status_var.set("Starting trading agent...")
        self.start_btn.config(state="disabled", text="Starting...")

        def run_agent():
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "src.main", "run"],
                    cwd=PROJECT_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                self.root.after(0, self.on_agent_started)
            except Exception as e:
                self.root.after(0, lambda: self.on_agent_error(str(e)))

        threading.Thread(target=run_agent, daemon=True).start()

    def on_agent_started(self):
        self.start_btn.config(state="normal", text="▶️  Start Trading Agent")
        self.status_var.set("✅ Trading agent started in background! Opening dashboard...")
        self.open_dashboard()

    def on_agent_error(self, error):
        self.start_btn.config(state="normal", text="▶️  Start Trading Agent")
        self.status_var.set(f"❌ Failed to start: {error}")
        messagebox.showerror("Error", f"Could not start agent: {error}")

    def open_dashboard(self):
        import webbrowser
        port = self.vars["dashboard_port"].get()
        webbrowser.open(f"http://localhost:{port}")
        self.status_var.set(f"Opened dashboard at http://localhost:{port}")

    def run_backtest(self):
        dialog = BacktestDialog(self.root)
        if dialog.result:
            symbol, days = dialog.result
            self.status_var.set(f"Running backtest on {symbol}...")
            threading.Thread(
                target=lambda: subprocess.run(
                    [sys.executable, "-m", "src.main", "backtest", symbol, "--days", str(days)],
                    cwd=PROJECT_DIR
                ),
                daemon=True
            ).start()

    def generate_report(self):
        self.status_var.set("Generating pre-report...")
        threading.Thread(
            target=lambda: subprocess.run(
                [sys.executable, "-m", "src.main", "generate-pre-report"],
                cwd=PROJECT_DIR
            ),
            daemon=True
        ).start()


class BacktestDialog:
    def __init__(self, parent):
        self.result = None

        self.win = tk.Toplevel(parent)
        self.win.title("Run Backtest")
        self.win.geometry("360x200")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        self.win.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 180
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 100
        self.win.geometry(f"+{x}+{y}")

        ttk.Label(self.win, text="Run Backtest", font=("SF Pro Display", 14, "bold")).pack(pady=15)

        ttk.Label(self.win, text="Symbol:").pack(anchor="w", padx=30)
        self.symbol_var = tk.StringVar(value="SPY")
        ttk.Entry(self.win, textvariable=self.symbol_var, width=30).pack(fill="x", padx=30, pady=(0, 10))

        ttk.Label(self.win, text="Days of History:").pack(anchor="w", padx=30)
        self.days_var = tk.IntVar(value=30)
        ttk.Spinbox(self.win, from_=7, to=365, textvariable=self.days_var, width=28).pack(fill="x", padx=30, pady=(0, 15))

        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill="x", padx=30, pady=5)
        ttk.Button(btn_frame, text="Cancel", command=self.win.destroy).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Run", command=self.on_run).pack(side="right")

    def on_run(self):
        symbol = self.symbol_var.get().strip().upper()
        days = self.days_var.get()
        if symbol:
            self.result = (symbol, days)
        self.win.destroy()


def main():
    root = tk.Tk()

    try:
        root.tk.call("tk", "scaling", 1.5)
    except:
        pass

    app = SetupApp(root)

    def on_close():
        root.quit()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    root.mainloop()


if __name__ == "__main__":
    main()