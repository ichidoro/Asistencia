import os
import json
import subprocess
import sys

def main():
    print("Iniciando script de despliegue a Google Cloud Run...")
    
    # 1. Leer credenciales JSON de Google
    json_path = "asistencia-13c58-230b9fe62f70.json"
    if not os.path.exists(json_path):
        print(f"Error: No se encontro el archivo de credenciales '{json_path}'")
        sys.exit(1)
        
    with open(json_path, "r", encoding="utf-8") as f:
        credentials_data = json.load(f)
    
    # Convertir a JSON string compacto de una sola línea
    credentials_json_str = json.dumps(credentials_data)
    
    # 2. Configurar variables a actualizar
    folder_id = "1Y3YeLP9l1O5IZdLVlvCDqUjfLRehv_Rp"
    
    # 3. Construir comando gcloud run deploy usando un delimitador personalizado ^|^
    cmd = [
        "gcloud", "run", "deploy", "asistencia-aguacol",
        "--source", ".",
        "--region", "us-central1",
        "--update-env-vars", f"^|^GOOGLE_DRIVE_FOLDER_ID={folder_id}|GOOGLE_APPLICATION_CREDENTIALS_JSON={credentials_json_str}",
        "--allow-unauthenticated"
    ]
    
    print("Ejecutando 'gcloud run deploy'...")
    
    # Ejecutar subprocess de forma segura con shell=True en Windows
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", shell=True)
    
    print("--- STDOUT ---")
    print(result.stdout)
    
    print("--- STDERR ---")
    print(result.stderr)
    
    if result.returncode == 0:
        print("Despliegue completado exitosamente en Google Cloud Run!")
    else:
        print(f"Error durante el despliegue. Codigo de salida: {result.returncode}")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()
