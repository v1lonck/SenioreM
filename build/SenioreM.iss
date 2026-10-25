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
AppPublisherURL=https://github.com/v1lonck/SenioreM
AppSupportURL=https://github.com/v1lonck/SenioreM/issues
AppUpdatesURL=https://github.com/v1lonck/SenioreM/releases
VersionInfoVersion={#AppVersion}
VersionInfoCompany=SenioreM
VersionInfoDescription=Установщик SenioreM — голосовой помощник для Windows
VersionInfoProductName=SenioreM
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=© 2026 v1lonck
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
SetupIconFile=..\assets\icon.ico
ChangesAssociations=yes
UninstallDisplayIcon={app}\SenioreM.ico
UninstallDisplayName=SenioreM
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=no
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
; значок ярлыка отдельным файлом — Windows показывает его сразу, без задержки кэша значков
Source: "..\assets\icon.ico"; DestDir: "{app}"; DestName: "SenioreM.ico"; Flags: ignoreversion
Source: "..\dist\SenioreM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; старая папка с русскими буквами в пути (если программа переехала в C:\SenioreM)
Type: filesandordirs; Name: "{localappdata}\Programs\SenioreM"; Check: OldDirDiffers

[Icons]
Name: "{autodesktop}\SenioreM"; Filename: "{app}\SenioreM.exe"; IconFilename: "{app}\SenioreM.ico"; Comment: "SenioreM — голосовой помощник"
Name: "{autoprograms}\SenioreM"; Filename: "{app}\SenioreM.exe"; IconFilename: "{app}\SenioreM.ico"; Comment: "SenioreM — голосовой помощник"

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

{ Можно ли заменить уже установленные файлы без прав администратора?
  Если прошлое обновление ставилось с правами администратора, файлы принадлежат
  администраторам — обычная установка получит «Отказано в доступе». }
function CanReplaceInstalled: Boolean;
var
  F: String;
begin
  Result := True;
  F := InstallDir('') + '\SenioreM.exe';
  if not FileExists(F) then
    Exit;
  if RenameFile(F, F + '.check') then
    RenameFile(F + '.check', F)
  else
    Result := False;
end;

function InitializeSetup: Boolean;
var
  Code: Integer;
begin
  Result := True;
  { SenioreM работает с правами администратора — обычный установщик не сможет заменить его
    файлы. Перезапускаем установку с правами администратора (Windows спросит один раз). }
  if (not IsAdmin) and (FileExists(ExpandConstant('{userappdata}\SenioreM\admin_mode'))
                       or (not CanReplaceInstalled)) then
    if ShellExec('runas', ExpandConstant('{srcexe}'),
                 '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS ' +
                 '/nosplash=' + ExpandConstant('{param:nosplash|0}'),
                 '', SW_SHOWNORMAL, ewNoWait, Code) then
    begin
      Result := False;
      Exit;
    end;
end;

{ Перед установкой закрываем запущенный SenioreM и движок ИИ, иначе их файлы заняты
  («Отказано в доступе» при замене файлов). }
procedure KillApp;
var
  Code, Code2, I: Integer;
begin
  { SenioreM не запущен (его файл можно заменить) — ничего не ждём, ставим сразу }
  if CanReplaceInstalled then
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM llama-server.exe', '', SW_HIDE,
         ewWaitUntilTerminated, Code2);
    Exit;
  end;
  { сначала просим SenioreM закрыться самому (работает, даже если он запущен от администратора) }
  ForceDirectories(ExpandConstant('{userappdata}\SenioreM'));
  SaveStringToFile(ExpandConstant('{userappdata}\SenioreM\quit.flag'), '1', False);
  for I := 1 to 12 do
  begin
    Sleep(250);
    if CanReplaceInstalled then
      Break;
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM SenioreM.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM llama-server.exe', '', SW_HIDE,
       ewWaitUntilTerminated, Code2);
  { SenioreM работает с правами администратора — обычный установщик закрыть его не может
    («Отказано в доступе»). Тогда закрываем с правами администратора (Windows спросит). }
  if ((Code = 1) or (Code2 = 1)) and not CanReplaceInstalled then
  begin
    ShellExec('runas', ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM SenioreM.exe', '',
              SW_HIDE, ewWaitUntilTerminated, Code);
    ShellExec('runas', ExpandConstant('{sys}\taskkill.exe'), '/F /IM llama-server.exe', '',
              SW_HIDE, ewWaitUntilTerminated, Code2);
  end;
  for I := 1 to 8 do
  begin
    if CanReplaceInstalled then
      Break;
    Sleep(250);
  end;
end;

function WantSplash: Boolean;
begin
  { при автообновлении из программы (/nosplash=1) окно не нужно — SenioreM сам откроется }
  Result := ExpandConstant('{param:nosplash|0}') = '0';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { наше окно с прогрессом — сразу, ещё до закрытия старой версии }
  if WantSplash and (Splash = nil) then
    ShowInstallSplash;
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
  { стандартное окно мастера не показываем вовсе — только своё окно с прогрессом
    (без перезапуска установщика самого себя: антивирусы такого не любят) }
  if ExpandConstant('{param:showwizard|0}') = '0' then
  begin
    WizardForm.Position := poDesigned;
    WizardForm.Left := -32000;
    WizardForm.Top := -32000;
  end;
end;

{ Страницы мастера не показываем вовсе — сразу установка }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpWelcome) or (PageID = wpSelectDir) or (PageID = wpSelectProgramGroup) or
            (PageID = wpReady) or (PageID = wpFinished);
end;

{ Если мастер всё-таки открылся — не ждём нажатия «Установить», ставим сразу }
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
    WizardForm.NextButton.OnClick(WizardForm.NextButton);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  { при автообновлении из программы окно не показываем — SenioreM сам откроется снова }
  { при ручной установке показываем окно (чтобы не нажимали установщик повторно);
    при автообновлении из программы (/nosplash=1) — не показываем: SenioreM сам откроется }
  if (CurStep = ssInstall) and WantSplash and (Splash = nil) then
    ShowInstallSplash;
  { после установки с правами администратора разрешаем обычному пользователю менять файлы —
    чтобы следующие обновления ставились без окон и ошибок }
  if (CurStep = ssPostInstall) and IsAdmin then
    Exec(ExpandConstant('{sys}\icacls.exe'), '"' + ExpandConstant('{app}') + '" /grant *S-1-5-32-545:(OI)(CI)M /T /C /Q',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
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
