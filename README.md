# Monitor Hikvision + Worker de Cola con System Tray

**Version**: 2.0 con System Tray
**Fecha**: Octubre 2025

## Descripcion

Monitor de eventos Hikvision con worker automatico de cola de comandos, ahora con soporte completo para System Tray (area de notificacion) de Windows. La aplicacion inicia minimizada y permanece accesible desde el icono junto al reloj, similar a WireGuard, Dropbox y otras aplicaciones profesionales.

## Caracteristicas Principales

### Sistema de Monitoreo
- ✅ Servidor HTTP para recibir eventos de dispositivos Hikvision
- ✅ Procesamiento asincrono de eventos (multithreading)
- ✅ Almacenamiento de eventos en base de datos SQL Server
- ✅ Soporte para eventos de control de acceso (5-75, 5-76)

### Worker de Cola Automatico
- ✅ Procesa comandos de cola automaticamente (F0ADD, F0UPD, F0DEL)
- ✅ Sincronizacion con dispositivos Hikvision via ISAPI
- ✅ Optimizacion automatica de imagenes faciales
- ✅ Inicio automatico con la aplicacion

### System Tray (NUEVO)
- ✅ Inicio minimizado en area de notificacion
- ✅ Icono personalizable (icon.ico)
- ✅ Menu contextual completo
- ✅ No se cierra accidentalmente
- ✅ Servicios activos en segundo plano

## Inicio Rapido

### 1. Instalar Dependencias
```bash
# Opcion A: Script automatico (Windows)
instalar_dependencias.bat

# Opcion B: Manual
pip install pystray Pillow pyodbc requests urllib3
```

### 2. Ejecutar
```bash
python hikvision_tcp_monitor.py
```

### 3. Buscar el Icono
- Busca el icono en el area de notificacion (junto al reloj)
- Doble clic para abrir la ventana
- Clic derecho para ver el menu

## Archivos del Proyecto

### Archivos Principales
```
hikvision_tcp_monitor.py    # Aplicacion principal con system tray
database_connection.py       # Conexion a SQL Server
queue_worker.py              # Worker automatico de cola
hikvision_manager.py         # API de Hikvision
icon.ico                     # Icono de la aplicacion
videoman.udl                 # Configuracion de BD
```

### Utilidades
```
instalar_dependencias.bat    # Script de instalacion
requirements.txt             # Dependencias Python
```

## Uso del System Tray

### Abrir Ventana
- **Doble clic** en el icono del tray
- O: **Clic derecho** → "Mostrar"

### Ocultar Ventana
- **Cerrar** la ventana (X)
- O: **Clic derecho** en el icono → "Ocultar"

### Cerrar Aplicacion
- **Clic derecho** en el icono → "Salir"

## Requisitos

### Sistema Operativo
- Windows 7 o superior
- Windows 10/11 recomendado

### Software
- Python 3.8 o superior
- SQL Server (ODBC Driver 17 recomendado)

### Python Packages
- pystray >= 0.19.4
- Pillow >= 9.0.0
- pyodbc >= 4.0.35
- requests >= 2.28.0
- urllib3 >= 1.26.0
- tkinter (incluido en Python)

### Base de Datos
- Tabla `cola_comunicacion`
- Tabla `per` (personas)
- Tabla `mdl` (dispositivos)
- Tabla `cfgopt` (configuracion)
- Tabla `hikvision` (opcional)

## Configuracion

### Base de Datos
Edita `videoman.udl` o configuralo en la BD:
```
Server: localhost\SQLEXPRESS
Database: RobleJoven
User: sa
Password: [tu_password]
```

### Path de Imagenes
En la tabla `cfgopt`:
```sql
INSERT INTO cfgopt (Nombre, Valor)
VALUES ('PATH_IMAGENES_PERSONAS', 'C:\ImagenesPersonas\');
```

### Dispositivos Hikvision
En la tabla `mdl`:
```sql
UPDATE mdl SET
    HikIP = '192.168.0.222',
    HikUsuario = 'admin',
    HikPassword = 'password',
    HikEnable = 1
WHERE ModuloID = 1;
```

## Comandos de Cola

Formato en `cola_comunicacion.recepcion`:

### Alta/Actualizacion
```
F0ADD-192.168.0.222-100005
F0UPD-192.168.0.222-100005
```

### Baja
```
F0DEL-192.168.0.222-100005
```

Donde:
- `192.168.0.222` = IP del dispositivo Hikvision
- `100005` = ID de la persona

## Puertos Utilizados

- **8080**: Servidor HTTP para eventos Hikvision (configurable)
- **1433**: SQL Server (default)
- **80/443**: API ISAPI de Hikvision

## Logs

La aplicacion genera 3 tipos de logs visibles en la interfaz:

### Log de Eventos HTTP
- Eventos recibidos de dispositivos
- Accesos correctos/denegados
- Heartbeats

### Log de Worker
- Comandos procesados
- Estado de sincronizacion
- Errores de operacion

### Log de Sistema
- Estado del servidor
- Conexiones a BD
- Eventos del sistema

## Resolucion de Problemas

### El icono no aparece en el tray
```bash
pip install --upgrade pystray Pillow
```

### No se ve mi icono personalizado
1. Verifica que se llame exactamente `icon.ico`
2. Debe estar en la MISMA carpeta que el script
3. Reinicia la aplicacion

### Worker no procesa comandos
1. Verifica que Worker este "ACTIVO" (verde)
2. Revisa comandos en cola: Boton "Ver Cola"
3. Verifica que HikEnable = 1 en tabla mdl

### Error de conexion a BD
1. Verifica credenciales en videoman.udl
2. Prueba conexion con SQL Server Management Studio
3. Verifica que el servicio SQL Server este corriendo

## Iniciar con Windows

### Metodo 1: Carpeta Inicio
1. `Win + R` → `shell:startup`
2. Crea acceso directo a `hikvision_tcp_monitor.py`

### Metodo 2: Tarea Programada
1. Abre "Programador de tareas"
2. "Crear tarea basica"
3. Desencadenador: "Al iniciar sesion"
4. Accion: Ejecutar Python script

## Arquitectura

```
┌─────────────────────────────────────────────┐
│         System Tray Icon (pystray)          │
│              [Menu Contextual]              │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│      Ventana Principal (tkinter)            │
│  ┌────────────┐  ┌────────────┐            │
│  │ Servidor   │  │  Worker    │            │
│  │ HTTP:8080  │  │  de Cola   │            │
│  └─────┬──────┘  └──────┬─────┘            │
│        │                │                   │
└────────┼────────────────┼───────────────────┘
         │                │
         │                │
    ┌────▼─────┐     ┌────▼────────┐
    │ Eventos  │     │  Comandos   │
    │ Hikvision│     │  F0ADD/UPD  │
    └────┬─────┘     └────┬────────┘
         │                │
         │                │
    ┌────▼────────────────▼─────┐
    │    SQL Server Database     │
    │  - cola_comunicacion       │
    │  - per (personas)          │
    │  - mdl (dispositivos)      │
    └────────────────────────────┘
```

## Seguridad

- ⚠ Contraseñas en texto plano en BD (considera encriptar)
- ⚠ Sin autenticacion en servidor HTTP (usar firewall)
- ⚠ SSL deshabilitado para dispositivos locales
- ✅ Autenticacion Digest para API Hikvision
- ✅ Transacciones de BD para integridad

## Licencia

[Especifica tu licencia aqui]

## Soporte

Para reportar problemas o solicitar ayuda:
1. Revisa los logs de la aplicacion
2. Consulta la documentacion
3. Verifica configuracion de BD
4. Contacta al administrador del sistema

## Creditos

- **Desarrollo**: [Tu nombre/equipo]
- **Version System Tray**: Octubre 2025
- **Librerias**: pystray, Pillow, pyodbc, requests

## Version

### 2.0 (Octubre 2025) - System Tray
- ✅ Inicio en system tray
- ✅ Icono personalizable
- ✅ Menu contextual
- ✅ Comportamiento profesional

### 1.0 (Anterior) - Base
- ✅ Servidor HTTP de eventos
- ✅ Worker automatico de cola
- ✅ Procesamiento asincrono
- ✅ Integracion con Hikvision

## Roadmap Futuro

- 🔲 Notificaciones emergentes
- 🔲 Estadisticas en tiempo real
- 🔲 Panel web de administracion
- 🔲 Soporte para multiples dispositivos
- 🔲 Backup automatico de configuracion
- 🔲 Logs a archivo
- 🔲 Metricas y analytics
