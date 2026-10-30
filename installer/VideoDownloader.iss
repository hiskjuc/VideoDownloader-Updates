; VideoDownloader_Setup.iss

[Setup]
AppName=VideoDownloader
AppVersion=1.1.0
AppPublisher=VideoDownloader

DefaultDirName={autopf}\VideoDownloader
DefaultGroupName=VideoDownloader
DisableProgramGroupPage=yes

ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

OutputDir=..\dist-installer
OutputBaseFilename=VideoDownloader_Setup

SetupIconFile=icon.ico
UninstallDisplayIcon={app}\VideoDownloader.exe

Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "..\dist\VideoDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VideoDownloader"; Filename: "{app}\VideoDownloader.exe"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,VideoDownloader}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VideoDownloader"; Filename: "{app}\VideoDownloader.exe"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\VideoDownloader.exe"; Description: "Executar VideoDownloader"; Flags: nowait postinstall skipifsilent