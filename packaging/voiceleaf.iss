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
AppName=VoiceLeaf
AppVersion={#AppVersion}
AppPublisher=VoiceLeaf
AppPublisherURL=https://github.com/Dewmith/Text2Voice
AppSupportURL=https://github.com/Dewmith/Text2Voice/issues
DefaultDirName={localappdata}\Programs\VoiceLeaf
DefaultGroupName=VoiceLeaf
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
OutputDir={#InstallerOutputDir}
OutputBaseFilename=VoiceLeaf-{#AppVersion}-windows-x64-setup
VersionInfoVersion={#WindowsVersion}
VersionInfoProductVersion={#WindowsVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoProductTextVersion={#AppVersion}
UninstallDisplayIcon={app}\VoiceLeaf.exe
CreateUninstallRegKey=not IsVerificationInstall
UsePreviousAppDir=not IsVerificationInstall
UsePreviousTasks=not IsVerificationInstall
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

[Icons]
Name: "{group}\VoiceLeaf"; Filename: "{app}\VoiceLeaf.exe"; Check: not IsVerificationInstall
Name: "{autodesktop}\VoiceLeaf"; Filename: "{app}\VoiceLeaf.exe"; Tasks: desktopicon; Check: not IsVerificationInstall

[Run]
Filename: "{app}\VoiceLeaf.exe"; Description: "Launch VoiceLeaf"; Flags: nowait postinstall skipifsilent

[Code]
function IsVerificationInstall: Boolean;
begin
  { CI checks must not replace a user's normal uninstall registration/shortcuts. }
  Result := ExpandConstant('{param:VERIFYINSTALL|0}') = '1';
end;
