log_path = r"c:\Users\danie\Proyectos_Python\Asistencia\logs\app.log"
output_path = r"c:\Users\danie\Proyectos_Python\Asistencia\scratch\recent_errors_output.txt"

def analyze_recent():
    print("Filtering errors/warnings since June 1st, 2026...")
    recent_lines = []
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("2026-06-"):
                if "ERROR" in line or "WARNING" in line or "CRITICAL" in line:
                    recent_lines.append(line.strip())
                    
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"=== Errors/Warnings since June 1st, 2026 ({len(recent_lines)} occurrences) ===\n")
        for idx, line in enumerate(recent_lines):
            out.write(f"{line}\n")
            
    print(f"Done. Written to {output_path}")

if __name__ == "__main__":
    analyze_recent()
