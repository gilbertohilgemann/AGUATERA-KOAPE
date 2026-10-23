@echo off
REM Lanzador: la logica vive en start.ps1 (start^|stop^|status^|restart^|logs^|update^|red^|red-quitar^|https^|https-quitar^|
REM   respaldo^|respaldo-programar^|respaldo-quitar^|verificar ARCHIVO^|restaurar ARCHIVO^|seguridad^|datos-prueba)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
