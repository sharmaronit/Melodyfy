import torch
import os
try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False
from transformers import AutoProcessor, MusicgenForConditionalGeneration
import time
from pathlib import Path
from datetime import datetime

MOODS = {
    "1":  ("EDM / Club Banger",         "energetic EDM beat with heavy bass drops, synthesizers, and pulsing drums at 128 bpm, club music"),
    "2":  ("Trap / Hip-Hop",            "dark trap beat with 808 bass, hi-hats, and atmospheric pads, hip hop production, 140 bpm"),
    "3":  ("Lo-fi Chill",               "lo-fi hip hop beat with vinyl crackle, mellow chords, relaxed drums, chill study music"),
    "4":  ("Synthwave / Retrowave",     "synthwave retro 80s electronic music with lush synthesizers, driving beat, nostalgic neon vibes"),
    "5":  ("Deep House",                "deep house music with groovy bassline, smooth synthesizers, four-on-the-floor drums, midnight dance floor"),
    "6":  ("Drum and Bass",             "fast drum and bass with rapid breakbeats, heavy sub-bass, aggressive energy, 174 bpm"),
    "7":  ("Ambient / Atmospheric",     "ambient atmospheric music with evolving synthesizer pads, ethereal textures, slow floating soundscape"),
    "8":  ("Phonk",                     "phonk music with memphis rap samples, dark twisted bass, aggressive drums, drifting energy"),
    "9":  ("Calm Piano",                "calm solo piano music, emotional and introspective, soft dynamics, gentle melody"),
    "10": ("Acoustic Guitar",           "fingerpicked acoustic guitar, warm and intimate, folk style, gentle arpeggios"),
    "11": ("Jazz / Smooth Jazz",        "smooth jazz with saxophone lead, soft piano chords, upright bass, brushed drums, late night bar vibe"),
    "12": ("Blues",                     "soulful blues guitar with electric guitar riffs, steady rhythm, emotional and raw, Delta blues feel"),
    "13": ("Classical / Orchestral",    "cinematic orchestral music with strings, brass, and dramatic crescendos, epic film score feeling"),
    "14": ("R&B / Soul",                "modern R&B soul music with warm chord progressions, smooth bass, subtle drums, emotional vocals bed"),
    "15": ("Epic / Cinematic",          "epic cinematic orchestral battle music with massive drums, brass fanfare, intense strings, heroic"),
    "16": ("Metal / Hard Rock",         "heavy metal music with distorted electric guitars, fast double kick drums, aggressive energy"),
    "17": ("Punk / Indie Rock",         "indie rock with jangly guitars, energetic drums, catchy melody, stadium anthemic feel"),
    "18": ("Afrobeats",                 "afrobeats music with percussion, talking drums, bright guitar riffs, danceable groove, West African rhythm"),
    "19": ("Meditation / Zen",          "peaceful meditation music with singing bowls, soft pads, nature ambience, slow breathing rhythm"),
    "20": ("Nature Sounds + Music",     "gentle acoustic music blended with nature sounds, birds, stream, forest atmosphere, peaceful"),
    "21": ("Sleep / Night Drone",       "slow droning ambient music, very soft, hypnotic, warm bass tones, for sleep and relaxation"),
    "22": ("Bossa Nova",                "bossa nova Brazilian jazz with nylon string guitar, light percussion, romantic and breezy"),
    "23": ("Video Game / 8-Bit",        "retro video game chiptune music with 8-bit synth melodies, catchy loop, upbeat pixel adventure mood"),
    "24": ("Middle Eastern",            "Middle Eastern music with oud, darbuka drums, haunting scales, traditional yet modern fusion"),
    "25": ("Custom Prompt",             None),
}

DURATION_TOKENS = 512
OUTPUT_DIR = Path("beat_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    print("=" * 65)
    print("  BEAT GENERATOR  |  Powered by MusicGen")
    print("=" * 65)

def mood_menu():
    print("\n  Choose a MOOD / VIBE for your beat:\n")
    sections = [
        ("ELECTRONIC",         ["1","2","3","4","5","6","7","8"]),
        ("ACOUSTIC / ORGANIC", ["9","10","11","12","13","14"]),
        ("INTENSE / ENERGETIC",["15","16","17","18"]),
        ("RELAXED / PEACEFUL", ["19","20","21","22"]),
        ("SPECIAL / FUN",      ["23","24","25"]),
    ]
    for section, keys in sections:
        pad = "-" * (48 - len(section))
        print(f"  -- {section} {pad}")
        for k in keys:
            name, _ = MOODS[k]
            print(f"    [{k:>2}] {name}")
    print()

def save_audio(audio_values, sampling_rate, filepath):
    import numpy as np
    audio_np = audio_values.cpu().numpy()
    if len(audio_np.shape) == 3:
        audio_np = audio_np[0]
    if len(audio_np.shape) == 2:
        audio_np = audio_np.T
    else:
        audio_np = audio_np.squeeze()
    if HAS_SOUNDFILE:
        sf.write(str(filepath), audio_np, sampling_rate)
    else:
        import torchaudio
        tensor = torch.from_numpy(audio_np)
        if len(tensor.shape) == 1:
            tensor = tensor.unsqueeze(0)
        torchaudio.save(str(filepath), tensor, sampling_rate)

def load_model():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  [LOADING] MusicGen model ... (device: {device})")
    model_name = "facebook/musicgen-small"
    processor = AutoProcessor.from_pretrained(model_name)
    model = MusicgenForConditionalGeneration.from_pretrained(model_name)
    model.to(device)
    print("  [OK] Model ready!\n")
    return processor, model, device

def generate(processor, model, device, prompt, label):
    inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)
    print(f"\n  [..] Generating ~10s beat (takes ~60-120s on CPU) ...")
    t0 = time.time()
    with torch.no_grad():
        audio_values = model.generate(**inputs, max_new_tokens=DURATION_TOKENS)
    elapsed = time.time() - t0
    sampling_rate = model.config.audio_encoder.sampling_rate
    duration = audio_values.shape[-1] / sampling_rate
    timestamp = datetime.now().strftime("%H%M%S")
    safe_label = label.lower().replace("/", "-").replace(" ", "_")
    filename = f"{safe_label}_{timestamp}.wav"
    filepath = OUTPUT_DIR / filename
    save_audio(audio_values, sampling_rate, filepath)
    print(f"  [OK] Done in {elapsed:.1f}s  |  Duration: {duration:.1f}s")
    print(f"  [OK] Saved -> {filepath}")
    return filepath

def main():
    clear()
    banner()
    print()
    processor, model, device = load_model()
    while True:
        clear()
        banner()
        mood_menu()
        choice = input("  Enter number (or q to quit): ").strip()
        if choice.lower() == "q":
            print("\n  Bye!\n")
            break
        if choice not in MOODS:
            print("  [!] Invalid choice. Press Enter to retry.")
            input()
            continue
        label, prompt = MOODS[choice]
        if prompt is None:
            print("\n  [CUSTOM] Describe your beat:")
            prompt = input("  > ").strip()
            if not prompt:
                print("  [!] Empty prompt. Press Enter to retry.")
                input()
                continue
            label = "custom"
        print(f"\n  [MOOD]   {label}")
        print(f"  [PROMPT] {prompt}")
        try:
            generate(processor, model, device, prompt, label)
            print("\n  Press Enter for another beat, or q to quit.")
            if input("  > ").strip().lower() == "q":
                print("\n  Bye!\n")
                break
        except Exception as e:
            print(f"\n  [ERROR] {e}")
            print("  Press Enter to continue.")
            input()

if __name__ == "__main__":
    main()
