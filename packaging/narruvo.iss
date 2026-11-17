; Compile through scripts/build.ps1; all build paths and versions are explicit.
#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif
#ifndef WindowsVersion
  #error WindowsVersion must be supplied by the build script
#endif
#ifndef BundleDir
  #error BundleDir must be supplied by the build script
#endif
#ifndef InstallerOutputDir
  #error InstallerOutputDir must be supplied by the build script
#endif

[Setup]
AppId={{8748FC96-84F0-4F51-93B2-3F667F937686}
AppName=Narruvo
AppVersion={#AppVersion}
AppPublisher=Narruvo
AppPublisherURL=https://github.com/Dewmith/Narruvo
AppSupportURL=https://github.com/Dewmith/Narruvo/issues
DefaultDirName={localappdata}\Programs\Narruvo
DefaultGroupName=Narruvo
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
OutputDir={#InstallerOutputDir}
OutputBaseFilename=Narruvo-{#AppVersion}-windows-x64-setup
VersionInfoVersion={#WindowsVersion}
VersionInfoProductVersion={#WindowsVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoProductTextVersion={#AppVersion}
UninstallDisplayIcon={app}\Narruvo.exe
CreateUninstallRegKey=not IsVerificationInstall
UsePreviousAppDir=not IsVerificationInstall
UsePreviousTasks=not IsVerificationInstall
UsePreviousGroup=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked; Check: not IsVerificationInstall

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Keep the stable AppId while replacing the old executable and default shortcuts.
Type: files; Name: "{app}\VoiceLeaf.exe"
Type: files; Name: "{userprograms}\VoiceLeaf\VoiceLeaf.lnk"; Check: not IsVerificationInstall
Type: dirifempty; Name: "{userprograms}\VoiceLeaf"; Check: not IsVerificationInstall
Type: files; Name: "{userdesktop}\VoiceLeaf.lnk"; Check: not IsVerificationInstall

[Icons]
Name: "{group}\Narruvo"; Filename: "{app}\Narruvo.exe"; Check: not IsVerificationInstall
Name: "{autodesktop}\Narruvo"; Filename: "{app}\Narruvo.exe"; Tasks: desktopicon; Check: not IsVerificationInstall

[Run]
Filename: "{app}\Narruvo.exe"; Description: "Launch Narruvo"; Flags: nowait postinstall skipifsilent

[Code]
function IsVerificationInstall: Boolean;
begin
  { CI checks must not replace a user's normal uninstall registration/shortcuts. }
  Result := ExpandConstant('{param:VERIFYINSTALL|0}') = '1';
end;
