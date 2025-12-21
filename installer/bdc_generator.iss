#define MyAppName "BDC Generator"
#define MyAppVersion "1.0.0"
#define MyAppExeName "BDC Generator.exe"

[Setup]
AppId={{9E3A2080-6B39-4F75-AB2A-6D02159E1A30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\{#MyAppName}
DisableDirPage=yes
PrivilegesRequired=lowest
WizardStyle=modern
OutputBaseFilename=BDC_Generator_Setup_User
OutputDir=..\dist_installer

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\dist\BDC Generator\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Dirs]
Name: "{userappdata}\{#MyAppName}\Templates"; Flags: uninsneveruninstall

[Icons]
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
