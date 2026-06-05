import re

log_path = r"c:\Users\danie\Proyectos_Python\Asistencia\logs\app.log"
output_path = r"c:\Users\danie\Proyectos_Python\Asistencia\scratch\sql_errors_output.txt"

def extract_errors():
    error_patterns = [
        "no such column: empleado_id",
        "no such column: e.apellido",
        "ambiguous column name: nombre"
    ]
    
    found = {pat: [] for pat in error_patterns}
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        for idx, line in enumerate(lines):
            for pat in error_patterns:
                if pat in line:
                    snippet = lines[idx:idx+3]
                    snippet_str = "".join(snippet).strip()
                    if snippet_str not in found[pat]:
                        found[pat].append(snippet_str)

    with open(output_path, "w", encoding="utf-8") as out:
        for pat, snippets in found.items():
            out.write(f"\n=== PATTERN: {pat} ({len(snippets)} unique snippets) ===\n")
            for s in snippets:
                out.write(s + "\n")
                out.write("-" * 40 + "\n")

    print(f"Extraction complete. Written to {output_path}")

if __name__ == "__main__":
    extract_errors()
