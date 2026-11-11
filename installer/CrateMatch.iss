; Inno Setup script for CrateMatch. Build with "Build Installer.bat" in the folder above.
#define AppName "CrateMatch"
; Build Installer.bat passes the version from cratematch\__init__.py (/DAppVersion=...).
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "CrateMatch.exe"

[Setup]
AppId={{3B7D2E94-6A1C-4F58-9E2B-C41D8A7F6E03}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=xoxoFaith
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
; Per-user install: no admin prompt needed.
PrivilegesRequired=lowest
InfoAfterFile=README.txt
OutputDir=Output
OutputBaseFilename=CrateMatchSetup
SetupIconFile=..\cratematch\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open CrateMatch now"; Flags: nowait postinstall skipifsilent
; After a self-update (the app runs this installer with /UPDATE=1): reopen it.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: IsUpdate

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im ""{#AppExe}"""; Flags: runhidden; RunOnceId: "StopApp"

[Code]
function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:update|0}') = '1';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  rc: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Sleep(800);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if SuppressibleMsgBox('Also delete CrateMatch''s settings and Spotify sign-in?' + #13#10 +
              '(Your music and VirtualDJ playlists are never touched.)',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\CrateMatch'), True, True, True);
end;
