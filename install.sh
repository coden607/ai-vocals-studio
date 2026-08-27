#!/bin/bash

# AI Vocals Studio - One Click Installer
echo "🎤 AI Vocals Studio - Installation"
echo "=================================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "⚡ Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "🔧 Installing dependencies..."
echo "This may take a few minutes..."

pip install gtts demucs so-vits-svc-fork librosa numpy soundfile pydub qwen-tts

# Create desktop entry for easy launch
echo "🖥️ Creating desktop launcher..."
cat > ~/Desktop/AIVocalsStudio.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AI Vocals Studio
Comment=Advanced AI Voice Cloning Studio
Exec=bash $(pwd)/run.sh
Icon=$(pwd)/icon.png
Terminal=true
Categories=AudioVideo;Audio;
EOF

# Make scripts executable
chmod +x run.sh
chmod +x install.sh
chmod +x ~/Desktop/AIVocalsStudio.desktop

# Create directories
mkdir -p dataset
mkdir -p models
mkdir -p outputs

echo ""
echo "✅ Installation Complete!"
echo ""
echo "🚀 To run the application:"
echo "   Method 1: Double-click 'AIVocalsStudio' on your desktop"
echo "   Method 2: Run './run.sh' in this directory"
echo "   Method 3: Run 'python app_modern.py'"
echo ""
echo "📁 Folders created:"
echo "   - dataset/  (for training audio files)"
echo "   - models/   (for AI model files)"
echo "   - outputs/  (for generated vocals)"
echo ""
echo "🎤 AI Vocals Studio is ready to use!"
