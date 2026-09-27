# 🎤 AI Vocals Studio - Modern Edition

A beautiful, dark-themed AI voice cloning and generation application with advanced features and modern UI.

## ✨ Features

### 🎨 Modern Dark Theme UI
- Sleek dark interface with green accent colors
- Hover effects and smooth transitions
- Tabbed interface for better organization
- Professional typography and spacing

### 🤖 Model Management
- **Dropdown Model Selection**: Easy selection from available models
- **Pre-trained Models**: Download popular voice models instantly
- **Custom Model Import**: Add your own .pth model files
- **Batch Model Import**: Import entire folders of models
- **Real-time Model Loading**: Load models with visual feedback

### 📚 Training Data Management
- **Folder Import**: Import entire folders of audio files
- **All Audio Formats**: Support for WAV, MP3, FLAC, OGG, M4A, AIFF, AAC
- **Recursive Search**: Automatically finds audio files in subfolders
- **Duplicate Handling**: Smart filename handling for duplicates
- **Visual Counter**: Real-time count of training clips

### 🎵 Voice Generation
- **Text-to-Speech**: Generate vocals from text input
- **Audio-to-Audio**: Transform existing audio files
- **Format Options**: Output in WAV or MP3
- **Auto Flow Alignment**: Enhanced rap flow generation
- **Real-time Progress**: Visual feedback during processing

## 🚀 Quick Start

1. **Run the Application**:
   ```bash
   python app_modern.py
   ```

2. **Add Training Data**:
   - Go to the "Training Data" tab
   - Click "Import Entire Folder" to add audio files
   - Or use "Import Single File" for individual files

3. **Load a Model**:
   - Go to the "Models" tab
   - Download a pre-trained model or import your own
   - Select and load the model

4. **Generate Vocals**:
   - Go to the "Generate" tab
   - Enter text or select an audio file
   - Configure output settings
   - Click "Generate Vocals"

## Vercel + Worker Deployment

The Vercel frontdoor lives in `vercel_frontdoor/` and supports two storage backends:

- Supabase: production persistence for queued jobs, uploaded voice samples, target songs/audio, outputs, and reports.
- Local filesystem: fallback for local/self-hosted runs when Supabase env vars are not set.

Production setup:

```bash
scripts/setup_vercel_supabase.sh
cd vercel_frontdoor
npx vercel --prod --yes --scope stephens-projects-8fbc16d0
```

Worker setup:

```bash
scripts/run_supabase_worker.sh
```

For the one-click RVC training task, install a compatible trainer on the
worker and set its executable path before starting the worker:

```bash
export RVC_TRAINER=/absolute/path/to/rvc-train
export RVC_TRAIN_EPOCHS=300
scripts/run_supabase_worker.sh
```

The Vercel page queues this job; training runs on the local/GPU worker because
Vercel functions are not suitable for long-running model training.

### Free Kaggle GPU Worker

When no local GPU is available, open
`cloud/kaggle_rvc_worker.ipynb` in Kaggle, enable a free NVIDIA GPU, add
Supabase Secrets named `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`SUPABASE_STORAGE_BUCKET`, then run all cells. The notebook claims one queued
RVC training job, trains it with Applio, uploads the `.pth` and `.index` to
Supabase, and the regular worker hydrates that model automatically.

Free GPU availability and quotas are controlled by Kaggle; a session can be
queued or unavailable during busy periods. The notebook is resumable at the
job level and should be stopped after the training job completes.


## 🎙️ Authorized Pacaveli Workflow

Pacaveli is an authorized project voice. Keep source recordings and trained model binaries out of Git; use local/private object storage for those artifacts.

For high-fidelity rap/singing conversion, use a **real RVC model** rather than the legacy DSP/persona transform. Prepare/train an authorized dataset with:

```bash
venv/bin/python rvc_training_cli.py \\
  --voice-dir models/voices/pacaveli \\
  --dataset /path/to/authorized/pacaveli-clean-vocals \\
  --i-have-permission
```

Or register an already-trained RVC model:

```bash
venv/bin/python rvc_training_cli.py \\
  --voice-dir models/voices/pacaveli \\
  --model /path/to/pacaveli.pth \\
  --index /path/to/pacaveli.index \\
  --i-have-permission
```

The intended production song path is **ingest → Demucs separation (when needed) → vocal cleanup → authorized RVC conversion → timing/prosody preservation → QA → remix/export**. Qwen3-TTS and XTTS are reference/TTS options; ElevenLabs remains optional. WORLD/DSP is a preview/fallback and must not be presented as a trained clone.

> Do not commit private training audio, credentials, or trained model binaries. See `AGENTS.md` for quality gates and release discipline.

## RVC Pro-Match Models

The WORLD/DSP profile is a fallback and cannot provide near-indistinguishable
voice replacement. Pro-match requires a real, authorized RVC model plus the
RVC inference sidecar. Validate a clean dataset before training:

```bash
venv/bin/python rvc_training_cli.py \
  --voice-dir models/voices/my_authorized_voice \
  --dataset /path/to/clean-vocals \
  --i-have-permission
```

The command expects an installed trainer named `rvc-train` with `--dataset`,
`--output`, and `--epochs` options. To register a model trained by another
authorized RVC tool:

```bash
venv/bin/python rvc_training_cli.py \
  --voice-dir models/voices/my_authorized_voice \
  --model /path/to/model.pth \
  --index /path/to/model.index \
  --i-have-permission
```

The importer rejects undersized or invalid artifacts, writes
`rvc_training_report.json` when validating data, and updates the voice profile
so the conversion planner can select RVC. Pro-match stops if RVC is not
actually available; it does not silently return a weaker DSP clone.

Local fallback setup:

```bash
cd vercel_frontdoor
env -u SUPABASE_URL -u SUPABASE_SERVICE_ROLE_KEY npx vercel dev
```

In another terminal:

```bash
cd /path/to/ai-vocals-studio
env -u SUPABASE_URL -u SUPABASE_SERVICE_ROLE_KEY python supabase_worker.py
```

Local jobs and objects are stored under `vercel_frontdoor/.local_voiceover_storage/`. This directory is ignored by git.

## 📁 Supported Audio Formats

- **WAV** - High quality uncompressed audio
- **MP3** - Compressed audio format
- **FLAC** - Lossless compressed audio
- **OGG** - Open source audio format
- **M4A** - Apple audio format
- **AIFF** - Apple uncompressed format
- **AAC** - Advanced Audio Coding

## 🎯 Model Features

### Pre-trained Models Available:
- **KIFM - Male Rapper**: Professional rap voice
- **KIFM - Female Singer**: Female singing voice
- **DiffSVC - Default**: General purpose voice conversion
- **VITS - English**: English text-to-speech
- **SO-VITS - Pop Male**: Pop style male voice
- **SO-VITS - Pop Female**: Pop style female voice

### Custom Models:
- Import your own trained .pth models
- Support for SO-VITS-SVC models
- Batch import from folders

## 🛠️ Technical Features

### UI/UX Enhancements:
- **Dark Theme**: Easy on the eyes for long sessions
- **Hover Effects**: Interactive button animations
- **Color-coded Status**: Visual feedback for operations
- **Tabbed Interface**: Organized workflow
- **Progress Indicators**: Real-time processing feedback

### Advanced Functionality:
- **Vocal Separation**: Automatic vocal extraction from mixed audio
- **Prosody Enhancement**: Improved rhythm and flow
- **Batch Processing**: Handle multiple files efficiently
- **Error Handling**: Comprehensive error reporting
- **File Management**: Smart file organization

## 📂 Directory Structure

```
ai-vocals-studio/
├── app_modern.py          # Main application
├── dataset/               # Training audio files
├── models/                # AI model files
├── outputs/               # Generated vocals
└── README.md             # This file
```

## 🔧 Dependencies

Install required packages:
```bash
pip install tkinter gtts demucs so-vits-svc-fork librosa numpy soundfile pydub
```

## 💡 Tips

1. **Training Data Quality**: Use clean, high-quality audio files for best results
2. **Model Selection**: Different models work better for different voice types
3. **Flow Alignment**: Enable for rap vocals to improve rhythm
4. **Format Choice**: Use WAV for highest quality, MP3 for smaller files
5. **Batch Import**: Save time by importing entire folders of training data

## 🎨 UI Color Scheme

- **Background**: #1a1a1a (Dark)
- **Panels**: #2b2b2b (Medium Dark)
- **Accent**: #00ff88 (Green)
- **Buttons**: Various colors for different actions
- **Text**: White with gray accents

## 📞 Support

For issues and questions:
1. Check that all dependencies are installed
2. Ensure audio files are in supported formats
3. Verify model files are valid .pth format
4. Check available disk space for outputs

---

🎤 **AI Vocals Studio - Modern Edition**  
*Professional Voice Cloning Made Beautiful*
