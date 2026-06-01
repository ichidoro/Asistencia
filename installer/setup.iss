; ===========================================================
; Aguacol_Asistencia_Setup.iss
; Instalador profesional — Sistema de Asistencia Aguacol
; Herramienta: Inno Setup 6.x
; ===========================================================

#define MyAppName      "Sistema de Asistencia Aguacol"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "Aguacol SPA"
#define MyAppURL       "https://aguacol.cl"
#define ServiceName    "AsistenciaAguacol"
#define DefaultDir     "C:\Asistencia"

[Setup]
AppId={{A3F2C1D4-8E5B-4A7F-9C2E-1D3F5A7B9C0E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={#DefaultDir}
DefaultGroupName={#MyAppName}
AllowNoIcons=no
OutputDir=dist
OutputBaseFilename=Aguacol_Asistencia_Setup
SetupIconFile=assets\logo.ico
WizardImageFile=assets\sidebar.bmp
WizardSmallImageFile=assets\logo_small.bmp
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0.17763
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\assets\logo.ico
UninstallDisplayName={#MyAppName}
CreateUninstallRegKey=yes
ShowLanguageDialog=no
LanguageDetectionMethod=none
WizardImageStretch=no
DisableDirPage=no
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
spanish.WelcomeLabel1=Bienvenido al Instalador del%nSistema de Asistencia Aguacol
spanish.WelcomeLabel2=Este asistente le guiará en la instalación del Sistema de Control de Asistencia.%n%nLa instalación incluirá:%n  • La aplicación completa%n  • Las dependencias necesarias%n  • El servicio de Windows (inicio automático)%n  • Acceso directo en el escritorio%n%nHaga clic en [Siguiente] para continuar.

[Files]
; ── Código fuente de la aplicación ─────────────────────────────────
Source: "..\.env"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\__init__.py"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\backend\*"; DestDir: "{app}\backend"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "*.pyc,*.pyo"
Source: "..\frontend\*"; DestDir: "{app}\frontend"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\data\*"; DestDir: "{app}\data"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion

; ── Scripts del instalador ──────────────────────────────────────
Source: "scripts\find_python.ps1"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\post_install.py"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\connectivity_check.py"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\install_service.py"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\uninstall_service.py"; DestDir: "{app}\.installer"; Flags: ignoreversion

; ── Lanzador silencioso ──────────────────────────────────────────
Source: "scripts\abrir_asistencia.pyw"; DestDir: "{app}"; Flags: ignoreversion

; ── Assets ──────────────────────────────────────────────────────
Source: "assets\logo.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "assets\logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\nssm.exe"; DestDir: "{app}\assets"; Flags: ignoreversion

[Dirs]
Name: "{app}\logs"
Name: "{app}\data"
Name: "{app}\.installer"

[Icons]
; Acceso directo escritorio — apunta a pythonw.exe (sin consola)
; NOTA: pythonw.exe existe en .venv despues de que post_install.py corre exitosamente
Name: "{autodesktop}\Sistema de Asistencia Aguacol"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\abrir_asistencia.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\logo.ico"; Comment: "Abrir el Sistema de Asistencia Aguacol"

; Menú inicio
Name: "{group}\Sistema de Asistencia Aguacol"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\abrir_asistencia.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\logo.ico"; Comment: "Abrir el Sistema de Asistencia Aguacol"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"

[Run]
; ── PASO 1: Buscar Python y ejecutar post_install.py ─────────────
; Usa find_python.ps1 que detecta Python por 5 metodos distintos.
; runhidden: oculta la consola de PowerShell (la UI de progreso tkinter sigue visible).
; waituntilterminated: espera a que termine antes de continuar.
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\.installer\find_python.ps1"" ""{app}"""; \
    StatusMsg: "Configurando Python y dependencias (esto puede tardar 2-4 minutos)..."; \
    Flags: runhidden waituntilterminated

; ── PASO 2: Abrir navegador ─────────────────────────────────────
; Usa abrir_asistencia.pyw que espera a que el servidor responda
; antes de abrir el browser (hasta 60 segundos).
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\abrir_asistencia.pyw"""; WorkingDir: "{app}"; StatusMsg: "Abriendo la aplicacion..."; Flags: nowait runasoriginaluser postinstall skipifsilent; Description: "Abrir el Sistema de Asistencia ahora"

[UninstallRun]
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$p='{app}\.venv\Scripts\python.exe'; if(Test-Path $p){{& $p '{app}\.installer\uninstall_service.py' '{app}'}}"""; \
    Flags: runhidden waituntilterminated; \
    RunOnceId: "UninstallService"

[UninstallDelete]
; Limpiar .venv para que reinstalar no encuentre uno roto
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\.installer"

[Code]
// ─── Personalizar texto de bienvenida ────────────────────────────
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel1.Font.Size := 14;
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
end;

// ─── Confirmacion antes de desinstalar ───────────────────────────
function InitializeUninstall(): Boolean;
begin
  Result := MsgBox(
    'Esta accion desinstalara el Sistema de Asistencia Aguacol.' + #13#10 +
    'El servicio de Windows sera detenido y eliminado.' + #13#10#13#10 +
    'Los datos de la base de datos NO seran eliminados.' + #13#10 +
    'Desea continuar?',
    mbConfirmation, MB_YESNO) = IDYES;
end;
