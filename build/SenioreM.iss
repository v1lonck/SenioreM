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
DefaultDirName={code:InstallDir}
UsePreviousAppDir=no
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

[InstallDelete]
; старая папка с русскими буквами в пути (если программа переехала в C:\SenioreM)
Type: filesandordirs; Name: "{localappdata}\Programs\SenioreM"; Check: OldDirDiffers

[Icons]
Name: "{autodesktop}\SenioreM"; Filename: "{app}\SenioreM.exe"; IconFilename: "{app}\SenioreM.exe"; Comment: "SenioreM — голосовой помощник"
Name: "{autoprograms}\SenioreM"; Filename: "{app}\SenioreM.exe"; IconFilename: "{app}\SenioreM.exe"; Comment: "SenioreM — голосовой помощник"

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

{ Путь установки без русских букв: голосовые библиотеки не понимают кириллицу в пути }
function IsAscii(S: String): Boolean;
var
  I: Integer;
begin
  Result := True;
  for I := 1 to Length(S) do
    if Ord(S[I]) > 127 then
    begin
      Result := False;
      Exit;
    end;
end;

function InstallDir(Param: String): String;
begin
  Result := ExpandConstant('{localappdata}\Programs\SenioreM');
  if not IsAscii(Result) then
    Result := ExpandConstant('{sd}\SenioreM');
end;

function OldDirDiffers: Boolean;
begin
  Result := CompareText(ExpandConstant('{app}'),
                        ExpandConstant('{localappdata}\Programs\SenioreM')) <> 0;
end;

{ Окно установки в том же дизайне, что и окно загрузки программы }
procedure ShowInstallSplash;
var
  Logo, Track: TBitmapImage;
  W, H, Y: Integer;
begin
  W := ScaleX(860);
  H := ScaleY(500);
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
  Logo.Left := W - ScaleX(190);
  Logo.Top := ScaleY(70);
  Logo.Width := ScaleX(128);
  Logo.Height := ScaleY(128);
  Logo.Stretch := True;
  Logo.Bitmap.LoadFromFile(ExpandConstant('{tmp}\install_logo.bmp'));

  MakeText(Splash, ScaleX(56), ScaleY(64), 'ГОЛОСОВОЙ ПОМОЩНИК ДЛЯ WINDOWS', 8, $FF8C5B, True);
  with MakeText(Splash, ScaleX(52), ScaleY(84), 'SenioreM', 44, $F5EFEC, False) do
    Font.Name := 'Segoe UI Light';
  MakeText(Splash, ScaleX(56), ScaleY(170), 'Скажите «Сеньор» — остальное он сделает сам.', 13, $A6938A, False);

  Y := ScaleY(232);
  MakeText(Splash, ScaleX(56), Y, '01', 9, $FF8C5B, True);
  MakeText(Splash, ScaleX(84), Y - ScaleY(2), 'Звук и громкость', 11, $F5EFEC, True);
  MakeText(Splash, ScaleX(84), Y + ScaleY(22), '«Сеньор, громкость десять»', 9, $6E5C53, False);
  MakeText(Splash, ScaleX(460), Y, '02', 9, $FF8C5B, True);
  MakeText(Splash, ScaleX(488), Y - ScaleY(2), 'Открыть и закрыть программы', 11, $F5EFEC, True);
  MakeText(Splash, ScaleX(488), Y + ScaleY(22), '«Сеньор, открой осу»', 9, $6E5C53, False);
  Y := ScaleY(294);
  MakeText(Splash, ScaleX(56), Y, '03', 9, $FF8C5B, True);
  MakeText(Splash, ScaleX(84), Y - ScaleY(2), 'Сайты и поиск', 11, $F5EFEC, True);
  MakeText(Splash, ScaleX(84), Y + ScaleY(22), '«Сеньор, открой яндекс музыку»', 9, $6E5C53, False);
  MakeText(Splash, ScaleX(460), Y, '04', 9, $FF8C5B, True);
  MakeText(Splash, ScaleX(488), Y - ScaleY(2), 'Музыка, время, скриншоты', 11, $F5EFEC, True);
  MakeText(Splash, ScaleX(488), Y + ScaleY(22), '«Сеньор, который час»', 9, $6E5C53, False);

  MakeText(Splash, ScaleX(56), H - ScaleY(88), 'Устанавливаю — через несколько секунд программа откроется сама', 10, $A6938A, False);
  BarW := W - ScaleX(112);
  Track := TBitmapImage.Create(Splash);
  Track.Parent := Splash;
  Track.Left := ScaleX(56);
  Track.Top := H - ScaleY(56);
  Track.Width := BarW;
  Track.Height := ScaleY(3);
  Track.BackColor := $382B25;

  BarFill := TBitmapImage.Create(Splash);
  BarFill.Parent := Splash;
  BarFill.Left := ScaleX(56);
  BarFill.Top := H - ScaleY(56);
  BarFill.Width := ScaleX(8);
  BarFill.Height := ScaleY(3);
  BarFill.BackColor := $FF8C5B;

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

{ Перед установкой закрываем запущенный SenioreM и движок ИИ, иначе их файлы заняты
  («Отказано в доступе» при замене файлов). }
procedure KillApp;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM SenioreM.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM llama-server.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Sleep(1200);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  KillApp;
  Result := '';
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
