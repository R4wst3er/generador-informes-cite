; Instalador de Windows del Generador de Informes Finales (Inno Setup 6).
; Lo construye el flujo de GitHub (.github/workflows/publicar.yml):  ISCC /DVersion=1.0.0 empaquetado\instalador.iss
; Instala solo para el usuario actual (no pide permisos de administrador) y permite actualizar encima de la versión anterior.

#ifndef Version
  #define Version "0.0.0"
#endif
#define NombreApp "Generador de Informes Finales"
#define Ejecutable "GeneradorInformes.exe"

[Setup]
; No cambies el AppId: es lo que permite a una versión nueva reemplazar a la anterior
AppId={{BE43ACD5-2526-4A1A-8C69-0A26028EEE1A}
AppName={#NombreApp}
AppVersion={#Version}
VersionInfoVersion={#Version}
AppPublisher=Generador de Informes
DefaultDirName={autopf}\GeneradorInformes
DefaultGroupName={#NombreApp}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-instalador
OutputBaseFilename=GeneradorInformes-Setup-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#Ejecutable}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Si el programa está abierto, el instalador lo cierra y lo vuelve a abrir (así funciona «Actualizar ahora»)
CloseApplications=yes
RestartApplications=no

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Spanish.isl")
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
#endif

[Tasks]
Name: "icono_escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\GeneradorInformes\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"
Name: "{autodesktop}\{#NombreApp}"; Filename: "{app}\{#Ejecutable}"; Tasks: icono_escritorio

[Run]
; Instalación normal: casilla «Abrir el programa» en la última pantalla
Filename: "{app}\{#Ejecutable}"; Description: "Abrir {#NombreApp}"; Flags: nowait postinstall skipifsilent
; Actualización automática (silenciosa): el programa se vuelve a abrir solo
Filename: "{app}\{#Ejecutable}"; Flags: nowait; Check: WizardSilent

[Code]
// Los informes en PDF se generan con LaTeX, que no viene dentro del programa: se avisa si no se encuentra.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: Integer;
begin
  if (CurStep = ssPostInstall) and (not WizardSilent) then
  begin
    if (not Exec(ExpandConstant('{cmd}'), '/C where pdflatex', '', SW_HIDE, ewWaitUntilTerminated, Codigo)) or (Codigo <> 0) then
      MsgBox('El programa se instaló correctamente.' + #13#10 + #13#10 +
        'Para generar el PDF de los informes esta PC necesita LaTeX (por ejemplo MiKTeX, gratis: https://miktex.org). ' +
        'No se encontró «pdflatex» ahora mismo. Al instalar MiKTeX, elige "Instalar paquetes que falten: Siempre" (Always) ' +
        'y reinicia el programa después. Puedes seguir usando todo lo demás sin LaTeX.',
        mbInformation, MB_OK);
  end;
end;
