import os
import subprocess
import sys

def main():
    print("==================================================")
    print("🚀 INICIANDO ACTUALIZACIÓN DEL INSTALADOR 🚀")
    print("==================================================\n")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)

    # Paso 1: Ejecutar PyInstaller (constructor.py)
    print("▶️ PASO 1/2: Empaquetando el código nuevo (PyInstaller)...")
    constructor_path = os.path.join(base_dir, "constructor.py")
    result_pyinst = subprocess.run([sys.executable, constructor_path], cwd=project_root)
    
    if result_pyinst.returncode != 0:
        print("\n❌ Error empaquetando el código. Compilación detenida.")
        sys.exit(1)

    # Paso 2: Ejecutar Inno Setup
    print("\n▶️ PASO 2/2: Ensamblando el archivo ejecutable final (Inno Setup)...")
    possible_paths = [
        r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        r'C:\Program Files\Inno Setup 6\ISCC.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe')
    ]

    iscc_path = None
    for p in possible_paths:
        if os.path.exists(p):
            iscc_path = p
            break

    if not iscc_path:
        print('\n❌ No se pudo encontrar el compilador de Inno Setup (ISCC.exe).')
        sys.exit(1)

    iss_file = os.path.join(base_dir, 'setup.iss')
    result_inno = subprocess.run([iscc_path, iss_file], capture_output=True, text=True, cwd=project_root)
    
    if result_inno.returncode == 0:
        print("\n✅ ¡ACTUALIZACIÓN EXITOSA! ✅")
        print(f"Tu nuevo instalador actualizado está listo en la carpeta 'Empaquetado'")
    else:
        print("\n❌ Error generando el Instalador:\n", result_inno.stderr)
        sys.exit(result_inno.returncode)

if __name__ == "__main__":
    main()
