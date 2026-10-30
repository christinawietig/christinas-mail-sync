; Inno-Setup-Skript fuer die Windows-Installation (setup.exe).
; Bauen:  iscc /DAppVersion=1.2.3 installer\windows.iss
; Vorher: pyinstaller mailsync.spec  (-> dist\Christinas Mail-Sync\)
;
; Installiert ohne Administratorrechte fuer den angemeldeten Benutzer
; (%LOCALAPPDATA%\Programs), mit Eintrag im Startmenue und auf Wunsch auf dem Desktop.
; Einstellungen und Liste der uebertragenen Mails (%APPDATA%) bleiben beim Deinstallieren erhalten.

#define AppName "Christinas Mail-Sync"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{695C6AFB-3343-4A25-90BB-CED08A5B8A8C}
AppName={#AppName}
AppVersion={#AppVersion}
; Version im Titel des Installers und in den Dateieigenschaften der Setup.exe
; (der Dateiname bleibt gleich, damit die Download-Links in der README immer stimmen)
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription={#AppName} {#AppVersion} Setup
VersionInfoCompany=Christina Wietig
AppPublisher=Christina Wietig
AppPublisherURL=https://github.com/christinawietig/christinas-mail-sync
AppSupportURL=https://github.com/christinawietig/christinas-mail-sync
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Christinas-Mail-Sync-Setup
SetupIconFile=..\assets\MailSync.ico
UninstallDisplayIcon={app}\{#AppName}.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Reste einer aelteren Version entfernen
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
