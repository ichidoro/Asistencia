def find_hard_delet():
    with open("logs/app.log", "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            if "hard_delete" in line.lower():
                clean = line.strip().encode('ascii', 'ignore').decode('ascii')
                print(f"L{idx}: {clean}")

if __name__ == "__main__":
    find_hard_delet()
