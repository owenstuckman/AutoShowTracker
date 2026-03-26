; Inno Setup Script for AutoShowTracker
; Build with: iscc scripts\inno_setup.iss
;
; Prerequisites:
;   1. Install Inno Setup from https://jrsoftware.org/isinfo.php
;   2. Build the PyInstaller binary first:
;        pyinstaller show_tracker.spec
;   3. The dist\show-tracker\ directory must exist with the built app.

#define MyAppName "AutoShowTracker"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "AutoShowTracker"
#define MyAppURL "https://github.com/ostuc/AutoShowTracker"
#define MyAppExeName "show-tracker.exe"

[Setup]
AppId={{A8E4F2C1-3B7D-4E5A-9F6C-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output installer to dist\
OutputDir=..\dist
OutputBaseFilename=AutoShowTracker-{#MyAppVersion}-setup
; Compression
Compression=lzma2
SolidCompression=yes
; Require admin for Program Files install, but allow per-user
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Installer UI
WizardStyle=modern
; Icon (if available)
SetupIconFile=..\assets\icon.ico
; Uninstall icon
UninstallDisplayIcon={app}\{#MyAppExeName}
; Min Windows version: Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry"; Description: "Start AutoShowTracker when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller output directory
Source: "..\dist\show-tracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcuts
Name: "{group}\AutoShowTracker"; Filename: "{app}\{#MyAppExeName}"; Parameters: "run"; Comment: "Start AutoShowTracker"
Name: "{group}\AutoShowTracker Dashboard"; Filename: "http://localhost:7600/"; Comment: "Open Dashboard in browser"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Desktop shortcut (optional task)
Name: "{userdesktop}\AutoShowTracker"; Filename: "{app}\{#MyAppExeName}"; Parameters: "run"; Tasks: desktopicon
; Startup entry (optional task)
Name: "{userstartup}\AutoShowTracker"; Filename: "{app}\{#MyAppExeName}"; Parameters: "run"; Tasks: startupentry

[Run]
; Initialize the database after install
Filename: "{app}\{#MyAppExeName}"; Parameters: "init-db"; StatusMsg: "Initializing database..."; Flags: runhidden waituntilterminated
; Offer to launch after install
Filename: "{app}\{#MyAppExeName}"; Parameters: "run"; Description: "Launch AutoShowTracker"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up log files on uninstall (but NOT the database — that's user data)
Type: filesandordirs; Name: "{userappdata}\show-tracker\logs"

[Code]
// Show a note about user data preservation during uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    MsgBox('AutoShowTracker has been uninstalled.' + #13#10 + #13#10 +
           'Your watch history database is preserved at:' + #13#10 +
           ExpandConstant('{userprofile}') + '\.show-tracker\watch_history.db' + #13#10 + #13#10 +
           'Delete that folder manually if you want to remove all data.',
           mbInformation, MB_OK);
  end;
end;
