#!/usr/bin/env python3
"""
WIC 2026 Trading Agent - Terminal Setup
Simple interactive terminal configuration.
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()

PROVIDERS = {
    "openrouter": {"fields": ["api_key", "model"], "defaults": {"model": "anthropic/claude-3.5-sonnet"}, "url": "https://openrouter.ai/keys"},
    "anthropic": {"fields": ["api_key", "model"], "defaults": {"model": "claude-3-5-sonnet-20241022"}, "url": "https://console.anthropic.com/"},
    "openai": {"fields": ["api_key", "base_url", "model"], "defaults": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o"}, "url": "https://platform.openai.com/"},
    "azure": {"fields": ["api_key", "endpoint", "api_version", "deployment"], "defaults": {"api_version": "2024-02-15-preview"}, "url": "https://azure.microsoft.com/"},
    "gemini": {"fields": ["api_key", "model"], "defaults": {"model": "gemini-1.5-pro"}, "url": "https://aistudio.google.com/"},
    "ollama": {"fields": ["base_url", "model"], "defaults": {"base_url": "http://localhost:11434/v1", "model": "llama3.1:70b"}, "url": "https://ollama.ai/"},
    "nvidia": {"fields": ["api_key", "model"], "defaults": {"model": "nvidia/nemotron-3-ultra"}, "url": "https://www.nvidia.com/en-us/research/"},
    "team_key": {"fields": ["api_key", "base_url", "model"], "defaults": {}, "url": "Provided by organizers"},
    "mock": {"fields": [], "defaults": {}, "url": "No API needed"},
}

FIELD_LABELS = {
    "api_key": "API Key",
    "model": "Model",
    "base_url": "Base URL",
    "endpoint": "Endpoint",
    "api_version": "API Version",
    "deployment": "Deployment Name",
}

def load_env():
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


def prompt(text, default=None, secret=False, validator=None):
    """Prompt user for input with optional default and validation."""
    while True:
        if default:
            prompt_text = f"{text} [{default}]: "
        else:
            prompt_text = f"{text}: "

        if secret:
            import getpass
            value = getpass.getpass(prompt_text)
        else:
            value = input(prompt_text).strip()

        if not value and default:
            value = default

        if validator and not validator(value):
            print("  Invalid input, try again.")
            continue

        return value


def main():
    print("\n" + "="*60)
    print("  WIC 2026 Trading Agent - Terminal Setup")
    print("  World Investment Competition - AI Agent Division")
    print("="*60 + "\n")

    existing = load_env()
    config = {}

    # --- Operating Mode ---
    print("\n📋 OPERATING MODE")
    print("  dev    - Development (your own LLM API)")
    print("  trial  - Competition trial period")
    print("  live   - Competition live period")
    config["MODE"] = prompt("Select mode", default=existing.get("MODE", "dev"),
                            validator=lambda x: x in ["dev", "trial", "live"])

    # --- LLM Provider ---
    print("\n🤖 LLM PROVIDER")
    print("Available providers:")
    for i, (key, info) in enumerate(PROVIDERS.items(), 1):
        print(f"  {i}. {key}")

    provider_list = list(PROVIDERS.keys())
    default_provider = existing.get("LLM_PROVIDER", "openrouter")
    while True:
        try:
            choice = prompt(f"Select provider (1-{len(provider_list)})",
                          default=str(provider_list.index(default_provider) + 1) if default_provider in provider_list else "1")
            idx = int(choice) - 1
            if 0 <= idx < len(provider_list):
                provider = provider_list[idx]
                break
        except (ValueError, IndexError):
            pass
        print("  Invalid choice, try again.")

    config["LLM_PROVIDER"] = provider
    provider_info = PROVIDERS[provider]

    # Provider-specific fields
    for field in provider_info["fields"]:
        env_key = f"{provider.upper()}_{field.upper()}"
        label = FIELD_LABELS.get(field, field.replace("_", " ").title())
        default = existing.get(env_key) or provider_info["defaults"].get(field, "")
        is_secret = "key" in field.lower() or "password" in field.lower()
        config[env_key] = prompt(f"  {label}", default=default, secret=is_secret)

    # --- Interactive Brokers ---
    print("\n📈 INTERACTIVE BROKERS")
    config["IB_USER"] = prompt("  IB Username", default=existing.get("IB_USER", ""))
    config["IB_PASSWORD"] = prompt("  IB Password", default=existing.get("IB_PASSWORD", ""), secret=True)
    config["IB_TRADING_MODE"] = prompt("  IB Mode (paper/live)", default=existing.get("IB_TRADING_MODE", "paper"),
                                        validator=lambda x: x in ["paper", "live"])

    # --- Trading Symbols ---
    print("\n📊 TRADING SYMBOLS")
    default_symbols = existing.get("DEFAULT_SYMBOLS", "SPY,QQQ,AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,JPM,BAC,GS,MS")
    config["DEFAULT_SYMBOLS"] = prompt("  Symbols (comma-separated)", default=default_symbols)

    # --- Risk Management ---
    print("\n⚖️ RISK MANAGEMENT")
    for label, env_key, default_val in [
        ("Max Position Size %", "MAX_POSITION_SIZE", "10"),
        ("Risk Per Trade %", "RISK_PER_TRADE", "1"),
        ("Max Daily Drawdown %", "MAX_DRAWDOWN", "5"),
    ]:
        val = prompt(f"  {label}", default=existing.get(env_key, default_val))
        try:
            config[env_key] = str(float(val) / 100)
        except ValueError:
            config[env_key] = str(float(default_val) / 100)

    # --- Review Interval ---
    print("\n🔄 LLM REVIEW")
    config["REVIEW_INTERVAL_MINUTES"] = prompt("  Review interval (minutes)",
                                               default=existing.get("REVIEW_INTERVAL_MINUTES", "60"),
                                               validator=lambda x: x.isdigit() and int(x) > 0)

    # --- Save ---
    print("\n" + "-"*60)
    save_env(config)
    print("✅ Configuration saved to .env")
    print(f"   Mode: {config['MODE']}")
    print(f"   LLM: {config['LLM_PROVIDER']}")
    print(f"   IB: {config['IB_USER']} ({config['IB_TRADING_MODE']})")
    print(f"   Symbols: {config['DEFAULT_SYMBOLS']}")

    # --- Ask to start ---
    print("\n" + "="*60)
    start = input("Start trading agent now? (y/N): ").strip().lower()
    if start == "y":
        print("\n🚀 Starting trading agent...")
        print("   Make sure IB Gateway is running on port 4002 (paper) or 4001 (live)")
        subprocess.Popen([sys.executable, "-m", "src.main", "run"],
                         cwd=PROJECT_DIR, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        print("✅ Agent started in background")
        print("🌐 Opening dashboard at http://localhost:8080")
        import webbrowser
        webbrowser.open("http://localhost:8080")
    else:
        print("\nTo start later, run: python -m src.main run")
        print("To open dashboard: python -m src.main dashboard")

    print("\nDone!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(1)