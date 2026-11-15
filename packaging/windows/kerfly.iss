; Windows installer of Kerfly (Inno Setup 6). Built by the release workflow:
;
;   iscc /DAppVersion=0.18.0 packaging\windows\kerfly.iss
;
; from the PyInstaller folder dist\Kerfly (packaging\kerfly.spec). When
; packaging\windows\K40_Driver_Install.exe is there (Scorch's K40 USB driver
; installer, downloaded and checked by the workflow), the installer offers to
; install the K40 driver too.
;
; Copyright (C) 2026 Kerfly contributors
; Licensed under the GNU General Public License v3 or later. See LICENSE.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define Root "..\.."

[Setup]
AppId={{6E3C2F0A-6B1D-4B67-9C2B-5A6F2E8D4C11}
AppName=Kerfly
AppVersion={#AppVersion}
AppVerName=Kerfly {#AppVersion}
AppPublisher=Kerfly contributors
; the installer's own file details (code signing needs the product name and version set)
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Kerfly
VersionInfoProductVersion={#AppVersion}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoCompany=Kerfly contributors
VersionInfoDescription=Kerfly setup
VersionInfoCopyright=GPL-3.0-or-later, Kerfly contributors
AppPublisherURL=https://cyryllo.github.io/Kerfly/
AppSupportURL=https://github.com/cyryllo/Kerfly/issues
AppUpdatesURL=https://github.com/cyryllo/Kerfly/releases
DefaultDirName={autopf}\Kerfly
DefaultGroupName=Kerfly
DisableProgramGroupPage=yes
LicenseFile={#Root}\LICENSE
SetupIconFile={#Root}\kerfly\gui\icons\kerfly.ico
UninstallDisplayIcon={app}\Kerfly.exe
OutputDir={#Root}\dist
OutputBaseFilename=Kerfly-{#AppVersion}-windows-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; the K40 driver needs administrator rights anyway
PrivilegesRequired=admin
; .kerfly projects open in Kerfly with a double click
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.DriverTask=Install the USB driver for the K40 laser (Lihuiyu board, libusb-win32)
polish.DriverTask=Zainstaluj sterownik USB lasera K40 (płyta Lihuiyu, libusb-win32)
german.DriverTask=USB-Treiber für den K40-Laser installieren (Lihuiyu-Platine, libusb-win32)
spanish.DriverTask=Instalar el controlador USB del láser K40 (placa Lihuiyu, libusb-win32)
french.DriverTask=Installer le pilote USB du laser K40 (carte Lihuiyu, libusb-win32)
english.DriverRun=Installing the K40 USB driver (plug the laser in and switch it on)...
polish.DriverRun=Instalacja sterownika USB lasera K40 (podłącz i włącz laser)...
german.DriverRun=Der K40-USB-Treiber wird installiert (Laser anschließen und einschalten)...
spanish.DriverRun=Instalando el controlador USB del K40 (conecte y encienda el láser)...
english.AssocTask=Open Kerfly projects (.kerfly) with Kerfly
polish.AssocTask=Otwieraj projekty Kerfly (.kerfly) w Kerfly
german.AssocTask=Kerfly-Projekte (.kerfly) mit Kerfly öffnen
spanish.AssocTask=Abrir los proyectos de Kerfly (.kerfly) con Kerfly
french.AssocTask=Ouvrir les projets Kerfly (.kerfly) avec Kerfly
english.AssocName=Kerfly project
polish.AssocName=Projekt Kerfly
german.AssocName=Kerfly-Projekt
spanish.AssocName=Proyecto de Kerfly
french.AssocName=Projet Kerfly
french.DriverRun=Installation du pilote USB du K40 (branchez et allumez le laser)...

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "fileassoc"; Description: "{cm:AssocTask}"
#if FileExists(AddBackslash(SourcePath) + "K40_Driver_Install.exe")
Name: "k40driver"; Description: "{cm:DriverTask}"
#endif

[Files]
Source: "{#Root}\dist\Kerfly\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#if FileExists(AddBackslash(SourcePath) + "K40_Driver_Install.exe")
Source: "K40_Driver_Install.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Tasks: k40driver
#endif

[Registry]
; .kerfly -> Kerfly.Project, opened by Kerfly.exe "%1"; removed again by the uninstaller
Root: HKA; Subkey: "Software\Classes\.kerfly"; ValueType: string; ValueName: ""; ValueData: "Kerfly.Project"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\.kerfly\OpenWithProgids"; ValueType: string; ValueName: "Kerfly.Project"; ValueData: ""; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Kerfly.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:AssocName}"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Kerfly.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Kerfly.exe,0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Kerfly.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Kerfly.exe"" ""%1"""; Tasks: fileassoc

[Icons]
Name: "{group}\Kerfly"; Filename: "{app}\Kerfly.exe"
Name: "{group}\{cm:UninstallProgram,Kerfly}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Kerfly"; Filename: "{app}\Kerfly.exe"; Tasks: desktopicon

[Run]
#if FileExists(AddBackslash(SourcePath) + "K40_Driver_Install.exe")
Filename: "{tmp}\K40_Driver_Install.exe"; StatusMsg: "{cm:DriverRun}"; Tasks: k40driver; Flags: waituntilterminated
#endif
Filename: "{app}\Kerfly.exe"; Description: "{cm:LaunchProgram,Kerfly}"; Flags: nowait postinstall skipifsilent
