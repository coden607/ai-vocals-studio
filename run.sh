#!/bin/bash

# AI Vocals Studio - One Click Launcher
echo "🎤 Starting AI Vocals Studio..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "⚡ Activating virtual environment..."
source venv/bin/activate

# Install dependencies if needed
echo "🔧 Checking dependencies..."
pip install -q gtts demucs so-vits-svc-fork librosa numpy soundfile pydub qwen-tts

# Run the application
echo "🚀 Launching AI Vocals Studio..."
python app_studio.py

# Keep terminal open if there's an error
if [ $? -ne 0 ]; then
    echo "❌ Error occurred. Press any key to exit..."
    read -n 1
fi
