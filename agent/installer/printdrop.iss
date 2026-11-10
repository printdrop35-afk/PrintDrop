; PrintDrop pour Windows — script Inno Setup (compilé par .github/workflows/windows-agent.yml)
#define AppVersion GetEnv("AGENT_VERSION")
#if AppVersion == ""
  #define AppVersion "0.4.0"
#endif

[Setup]
AppId={{7E1B1C2A-5D1F-4C55-9C0B-PRINTDROP0001}
AppName=PrintDrop pour Windows
AppVersion={#AppVersion}
AppPublisher=PrintDrop
DefaultDirName={autopf}\PrintDrop
DefaultGroupName=PrintDrop
OutputBaseFilename=PrintDrop-Setup-{#AppVersion}
OutputDir=..\dist
Compression=lzma2
SolidCompression=yes
MinVersion=10.0
PrivilegesRequired=admin
UninstallDisplayName=PrintDrop pour Windows
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"
Name: "autostart"; Description: "Démarrer PrintDrop automatiquement avec Windows (recommandé)"

[Files]
Source: "..\dist\PrintDrop.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\SumatraPDF.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "Guide-installation.md"

[Icons]
Name: "{group}\PrintDrop"; Filename: "{app}\PrintDrop.exe"
Name: "{group}\Désinstaller PrintDrop"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PrintDrop"; Filename: "{app}\PrintDrop.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PrintDrop"; \
  ValueData: """{app}\PrintDrop.exe"" --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\PrintDrop.exe"; Description: "Lancer PrintDrop et associer ce PC"; Flags: nowait postinstall skipifsilent
; silent install = one-click update from the dashboard: restart the agent for the signed-in user
Filename: "{app}\PrintDrop.exe"; Parameters: "--background"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PrintDrop\tmp"
