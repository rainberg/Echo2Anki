@echo off
chcp 65001 >nul
rem 拖拽音频文件/文件夹到本 bat 上即可批量标准化
set "SCRIPT_DIR=%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python "%SCRIPT_DIR%normalize_audio_win.py" %*
) else (
    py "%SCRIPT_DIR%normalize_audio_win.py" %*
)
if errorlevel 1 pause
