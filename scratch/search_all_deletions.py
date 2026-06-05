import re

def search_all_deletions():
    log_path = "logs/app.log"
    print(f"Buscando eventos de eliminacion en {log_path}...")
    
    # Buscaremos lineas que contengan "Hard Delete", "hard_delete", "desactivado", "eliminar", "DELETE FROM empleados"
    patterns = [
        re.compile(r"hard_delete", re.IGNORECASE),
        re.compile(r"hard delete", re.IGNORECASE),
        re.compile(r"eliminado permanentemente", re.IGNORECASE),
        re.compile(r"desactivado: ID", re.IGNORECASE),
        re.compile(r"DELETE FROM empleados", re.IGNORECASE)
    ]
    
    # Leemos todas las lineas del log
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        
    print(f"Total lineas leidas: {len(lines)}")
    
    events = []
    for i, line in enumerate(lines):
        for pat in patterns:
            if pat.search(line):
                events.append((i, line))
                break
                
    print(f"Eventos de eliminacion encontrados: {len(events)}")
    
    for idx, line in events:
        clean_line = line.encode('ascii', 'ignore').decode('ascii').strip()
        print(f"\n--- Evento en Linea {idx+1}: {clean_line}")
        # Mostrar las 15 lineas siguientes para ver si hubo errores inmediatos
        print("Lineas siguientes en el log:")
        for offset in range(1, 15):
            if idx + offset < len(lines):
                next_line = lines[idx + offset].encode('ascii', 'ignore').decode('ascii').strip()
                # Destacar si es error/warning
                prefix = "  >>>" if any(w in next_line.lower() for w in ["error", "warning", "critical", "fail", "conflict"]) else "     "
                print(f"{prefix} L{idx+1+offset}: {next_line}")

if __name__ == "__main__":
    search_all_deletions()
