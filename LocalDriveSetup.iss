; filepath: e:\CODING\Tools\Local_Drive_Krishna\build_exe_final\win-build\LocalDriveSetup.iss
#define MyAppName "LocalDrive"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "RANJAN SOFTWARES"
#define MyAppURL "https://github.com/ranjanlive/localDrive"
#define MyAppExeName "LocalDrive.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".localdrive"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt
#define MyAppLicense "LICENSE"

[Setup]
; NOTE: The value of AppId uniquely identifies this application. Do not use the same AppId in installers for other applications.
AppId={{E1393C8B-7936-42E6-BD6C-068C94B682D9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Uncomment the following line to run in non administrative install mode (install for current user only.)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_output
OutputBaseFilename=LocalDriveSetup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
WizardResizable=no
UninstallDisplayIcon={app}\icon.ico
; License file - Show GNU GPL during installation
LicenseFile=dist\LICENSE
InfoBeforeFile=gpl_notice.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode
Name: "startup"; Description: "Start LocalDrive when Windows starts"; GroupDescription: "Windows Integration"; Flags: unchecked
Name: "contextmenu"; Description: "Add 'Share with LocalDrive' to Explorer context menu"; GroupDescription: "Windows Integration"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\settings.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\static\*"; DestDir: "{app}\static\"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\templates\*"; DestDir: "{app}\templates\"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\License"; Filename: "{app}\LICENSE"; Comment: "View GNU GPL License"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "notepad"; Parameters: "{app}\LICENSE"; Description: "View GNU GPL License"; Flags: postinstall shellexec skipifsilent unchecked

[Registry]
; Register LocalDrive in the registry for context menu integration if selected
Root: HKCU; Subkey: "Software\{#MyAppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "License"; ValueData: "GNU GPL v3"; Flags: uninsdeletekey
; Add to Explorer right-click menu when the task is selected
Root: HKCR; Subkey: "Directory\shell\LocalDrive"; ValueType: string; ValueName: ""; ValueData: "Share with LocalDrive"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\shell\LocalDrive"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icon.ico"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCR; Subkey: "Directory\shell\LocalDrive\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --folder ""%V"""; Tasks: contextmenu; Flags: uninsdeletekey

[Code]
// Additional code to show warnings, perform validation, etc.
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// Ask user if they want to start LocalDrive after installation
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    // Update settings.json if the context menu task was selected
    if WizardIsTaskSelected('contextmenu') then begin
      // We'll just let the application handle this when it runs
    end;
  end;
end;