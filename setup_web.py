#!/usr/bin/env python3
"""
WIC 2026 Trading Agent - Web Setup Wizard
Run with: python setup_web.py
Then open http://localhost:8081 in your browser
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import json

PROJECT_PATH = Path(__file__).parent
SETUP_PORT = 8081


class SetupHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_PATH), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_setup_page()
        elif parsed.path == "/api/check-docker":
            self.send_json({"docker": self.check_docker()})
        elif parsed.path == "/api/check-config":
            self.send_json(self.check_config())
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/save-config":
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length))
            self.save_config(data)
        elif parsed.path == "/api/run-command":
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length))
            self.run_command(data.get("cmd", []))
        else:
            self.send_error(404)

    def serve_setup_page(self):
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WIC 2026 Trading Agent - Setup</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .input-field { @apply w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition; }
        .label { @apply block text-sm font-medium text-gray-700 mb-1; }
        .section { @apply bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6; }
        .btn { @apply px-4 py-2 rounded-lg font-medium transition-colors; }
        .btn-primary { @apply bg-blue-600 text-white hover:bg-blue-700; }
        .btn-secondary { @apply bg-gray-100 text-gray-700 hover:bg-gray-200; }
        .btn-success { @apply bg-green-600 text-white hover:bg-green-700; }
        .status-ok { @apply text-green-600; }
        .status-warn { @apply text-yellow-600; }
        .status-error { @apply text-red-600; }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="max-w-3xl mx-auto px-4 py-8">
        <!-- Header -->
        <div class="text-center mb-8">
            <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 mb-4">
                <svg class="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
            <h1 class="text-3xl font-bold text-gray-900">WIC 2026 Trading Agent</h1>
            <p class="text-gray-600 mt-1">World Investment Competition - AI Agent Division</p>
            <p class="text-sm text-gray-500 mt-2">Setup Wizard</p>
        </div>

        <div id="docker-status" class="mb-6"></div>

        <!-- Mode Selection -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">🎯 Operating Mode</h2>
            <div class="grid grid-cols-3 gap-3">
                <label class="relative cursor-pointer">
                    <input type="radio" name="mode" value="dev" class="sr-only peer" checked>
                    <div class="p-4 border-2 rounded-lg text-center peer-checked:border-blue-500 peer-checked:bg-blue-50 transition">
                        <div class="font-medium">Development</div>
                        <div class="text-sm text-gray-500">OpenRouter API</div>
                    </div>
                </label>
                <label class="relative cursor-pointer">
                    <input type="radio" name="mode" value="trial" class="sr-only peer">
                    <div class="p-4 border-2 rounded-lg text-center peer-checked:border-blue-500 peer-checked:bg-blue-50 transition">
                        <div class="font-medium">Trial</div>
                        <div class="text-sm text-gray-500">Competition Trial</div>
                    </div>
                </label>
                <label class="relative cursor-pointer">
                    <input type="radio" name="mode" value="live" class="sr-only peer">
                    <div class="p-4 border-2 rounded-lg text-center peer-checked:border-blue-500 peer-checked:bg-blue-50 transition">
                        <div class="font-medium">Live</div>
                        <div class="text-sm text-gray-500">Competition Live</div>
                    </div>
                </label>
            </div>
        </div>

        <!-- LLM Config -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">🤖 LLM Configuration <span class="text-sm font-normal text-gray-500">(Required for Development)</span></h2>
            <div class="grid gap-4 md:grid-cols-2">
                <div>
                    <label class="label">OpenRouter API Key</label>
                    <input type="password" id="openrouter_key" class="input-field" placeholder="sk-or-v1-...">
                    <p class="text-xs text-gray-500 mt-1">Get at <a href="https://openrouter.ai/keys" target="_blank" class="text-blue-600">openrouter.ai/keys</a></p>
                </div>
                <div>
                    <label class="label">Model</label>
                    <input type="text" id="openrouter_model" class="input-field" value="anthropic/claude-3.5-sonnet">
                </div>
            </div>
        </div>

        <!-- IB Config -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">📈 Interactive Brokers <span class="text-sm font-normal text-gray-500">(Required)</span></h2>
            <div class="grid gap-4 md:grid-cols-2">
                <div>
                    <label class="label">IB Username</label>
                    <input type="text" id="ib_user" class="input-field">
                </div>
                <div>
                    <label class="label">IB Password</label>
                    <input type="password" id="ib_password" class="input-field">
                </div>
                <div>
                    <label class="label">Trading Mode</label>
                    <select id="ib_mode" class="input-field">
                        <option value="paper">Paper Trading</option>
                        <option value="live">Live Trading</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- Symbols -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">📊 Trading Symbols</h2>
            <label class="label">Comma-separated symbols</label>
            <textarea id="symbols" class="input-field h-24" placeholder="SPY, QQQ, AAPL, MSFT, NVDA...">SPY,QQQ,AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,BAC,GS,MS</textarea>
        </div>

        <!-- Risk Management -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">⚖️ Risk Management</h2>
            <div class="grid gap-4 md:grid-cols-3">
                <div>
                    <label class="label">Max Position Size <span id="pos_val" class="text-blue-600">10%</span></label>
                    <input type="range" id="max_position" min="1" max="50" value="10" class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600" oninput="document.getElementById('pos_val').textContent = this.value + '%'">
                </div>
                <div>
                    <label class="label">Risk Per Trade <span id="risk_val" class="text-blue-600">1%</span></label>
                    <input type="range" id="risk_per_trade" min="0.1" max="5" step="0.1" value="1" class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600" oninput="document.getElementById('risk_val').textContent = this.value + '%'">
                </div>
                <div>
                    <label class="label">Max Daily Drawdown <span id="dd_val" class="text-blue-600">5%</span></label>
                    <input type="range" id="max_drawdown" min="1" max="20" value="5" class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600" oninput="document.getElementById('dd_val').textContent = this.value + '%'">
                </div>
            </div>
        </div>

        <!-- LLM Review -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">🔄 LLM Review Schedule</h2>
            <div class="grid gap-4 md:grid-cols-2">
                <div>
                    <label class="label">Review Interval</label>
                    <select id="review_interval" class="input-field">
                        <option value="15">15 minutes</option>
                        <option value="30">30 minutes</option>
                        <option value="60" selected>1 hour</option>
                        <option value="120">2 hours</option>
                        <option value="240">4 hours</option>
                    </select>
                </div>
                <div>
                    <label class="label">Dashboard Port</label>
                    <input type="number" id="dashboard_port" class="input-field" value="8080">
                </div>
            </div>
        </div>

        <!-- Actions -->
        <div class="section">
            <h2 class="text-lg font-semibold mb-4">🚀 Actions</h2>
            <div class="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                <button onclick="saveConfig()" class="btn btn-primary py-3 text-lg">💾 Save Configuration</button>
                <button onclick="startAgent()" class="btn btn-success py-3 text-lg">▶️ Start Trading Agent</button>
                <button onclick="openDashboard()" class="btn btn-secondary py-3 text-lg">🌐 Open Dashboard</button>
            </div>
            <div id="docker-actions" class="grid gap-3 md:grid-cols-3 mt-4 hidden">
                <button onclick="runCommand(['./scripts/deploy.sh', 'build'])" class="btn btn-secondary">🐳 Build Docker</button>
                <button onclick="runCommand(['./scripts/deploy.sh', 'up'])" class="btn btn-primary">▶️ Start with Docker</button>
                <button onclick="runCommand(['./scripts/deploy.sh', 'logs'])" class="btn btn-secondary">📋 View Logs</button>
            </div>
            <div class="grid gap-3 md:grid-cols-3 mt-4">
                <button onclick="runBacktest()" class="btn btn-secondary">📊 Run Backtest</button>
                <button onclick="runCommand(['python3', '-m', 'src.main', 'generate-pre-report'])" class="btn btn-secondary">📄 Generate Pre-Report</button>
                <button onclick="checkConfig()" class="btn btn-secondary">🔍 Validate Config</button>
            </div>
        </div>

        <!-- Status -->
        <div id="status" class="section bg-gray-50 border-gray-200 hidden">
            <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full bg-blue-500 animate-pulse" id="status-dot"></div>
                <span id="status-text">Ready</span>
            </div>
        </div>
    </div>

    <script>
        async function checkDocker() {
            const res = await fetch('/api/check-docker');
            const data = await res.json();
            const div = document.getElementById('docker-status');
            if (data.docker) {
                div.innerHTML = '<div class="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3"><svg class="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg><span class="font-medium">Docker is available</span><span class="text-sm text-gray-500 ml-auto">You can use Docker deployment</span></div>';
                document.getElementById('docker-actions').classList.remove('hidden');
            } else {
                div.innerHTML = '<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-center gap-3"><svg class="w-5 h-5 text-yellow-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg><span class="font-medium">Docker not found</span><span class="text-sm text-gray-500 ml-auto">Install Docker for containerized deployment</span></div>';
            }
        }

        async function checkConfig() {
            const res = await fetch('/api/check-config');
            const data = await res.json();
            alert(data.message);
        }

        async function saveConfig() {
            showStatus('Saving configuration...', 'blue');
            const config = {
                mode: document.querySelector('input[name="mode"]:checked').value,
                openrouter_key: document.getElementById('openrouter_key').value,
                openrouter_model: document.getElementById('openrouter_model').value,
                ib_user: document.getElementById('ib_user').value,
                ib_password: document.getElementById('ib_password').value,
                ib_mode: document.getElementById('ib_mode').value,
                symbols: document.getElementById('symbols').value,
                max_position: parseFloat(document.getElementById('max_position').value) / 100,
                risk_per_trade: parseFloat(document.getElementById('risk_per_trade').value) / 100,
                max_drawdown: parseFloat(document.getElementById('max_drawdown').value) / 100,
                review_interval: parseInt(document.getElementById('review_interval').value),
                dashboard_port: parseInt(document.getElementById('dashboard_port').value),
            };

            const res = await fetch('/api/save-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const data = await res.json();
            if (data.success) {
                showStatus('✅ Configuration saved!', 'green');
            } else {
                showStatus('❌ ' + data.error, 'red');
            }
        }

        async function startAgent() {
            if (!confirm('Start the trading agent? Make sure IB Gateway is running on port 4002 (paper) or 4001 (live).')) return;
            runCommand(['python3', '-m', 'src.main', 'run']);
        }

        async function runBacktest() {
            const symbol = prompt('Enter symbol:', 'SPY');
            if (!symbol) return;
            const days = prompt('Days of history:', '30');
            if (!days) return;
            runCommand(['python3', '-m', 'src.main', 'backtest', symbol.toUpperCase(), '--days', days]);
        }

        async function runCommand(cmd) {
            showStatus('Running: ' + cmd[0] + '...', 'blue');
            const res = await fetch('/api/run-command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cmd })
            });
            const data = await res.json();
            if (data.started) {
                showStatus('✅ Started in background. Check terminal for output.', 'green');
            } else {
                showStatus('❌ ' + data.error, 'red');
            }
        }

        async function openDashboard() {
            const port = document.getElementById('dashboard_port').value;
            window.open('http://localhost:' + port, '_blank');
            showStatus('Opened dashboard', 'green');
        }

        function showStatus(msg, color) {
            const el = document.getElementById('status');
            const dot = document.getElementById('status-dot');
            const text = document.getElementById('status-text');
            el.classList.remove('hidden');
            dot.className = 'w-2 h-2 rounded-full ' + (color === 'green' ? 'bg-green-500' : color === 'red' ? 'bg-red-500' : 'bg-blue-500 animate-pulse');
            text.textContent = msg;
        }

        // Initialize
        checkDocker();
    </script>
</body>
</html>
        """
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def check_docker(self):
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
            return True
        except:
            try:
                subprocess.run(["docker", "compose", "version"], capture_output=True, check=True)
                return True
            except:
                return False

    def check_config(self):
        env_path = PROJECT_PATH / ".env"
        if env_path.exists():
            return {"success": True, "message": "✅ Configuration file exists"}
        return {"success": False, "message": "❌ No .env file found. Please save configuration first."}

    def save_config(self, data):
        template_path = PROJECT_PATH / ".env.example"
        if template_path.exists():
            template = template_path.read_text()
        else:
            template = ""

        lines = []
        for line in template.splitlines():
            if line.strip() and not line.startswith("#"):
                key = line.split("=")[0].strip()
                val = data.get(key.lower())
                if val is not None:
                    lines.append(f"{key}={val}")
                else:
                    lines.append(line)
            else:
                lines.append(line)

        (PROJECT_PATH / ".env").write_text("\n".join(lines))
        self.send_json({"success": True})

    def run_command(self, data):
        cmd = data.get("cmd", [])
        def run():
            try:
                subprocess.Popen(cmd, cwd=PROJECT_PATH)
            except Exception as e:
                print(f"Error: {e}")
        threading.Thread(target=run, daemon=True).start()
        self.send_json({"started": True})


def run_server():
    server = HTTPServer(("", SETUP_PORT), SetupHandler)
    print(f"Setup wizard running at http://localhost:{SETUP_PORT}")
    server.serve_forever()


def main():
    # Open browser
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{SETUP_PORT}")).start()
    run_server()


if __name__ == "__main__":
    main()