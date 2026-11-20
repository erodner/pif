; Inno Setup script for the Windows installer.
; iscc /DAppVersion=0.5.0 /DSourceDir=dist\PromptInjectionFinder /DOutputDir=release packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\PromptInjectionFinder"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

[Setup]
AppId={{6C1E0B2B-8E44-4C55-9B6B-5F2E8A9D3F11}
AppName=Prompt Injection Finder
AppVersion={#AppVersion}
AppPublisher=promptinjectorfinder contributors
AppPublisherURL=https://github.com/erodner/pif
DefaultDirName={autopf}\Prompt Injection Finder
DefaultGroupName=Prompt Injection Finder
UninstallDisplayIcon={app}\PromptInjectionFinder.exe
LicenseFile=..\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=PromptInjectionFinder-{#AppVersion}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
ChangesEnvironment=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "addtopath"; Description: "Add the pif command line tool to PATH"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Prompt Injection Finder"; Filename: "{app}\PromptInjectionFinder.exe"
Name: "{group}\Uninstall Prompt Injection Finder"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Prompt Injection Finder"; Filename: "{app}\PromptInjectionFinder.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\PromptInjectionFinder.exe"; Description: "Launch Prompt Injection Finder"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
