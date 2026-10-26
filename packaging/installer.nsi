Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!ifndef VERSION
!define VERSION "0.5.0"
!endif
Name "Look to Ask"
OutFile "..\dist\LookToAsk-${VERSION}-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Look to Ask"
RequestExecutionLevel user
SetCompressor /SOLID zlib
BrandingText "Look to Ask — Look at anything, ask anything."
!define MUI_ABORTWARNING
!define MUI_ICON "..\build\LookToAsk.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_TEXT_TOP "$(IntelRuntimeTop)"
!insertmacro MUI_PAGE_LICENSE "..\build\LICENSES\Intel-Runtime-Terms.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\LookToAsk.exe"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"
LangString RuntimeRequired ${LANG_ENGLISH} "Install Microsoft Visual C++ v14 x64 Runtime (14.51.36247 or newer) first, then run this installer again. Official download: https://aka.ms/vc14/vc_redist.x64.exe"
LangString RuntimeRequired ${LANG_SIMPCHINESE} "请先安装微软 Visual C++ v14 x64 运行库（14.51.36247 或更新），再运行本安装程序。官方下载：https://aka.ms/vc14/vc_redist.x64.exe"
LangString IntelRuntimeTop ${LANG_ENGLISH} "The following terms cover only Intel's proprietary OpenMP/oneMKL components. Look to Ask remains MIT; Qt/FFmpeg LGPL modification and debugging rights are unchanged."
LangString IntelRuntimeTop ${LANG_SIMPCHINESE} "以下条款仅适用于 Intel 专有的 OpenMP/oneMKL 组件。Look to Ask 仍为 MIT；不限制 Qt/FFmpeg 的 LGPL 修改、调试和替换权利。"

Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Look to Ask requires 64-bit Windows 10 or 11."
    Abort
  ${EndIf}
  SetRegView 64
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
  ReadRegDWORD $1 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Major"
  ReadRegDWORD $2 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Minor"
  ReadRegDWORD $3 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Bld"
  ${If} $0 != 1
  ${OrIf} $1 < 14
    Goto runtime_missing
  ${EndIf}
  ${If} $1 == 14
    ${If} $2 < 51
      Goto runtime_missing
    ${EndIf}
    ${If} $2 == 51
    ${AndIf} $3 < 36247
      Goto runtime_missing
    ${EndIf}
  ${EndIf}
  IfFileExists "$WINDIR\Sysnative\MSVCP140.dll" 0 runtime_missing
  IfFileExists "$WINDIR\Sysnative\VCRUNTIME140_1.dll" 0 runtime_missing
  IfFileExists "$WINDIR\Sysnative\VCOMP140.dll" 0 runtime_missing
  SetShellVarContext current
  Return
runtime_missing:
  MessageBox MB_ICONSTOP|MB_OK "$(RuntimeRequired)" /SD IDOK
  SetErrorLevel 2
  Abort
FunctionEnd

Section "Look to Ask"
  SetOutPath "$INSTDIR"
  File /r "..\dist\LookToAsk\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Look to Ask"
  CreateShortcut "$SMPROGRAMS\Look to Ask\Look to Ask.lnk" "$INSTDIR\LookToAsk.exe"
  CreateShortcut "$SMPROGRAMS\Look to Ask\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LookToAsk" "DisplayName" "Look to Ask"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LookToAsk" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LookToAsk" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LookToAsk" "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
  SetRegView 64
  SetShellVarContext current
  Delete "$SMPROGRAMS\Look to Ask\Look to Ask.lnk"
  Delete "$SMPROGRAMS\Look to Ask\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Look to Ask"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LookToAsk"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\LookToAsk.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ; Preferences/model cache/vault entries are intentionally preserved; no user data is removed.
SectionEnd
