#!/usr/bin/env python3
"""
WIC 2026 Trading Agent - Simple Setup
Single file, no scrollbars, no canvas, just works.
"""

import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT_DIR = Path(__file__).parent.resolve()


def load_env():
    """Load existing .env if present"""
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return {}
    data = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def save_env(data):
    """Save to .env using template"""
    template_path = PROJECT_DIR / ".env.example"
    template = template_path.read_text() if template_path.exists() else ""
    lines = []
    for line in template.splitlines():
        if line.strip() and not line.startswith("#"):
            key = line.split("=")[0].strip()
            if key in data:
                lines.append(f"{key}={data[key]}")
            else:
                lines.append(line)
        else:
            lines.append(line)
    (PROJECT_DIR / ".env").write_text("\n".join(lines))


class SetupApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WIC 2026 Trading Agent - Setup")
        self.root.geometry("520x680")
        self.root.resizable(False, False)

        # Variables
        self.vars = {}
        self.provider_vars = {}
        self.existing = load_env()

        self.build_ui()
        self.center_and_focus()
        self.load_values()

    def center_and_focus(self):
        """Center window and force focus on macOS"""
        self.root.update_idletasks()
        w, h = 520, 680
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # macOS focus
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.focus_force()
        self.root.after(50, lambda: self.root.attributes('-topmost', False))

    def build_ui(self):
        # Main frame with padding
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill="both", expand=True)

        # Title
        ttk.Label(main, text="🏆 WIC 2026 Trading Agent", font=("SF Pro Display", 18, "bold")).pack(pady=(0, 5))
        ttk.Label(main, text="World Investment Competition - AI Agent Division", foreground="gray").pack(pady=(0, 20))

        # Notebook for sections
        nb = ttk.Notebook(main)
        nb.pack(fill="both", expand=True)

        # --- Tab 1: LLM ---
        tab_llm = ttk.Frame(nb, padding=15)
        nb.add(tab_llm, text="LLM Provider")

        ttk.Label(tab_llm, text="Provider", font=("SF Pro", 11, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.vars["llm_provider"] = tk.StringVar(value="openrouter")
        provider_combo = ttk.Combobox(tab_llm, textvariable=self.vars["llm_provider"],
            values=["openrouter", "anthropic", "openai", "azure", "gemini", "ollama", "team_key", "mock"],
            state="readonly", width=30)
        provider_combo.grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0))
        provider_combo.bind("<<ComboboxSelected>>", lambda e: self.update_provider_fields())
        tab_llm.columnconfigure(1, weight=1)

        # Provider-specific fields frame
        self.provider_frame = ttk.Frame(tab_llm)
        self.provider_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=10)
        self.provider_frame.columnconfigure(1, weight=1)

        # --- Tab 2: IB & Trading ---
        tab_trade = ttk.Frame(nb, padding=15)
        nb.add(tab_trade, text="IB & Trading")

        row = 0
        for label, key, opts in [
            ("Mode", "mode", {"type": "combo", "values": ["dev", "trial", "live"]}),
            ("IB Username", "ib_user", {}),
            ("IB Password", "ib_password", {"show": "•"}),
            ("IB Mode", "ib_mode", {"type": "combo", "values": ["paper", "live"]}),
            ("Symbols", "symbols", {"width": 40}),
        ]:
            ttk.Label(tab_trade, text=label).grid(row=row, column=0, sticky="w", pady=6)
            var = tk.StringVar()
            self.vars[key] = var
            if opts.get("type") == "combo":
                w = ttk.Combobox(tab_trade, textvariable=var, values=opts["values"], state="readonly", width=28)
            elif opts.get("show"):
                w = ttk.Entry(tab_trade, textvariable=var, show=opts["show"], width=30)
            else:
                w = ttk.Entry(tab_trade, textvariable=var, width=opts.get("width", 30))
            w.grid(row=row, column=1, sticky="ew", pady=6, padx=(10, 0))
            row += 1

        ttk.Label(tab_trade, text="Risk Management", font=("SF Pro", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(15, 5))
        row += 1

        for label, key, opts in [
            ("Max Position %", "max_position", {"type": "scale", "from": 1, "to": 50, "step": 1}),
            ("Risk Per Trade %", "risk_per_trade", {"type": "scale", "from": 0.5, "to": 5, "step": 0.5}),
            ("Max Drawdown %", "max_drawdown", {"type": "scale", "from": 1, "to": 20, "step": 1}),
        ]:
            ttk.Label(tab_trade, text=label).grid(row=row, column=0, sticky="w", pady=6)
            var = tk.DoubleVar()
            self.vars[key] = var
            w = ttk.Scale(tab_trade, variable=var, from_=opts["from"], to=opts["to"], orient="horizontal")
            w.grid(row=row, column=1, sticky="ew", pady=6, padx=(10, 0))
            # Value label
            val = ttk.Label(tab_trade, text="", width=6)
            val.grid(row=row, column=2, padx=5)
            step = opts.get("step", 1)
            var.trace_add("write", lambda *_, v=var, l=val, s=step: l.config(text=f"{round(v.get()/s)*s:g}"))
            row += 1

        ttk.Label(tab_trade, text="Review Interval", font=("SF Pro", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(15, 5))
        row += 1
        ttk.Label(tab_trade, text="Minutes").grid(row=row, column=0, sticky="w", pady=6)
        var = tk.IntVar(value=60)
        self.vars["review_interval"] = var
        ttk.Combobox(tab_trade, textvariable=var, values=[15, 30, 60, 120, 240], state="readonly", width=28).grid(row=row, column=1, sticky="ew", pady=6, padx=(10, 0))

        tab_trade.columnconfigure(1, weight=1)

        # --- Buttons ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=20)

        ttk.Button(btn_frame, text="💾 Save Configuration", command=self.save, style="Accent.TButton").pack(side="left", expand=True, fill="x", padx=5, ipady=8)
        ttk.Button(btn_frame, text="▶️ Start Trading Agent", command=self.start_agent).pack(side="left", expand=True, fill="x", padx=5, ipady=8)

        # Secondary buttons
        btn_frame2 = ttk.Frame(main)
        btn_frame2.pack(fill="x", pady=5)

        ttk.Button(btn_frame2, text="🌐 Open Dashboard", command=self.open_dashboard).pack(side="left", expand=True, fill="x", padx=2, ipady=6)
        ttk.Button(btn_frame2, text="📊 Run Backtest", command=self.run_backtest).pack(side="left", expand=True, fill="x", padx=2, ipady=6)
        ttk.Button(btn_frame2, text="📄 Generate Report", command=self.generate_report).pack(side="left", expand=True, fill="x", padx=2, ipady=6)

        # Style
        style = ttk.Style()
        style.configure("Accent.TButton", font=("SF Pro", 11, "bold"))

        # Initialize provider fields
        self.update_provider_fields()

    def update_provider_fields(self):
        """Clear and rebuild provider-specific fields"""
        for w in self.provider_frame.winfo_children():
            w.destroy()

        provider = self.vars["llm_provider"].get()
        fields = {
            "openrouter": [("API Key", "openrouter_api_key", True), ("Model", "openrouter_model", False)],
            "anthropic": [("API Key", "anthropic_api_key", True), ("Model", "anthropic_model", False)],
            "openai": [("API Key", "openai_api_key", True), ("Base URL", "openai_base_url", False), ("Model", "openai_model", False)],
            "azure": [("API Key", "azure_api_key", True), ("Endpoint", "azure_endpoint", False), ("API Version", "azure_api_version", False), ("Deployment", "azure_deployment", False)],
            "gemini": [("API Key", "gemini_api_key", True), ("Model", "gemini_model", False)],
            "ollama": [("Base URL", "ollama_base_url", False), ("Model", "ollama_model", False)],
            "team_key": [("API Key", "team_key_api_key", True), ("Base URL", "team_key_base_url", False), ("Model", "team_key_model", False)],
            "mock": [],
        }

        defaults = {
            "openrouter_model": "anthropic/claude-3.5-sonnet",
            "anthropic_model": "claude-3-5-sonnet-20241022",
            "openai_model": "gpt-4o",
            "openai_base_url": "https://api.openai.com/v1",
            "azure_api_version": "2024-02-15-preview",
            "gemini_model": "gemini-1.5-pro",
            "ollama_base_url": "http://localhost:11434/v1",
            "ollama_model": "llama3.1:70b",
        }

        for i, (label, key, is_password) in enumerate(fields.get(provider, [])):
            ttk.Label(self.provider_frame, text=label).grid(row=i, column=0, sticky="w", pady=5)
            var = tk.StringVar()
            self.provider_vars[key] = var
            if is_password:
                ttk.Entry(self.provider_frame, textvariable=var, show="•", width=40).grid(row=i, column=1, sticky="ew", pady=5, padx=(10, 0))
            else:
                ttk.Entry(self.provider_frame, textvariable=var, width=40).grid(row=i, column=1, sticky="ew", pady=5, padx=(10, 0))
            # Set default
            if key in defaults:
                var.set(defaults[key])

        self.provider_frame.columnconfigure(1, weight=1)

    def load_values(self):
        """Load from existing .env"""
        # Core vars
        mapping = {
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
        }
        for env_key, var_key in mapping.items():
            if env_key in self.existing and var_key in self.vars:
                val = self.existing[env_key]
                try:
                    if var_key in ("max_position", "risk_per_trade", "max_drawdown"):
                        self.vars[var_key].set(float(val) * 100)
                    elif var_key == "review_interval":
                        self.vars[var_key].set(int(val))
                    else:
                        self.vars[var_key].set(val)
                except:
                    pass

        # Provider-specific
        provider = self.vars.get("llm_provider", tk.StringVar(value="openrouter")).get()
        prefix = f"{provider}_"
        for env_key, val in self.existing.items():
            if env_key.startswith(prefix):
                field = env_key[len(prefix):].lower()
                full_key = f"{provider}_{field}"
                if full_key in self.provider_vars:
                    self.provider_vars[full_key].set(val)

    def save(self):
        """Save all to .env"""
        data = {}

        # Core
        core = {
            "MODE": "mode",
            "LLM_PROVIDER": "llm_provider",
            "IB_USER": "ib_user",
            "IB_PASSWORD": "ib_password",
            "IB_TRADING_MODE": "ib_mode",
            "DEFAULT_SYMBOLS": "symbols",
            "REVIEW_INTERVAL_MINUTES": "review_interval",
        }
        for env_key, var_key in core.items():
            val = self.vars[var_key].get()
            if val:
                data[env_key] = str(val)

        # Percentages (convert from display % to decimal)
        for var_key, env_key in [("max_position", "MAX_POSITION_SIZE"), ("risk_per_trade", "RISK_PER_TRADE"), ("max_drawdown", "MAX_DRAWDOWN")]:
            val = self.vars[var_key].get()
            if val:
                data[env_key] = str(val / 100)

        # Provider-specific
        provider = self.vars["llm_provider"].get()
        for key, var in self.provider_vars.items():
            val = var.get()
            if val:
                data[key.upper()] = val

        save_env(data)
        messagebox.showinfo("Saved", "Configuration saved to .env\n\nYou can now click 'Start Trading Agent'")

    def start_agent(self):
        if not (PROJECT_DIR / ".env").exists():
            messagebox.showwarning("Not Configured", "Please save configuration first!")
            return
        if not messagebox.askyesno("Start Agent", "Start the trading agent?\n\nMake sure IB Gateway is running on port 4002 (paper) or 4001 (live)."):
            return

        # Launch in background
        subprocess.Popen([sys.executable, "-m", "src.main", "run"], cwd=PROJECT_DIR,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        messagebox.showinfo("Started", "Trading agent started in background!\nOpening dashboard...")
        self.open_dashboard()

    def open_dashboard(self):
        import webbrowser
        webbrowser.open("http://localhost:8080")

    def run_backtest(self):
        # Simple dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Run Backtest")
        dialog.geometry("340x180")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Run Backtest", font=("SF Pro Display", 14, "bold")).pack(pady=15)

        ttk.Label(dialog, text="Symbol:").pack(anchor="w", padx=30)
        sym = tk.StringVar(value="SPY")
        ttk.Entry(dialog, textvariable=sym, width=30).pack(fill="x", padx=30, pady=(0, 10))

        ttk.Label(dialog, text="Days:").pack(anchor="w", padx=30)
        days = tk.IntVar(value=30)
        ttk.Spinbox(dialog, from_=7, to=365, textvariable=days, width=28).pack(fill="x", padx=30, pady=(0, 15))

        def run():
            subprocess.Popen([sys.executable, "-m", "src.main", "backtest", sym.get().upper(), "--days", str(days.get())],
                           cwd=PROJECT_DIR)
            dialog.destroy()

        ttk.Button(dialog, text="Run", command=run).pack(side="right", padx=10, pady=10)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(side="right", padx=10, pady=10)

    def generate_report(self):
        subprocess.Popen([sys.executable, "-m", "src.main", "generate-pre-report"], cwd=PROJECT_DIR)

    def run(self):
        self.root.mainloop()


def main():
    app = SetupApp()
    app.run()


if __name__ == "__main__":
    main()