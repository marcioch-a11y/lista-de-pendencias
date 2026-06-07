@echo off
title Atualizar Google Tasks a partir do Sheets
echo Iniciando Sincronizacao...
python "%~dp0sync_to_tasks.py"
echo.
echo Processo concluido! Pressione qualquer tecla para fechar.
pause > nul
