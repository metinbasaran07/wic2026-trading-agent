#!/usr/bin/env python3
"""
WIC 2026 Trading Agent - GUI Setup Wizard
Run with: python setup_gui.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


class SetupWizard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("WIC 2026 Trading Agent - Setup Wizard")
        self.root.geometry("600x700")
        self.root.resizable(False, False)

        # Center window
        self.center_window()

        # Project path
        self.project_path = Path(__file__).parent

        # Variables
        self.mode_var = tk.StringVar(value="dev")
        self.openrouter_key_var = tk.StringVar()
        self.openrouter_model_var = tk.StringVar(value="anthropic/claude-3.5-sonnet")
        self.ib_user_var = tk.StringVar()
        self.ib_password_var = tk.StringVar()
        self.ib_mode_var = tk.StringVar(value="paper")
        self.symbols_var = tk.StringVar(value="SPY,QQQ,AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,BAC,GS,MS")
        self.max_position_var = tk.DoubleVar(value=0.1)
        self.risk_per_trade_var = tk.DoubleVar(value=0.01)
        self.max_drawdown_var = tk.DoubleVar(value=0.05)
        self.review_interval_var = tk.IntVar(value=60)
        self.dashboard_port_var = tk.IntVar(value=8080)

        # Docker availability
        self.docker_available = self.check_docker()

        self.create_widgets()

    def center_window(self):
        self.root.update_idletasks()
        width = 600
        height = 700
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def check_docker(self) -> bool:
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                subprocess.run(["docker", "compose", "version"], capture_output=True, check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                return False

    def create_widgets(self):
        # Scrollable frame
        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mouse wheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        main = self.scrollable_frame
        main.columnconfigure(1, weight=1)

        # Header
        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=20)
        ttk.Label(header, text="🏆 WIC 2026 Trading Agent", font=("SF Pro Display", 18, "bold")).pack()
        ttk.Label(header, text="World Investment Competition - AI Agent Division", font=("SF Pro Display", 11)).pack()
        ttk.Label(header, text="Setup Wizard", font=("SF Pro Display", 11, "bold")).pack(pady=(5, 0))

        row = 1

        # --- Mode Selection ---
        row = self.create_section(main, row, "🎯 Operating Mode", [
            ("Development (OpenRouter)", "dev"),
            ("Competition Trial", "trial"),
            ("Competition Live", "live"),
        ], self.mode_var)

        # --- LLM Configuration ---
        row = self.create_section(main, row, "🤖 LLM Configuration (Required for Dev)", [
            ("OpenRouter API Key:", "entry", self.openrouter_key_var, {"show": "•"}),
            ("Model:", "entry", self.openrouter_model_var),
        ])
        ttk.Label(main, text="Get your key at: https://openrouter.ai/keys", font=("SF Pro", 9), foreground="blue").grid(row=row, column=1, sticky="w", padx=10)
        row += 1

        # --- Interactive Brokers ---
        row = self.create_section(main, row, "📈 Interactive Brokers (Required)", [
            ("IB Username:", "entry", self.ib_user_var),
            ("IB Password:", "entry", self.ib_password_var, {"show": "•"}),
            ("Trading Mode:", "combo", self.ib_mode_var, ["paper", "live"]),
        ])
        if not self.docker_available:
            ttk.Label(main, text="⚠ Docker not found - you'll need to run IB Gateway manually", font=("SF Pro", 9), foreground="orange").grid(row=row, column=1, sticky="w", padx=10)
            row += 1

        # --- Trading Symbols ---
        row = self.create_section(main, row, "📊 Trading Universe", [
            ("Symbols (comma-separated):", "entry", self.symbols_var),
        ])

        # --- Risk Management ---
        row = self.create_section(main, row, "⚖️ Risk Management", [
            ("Max Position Size (%):", "scale", self.max_position_var, {"from_": 1, "to": 50, "resolution": 1, "format": "%.0f%%"}),
            ("Risk Per Trade (%):", "scale", self.risk_per_trade_var, {"from_": 0.1, "to": 5, "resolution": 0.1, "format": "%.1f%%"}),
            ("Max Daily Drawdown (%):", "scale", self.max_drawdown_var, {"from_": 1, "to": 20, "resolution": 1, "format": "%.0f%%"}),
        ])

        # --- LLM Review ---
        row = self.create_section(main, row, "🔄 LLM Review Schedule", [
            ("Review Interval (minutes):", "combo", self.review_interval_var, [15, 30, 60, 120, 240]),
        ])

        # --- Dashboard ---
        row = self.create_section(main, row, "🖥️ Dashboard", [
            ("Port:", "entry", self.dashboard_port_var),
        ])

        # --- Buttons ---
        button_frame = ttk.Frame(main)
        button_frame.grid(row=row, column=0, columnspan=2, pady=30, padx=20, sticky="ew")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        ttk.Button(button_frame, text="💾 Save Configuration", command=self.save_config, style="Accent.TButton").grid(row=0, column=0, sticky="ew", padx=5)
        ttk.Button(button_frame, text="🚀 Start Trading Agent", command=self.start_agent).grid(row=0, column=1, sticky="ew", padx=5)

        row += 1

        # Docker buttons
        if self.docker_available:
            docker_frame = ttk.Frame(main)
            docker_frame.grid(row=row, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
            docker_frame.columnconfigure(0, weight=1)
            docker_frame.columnconfigure(1, weight=1)
            docker_frame.columnconfigure(2, weight=1)
            ttk.Button(docker_frame, text="🐳 Build Docker", command=self.docker_build).grid(row=0, column=0, sticky="ew", padx=5)
            ttk.Button(docker_frame, text="▶️ Start with Docker", command=self.docker_up).grid(row=0, column=1, sticky="ew", padx=5)
            ttk.Button(docker_frame, text="📋 View Logs", command=self.docker_logs).grid(row=0, column=2, sticky="ew", padx=5)

        row += 1

        # Quick actions
        quick_frame = ttk.Frame(main)
        quick_frame.grid(row=row, column=0, columnspan=2, pady=10, padx=20, sticky="ew")
        quick_frame.columnconfigure(0, weight=1)
        quick_frame.columnconfigure(1, weight=1)
        quick_frame.columnconfigure(2, weight=1)
        ttk.Button(quick_frame, text="📊 Run Backtest", command=self.run_backtest).grid(row=0, column=0, sticky="ew", padx=5)
        ttk.Button(quick_frame, text="📄 Generate Pre-Report", command=self.generate_pre_report).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(quick_frame, text="🌐 Open Dashboard", command=self.open_dashboard).grid(row=0, column=2, sticky="ew", padx=5)

        row += 1

        # Status
        self.status_var = tk.StringVar(value="Ready to configure")
        ttk.Label(main, textvariable=self.status_var, font=("SF Pro", 9), foreground="gray").grid(row=row, column=0, columnspan=2, pady=20)

        # Style
        style = ttk.Style()
        style.configure("Accent.TButton", font=("SF Pro", 10, "bold"))

    def create_section(self, parent, row, title, fields, var=None):
        # Section header
        ttk.Separator(parent, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=10)
        row += 1
        ttk.Label(parent, text=title, font=("SF Pro Display", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1

        if isinstance(fields[0], tuple) and len(fields[0]) == 2 and fields[0][1] in ("dev", "trial", "live"):
            # Radio buttons for mode
            for i, (label, value) in enumerate(fields):
                ttk.Radiobutton(parent, text=label, variable=var, value=value).grid(row=row, column=1, sticky="w", padx=10, pady=2)
                row += 1
        else:
            for field in fields:
                label_text = field[0]
                field_type = field[1]
                var = field[2]
                kwargs = field[3] if len(field) > 3 else {}

                ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=10, pady=5)

                if field_type == "entry":
                    widget = ttk.Entry(parent, textvariable=var, width=40, **kwargs)
                elif field_type == "combo":
                    widget = ttk.Combobox(parent, textvariable=var, values=kwargs.get("values", []), width=37, state="readonly")
                elif field_type == "scale":
                    frame = ttk.Frame(parent)
                    frame.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
                    widget = ttk.Scale(frame, variable=var, from_=kwargs.get("from_", 0), to=kwargs.get("to", 100), orient="horizontal")
                    widget.pack(side="left", fill="x", expand=True)
                    # Value label
                    val_label = ttk.Label(frame, text="", width=6)
                    val_label.pack(side="left", padx=5)
                    def update_label(v, label=val_label, fmt=kwargs.get("format", "%.1f")):
                        label.config(text=fmt % float(v))
                    var.trace_add("write", lambda *args: update_label(var.get()))
                    update_label(var.get())
                    row += 1
                    continue

                widget.grid(row=row, column=1, sticky="ew", padx=10, pady=5)
                row += 1

        return row

    def save_config(self):
        """Save configuration to .env file"""
        env_path = self.project_path / ".env"

        # Read existing .env.example as template
        template_path = self.project_path / ".env.example"
        if template_path.exists():
            template = template_path.read_text()
        else:
            template = ""

        # Build new config
        lines = []
        for line in template.splitlines():
            if line.strip() and not line.startswith("#"):
                key = line.split("=")[0].strip()
                if key == "MODE":
                    lines.append(f"MODE={self.mode_var.get()}")
                elif key == "OPENROUTER_API_KEY":
                    lines.append(f"OPENROUTER_API_KEY={self.openrouter_key_var.get()}")
                elif key == "OPENROUTER_MODEL":
                    lines.append(f"OPENROUTER_MODEL={self.openrouter_model_var.get()}")
                elif key == "IB_USER":
                    lines.append(f"IB_USER={self.ib_user_var.get()}")
                elif key == "IB_PASSWORD":
                    lines.append(f"IB_PASSWORD={self.ib_password_var.get()}")
                elif key == "IB_TRADING_MODE":
                    lines.append(f"IB_TRADING_MODE={self.ib_mode_var.get()}")
                elif key == "DEFAULT_SYMBOLS":
                    lines.append(f"DEFAULT_SYMBOLS={self.symbols_var.get()}")
                elif key == "MAX_POSITION_SIZE":
                    lines.append(f"MAX_POSITION_SIZE={self.max_position_var.get() / 100}")
                elif key == "RISK_PER_TRADE":
                    lines.append(f"RISK_PER_TRADE={self.risk_per_trade_var.get() / 100}")
                elif key == "MAX_DRAWDOWN":
                    lines.append(f"MAX_DRAWDOWN={self.max_drawdown_var.get() / 100}")
                elif key == "REVIEW_INTERVAL_MINUTES":
                    lines.append(f"REVIEW_INTERVAL_MINUTES={self.review_interval_var.get()}")
                elif key == "DASHBOARD_PORT":
                    lines.append(f"DASHBOARD_PORT={self.dashboard_port_var.get()}")
                else:
                    lines.append(line)
            else:
                lines.append(line)

        env_path.write_text("\n".join(lines))
        self.status_var.set(f"✅ Configuration saved to .env")
        messagebox.showinfo("Success", "Configuration saved!\n\nYou can now start the trading agent.")

    def run_command(self, cmd, cwd=None, show_output=True):
        """Run command in background thread"""
        def run():
            self.status_var.set(f"Running: {cmd[0]}...")
            try:
                result = subprocess.run(cmd, cwd=cwd or self.project_path, capture_output=not show_output, text=True, timeout=300)
                if result.returncode == 0:
                    self.status_var.set(f"✅ {cmd[0]} completed")
                    if show_output and result.stdout:
                        messagebox.showinfo("Output", result.stdout[:2000])
                else:
                    self.status_var.set(f"❌ {cmd[0]} failed")
                    messagebox.showerror("Error", result.stderr[:2000] or "Command failed")
            except subprocess.TimeoutExpired:
                self.status_var.set(f"⏱️ {cmd[0]} timed out")
                messagebox.showerror("Timeout", "Command took too long")
            except Exception as e:
                self.status_var.set(f"❌ Error: {e}")
                messagebox.showerror("Error", str(e))

        threading.Thread(target=run, daemon=True).start()

    def start_agent(self):
        """Start the trading agent"""
        # Check .env exists
        if not (self.project_path / ".env").exists():
            messagebox.showwarning("Missing Config", "Please save configuration first!")
            return

        self.run_command([sys.executable, "-m", "src.main", "run"])

    def docker_build(self):
        self.run_command(["./scripts/deploy.sh", "build"])

    def docker_up(self):
        self.run_command(["./scripts/deploy.sh", "up"])

    def docker_logs(self):
        self.run_command(["./scripts/deploy.sh", "logs"])

    def run_backtest(self):
        symbol = tk.simpledialog.askstring("Backtest", "Enter symbol:", initialvalue="SPY", parent=self.root)
        if symbol:
            days = tk.simpledialog.askinteger("Backtest", "Days of history:", initialvalue=30, parent=self.root)
            if days:
                self.run_command([sys.executable, "-m", "src.main", "backtest", symbol.upper(), "--days", str(days)])

    def generate_pre_report(self):
        self.run_command([sys.executable, "-m", "src.main", "generate-pre-report"])

    def open_dashboard(self):
        import webbrowser
        port = self.dashboard_port_var.get()
        webbrowser.open(f"http://localhost:{port}")
        self.status_var.set(f"Opened dashboard at http://localhost:{port}")


def main():
    root = tk.Tk()
    # Set theme for macOS
    try:
        root.tk.call("tk", "scaling", 1.5)  # Retina support
    except:
        pass

    app = SetupWizard(root)
    root.mainloop()


if __name__ == "__main__":
    main()