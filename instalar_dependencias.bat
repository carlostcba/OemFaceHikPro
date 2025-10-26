@echo off
REM Script de instalacion para Monitor Hikvision con System Tray
REM Ejecuta como administrador para mejor compatibilidad

echo ===============================================
echo  Monitor Hikvision - Instalacion de Dependencias
echo ===============================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no esta instalado o no esta en PATH
    echo Por favor instala Python 3.8 o superior desde python.org
    pause
    exit /b 1
)

echo Python encontrado:
python --version
echo.

REM Actualizar pip
echo Actualizando pip...
python -m pip install --upgrade pip
echo.

REM Instalar dependencias
echo Instalando dependencias necesarias...
echo.

echo [1/5] Instalando pystray (System Tray)...
pip install pystray>=0.19.4

echo.
echo [2/5] Instalando Pillow (Procesamiento de imagenes)...
pip install Pillow>=9.0.0

echo.
echo [3/5] Instalando pyodbc (Base de datos)...
pip install pyodbc>=4.0.35

echo.
echo [4/5] Instalando requests (HTTP)...
pip install requests>=2.28.0

echo.
echo [5/5] Instalando urllib3 (Utilidades HTTP)...
pip install urllib3>=1.26.0

echo.
echo ===============================================
echo  Verificando instalacion
echo ===============================================
echo.

python -c "import pystray; print('✓ pystray instalado correctamente')" 2>nul || echo "✗ Error con pystray"
python -c "from PIL import Image; print('✓ Pillow instalado correctamente')" 2>nul || echo "✗ Error con Pillow"
python -c "import pyodbc; print('✓ pyodbc instalado correctamente')" 2>nul || echo "✗ Error con pyodbc"
python -c "import requests; print('✓ requests instalado correctamente')" 2>nul || echo "✗ Error con requests"
python -c "import urllib3; print('✓ urllib3 instalado correctamente')" 2>nul || echo "✗ Error con urllib3"
python -c "import tkinter; print('✓ tkinter disponible')" 2>nul || echo "✗ Error con tkinter - reinstala Python con soporte tkinter"

echo.
echo ===============================================
echo  Verificando archivos del proyecto
echo ===============================================
echo.

if exist "hikvision_tcp_monitor.py" (
    echo ✓ hikvision_tcp_monitor.py encontrado
) else (
    echo ✗ FALTA: hikvision_tcp_monitor.py
)

if exist "database_connection.py" (
    echo ✓ database_connection.py encontrado
) else (
    echo ✗ FALTA: database_connection.py
)

if exist "queue_worker.py" (
    echo ✓ queue_worker.py encontrado
) else (
    echo ✗ FALTA: queue_worker.py
)

if exist "hikvision_manager.py" (
    echo ✓ hikvision_manager.py encontrado
) else (
    echo ✗ FALTA: hikvision_manager.py
)

if exist "icon.ico" (
    echo ✓ icon.ico encontrado
) else (
    echo ⚠ ADVERTENCIA: icon.ico no encontrado - se usara icono por defecto
)

if exist "videoman.udl" (
    echo ✓ videoman.udl encontrado
) else (
    echo ⚠ ADVERTENCIA: videoman.udl no encontrado - se creara automaticamente
)

echo.
echo ===============================================
echo  Instalacion completada
echo ===============================================
echo.
echo Para ejecutar la aplicacion:
echo   python hikvision_tcp_monitor.py
echo.
echo La aplicacion iniciara minimizada en el area de notificacion.
echo.

pause
