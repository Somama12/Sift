#!/bin/bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
export PYINSTALLER_CONFIG_DIR="$project_root/build/pyinstaller-config"

"$project_root/mac/build-app.sh"
"$project_root/.venv/bin/pyinstaller" --noconfirm --clean --onedir \
    --name sift-helper --paths "$project_root" --hidden-import pypdf \
    --hidden-import pypdfium2 --collect-all pypdfium2 --collect-all PIL \
    --distpath "$project_root/dist/helper" \
    --workpath "$project_root/build/pyinstaller" \
    --specpath "$project_root/build" \
    "$project_root/mac/helper_main.py"

app="$project_root/build/Sift.app"
rm -rf "$app/Contents/Resources/sift-helper"
cp -R "$project_root/dist/helper/sift-helper" "$app/Contents/Resources/sift-helper"
codesign --force --deep --sign - "$app"
mkdir -p "$project_root/dist"
ditto -c -k --keepParent "$app" "$project_root/dist/Sift-macOS-arm64.zip"
echo "Packaged $project_root/dist/Sift-macOS-arm64.zip"
