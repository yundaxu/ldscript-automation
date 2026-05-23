; 模拟器脚本自助 — Inno Setup 安装脚本
; 用法: 安装 Inno Setup (https://jrsoftware.org/isinfo.php) 后用 ISCC.exe 编译此文件

#define MyAppName "模拟器脚本自助"
#define MyAppVersion "1.0"
#define MyAppPublisher "墨尔本的晴空"
#define MyAppURL "https://github.com/yundaxu/ldscript-automation"
#define MyAppExeName "模拟器脚本自助.exe"

[Setup]
AppId={{A8F3E5D2-7B4C-4E9A-8F1D-2C6E5A3B0D7F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=模拟器脚本自助_Setup_v1.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden

[Code]
function InitializeSetup: Boolean;
begin
  Result := True;
end;
