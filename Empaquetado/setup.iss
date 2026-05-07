[Setup]
AppName=Aguacol_Asistencia
AppVersion=4.4.2
DefaultDirName={autopf}\Aguacol_Asistencia
DefaultGroupName=Aguacol_Asistencia
OutputDir=.
OutputBaseFilename=Instalador_Aguacol_Asistencia
Compression=lzma2
SolidCompression=yes
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\Aguacol_Asistencia.exe
WizardImageFile=wizard_side.bmp
WizardSmallImageFile=wizard_top.bmp
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
CloseApplications=force
RestartApplications=no
LanguageDetectionMethod=uilanguage

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Aguacol_Asistencia\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "asistencia_local.db"; DestDir: "{localappdata}\Aguacol_Asistencia\data\local_db"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\Aguacol_Asistencia"; Filename: "{app}\Aguacol_Asistencia.exe"
Name: "{autodesktop}\Aguacol_Asistencia"; Filename: "{app}\Aguacol_Asistencia.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\Aguacol_Asistencia"

[Run]
Filename: "{app}\Aguacol_Asistencia.exe"; Description: "{cm:LaunchProgram,Aguacol_Asistencia}"; Flags: nowait postinstall skipifsilent

[Code]
// Script Pascal para matar el proceso ANTES de que Inno Setup revise los archivos
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  // Ejecutamos taskkill silenciosamente (/F forzar, /IM nombre_imagen, /T árbol completo)
  Exec('cmd.exe', '/c taskkill /F /IM Aguacol_Asistencia.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
