@echo off
REM MusicGen Setup Script for Windows
REM Run this to install all dependencies

echo ==========================================
echo MusicGen Testing Setup for Windows
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ first.
    pause
    exit /b 1
)

echo [1/4] Checking Python version...
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python version: %PYTHON_VERSION%
echo.

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip
    pause
    exit /b 1
)
echo.

echo [3/4] Installing MusicGen dependencies...
pip install -r musicgen_requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    echo Check your internet connection and try again.
    pause
    exit /b 1
)
echo.

echo [4/4] Verifying installations...
python -c "import torch; print(f'PyTorch: {torch.__version__}')" || goto :error
python -c "import audiocraft; print(f'AudioCraft: ready')" || goto :error
python -c "import librosa; print(f'Librosa: ready')" || goto :error
echo.

echo ==========================================
echo Setup completed successfully!
echo ==========================================
echo.
echo Next steps:
echo 1. Run: python test_musicgen_01_load_model.py
echo 2. Or run all tests: python run_all_musicgen_tests.py
echo.
pause
exit /b 0

:error
echo.
echo ERROR: Installation verification failed.
echo Try running: pip install -r musicgen_requirements.txt
pause
exit /b 1
