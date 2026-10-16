; Inno Setup script for Gestura — builds a Windows installer from the PyInstaller output.
;
; Prerequisites:
;   1. python scripts/build_exe.py        (produces dist/Gestura/)
;   2. Install Inno Setup 6 (https://jrsoftware.org/isinfo.php)
;   3. iscc packaging\gestura_installer.iss   (produces packaging/dist/GesturaSetup-<version>.exe)

#define AppName "Gestura"
#define AppVersion "0.2.0"
#define AppPublisher "Krithik S"
#define AppExeName "Gestura.exe"

[Setup]
AppId={{7F3C4A2E-1B6D-4E2A-9C3B-GESTURA000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\icons\gestura.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=GesturaSetup-{#AppVersion}
LicenseFile=..\LICENSE
DisableProgramGroupPage=yes
; Gestura is a per-user app (settings, startup entry), so install for the current user without
; an admin prompt by default; the wizard still offers an all-users install.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
VersionInfoVersion={#AppVersion}
UninstallDisplayName={#AppName} {#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startup"; Description: "Start Gestura when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller one-folder output.
Source: "..\dist\Gestura\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; The same per-user startup entry the app's "Start with Windows" setting manages, so the two never
; disagree (or launch Gestura twice). Starts quietly in the tray; removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"" --minimized"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
