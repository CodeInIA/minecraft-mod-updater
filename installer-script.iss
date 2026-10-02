; Minecraft Mod Updater - Inno Setup script
; Build the app first with: pyinstaller --noconfirm mod_updater.spec
; The release workflow passes the version with /DMyAppVersion=x.y.z

#define MyAppName "Minecraft Mod Updater"
#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif
#define MyAppPublisher "CodeInIA"
#define MyAppURL "https://github.com/CodeInIA/minecraft-mod-updater"
#define MyAppExeName "mod_updater.exe"

[Setup]
; Keep this AppId unchanged so new installers upgrade existing installations.
AppId={{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
PrivilegesRequired=admin
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=installer
OutputBaseFilename=MinecraftModUpdater_Setup
SetupIconFile=updater-logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage

[Languages]
; The installer picks the Windows display language automatically (English if it is not listed).
; Each Inno Setup release ships a slightly different set of languages, so only the ones
; present in the compiler used for the build are included.
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists(AddBackslash(CompilerPath) + "Languages\Arabic.isl")
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Armenian.isl")
Name: "armenian"; MessagesFile: "compiler:Languages\Armenian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\BrazilianPortuguese.isl")
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Bulgarian.isl")
Name: "bulgarian"; MessagesFile: "compiler:Languages\Bulgarian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Catalan.isl")
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Corsican.isl")
Name: "corsican"; MessagesFile: "compiler:Languages\Corsican.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Czech.isl")
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Danish.isl")
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Dutch.isl")
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Finnish.isl")
Name: "finnish"; MessagesFile: "compiler:Languages\Finnish.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\French.isl")
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\German.isl")
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Hebrew.isl")
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Hungarian.isl")
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Icelandic.isl")
Name: "icelandic"; MessagesFile: "compiler:Languages\Icelandic.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Italian.isl")
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Japanese.isl")
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Korean.isl")
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Norwegian.isl")
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Polish.isl")
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Portuguese.isl")
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Russian.isl")
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Slovak.isl")
Name: "slovak"; MessagesFile: "compiler:Languages\Slovak.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Slovenian.isl")
Name: "slovenian"; MessagesFile: "compiler:Languages\Slovenian.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Spanish.isl")
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Swedish.isl")
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Tamil.isl")
Name: "tamil"; MessagesFile: "compiler:Languages\Tamil.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Turkish.isl")
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
#endif
#if FileExists(AddBackslash(CompilerPath) + "Languages\Ukrainian.isl")
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
#endif
; Not bundled with Inno Setup: https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation (MIT)
Name: "chinesesimplified"; MessagesFile: "packaging\windows\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Files left by the 1.x console version
Type: files; Name: "{app}\README.md"

[Files]
Source: "dist\mod_updater\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "updater-logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\updater-logo.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Never touch an existing desktop shortcut (recreating it moves it on the desktop) and never
; create one during a silent update started from the app, so a deleted shortcut stays deleted.
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\updater-logo.ico"; Tasks: desktopicon; Check: ShouldCreateDesktopShortcut

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Silent install = update started from inside the app: reopen it as the normal (non-admin) user
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser skipifnotsilent

[Code]
function ShouldCreateDesktopShortcut: Boolean;
begin
  Result := (not WizardSilent) and
            (not FileExists(ExpandConstant('{autodesktop}\{#MyAppName}.lnk')));
end;
