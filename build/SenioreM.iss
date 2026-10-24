; Установщик SenioreM (Inno Setup 6). Собирается в GitHub Actions.
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #undef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8C4E2B7A-3F1D-4E7B-9A51-5E0C2D9F6B13}
AppName=SenioreM
AppVersion={#AppVersion}
AppVerName=SenioreM {#AppVersion}
AppPublisher=SenioreM
DefaultDirName={localappdata}\Programs\SenioreM
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
DisableFinishedPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\Output
OutputBaseFilename=SenioreM-Setup
SetupIconFile=setup.ico
ChangesAssociations=yes
UninstallDisplayIcon={app}\SenioreM.exe
UninstallDisplayName=SenioreM
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
WizardSizePercent=110
WizardImageFile=wizard_164.bmp,wizard_410.bmp
WizardSmallImageFile=small_55.bmp,small_138.bmp
CloseApplications=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
ru.WelcomeLabel1=SenioreM
ru.WelcomeLabel2=Голосовой помощник для Windows.%n%nСкажите «Сеньор» — и он сделает сам:%n%n•  поменяет громкость и яркость%n•  откроет программу или сайт%n•  найдёт в интернете%n•  поставит музыку на паузу, скажет время%n%nУстановка займёт несколько секунд. Ярлык появится на рабочем столе.
ru.FinishedHeadingLabel=Готово
ru.FinishedLabel=SenioreM установлен, ярлык — на рабочем столе.%n%nПри первом запуске программа один раз докачает речевую модель (около 45 МБ).

[Files]
Source: "..\dist\SenioreM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\SenioreM"; Filename: "{app}\SenioreM.exe"
Name: "{autoprograms}\SenioreM"; Filename: "{app}\SenioreM.exe"

[Run]
; сразу после установки запускаем программу
Filename: "{app}\SenioreM.exe"; Flags: nowait

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\SenioreM"
Type: filesandordirs; Name: "{commonappdata}\SenioreM"

[Code]
var
  Installed: Boolean;

function SetupOnDesktop: Boolean;
var
  Desk: String;
begin
  Desk := AddBackslash(Lowercase(ExpandConstant('{userdesktop}')));
  Result := Pos(Desk, Lowercase(ExpandConstant('{srcexe}'))) = 1;
end;

{ Тёмное оформление установщика в цветах программы }
procedure InitializeWizard;
var
  Dark, Panel, TextC, Muted: TColor;
begin
  Dark := $120D0B;   { #0B0D12 }
  Panel := $231A16;  { #161A23 }
  TextC := $F5EFEC;  { #ECEFF5 }
  Muted := $A6938A;  { #8A93A6 }
  WizardForm.Color := Dark;
  WizardForm.InnerPage.Color := Dark;
  WizardForm.InstallingPage.Color := Dark;
  WizardForm.MainPanel.Color := Panel;
  WizardForm.Bevel.Visible := False;
  WizardForm.Bevel1.Visible := False;
  WizardForm.PageNameLabel.Font.Color := TextC;
  WizardForm.PageDescriptionLabel.Font.Color := Muted;
  WizardForm.StatusLabel.Font.Color := TextC;
  WizardForm.FilenameLabel.Font.Color := Muted;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    Installed := True;
end;

{ Установщик, скачанный на рабочий стол, убираем после установки,
  чтобы на рабочем столе остался только ярлык SenioreM. }
procedure DeinitializeSetup;
var
  Code: Integer;
begin
  if Installed and SetupOnDesktop then
    Exec(ExpandConstant('{cmd}'),
         '/c ping 127.0.0.1 -n 4 >nul & del /f /q "' + ExpandConstant('{srcexe}') + '"',
         '', SW_HIDE, ewNoWait, Code);
end;
