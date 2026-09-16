@echo off
title Casa Antik - Servidor de Laudos Tecnicos
cls
echo ==================================================
echo   Casa Antik - Gerador de Laudos Tecnicos PDF
echo ==================================================
echo.
echo [1/2] Abrindo navegador em http://localhost:8000...
start http://localhost:8000
echo.
echo [2/2] Iniciando servidor FastAPI (Uvicorn)...
echo Pressione Ctrl+C para encerrar o servidor.
echo.
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha ao iniciar o servidor. Verifique se o Python esta instalado.
    pause
)
