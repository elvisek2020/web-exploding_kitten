#!/usr/bin/env python3
"""
Script pro generování placeholder zvukových souborů.
Vytvoří jednoduché beep zvuky ve formátu WAV, které lze převést na MP3.
"""

import wave
import math
import struct

def generate_beep(filename, duration=0.5, frequency=440, sample_rate=44100):
    """Vygeneruje jednoduchý beep zvuk"""
    num_samples = int(duration * sample_rate)
    samples = []
    
    for i in range(num_samples):
        # Sinusová vlna s fade in/out
        t = float(i) / sample_rate
        fade = min(1.0, i / (sample_rate * 0.1), (num_samples - i) / (sample_rate * 0.1))
        value = math.sin(2 * math.pi * frequency * t) * fade * 0.3
        samples.append(int(value * 32767))
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack('<' + 'h' * len(samples), *samples))

def generate_explosion_sound(filename, duration=1.0, sample_rate=44100):
    """Vygeneruje zvuk exploze (nízkofrekvenční rumbling)"""
    import random
    num_samples = int(duration * sample_rate)
    samples = []
    
    for i in range(num_samples):
        t = float(i) / sample_rate
        # Kombinace nízkých frekvencí s náhodným šumem
        value = (math.sin(2 * math.pi * 60 * t) * 0.5 +
                 math.sin(2 * math.pi * 120 * t) * 0.3 +
                 (random.random() - 0.5) * 0.2)
        # Fade out
        fade = 1.0 - (t / duration)
        value = value * fade * 0.4
        samples.append(int(value * 32767))
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack('<' + 'h' * len(samples), *samples))

def generate_victory_sound(filename, duration=2.0, sample_rate=44100):
    """Vygeneruje fanfáru (stoupající tóny)"""
    num_samples = int(duration * sample_rate)
    samples = []
    
    # Stupnice C dur
    frequencies = [523.25, 659.25, 783.99, 1046.50]  # C, E, G, C
    
    for i in range(num_samples):
        t = float(i) / sample_rate
        # Postupně přidáváme tóny
        value = 0
        for j, freq in enumerate(frequencies):
            start_time = j * 0.3
            if t >= start_time:
                fade_in = min(1.0, (t - start_time) / 0.1)
                fade_out = min(1.0, (duration - t) / 0.2)
                fade = fade_in * fade_out
                value += math.sin(2 * math.pi * freq * (t - start_time)) * fade * 0.15
        samples.append(int(value * 32767))
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack('<' + 'h' * len(samples), *samples))

def generate_defused_sound(filename, duration=1.0, sample_rate=44100):
    """Vygeneruje zvuk přežití výbuchu (relief sound - stoupající tóny)"""
    num_samples = int(duration * sample_rate)
    samples = []
    
    # Stoupající tóny pro pocit úlevy
    frequencies = [440, 523.25, 659.25, 783.99]  # A, C, E, G
    
    for i in range(num_samples):
        t = float(i) / sample_rate
        value = 0
        for j, freq in enumerate(frequencies):
            start_time = j * 0.2
            if t >= start_time:
                fade_in = min(1.0, (t - start_time) / 0.1)
                fade_out = min(1.0, (duration - t) / 0.3)
                fade = fade_in * fade_out
                value += math.sin(2 * math.pi * freq * (t - start_time)) * fade * 0.12
        samples.append(int(value * 32767))
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack('<' + 'h' * len(samples), *samples))

def generate_meow_sound(filename, duration=0.8, sample_rate=44100):
    """Vygeneruje mňau efekt (simulace kočičího mňau)"""
    num_samples = int(duration * sample_rate)
    samples = []
    
    for i in range(num_samples):
        t = float(i) / sample_rate
        # Simulace mňau pomocí modulované frekvence
        # Začínáme vyšší frekvencí, pak klesáme a zase stoupáme
        if t < 0.2:
            # "M" - vyšší tón
            freq = 600 + 200 * math.sin(t * 10)
        elif t < 0.5:
            # "ň" - klesající tón
            freq = 500 - 150 * (t - 0.2) / 0.3
        else:
            # "au" - stoupající tón
            freq = 350 + 100 * (t - 0.5) / 0.3
        
        # Přidáme harmonické pro realističtější zvuk
        value = (math.sin(2 * math.pi * freq * t) * 0.6 +
                 math.sin(2 * math.pi * freq * 2 * t) * 0.3 +
                 math.sin(2 * math.pi * freq * 3 * t) * 0.1)
        
        # Fade in/out
        fade = min(1.0, t / 0.1, (duration - t) / 0.2)
        value = value * fade * 0.3
        samples.append(int(value * 32767))
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack('<' + 'h' * len(samples), *samples))

if __name__ == '__main__':
    import os
    import random
    
    # Nastavíme seed pro konzistentní výsledky
    random.seed(42)
    
    sounds_dir = 'static/sounds'
    os.makedirs(sounds_dir, exist_ok=True)
    
    print('Generuji zvukové soubory...')
    
    # Exploding kitten - exploze
    explosion_wav = os.path.join(sounds_dir, 'exploding_kitten.wav')
    generate_explosion_sound(explosion_wav)
    print(f'Vytvořeno: {explosion_wav}')
    
    # Game end - fanfára
    victory_wav = os.path.join(sounds_dir, 'game_end.wav')
    generate_victory_sound(victory_wav)
    print(f'Vytvořeno: {victory_wav}')
    
    # Defused - přežití výbuchu
    defused_wav = os.path.join(sounds_dir, 'defused.wav')
    generate_defused_sound(defused_wav)
    print(f'Vytvořeno: {defused_wav}')
    
    # Game start - mňau efekt
    game_start_wav = os.path.join(sounds_dir, 'game_start.wav')
    generate_meow_sound(game_start_wav)
    print(f'Vytvořeno: {game_start_wav}')
    
    print('\nZvukové soubory byly vytvořeny ve formátu WAV.')
    print('Pro produkci je doporučeno převést je na MP3 pomocí ffmpeg:')
    print('  ffmpeg -i static/sounds/exploding_kitten.wav static/sounds/exploding_kitten.mp3')
    print('  ffmpeg -i static/sounds/game_end.wav static/sounds/game_end.mp3')
    print('  ffmpeg -i static/sounds/defused.wav static/sounds/defused.mp3')
    print('  ffmpeg -i static/sounds/game_start.wav static/sounds/game_start.mp3')

