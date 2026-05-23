import sys

# Reconfigure stdout to use utf-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

with open("logs/app.log", "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()
    print("Last 100 log lines:")
    for line in lines[-100:]:
        safe_line = line.encode('ascii', errors='replace').decode('ascii')
        print(safe_line.strip())
