@echo off
cd /d "%~dp0"
set PATH=C:\Program Files\nodejs;%PATH%
streamlit run app.py --server.port 8501
pause
