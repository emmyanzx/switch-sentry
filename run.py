"""Single-command runner for Switch Sentry War Room."""
import os
import sys
import uvicorn

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

BANNER = r"""
  ___         _ _       _      ___             _              
 / __|_ __ __(_) |_  __| |_   / __|___ _ _  _| |_ _ _ _  _   
 \__ \ V  V /| |  _|/ _| ' \  \__ / -_) ' \|  _| '_| || |   
 |___/\_/\_/ |_|\__|\__|_||_| |___|___|_||_|\__|_|  \_, |   
                                                    |__/    
 Multi-Agent Incident Response Squad | Powered by Switch AI
"""

def main():
    print(BANNER)
    print("=" * 66)
    print("🚀 Starting Switch Sentry War Room...")
    print("🔗 Web Interface:        http://localhost:8080")
    print("📑 Switch Template:      templates/switch-sentry.template.yaml")
    print("🛡️ Switch Trust HUD:     Active (observability & audit trail)")
    print("🤖 AI Squad on Duty:     @incident-commander & @code-remediator")
    print("=" * 66)
    print("\nPress Ctrl+C to stop the server.\n")

    uvicorn.run(
        "switch_sentry.server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
