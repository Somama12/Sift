#!/bin/bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
app="$project_root/build/Sift.app"
sdk="/Library/Developer/CommandLineTools/SDKs/MacOSX13.3.sdk"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" "$project_root/build/module-cache"
CLANG_MODULE_CACHE_PATH="$project_root/build/module-cache" swiftc -parse-as-library -sdk "$sdk" -target arm64-apple-macos13.0 "$project_root/mac/SiftApp.swift" -o "$app/Contents/MacOS/Sift"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>en</string>
<key>CFBundleExecutable</key><string>Sift</string>
<key>CFBundleIdentifier</key><string>com.sift.localorganizer</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key><string>Sift</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>LSUIElement</key><true/>
</dict></plist>
PLIST
echo "Built $app"
