$python = "D:\Ronit Sharma\vs code\ML Models\.conda\python.exe"
& $python -m pip install torch torchaudio transformers audiocraft librosa soundfile scipy numpy psutil GPUtil tqdm --quiet --upgrade
Write-Host "Installation complete!"
