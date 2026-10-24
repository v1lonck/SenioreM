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
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\Output
OutputBaseFilename=SenioreM-Setup
SetupIconFile=..\assets\icon.ico
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
Filename: "{app}\SenioreM.exe"; Description: "Запустить SenioreM"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\SenioreM"
