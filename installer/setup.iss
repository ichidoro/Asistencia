; ===========================================================
; Aguacol_Asistencia_Setup.iss
; Instalador profesional — Sistema de Asistencia Aguacol
; Herramienta: Inno Setup 6.x
; ===========================================================

#define MyAppName      "Sistema de Asistencia Aguacol"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "Aguacol SPA"
#define MyAppURL       "https://aguacol.cl"
#define MyAppExeName   "iniciar_asistencia.bat"
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

; Pantalla de bienvenida con texto personalizado
WizardImageStretch=no
DisableDirPage=no
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
spanish.WelcomeLabel1=Bienvenido al Instalador del%nSistema de Asistencia Aguacol
spanish.WelcomeLabel2=Este asistente le guiará en la instalación del Sistema de Control de Asistencia.%n%nLa instalación incluirá:%n  • La aplicación completa%n  • Las dependencias necesarias%n  • El servicio de Windows (inicio automático)%n  • Acceso directo en el escritorio%n%nHaga clic en [Siguiente] para continuar.
spanish.ClickNext=Haga clic en Siguiente para continuar, o en Cancelar para salir.
spanish.SelectDirLabel3=La aplicación se instalará en la siguiente carpeta. Haga clic en Siguiente para continuar o en Examinar si desea elegir una ubicación diferente.
spanish.ReadyLabel1=El asistente está listo para instalar {#MyAppName} en su equipo.
spanish.ReadyLabel2a=Haga clic en Instalar para comenzar la instalación, o en Atrás si desea revisar o cambiar alguna opción.

[Files]
; ── Código fuente de la aplicación ──────────────────────────────
Source: "..\backend\*"; DestDir: "{app}\backend"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "__pycache__,*.pyc,*.pyo,.git"
Source: "..\frontend\*"; DestDir: "{app}\frontend"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\data\*"; DestDir: "{app}\data"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion

; ── Scripts del instalador ──────────────────────────────────────
Source: "scripts\post_install.py"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\connectivity_check.py"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\install_service.py"; DestDir: "{app}\.installer"; Flags: ignoreversion
Source: "scripts\uninstall_service.py"; DestDir: "{app}\.installer"; Flags: ignoreversion

; ── Assets ──────────────────────────────────────────────────────
Source: "assets\logo.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "assets\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

; ── Archivo de inicio rápido ────────────────────────────────────
Source: "scripts\iniciar_asistencia.bat"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\logs"
Name: "{app}\data"
Name: "{app}\.installer"

[Icons]
; Acceso directo en el escritorio
Name: "{autodesktop}\Sistema de Asistencia Aguacol"; Filename: "{app}\iniciar_asistencia.bat"; IconFilename: "{app}\assets\logo.ico"; Comment: "Iniciar el Sistema de Asistencia Aguacol"; WorkingDir: "{app}"

; Acceso directo en menú inicio
Name: "{group}\Sistema de Asistencia Aguacol"; Filename: "{app}\iniciar_asistencia.bat"; IconFilename: "{app}\assets\logo.ico"; Comment: "Iniciar el Sistema de Asistencia Aguacol"; WorkingDir: "{app}"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"

[Run]
; Paso 1: Instalación de dependencias y configuración (ventana propia con progreso)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""& {{ $py = (Get-Command python -ErrorAction SilentlyContinue); if (-not $py) {{ $py = (Get-Command py -ErrorAction SilentlyContinue) }}; if ($py) {{ & $py.Path '{app}\.installer\post_install.py' '{app}' }} else {{ [System.Windows.Forms.MessageBox]::Show('Python no encontrado. Instale Python 3.13 o superior desde python.org', 'Error') }} }}"""; StatusMsg: "Configurando la aplicación..."; Flags: runhidden waituntilterminated; Check: PythonExists

; Si Python no está: ejecutar instalador silencioso
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""winget install Python.Python.3.13 --silent --accept-package-agreements --accept-source-agreements; Start-Sleep 5"""; StatusMsg: "Instalando Python 3.13..."; Flags: runhidden waituntilterminated; Check: not PythonExists

; Paso 2 (después de instalar Python si fue necesario): post_install
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$py = (Get-Command python -ErrorAction SilentlyContinue); if (-not $py) {{ $py = (Get-Command py -ErrorAction SilentlyContinue) }}; & $py.Path '{app}\.installer\post_install.py' '{app}'"""; StatusMsg: "Configurando dependencias..."; Flags: runhidden waituntilterminated; Check: not PythonExists

; Paso 3: Verificación de conectividad (visible al usuario)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$py = '{app}\.venv\Scripts\python.exe'; if (Test-Path $py) {{ & $py '{app}\.installer\connectivity_check.py' '{app}' }}"""; StatusMsg: "Verificando conectividad..."; Flags: waituntilterminated

; Paso 4: Abrir la app en el navegador
Filename: "{app}\iniciar_asistencia.bat"; StatusMsg: "Iniciando la aplicación..."; Flags: nowait runasoriginaluser postinstall skipifsilent; Description: "Abrir el Sistema de Asistencia ahora"

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$py = '{app}\.venv\Scripts\python.exe'; if (Test-Path $py) {{ & $py '{app}\.installer\uninstall_service.py' '{app}' }}"""; Flags: runhidden waituntilterminated; RunOnceId: "UninstallService"

[Code]
// ─── Verificar si Python está instalado ──────────────────────────
function PythonExists(): Boolean;
var
  PythonPath: String;
begin
  Result := False;
  // Buscar primero Python 3.13 (versión requerida por la app)
  if FileExists(ExpandConstant('{sys}\..\..\Python313\python.exe')) then begin Result := True; Exit; end;
  if FileExists(ExpandConstant('{pf}\Python313\python.exe')) then begin Result := True; Exit; end;
  if FileExists(ExpandConstant('{pf32}\Python313\python.exe')) then begin Result := True; Exit; end;
  // Registro HKLM — Python 3.13, 3.12, 3.11 (en orden de preferencia)
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.13\InstallPath', '', PythonPath) then begin
    Result := FileExists(PythonPath + '\python.exe');
    if Result then Exit;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', PythonPath) then begin
    Result := FileExists(PythonPath + '\python.exe');
    if Result then Exit;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Python\PythonCore\3.11\InstallPath', '', PythonPath) then begin
    Result := FileExists(PythonPath + '\python.exe');
    if Result then Exit;
  end;
  // Registro HKCU (instalación de usuario) — Python 3.13 y 3.12
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.13\InstallPath', '', PythonPath) then begin
    Result := FileExists(PythonPath + '\python.exe');
    if Result then Exit;
  end;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Python\PythonCore\3.12\InstallPath', '', PythonPath) then begin
    Result := FileExists(PythonPath + '\python.exe');
    if Result then Exit;
  end;
end;

// ─── Texto personalizado de la página de bienvenida ──────────────
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel1.Font.Size := 14;
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
end;

// ─── Confirmación antes de desinstalar ───────────────────────────
function InitializeUninstall(): Boolean;
begin
  Result := MsgBox(
    'Esta acción desinstalará el Sistema de Asistencia Aguacol.' + #13#10 +
    'El servicio de Windows será detenido y eliminado.' + #13#10#13#10 +
    'Los datos de la base de datos NO serán eliminados.' + #13#10 +
    '¿Desea continuar?',
    mbConfirmation, MB_YESNO) = IDYES;
end;
