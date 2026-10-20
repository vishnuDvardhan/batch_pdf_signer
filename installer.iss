; Inno Setup 6 script
#define MyAppName "Batch PDF Signer"
#define MyAppVersion "1.0.0"
#define MyAppExeName "Batch PDF Signer.exe"
[Setup]
AppId={{6B9F87A1-9D72-4B4B-A7E4-7C52E60D1132}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Batch PDF Signer
DefaultDirName={autopf}\Batch PDF Signer
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=BatchPDFSignerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
[Files]
Source: "dist\Batch PDF Signer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Batch PDF Signer"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Batch PDF Signer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Batch PDF Signer"; Flags: postinstall nowait skipifsilent
