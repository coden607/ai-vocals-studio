## Shipped voice contract

`clone_any_voice.py` is the production CLI. Studio and pro fail if the only engine is WORLD/DSP or gTTS. The headline score is speaker identity. The old pitch/timbre number is `legacy_heuristic` and is not accuracy. Install neural engines with `./install_voice_engines.sh` (includes Resemblyzer for speaker verification). A real clone still needs an authorized `rvc_model.pth` or a configured Qwen/XTTS/ElevenLabs backend. Pacaveli has no trained checkpoint in this repo.

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

Install the complete local stack once, then launch the desktop app:

```bash
./install.sh
./run.sh
```

For the fastest no-training workflow, create a saved profile from 15–20 seconds of clean authorized voice audio, select a song under **Generate → Audio Input**, and click **Replace Song Vocals**. Seed-VC performs zero-shot neural conversion after Demucs separation; no paid API or per-speaker training is required.

The equivalent one-command CLI workflow and stem-only commands are in [QUICK_START.md](QUICK_START.md). A trained RVC model can still be imported or trained for voice-specific conversion.

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
.venv/bin/python rvc_training_cli.py \\
  --voice-dir models/voices/pacaveli \\
  --dataset /path/to/authorized/pacaveli-clean-vocals \\
  --i-have-permission
```

Or register an already-trained RVC model:

```bash
.venv/bin/python rvc_training_cli.py \\
  --voice-dir models/voices/pacaveli \\
  --model /path/to/pacaveli.pth \\
  --index /path/to/pacaveli.index \\
  --i-have-permission
```

The intended production song path is **ingest → Demucs separation (when needed) → vocal cleanup → authorized Seed-VC/RVC conversion → timing/prosody preservation → QA → remix/export**. Qwen3-TTS and XTTS are reference/TTS options; ElevenLabs remains optional. WORLD/DSP is a preview/fallback and must not be presented as a trained clone.

> Do not commit private training audio, credentials, or trained model binaries. See `AGENTS.md` for quality gates and release discipline.

## Seed-VC zero-shot song conversion

AI Vocals Studio uses **[Seed-VC](https://github.com/Plachtaa/seed-vc)** as the default zero-shot audio-to-audio engine for authorized speech, rap, and singing. It needs only a clean reference recording—no per-speaker training. The installer clones the upstream GPL-3.0 source into the ignored `.engines/seed-vc/` directory and installs an isolated Python 3.10 runtime:

```bash
./install_voice_engines.sh
```

The adapter automatically discovers this installation. For an existing custom checkout, set `SEED_VC_DIR` and `SEED_VC_PYTHON`. It uses Seed-VC V1 with F0 conditioning for singing/rap, disables fp16 for CPU compatibility, preserves source timing with length-adjust 1.0, and keeps up to 20 seconds of authorized reference audio. Model checkpoints download from Hugging Face on first use and should be cached in the worker image/volume for production.

The desktop **Replace Song Vocals** button and `clone_any_voice.py` both route reference profiles through Demucs + Seed-VC when available. A trained RVC model remains another neural backend; DSP is fallback only and cannot pass Studio or Pro quality gates.

## Neural Pro-Match and optional RVC models

The WORLD/DSP profile is a fallback and cannot provide near-indistinguishable
voice replacement. Pro-match requires Seed-VC with an authorized reference or a real, authorized RVC model plus the RVC inference sidecar; either way, the neural speaker-identity and reference-quality gates must pass. Validate a clean dataset before optional RVC training:

```bash
.venv/bin/python rvc_training_cli.py \
  --voice-dir models/voices/my_authorized_voice \
  --dataset /path/to/clean-vocals \
  --i-have-permission
```

The command expects an installed trainer named `rvc-train` with `--dataset`,
`--output`, and `--epochs` options. To register a model trained by another
authorized RVC tool:

```bash
.venv/bin/python rvc_training_cli.py \
  --voice-dir models/voices/my_authorized_voice \
  --model /path/to/model.pth \
  --index /path/to/model.index \
  --i-have-permission
```

The importer rejects undersized or invalid artifacts, writes
`rvc_training_report.json` when validating data, and updates the voice profile
so the conversion planner can select RVC. Pro-match stops if neither neural
backend is actually available; it does not silently return a weaker DSP clone.

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


## Song separation, acapellas, and cloned-vocal replacement

The production song path is `song_pipeline_cli.py` + `song_converter.py`.

Create a clean vocal/acapella stem and the matching instrumental:

```bash
python song_pipeline_cli.py separate input_song.wav \
  --output-dir output/my_song \
  --method demucs \
  --require-neural
```

This produces `vocals.wav` (the acapella) and `instrumental.wav` (the beat/no-vocals stem).

After an authorized RVC model/profile has been created, replace the original vocal while preserving the song timing and remix it over the separated instrumental:

```bash
python song_pipeline_cli.py replace input_song.wav \
  --profile models/voices/pacaveli/profile.json \
  --output-dir output/pacaveli_song \
  --separation demucs \
  --require-neural \
  --i-have-permission
```

For final-quality replacement, `--require-neural` intentionally refuses center-channel separation and DSP voice morphing. It requires Demucs plus a valid trained RVC model instead of silently returning a lower-quality approximation.


### No-GPU Pacaveli bootstrap

A GPU is not required to create the first usable authorized Pacaveli profile. Point the CPU bootstrap at clean speech/acapella files or a folder:

```bash
python cpu_voice_bootstrap.py /path/to/pacaveli-audio \
  --name Pacaveli \
  --source-type speech \
  --i-have-permission
```

If the references are full songs, use `--source-type song`; the pipeline separates the vocal before profiling. This creates `models/voices/Pacaveli/voice_profile.json` and `reference.wav` for CPU DSP conversion and reference-based TTS. It deliberately does not label that profile as an RVC checkpoint. A trained RVC model remains the neural singing/rap conversion upgrade.

### Keep the clone intact and adapt the beat

Song replacement and rendering now use the completed cloned vocal as the master.
The mixer does not resample, trim, stretch, pitch-shift, normalize, or polish that
vocal. It resamples only the instrumental, conforms its duration with pitch-preserving
stretching when needed, and lowers the beat around vocal activity and available headroom.
The output retains the vocal's sample rate and every frame. Mono stems are duplicated
when mixed with stereo; original input files remain unchanged.

For an already cloned vocal and an instrumental that starts at the same point:

```bash
python song_pipeline_cli.py mix \
  --vocals cloned_vocal.wav --beat instrumental.wav --output mix.wav
```

This writes `mix.wav`, `mix_adapted_beat.wav`, and `mix.mix.json`. The report records
the original vocal file hash, beat stretch rate, gain, sample rate, and frame count.
Both audio exports are floating-point WAV; the original vocal stem remains the
lossless standalone vocal. Subtracting the adapted beat from the mix recovers the
decoded vocal to float32 rounding precision.

Limits: this conforms an existing beat, not a newly generated composition. It assumes
a shared start and does not infer downbeats, musical key, or variable-tempo phrasing.
Beat duration must be 0.8–1.25 times vocal duration when stretching is required.
Larger differences, silent/corrupt stems, missing stretch support, and vocals with
peaks at or above 0.999 fail with an actionable error. A nearly full-scale vocal can
force a very quiet beat; provide a clone with headroom for a louder accompaniment.
Nonzero `vocals_gain_db` is rejected in protected mode: adjust the beat instead.

`change_song` defaults to lossless WAV delivery and skips source-envelope vocal
polish. Protected mode ignores `source_matched_export=True` to avoid a lossy delivery
copy. Python callers can explicitly request the old behavior with
`preserve_vocals=False` (and `source_matched_export=True` if desired).

Validate without models, credentials, or network calls:

```bash
python -m pytest -q test_vocal_led_mix.py test_song_pipeline_production.py test_numpy_fallbacks.py
```

Synthetic tests establish sample preservation and beat-only transforms. They do not
establish neural clone quality or musical quality on real songs; audition those separately.

### Runtime limits and verification

Imported RVC checkpoints explicitly select RVC, including their retrieval index.
RVC keeps its native sample rate so upstream resampling cannot alter pitch or
timing. Its HuBERT metadata uses a scoped fairseq `Dictionary` allowlist under
PyTorch weights-only loading; arbitrary checkpoint globals remain blocked.

CPU inference can be slow, particularly Seed-VC's first run and model downloads.
A four-step CPU Seed-VC smoke produced clipped audio and was rejected by the
protected remix guard. Do not treat that run as verified Studio quality. Use a
licensed trained RVC profile for the verified CPU song-replacement path; speaker
identity and pitch preservation still require measurement for each voice/song.
The protected mixer rejects full-scale vocals rather than concealing clipping.

A local 3-second CPU acceptance run using the Apache-2.0-labelled
[Nekochu VCTK p226 sample](https://huggingface.co/Nekochu/RVC-VCTK_Voice-sample)
completed Demucs → RVC → protected remix in 68 seconds. Measured neural speaker
similarity was 0.7794 (Studio, below the 0.82 near-precision threshold), pitch
correlation 0.993, median voiced pitch error 10 cents, duration drift 20 ms, and
mix peak 0.631. The cloned vocal remained unchanged during remix. These are
results for this short fixture, not guarantees for arbitrary songs or voices.

### One-click voice-first quality selection

Choose your saved authorized voice and song, then click **Replace Song Vocals**.
The desktop action measures up to three RVC retrieval blends for that same voice
and returns the strongest passing neural match. It stops early at near-precision.
A Studio result is labelled Studio; the app does not call it indistinguishable.
Clipped, silent, non-finite, timing-drifted, or substantially pitch-altered
candidates are rejected. Pitch analysis covers up to 15 seconds around the
source vocal's strongest region. The selected vocal is never pitch-shifted,
time-stretched, normalized, or polished to fit the instrumental during mixing.
Only the instrumental is resampled, duration-conformed, ducked, and attenuated
for headroom. The original song's instrumental already shares its melody's key.

Candidate settings, measured identity/pitch/timing, and reasons are retained in
`quality_report.json`, including on failure. The app shows the achieved quality
and similarity. An authorized trained model and clean reference still determine
how closely the output can match a speaker. No numerical threshold guarantees
perceptual indistinguishability.

CLI Studio/Pro song conversion now checks vocal quality before remix. Explicit
`--quality-target pro` still fails closed unless near-precision passes; the
single desktop action selects the best verified Studio-or-better candidate.

For verified CLI song renders, `quality_report.json` now retains the candidate
selection evidence; the existing conversion summary is written separately to
`conversion_report.json`. Draft output keeps its previous report path.
A measured three-candidate CPU search on the licensed p226 fixture took 173
seconds and selected similarity 0.7887 over its first candidate's 0.7777.
This is still Studio, below the 0.82 near-precision target.
