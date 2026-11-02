#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

echo "AI Vocals Studio - installation"
./install_voice_engines.sh

mkdir -p dataset models outputs
chmod +x run.sh install.sh install_voice_engines.sh

if [ -d "$HOME/Desktop" ]; then
  cat > "$HOME/Desktop/AIVocalsStudio.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AI Vocals Studio
Comment=Authorized neural voice cloning and song conversion
Exec=bash $(pwd)/run.sh
Icon=$(pwd)/logo.png
Terminal=true
Categories=AudioVideo;Audio;
EOF
  chmod +x "$HOME/Desktop/AIVocalsStudio.desktop"
fi

echo "Installation complete. Launch with ./run.sh"
