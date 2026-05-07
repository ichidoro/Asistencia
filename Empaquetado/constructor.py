import os
import subprocess
import sys

def build():
    print("Iniciando compilacion AISLADA de AsistenciaApp con PyInstaller...")
    
    try:
        import PyInstaller.__main__
    except ImportError:
        print("Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "Pillow"])
        import PyInstaller.__main__
        
    sep = os.pathsep
    
    # Rutas clave asumiendo que este script se corre desde /Empaquetado/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    empaquetado_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Manejar el icono convirtiéndolo si es necesario (Priorizando v5 mejorado)
    logo_v5 = os.path.join(base_dir, "frontend", "assets", "img", "logo_v5.png")
    logo_jpg = os.path.join(base_dir, "frontend", "assets", "img", "logo.jpg")
    logo_ico = os.path.join(empaquetado_dir, "logo.ico")
    
    source_img = logo_v5 if os.path.exists(logo_v5) else logo_jpg
    
    if os.path.exists(source_img):
        from PIL import Image, ImageOps
        img = Image.open(source_img)
        # 1. Generar logo.ico (Icono de la app)
        img.save(logo_ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"✅ Icono {logo_ico} actualizado.")

        # 2. Generar Wizard Images para Inno Setup
        # wizard_side.bmp (164 x 314) - Fondo degradado/blanco con logo centrado
        side_img = Image.new('RGB', (164, 314), color='white')
        logo_resized_side = img.resize((140, 140), Image.Resampling.LANCZOS)
        side_img.paste(logo_resized_side, (12, 20)) # Logo en la parte superior
        side_img.save(os.path.join(empaquetado_dir, "wizard_side.bmp"), "BMP")
        
        # wizard_top.bmp (55 x 55) - Logo pequeño
        top_img = img.resize((55, 55), Image.Resampling.LANCZOS)
        top_img.save(os.path.join(empaquetado_dir, "wizard_top.bmp"), "BMP")
        print(f"✅ Imágenes de asistente (Wizard) generadas.")
    
    # Archivos adjuntos desde la raíz hacia ./
    frontend_path = os.path.join(base_dir, "frontend")
    env_path = os.path.join(base_dir, ".env")
    database_script = os.path.join(base_dir, "setup_db.py") # Por si hace falta
    
    data_files = [
        f"{frontend_path}{sep}frontend",
        f"{env_path}{sep}.",
    ]
    if os.path.exists(database_script):
        data_files.append(f"{database_script}{sep}.")
    
    # Rutas de aislamiento de PyInstaller (para no ensuciar el raíz del usuario)
    dist_path = os.path.join(empaquetado_dir, "dist")
    work_path = os.path.join(empaquetado_dir, "build")
    spec_path = empaquetado_dir
    script_to_compile = os.path.join(empaquetado_dir, "start_app.py")
    
    args = [
        script_to_compile,
        '--name=Aguacol_Asistencia',
        f'--distpath={dist_path}',
        f'--workpath={work_path}',
        f'--specpath={spec_path}',
        '--onedir',   
        '--noconfirm',
        '--noconsole',
        '--clean'
    ]
    
    if os.path.exists(logo_ico):
        args.append(f'--icon={logo_ico}')
    
    # Paths para que encuentre backend
    args.append(f'--paths={base_dir}')
    
    # Recolectar datos ocultos críticos
    args.append('--collect-all=holidays')
    args.append('--collect-all=apscheduler')
    args.append('--collect-all=tzlocal')
    args.append('--collect-all=pytz')
    
    # Módulos críticos
    hidden_imports = [
        'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on', 'websockets', 'sqlite3', 'backend.main'
    ]
    for hi in hidden_imports:
        args.extend(['--hidden-import', hi])
        
    for data in data_files:
        if os.path.exists(data.split(sep)[0]):
            args.extend(['--add-data', data])
            
    print(f"Ejecutando PyInstaller configurado para aislar archivos en {empaquetado_dir}")
    PyInstaller.__main__.run(args)
    
    print("\n✅ Compilación asilada completa! Los archivos binarios están en Empaquetado/dist/")

if __name__ == "__main__":
    build()
