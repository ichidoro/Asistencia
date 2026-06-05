import re
import sys
from collections import Counter

log_path = r"c:\Users\danie\Proyectos_Python\Asistencia\logs\app.log"
output_path = r"c:\Users\danie\Proyectos_Python\Asistencia\scratch\analysis_output.txt"

def analyze():
    print(f"Analyzing {log_path}...")
    
    total_lines = 0
    severity_counter = Counter()
    warnings = []
    errors = []
    traceback_count = 0
    in_traceback = False
    traceback_lines = []
    traceback_samples = []

    # Regex to match log format: 2026-06-04 23:01:17 | INFO     | backend.core.events:...
    log_pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| (\w+)\s*\| (.*)")

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_lines += 1
            line_str = line.strip()
            
            # Traceback detection
            if line_str.startswith("Traceback (most recent call last):"):
                in_traceback = True
                traceback_count += 1
                traceback_lines = [line_str]
                continue
            
            if in_traceback:
                if line_str == "" or re.match(r"^\d{4}-\d{2}-\d{2}", line_str):
                    in_traceback = False
                    traceback_samples.append("\n".join(traceback_lines[:15]))
                else:
                    traceback_lines.append(line_str)
                    continue

            match = log_pattern.match(line_str)
            if match:
                severity = match.group(1)
                message = match.group(2)
                severity_counter[severity] += 1
                
                if severity == "WARNING":
                    warnings.append(message)
                elif severity == "ERROR":
                    errors.append(message)
            else:
                pass

    with open(output_path, "w", encoding="utf-8") as out:
        out.write("=== Log Analysis Summary ===\n")
        out.write(f"Total Lines: {total_lines}\n")
        out.write("\nSeverities:\n")
        for sev, count in severity_counter.most_common():
            out.write(f"  {sev}: {count} ({count/total_lines*100:.2f}%)\n")
            
        out.write(f"\nTracebacks found: {traceback_count}\n")
        if traceback_samples:
            out.write("\nTraceback Samples:\n")
            for idx, sample in enumerate(traceback_samples[:10]):
                out.write(f"--- Sample {idx+1} ---\n")
                out.write(sample + "\n")
                out.write("-" * 20 + "\n")

        out.write("\nMost Common Warnings (Top 20):\n")
        warn_counts = Counter(warnings)
        for warn, count in warn_counts.most_common(20):
            out.write(f"  [{count}x] {warn}\n")

        out.write("\nMost Common Errors (Top 20):\n")
        err_counts = Counter(errors)
        for err, count in err_counts.most_common(20):
            out.write(f"  [{count}x] {err}\n")

    print(f"Analysis complete. Written to {output_path}")

if __name__ == "__main__":
    analyze()
