@echo off
cd /d "%~dp0"

REM Try to find Python
where python >nul 2>&1 && set PYTHON=python && goto :found
where python3 >nul 2>&1 && set PYTHON=python3 && goto :found
where py >nul 2>&1 && set PYTHON=py && goto :found

echo.
echo Python not found. Please install Python 3.10+ from https://python.org
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found
echo Using: %PYTHON%
%PYTHON% -m pip install -r requirements.txt --quiet
%PYTHON% -m streamlit run app.py
