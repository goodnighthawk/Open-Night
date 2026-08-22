#ifndef MyAppVersion
  #define MyAppVersion "2.0"
#endif
#ifndef MyVersionQuad
  #define MyVersionQuad "2.0.0.0"
#endif
#ifndef SourceExe
  #define SourceExe "..\..\dist\windows\OpenNight.exe"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\windows"
#endif
#ifndef SetupIcon
  #define SetupIcon "..\..\build\windows\snakepit.ico"
#endif

[Setup]
AppId={{7A209AA7-EDF9-4BB0-AD60-062459BBD219}
AppName=Open Night
AppVersion={#MyAppVersion}
AppVerName=Open Night {#MyAppVersion}
AppPublisher=Snakepit LLC
AppCopyright=Copyright (C) 2026 Snakepit LLC
DefaultDirName={localappdata}\Programs\Open Night
DefaultGroupName=Open Night
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=OpenNight-Setup-{#MyAppVersion}
OutputManifestFile=OpenNight-Setup-{#MyAppVersion}-manifest.txt
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\OpenNight.exe
VersionInfoVersion={#MyVersionQuad}
VersionInfoCompany=Snakepit LLC
VersionInfoDescription=Open Night Installer
VersionInfoProductName=Open Night
VersionInfoProductVersion={#MyAppVersion}
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "OpenNight.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Open Night"; Filename: "{app}\OpenNight.exe"
Name: "{autodesktop}\Open Night"; Filename: "{app}\OpenNight.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OpenNight.exe"; Description: "Launch Open Night"; Flags: nowait postinstall skipifsilent
