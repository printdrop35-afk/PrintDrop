#!/usr/bin/env bash
# Builds PrintDrop-Setup-<version>.exe (Windows 10/11 x64) from Linux or Windows with makensis.
# Bundles: official Python 3.12 embeddable (python.org) + Tcl/Tk from the official tcltk.msi, Windows wheels from PyPI
# (requests, pywin32, Pillow), SumatraPDF (official). Requires: makensis (nsis), msiextract (msitools), unzip, python + pip.
set -euo pipefail
PY=3.12.8
VERSION=$(grep -oP '^VERSION = "\K[^"]+' "$(dirname "$0")/../printdrop_agent.py")
HERE=$(cd "$(dirname "$0")" && pwd); AGENT=$(dirname "$HERE")
OUT=${1:-$AGENT/dist}; WORK=$(mktemp -d); STAGE=$WORK/stage
mkdir -p "$OUT" "$STAGE/python/Lib/site-packages" "$STAGE/python/tcl"
cd "$WORK"
curl -sSfLO "https://www.python.org/ftp/python/$PY/python-$PY-embed-amd64.zip"
curl -sSfLO "https://www.python.org/ftp/python/$PY/amd64/tcltk.msi"
curl -sSfL -o sumatra.zip "https://www.sumatrapdfreader.org/dl/rel/3.5.2/SumatraPDF-3.5.2-64.zip"
sed 's/;.*//' "$AGENT/requirements.txt" > req-win.txt  # Windows-only markers (pywin32) must not be skipped on Linux
python -m pip download -q --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp -d wheels -r req-win.txt
unzip -q "python-$PY-embed-amd64.zip" -d "$STAGE/python"
msiextract -C tk tcltk.msi >/dev/null
cp tk/DLLs/* "$STAGE/python/"
cp -r tk/tcl/tcl8.6 tk/tcl/tk8.6 tk/tcl/tcl8 "$STAGE/python/tcl/"
cp -r tk/Lib/tkinter "$STAGE/python/Lib/" && rm -rf "$STAGE/python/Lib/tkinter/test"
printf 'python312.zip\n.\nLib\nLib\\site-packages\nimport site\n' > "$STAGE/python/python312._pth"
for w in wheels/*.whl; do unzip -q -o "$w" -d "$STAGE/python/Lib/site-packages"; done
for f in python/pythonw.exe python/_tkinter.pyd python/tcl/tcl8.6/init.tcl python/tcl/tk8.6/tk.tcl python/Lib/tkinter/__init__.py \
         python/Lib/site-packages/win32/win32print.pyd python/Lib/site-packages/pywin32_system32/pywintypes312.dll \
         python/Lib/site-packages/pywin32_system32/pythoncom312.dll python/Lib/site-packages/win32com/client/__init__.py \
         python/Lib/site-packages/pywin32.pth python/Lib/site-packages/requests/__init__.py python/Lib/site-packages/certifi/cacert.pem \
         python/Lib/site-packages/PIL/Image.py; do
  [ -e "$STAGE/$f" ] || { echo "MANQUANT : $f" >&2; exit 1; }
done
rm -rf "$STAGE/python/Lib/site-packages/"{PyWin32.chm,adodbapi,isapi,pywin32-*.data}
unzip -q -j sumatra.zip '*.exe' -d "$STAGE" && mv "$STAGE"/SumatraPDF*.exe "$STAGE/SumatraPDF.exe"
cp "$AGENT/printdrop_agent.py" "$STAGE/" && cp "$AGENT/README.md" "$STAGE/Guide-installation.md"
python - "$STAGE/printdrop.ico" "$AGENT/../frontend/public/printdrop-app-icon-512.png" <<'PYICO'
import sys
from PIL import Image
Image.open(sys.argv[2]).save(sys.argv[1], sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
PYICO
makensis -V2 -DVERSION="$VERSION" -DSTAGE="$STAGE" -DOUTDIR="$OUT" "$HERE/printdrop.nsi"
# Optional code signing (removes the SmartScreen warning): SIGN_PFX=/path/cert.pfx SIGN_PASSWORD=... (needs osslsigncode).
if [ -n "${SIGN_PFX:-}" ]; then
  EXE="$OUT/PrintDrop-Setup-$VERSION.exe"
  osslsigncode sign -pkcs12 "$SIGN_PFX" -pass "${SIGN_PASSWORD:-}" -n "PrintDrop pour Windows" -i "https://printdrop.fr" \
    -h sha256 -ts http://timestamp.digicert.com -in "$EXE" -out "$EXE.signed" && mv "$EXE.signed" "$EXE"
  osslsigncode verify -in "$EXE" >/dev/null && echo "Installateur signé"
else
  echo "Installateur NON signé (SIGN_PFX absent) : Windows SmartScreen affichera un avertissement"
fi
cd "$OUT" && sha256sum "PrintDrop-Setup-$VERSION.exe" | tee "PrintDrop-Setup-$VERSION.exe.sha256"
rm -rf "$WORK"
