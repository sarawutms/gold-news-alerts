@echo off
REM
cd /d "%~dp0"

REM 
set PYTHONPATH=%CD%

REM 
call venv\Scripts\activate

REM run python
streamlit run  app/run.py

pause
