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
CloseApplications=force

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
ru.WelcomeLabel1=SenioreM
ru.WelcomeLabel2=Голосовой помощник для Windows.%n%nСкажите «Сеньор» — и он сделает сам:%n%n•  поменяет громкость и яркость%n•  откроет программу или сайт%n•  найдёт в интернете%n•  поставит музыку на паузу, скажет время%n%nУстановка займёт несколько секунд. Ярлык появится на рабочем столе.
ru.FinishedHeadingLabel=Готово
ru.FinishedLabel=SenioreM установлен, ярлык — на рабочем столе.%n%nПри первом запуске программа один раз докачает речевую модель (около 45 МБ).

[Files]
Source: "install_logo.bmp"; Flags: dontcopy
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
  Splash: TSetupForm;
  BarFill: TBitmapImage;
  BarW: Integer;

function MakeText(Form: TSetupForm; X, Y: Integer; Text: String; Size: Integer;
  Color: TColor; Bold: Boolean): TNewStaticText;
begin
  Result := TNewStaticText.Create(Form);
  Result.Parent := Form;
  Result.Left := X;
  Result.Top := Y;
  Result.Font.Name := 'Segoe UI';
  Result.Font.Size := Size;
  Result.Font.Color := Color;
  if Bold then
    Result.Font.Style := [fsBold];
  Result.Caption := Text;
end;

{ Своё тёмное окно «Устанавливаю…» вместо мастера установки }
procedure ShowInstallSplash;
var
  Logo, Track: TBitmapImage;
  W, H: Integer;
begin
  W := ScaleX(560);
  H := ScaleY(280);
#if Ver >= 0x06040000
  Splash := CreateCustomForm(W, H, False, False);
#else
  Splash := CreateCustomForm;
#endif
  Splash.BorderStyle := bsNone;
  Splash.ClientWidth := W;
  Splash.ClientHeight := H;
  Splash.Color := $120D0B;
  Splash.Position := poScreenCenter;
  Splash.Caption := 'SenioreM';

  ExtractTemporaryFile('install_logo.bmp');
  Logo := TBitmapImage.Create(Splash);
  Logo.Parent := Splash;
  Logo.Left := ScaleX(40);
  Logo.Top := ScaleY(40);
  Logo.Width := ScaleX(72);
  Logo.Height := ScaleY(72);
  Logo.Stretch := True;
  Logo.Bitmap.LoadFromFile(ExpandConstant('{tmp}\install_logo.bmp'));

  MakeText(Splash, ScaleX(132), ScaleY(42), 'SenioreM', 24, $F5EFEC, False);
  MakeText(Splash, ScaleX(135), ScaleY(88), 'ГОЛОСОВОЙ ПОМОЩНИК', 8, $FF8C5B, True);
  MakeText(Splash, ScaleX(40), ScaleY(170), 'Устанавливаю SenioreM…', 11, $F5EFEC, False);

  BarW := W - ScaleX(80);
  Track := TBitmapImage.Create(Splash);
  Track.Parent := Splash;
  Track.Left := ScaleX(40);
  Track.Top := ScaleY(206);
  Track.Width := BarW;
  Track.Height := ScaleY(4);
  Track.BackColor := $382B25;

  BarFill := TBitmapImage.Create(Splash);
  BarFill.Parent := Splash;
  BarFill.Left := ScaleX(40);
  BarFill.Top := ScaleY(206);
  BarFill.Width := ScaleX(8);
  BarFill.Height := ScaleY(4);
  BarFill.BackColor := $FF8C5B;

  MakeText(Splash, ScaleX(40), ScaleY(228),
    'Через несколько секунд программа откроется сама', 9, $A6938A, False);
  Splash.Show;
  Splash.Repaint;
end;

{ Окна мастера не показываем: установщик перезапускает себя в тихом режиме
  и показывает только своё тёмное окно с прогрессом. }
function InitializeSetup: Boolean;
var
  Code: Integer;
begin
  Result := True;
  if not WizardSilent then
    if Exec(ExpandConstant('{srcexe}'),
            '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS',
            '', SW_SHOWNORMAL, ewNoWait, Code) then
      Result := False;
end;

{ Тёмное оформление мастера — на случай, если он всё же понадобится }
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
  WizardForm.ReadyLabel.Font.Color := TextC;
end;

{ Если мастер всё-таки открылся — не ждём нажатия «Установить», ставим сразу }
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
    WizardForm.NextButton.OnClick(WizardForm.NextButton);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) and WizardSilent then
    ShowInstallSplash;
  if (CurStep = ssPostInstall) and (Splash <> nil) then
  begin
    BarFill.Width := BarW;
    Splash.Repaint;
  end;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  NewW: Integer;
begin
  if (Splash <> nil) and (MaxProgress > 0) then
  begin
    NewW := Round(BarW * (CurProgress / MaxProgress));
    if NewW < ScaleX(8) then
      NewW := ScaleX(8);
    BarFill.Width := NewW;
    Splash.Repaint;
  end;
end;

procedure DeinitializeSetup;
begin
  if Splash <> nil then
  begin
    Splash.Close;
    Splash.Free;
    Splash := nil;
  end;
end;
