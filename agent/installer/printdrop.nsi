; PrintDrop pour Windows — installateur NSIS (Windows 10/11 64 bits)
; Contient Python 3.12 embarqué (avec Tk), requests, pywin32, Pillow, SumatraPDF : rien d'autre à installer.
; Construit par agent/installer/build_nsis.sh (makensis, depuis Linux ou Windows).
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "LogicLib.nsh"
!include "Sections.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !define VERSION "0.4.0"
!endif
!define APPNAME "PrintDrop pour Windows"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\PrintDrop"
!define RUNKEY "Software\Microsoft\Windows\CurrentVersion\Run"
!define AGENT '"$INSTDIR\python\pythonw.exe" "$INSTDIR\printdrop_agent.py"'

Name "${APPNAME}"
OutFile "${OUTDIR}\PrintDrop-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\PrintDrop"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
BrandingText "PrintDrop ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "PrintDrop"
VIAddVersionKey "FileDescription" "Installateur PrintDrop pour Windows"
VIAddVersionKey "LegalCopyright" "PrintDrop"

!define MUI_ICON "${STAGE}\printdrop.ico"
!define MUI_UNICON "${STAGE}\printdrop.ico"
!define MUI_WELCOMEPAGE_TEXT "Cet assistant installe l'agent PrintDrop sur ce PC du comptoir.$\r$\n$\r$\nIl permet à PrintDrop d'imprimer les commandes et d'utiliser le scanner de vos imprimantes. Aucun autre logiciel n'est nécessaire.$\r$\n$\r$\nCliquez sur Suivant pour continuer."
!define MUI_COMPONENTSPAGE_SMALLDESC
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Lancer PrintDrop et associer ce PC"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchAgent
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "French"

!macro STOP_AGENT
  IfFileExists "$LOCALAPPDATA\PrintDrop\agent.pid" 0 +6
    FileOpen $0 "$LOCALAPPDATA\PrintDrop\agent.pid" r
    FileRead $0 $1
    FileClose $0
    nsExec::Exec 'taskkill /F /PID $1'
    Sleep 1500
!macroend

Section "PrintDrop (obligatoire)" SecMain
  SectionIn RO
  ${If} ${Silent}
    Sleep 4000  ; mise à jour en un clic : laisse l'ancien agent se fermer
  ${EndIf}
  !insertmacro STOP_AGENT
  SetOutPath "$INSTDIR"
  File /r "${STAGE}\*"
  WriteUninstaller "$INSTDIR\Desinstaller-PrintDrop.exe"
  CreateShortcut "$SMPROGRAMS\PrintDrop.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\printdrop_agent.py"' "$INSTDIR\printdrop.ico"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher" "PrintDrop"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\printdrop.ico"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Desinstaller-PrintDrop.exe"'
  WriteRegStr HKLM "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Desinstaller-PrintDrop.exe" /S'
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKLM "${UNINSTKEY}" "EstimatedSize" $0
SectionEnd

Section "Démarrer PrintDrop automatiquement avec Windows (recommandé)" SecAuto
  WriteRegStr HKCU "${RUNKEY}" "PrintDrop" '${AGENT} --background'
SectionEnd

Section /o "Raccourci sur le Bureau" SecDesk
  CreateShortcut "$DESKTOP\PrintDrop.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\printdrop_agent.py"' "$INSTDIR\printdrop.ico"
SectionEnd

Section "-Relance après mise à jour"
  ${If} ${Silent}
    Exec '${AGENT} --background'
  ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "L'agent PrintDrop et tout ce dont il a besoin."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAuto} "PrintDrop démarre à l'ouverture de Windows. Vous pourrez le désactiver plus tard dans le Gestionnaire des tâches › Démarrage."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesk} "Ajoute une icône PrintDrop sur le Bureau."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "PrintDrop nécessite Windows 10 ou Windows 11 en 64 bits." /SD IDOK
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "PrintDrop nécessite Windows 10 ou Windows 11." /SD IDOK
    Abort
  ${EndIf}
  SetRegView 64
  ; silent update: keep the employee's previous « démarrage automatique » choice
  ${If} ${Silent}
  ${AndIf} ${FileExists} "$INSTDIR\printdrop_agent.py"
    ReadRegStr $0 HKCU "${RUNKEY}" "PrintDrop"
    ${If} $0 == ""
      !insertmacro UnselectSection ${SecAuto}
    ${EndIf}
  ${EndIf}
FunctionEnd

Function LaunchAgent
  Exec '${AGENT}'
FunctionEnd

Function un.onInit
  SetRegView 64
FunctionEnd

Section "Uninstall"
  !insertmacro STOP_AGENT
  DeleteRegValue HKCU "${RUNKEY}" "PrintDrop"
  Delete "$SMPROGRAMS\PrintDrop.lnk"
  Delete "$DESKTOP\PrintDrop.lnk"
  RMDir /r "$INSTDIR"
  RMDir /r "$LOCALAPPDATA\PrintDrop\tmp"
  DeleteRegKey HKLM "${UNINSTKEY}"
SectionEnd
