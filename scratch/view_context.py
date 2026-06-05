def view_context():
    with open("logs/app.log", "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    for idx in range(13460, 13500):
        if idx < len(lines):
            clean = lines[idx].strip().encode('ascii', 'ignore').decode('ascii')
            print(f"L{idx+1}: {clean}")

if __name__ == "__main__":
    view_context()
