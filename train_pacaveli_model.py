#!/usr/bin/env python3
"""
Train a real ML voice model for Pacaveli using so-vits-svc-fork
Legacy Pacaveli training helper. Prefer rvc_training_cli.py for production RVC training.
"""
import os
import sys
import json
import subprocess
import shutil
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def prepare_pacaveli_dataset():
    """Prepare Pacaveli dataset for training"""
    print("🎤 Preparing Pacaveli dataset for ML training...")
    
    dataset_dir = Path('dataset')
    pacaveli_dir = dataset_dir / 'Pacaveli_training'
    
    if not pacaveli_dir.exists():
        print(f"❌ Pacaveli training directory not found: {pacaveli_dir}")
        return None
    
    # Get audio files
    audio_files = list(pacaveli_dir.glob('*.wav')) + list(pacaveli_dir.glob('*.mp3'))
    
    if not audio_files:
        print(f"❌ No audio files found in {pacaveli_dir}")
        return None
    
    print(f"📁 Found {len(audio_files)} authorized Pacaveli training files")
    
    # Create processed dataset directory
    processed_dir = dataset_dir / 'Pacaveli_processed'
    processed_dir.mkdir(exist_ok=True)
    
    # Process audio files (resample to 22.05kHz, normalize, trim silence)
    try:
        import librosa
        import soundfile as sf
        import numpy as np
        
        processed_files = []
        for i, audio_file in enumerate(audio_files):
            try:
                print(f"   Processing {audio_file.name} ({i+1}/{len(audio_files)})...")
                
                # Load audio at 22.05kHz
                y, sr = librosa.load(str(audio_file), sr=22050)
                
                # Trim silence
                y, _ = librosa.effects.trim(y, top_db=20)
                
                # Normalize
                y = librosa.util.normalize(y)
                
                # Save processed file
                output_file = processed_dir / f"pacaveli_{i:04d}.wav"
                sf.write(str(output_file), y, 22050)
                processed_files.append(str(output_file))
                
                print(f"   ✅ Processed: {output_file.name}")
                
            except Exception as e:
                print(f"   ⚠️ Error processing {audio_file.name}: {e}")
        
        print(f"✅ Successfully processed {len(processed_files)} files")
        return processed_files, processed_dir
        
    except ImportError:
        print("⚠️ librosa not available, using raw files")
        return [str(f) for f in audio_files], pacaveli_dir

def create_training_config(speaker_dir, speaker_name="Pacaveli"):
    """Create training configuration for so-vits-svc-fork"""
    print(f"🔧 Creating training configuration for {speaker_name}...")
    
    config = {
        "train": {
            "log_interval": 100,
            "eval_interval": 500,
            "seed": 1234,
            "epochs": 1000,  # Reduced for faster testing
            "learning_rate": 2e-4,
            "betas": [0.8, 0.99],
            "eps": 1e-9,
            "batch_size": 4,
            "fp16_run": True,
            "lr_decay": 0.999875,
            "segment_size": 8192,
            "init_lr_ratio": 1,
            "warmup_epochs": 0,
            "c_mel": 45,
            "c_kl": 1.0
        },
        "data": {
            "training_files": str(speaker_dir / "training_list.txt"),
            "validation_files": str(speaker_dir / "validation_list.txt"),
            "text_cleaners": ["cjke_cleaners2"],
            "max_wav_value": 32768.0,
            "sampling_rate": 22050,
            "filter_length": 1024,
            "hop_length": 256,
            "win_length": 1024,
            "n_mel_channels": 80,
            "mel_fmin": 0.0,
            "mel_fmax": None,
            "add_blank": True,
            "n_speakers": 1,
            "cleaned_text": True,
            "spk2id": {speaker_name: 0}
        },
        "model": {
            "inter_channels": 192,
            "hidden_channels": 192,
            "filter_channels": 768,
            "n_heads": 2,
            "n_layers": 6,
            "kernel_size": 3,
            "p_dropout": 0.1,
            "resblock": "1",
            "resblock_kernel_sizes": [3,7,11],
            "resblock_dilation_sizes": [[1,3,5], [1,3,5], [1,3,5]],
            "upsample_rates": [8,8,2,2],
            "upsample_initial_channel": 512,
            "upsample_kernel_sizes": [16,16,4,4],
            "n_layers_q": 3,
            "use_spectral_norm": False,
            "gin_channels": 256,
            "ssl_dim": 256,
            "n_speakers": 1,
            "sampling_rate": 22050
        }
    }
    
    config_file = speaker_dir / f"config_{speaker_name}.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Configuration saved to {config_file}")
    return str(config_file)

def create_training_lists(speaker_dir, processed_files):
    """Create training and validation file lists"""
    print("📝 Creating training and validation lists...")
    
    # Split 90% training, 10% validation
    split_idx = int(len(processed_files) * 0.9)
    train_files = processed_files[:split_idx]
    val_files = processed_files[split_idx:]
    
    # Create training list
    train_list = speaker_dir / "training_list.txt"
    with open(train_list, 'w') as f:
        for file_path in train_files:
            base_name = Path(file_path).stem
            f.write(f"{file_path}|{base_name}\n")
    
    # Create validation list
    val_list = speaker_dir / "validation_list.txt"
    with open(val_list, 'w') as f:
        for file_path in val_files:
            base_name = Path(file_path).stem
            f.write(f"{file_path}|{base_name}\n")
    
    print(f"✅ Training list: {len(train_files)} files")
    print(f"✅ Validation list: {len(val_files)} files")
    
    return str(train_list), str(val_list)

def train_with_svc_cli(config_file, model_name="Pacaveli"):
    """Train using so-vits-svc-fork CLI"""
    print(f"🚀 Starting ML training for {model_name}...")
    print("⏳ CPU neural training can be extremely slow; use cpu_voice_bootstrap.py for the immediate no-GPU path.")
    
    try:
        # Check if svc command is available
        result = subprocess.run(['svc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ so-vits-svc-fork CLI available: {result.stdout.strip()}")
        else:
            print("⚠️ svc CLI not found, will try Python API")
            return False, "svc CLI not available"
        
        # Run training command
        cmd = [
            'svc', 'train',
            '-c', config_file,
            '-n', model_name,
            '-t', 'so-vits-svc-4.0v1'
        ]
        
        print(f"🔧 Running: {' '.join(cmd)}")
        
        # Run training (this will take a long time)
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Training completed successfully!")
            
            # Find the generated model
            logs_dir = Path('logs/44k')
            if logs_dir.exists():
                model_files = sorted(logs_dir.glob('G_*.pth'), 
                                   key=lambda p: int(p.stem.split('_')[-1]))
                if model_files:
                    latest_model = model_files[-1]
                    
                    # Copy to models folder
                    models_dir = Path('models')
                    models_dir.mkdir(exist_ok=True)
                    model_output = models_dir / model_name
                    model_output.mkdir(exist_ok=True)
                    
                    final_model = model_output / 'model.pth'
                    shutil.copy(latest_model, final_model)
                    
                    # Copy config
                    config_output = model_output / 'config.json'
                    shutil.copy(config_file, config_output)
                    
                    print(f"🎯 Model saved to: {final_model}")
                    return True, str(final_model)
            
            return False, "Model file not found after training"
        else:
            print(f"❌ Training failed: {result.stderr}")
            return False, result.stderr
            
    except FileNotFoundError:
        return False, "svc command not found"
    except Exception as e:
        return False, str(e)

def create_fallback_model(speaker_name="Pacaveli"):
    """Create a fallback model using simple voice analysis"""
    print(f"🎤 Creating voice profile for {speaker_name}...")
    
    try:
        import librosa
        import numpy as np
        import json
        from pathlib import Path
        
        # Find audio files
        dataset_dir = Path('dataset')
        audio_files = []
        
        # Check for speaker-specific directory
        speaker_dir = dataset_dir / speaker_name
        if speaker_dir.exists():
            audio_files.extend(list(speaker_dir.glob('*.wav')))
            audio_files.extend(list(speaker_dir.glob('*.mp3')))
        
        # Also check main dataset directory
        if not audio_files:
            audio_files.extend(list(dataset_dir.glob('*2Pac*.wav')))
            audio_files.extend(list(dataset_dir.glob('*2pac*.wav')))
        
        if not audio_files:
            return False, "No audio files found"
        
        print(f"📁 Found {len(audio_files)} audio files for analysis")
        
        # Analyze first few files for voice characteristics
        pitch_values = []
        energy_values = []
        
        for audio_file in audio_files[:3]:  # Analyze first 3 files
            try:
                print(f"   Analyzing {audio_file.name}...")
                y, sr = librosa.load(str(audio_file), sr=22050, duration=30)  # 30 seconds max
                
                # Extract pitch
                pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
                pitch_mean = np.mean(pitches[pitches > 0]) if np.any(pitches > 0) else 150
                pitch_values.append(pitch_mean)
                
                # Extract energy
                energy = librosa.feature.rms(y=y)[0]
                energy_mean = np.mean(energy)
                energy_values.append(energy_mean)
                
            except Exception as e:
                print(f"   ⚠️ Error analyzing {audio_file.name}: {e}")
        
        if pitch_values:
            avg_pitch = float(np.mean(pitch_values))
            avg_energy = float(np.mean(energy_values)) if energy_values else 0.1
            
            # Create voice profile
            voice_profile = {
                "speaker": speaker_name,
                "model_name": speaker_name.lower(),
                "type": "voice_clone",
                "total_files": len(audio_files),
                "characteristics": {
                    "avg_pitch": avg_pitch,
                    "avg_energy": avg_energy,
                    "pitch_shift": -3 if avg_pitch < 150 else -2,  # Deep voice adjustment
                    "speed": 1.05,
                    "reverb": 0.35,
                    "gain": 3
                },
                "created": "2026-08-17"
            }
            
            # Save model
            models_dir = Path('models')
            model_dir = models_dir / speaker_name.lower()
            model_dir.mkdir(exist_ok=True)
            
            # Save voice profile
            with open(model_dir / "voice_profile.json", 'w') as f:
                json.dump(voice_profile, f, indent=2)
            
            # A voice profile is not a trained ML model. Do not create a placeholder .pth.\n            # Real model artifacts must come from the RVC training/import pipeline.\n\n            # Create config.json
            config = {
                "spk": {speaker_name: 0},
                "version": "4.0"
            }
            with open(model_dir / "config.json", 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"✅ Voice profile created successfully!")
            print(f"   Average pitch: {avg_pitch:.1f} Hz")
            print(f"   Average energy: {avg_energy:.3f}")
            print(f"   📍 Location: {model_dir}")
            
            return True, str(model_dir)
        else:
            return False, "Could not analyze voice characteristics"
            
    except ImportError:
        return False, "librosa not available"
    except Exception as e:
        return False, str(e)

def main():
    print("🎤 Pacaveli Voice Cloning - ML Training")
    print("=" * 60)
    
    # Step 1: Prepare dataset
    print("\n📁 Step 1: Preparing dataset...")
    result = prepare_pacaveli_dataset()
    
    if result is None:
        print("❌ Failed to prepare dataset")
        print("🔄 Trying fallback method...")
        success, message = create_fallback_model("Pacaveli")
        if success:
            print(f"✅ Fallback model created: {message}")
        else:
            print(f"❌ Fallback failed: {message}")
        return
    
    processed_files, processed_dir = result
    
    # Step 2: Create training configuration
    print("\n🔧 Step 2: Creating training configuration...")
    config_file = create_training_config(processed_dir, "Pacaveli")
    
    # Step 3: Create training lists
    print("\n📝 Step 3: Creating training lists...")
    train_list, val_list = create_training_lists(processed_dir, processed_files)
    
    # Step 4: Attempt ML training
    print("\n🚀 Step 4: ML Training...")
    print("⚠️  WARNING: Full ML training can take several hours on CPU")
    response = input("Do you want to proceed with ML training? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        success, message = train_with_svc_cli(config_file, "Pacaveli")
        if success:
            print(f"✅ ML training successful: {message}")
        else:
            print(f"❌ ML training failed: {message}")
            print("🔄 Creating voice profile fallback...")
            success, message = create_fallback_model("Pacaveli")
            if success:
                print(f"✅ Voice profile created: {message}")
    else:
        print("⏭️  Skipping ML training...")
        print("🔄 Creating voice profile fallback...")
        success, message = create_fallback_model("Pacaveli")
        if success:
            print(f"✅ Voice profile created: {message}")
    
    print("\n🎉 Process complete!")
    print("📂 Check the models/ directory for your Pacaveli voice model")

if __name__ == "__main__":
    main()