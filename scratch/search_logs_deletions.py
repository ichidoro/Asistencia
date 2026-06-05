import re

def search_deletions():
    log_path = "logs/app.log"
    print(f"Buscando en {log_path}...")
    
    # Palabras clave a buscar
    keywords = [
        "empleados", "empleado", "delete", "eliminar", "borrar", 
        "hard_delete", "cascade", "foreign_key", "constrain", 
        "foreign key", "violat", "restric", "referen"
    ]
    
    # Compilar patrones case-insensitive
    patterns = [re.compile(rf"\b{kw}", re.IGNORECASE) for kw in keywords]
    
    matches = []
    
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            # Buscar si coincide con alguna palabra clave
            matched_kw = []
            for kw, pat in zip(keywords, patterns):
                if pat.search(line):
                    matched_kw.append(kw)
            
            if matched_kw:
                # Si contiene palabras de eliminación, busquemos también si hay error/warning en la misma línea
                line_lower = line.lower()
                is_error = "error" in line_lower or "critical" in line_lower or "warning" in line_lower or "fall" in line_lower or "fail" in line_lower
                
                # O si contiene palabras clave específicas de error de BD
                is_bd_error = "no such" in line_lower or "ambiguous" in line_lower or "constraint" in line_lower
                
                if is_error or is_bd_error or "hard_delete" in line_lower or "eliminar" in line_lower:
                    matches.append((line_num, matched_kw, line.strip()))
                    
    print(f"Total coincidencias encontradas: {len(matches)}")
    # Mostrar las últimas 100 coincidencias con caracteres no-ascii filtrados
    for num, kws, text in matches[-100:]:
        clean_text = text.encode('ascii', 'ignore').decode('ascii')
        print(f"Linea {num} [{', '.join(kws)}]: {clean_text}")

if __name__ == "__main__":
    search_deletions()
