@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════╗
echo  ║     Zylmus - Konfiguracja (Windows)  ║
echo  ╚══════════════════════════════════════╝
echo.

:: Sprawdz czy Python jest zainstalowany
python --version >nul 2>&1
if errorlevel 1 (
    echo [BLAD] Python nie jest zainstalowany lub nie jest w PATH.
    echo Pobierz ze strony: https://www.python.org/downloads/
    echo Przy instalacji zaznacz opcje "Add Python to PATH"!
    pause
    exit /b 1
)

echo [OK] Python znaleziony:
python --version
echo.

:: Stworz srodowisko wirtualne
if not exist ".venv" (
    echo [1/4] Tworzenie srodowiska wirtualnego...
    python -m venv .venv
    echo [OK] Srodowisko .venv utworzone
) else (
    echo [OK] Srodowisko .venv juz istnieje
)
echo.

:: Aktywuj i zainstaluj zaleznosci
echo [2/4] Instalowanie zaleznosci Python...
call .venv\Scripts\activate.bat
pip install -r backend\requirements.txt --quiet
echo [OK] Zaleznosci zainstalowane
echo.

:: Stworz plik .env jesli nie istnieje
if not exist "backend\.env" (
    echo [3/4] Generowanie klucza szyfrowania...
    for /f "delims=" %%i in ('python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do set FERNET_KEY=%%i
    echo ZYLMUS_FERNET_KEY=%FERNET_KEY%> backend\.env
    echo [OK] Plik backend\.env utworzony z nowym kluczem
) else (
    echo [OK] Plik backend\.env juz istnieje
)
echo.

:: Stworz folder data
if not exist "data" mkdir data

echo [4/4] Konfiguracja zakonczona!
echo.
echo ══════════════════════════════════════════
echo  Aby uruchomic aplikacje wpisz:
echo.
echo    .venv\Scripts\activate
echo    uvicorn backend.main:app --reload --port 8000
echo.
echo  Nastepnie otworz przegladarke na:
echo    http://localhost:8000
echo ══════════════════════════════════════════
echo.
pause
