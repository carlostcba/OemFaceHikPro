#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
queue_worker.py
Worker para procesar comandos de cola_comunicacion automaticamente
"""

import threading
import time
from datetime import datetime
import os
from pathlib import Path
from hikvision_manager import HikvisionManager

class QueueWorker:
    """Worker que procesa comandos de la cola de comunicacion"""
    
    def __init__(self, db_manager, log_callback=None):
        self.db_manager = db_manager
        self.log_callback = log_callback
        self.is_running = False
        self.worker_thread = None
        self.poll_interval = 5  # segundos entre lecturas de cola
        self.path_imagenes = None
        
    def log(self, message):
        """Enviar mensaje al log"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    
    def load_config(self):
        """Cargar configuracion de paths desde cfgopt"""
        try:
            sql = """
                SELECT Valor 
                FROM cfgopt 
                WHERE Nombre = 'PATH_IMAGENES_PERSONAS'
            """
            result = self.db_manager.execute_query(sql)
            
            if result and result[0][0]:
                self.path_imagenes = result[0][0].strip()
                self.log(f"Path imagenes configurado: {self.path_imagenes}")
                return True
            else:
                self.log("ERROR: No se encontro PATH_IMAGENES_PERSONAS en cfgopt")
                return False
                
        except Exception as e:
            self.log(f"Error cargando configuracion: {e}")
            return False
    
    def start(self):
        """Iniciar worker"""
        if self.is_running:
            self.log("Worker ya esta en ejecucion")
            return
        
        if not self.load_config():
            self.log("No se pudo cargar configuracion. Worker no iniciado.")
            return
        
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self.log("Worker de cola iniciado")
    
    def stop(self):
        """Detener worker"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=10)
        self.log("Worker de cola detenido")
    
    def _worker_loop(self):
        """Loop principal del worker"""
        self.log("Worker loop iniciado")
        
        while self.is_running:
            try:
                # Leer siguiente item de la cola
                queue_item = self._get_next_queue_item()
                
                if queue_item:
                    # Procesar comando
                    self._process_queue_item(queue_item)
                else:
                    # No hay items, esperar
                    time.sleep(self.poll_interval)
                    
            except Exception as e:
                self.log(f"Error en worker loop: {e}")
                time.sleep(self.poll_interval)
    
    def _get_next_queue_item(self):
        """Obtener siguiente item de la cola pendiente"""
        try:
            sql = """
                SELECT TOP 1 id, recepcion, createdAt
                FROM dbo.cola_comunicacion
                WHERE recepcion IS NOT NULL
                  AND LEN(LTRIM(RTRIM(recepcion))) > 0
                ORDER BY createdAt ASC
            """
            
            result = self.db_manager.execute_query(sql)
            
            if result and len(result) > 0:
                return {
                    'id': result[0][0],
                    'comando': result[0][1].strip(),
                    'created_at': result[0][2]
                }
            
            return None
            
        except Exception as e:
            self.log(f"Error leyendo cola: {e}")
            return None
    
    def _process_queue_item(self, item):
        """Procesar un item de la cola"""
        item_id = item['id']
        comando = item['comando']
        
        try:
            self.log(f"Procesando comando: {comando}")
            
            # Parsear comando: F0ADD-192.168.0.222-100005
            parts = comando.split('-')
            
            if len(parts) < 3:
                self.log(f"ERROR: Formato de comando invalido: {comando}")
                self._mark_as_processed(item_id)
                return
            
            operation = parts[0]  # F0ADD, F0UPD, F0DEL
            hik_ip = parts[1]     # IP del dispositivo
            persona_id = parts[2] # ID de persona
            
            # Validar operacion
            if operation not in ['F0ADD', 'F0UPD', 'F0DEL']:
                self.log(f"ERROR: Operacion desconocida: {operation}")
                self._mark_as_processed(item_id)
                return
            
            # Obtener credenciales del dispositivo
            device_config = self._get_device_config(hik_ip)
            if not device_config:
                self.log(f"ERROR: No se encontro configuracion para IP {hik_ip}")
                self._mark_as_processed(item_id)
                return
            
            # Verificar que el dispositivo este habilitado
            if not device_config.get('enabled', False):
                self.log(f"SKIP: Dispositivo {hik_ip} deshabilitado")
                self._mark_as_processed(item_id)
                return
            
            # Crear manager de Hikvision
            hik_manager = HikvisionManager(self.db_manager)
            hik_manager.set_device_config_manual(
                device_config['ip'],
                device_config['usuario'],
                device_config['password']
            )
            
            # Ejecutar operacion segun comando
            if operation == 'F0DEL':
                success = self._execute_delete(hik_manager, persona_id, hik_ip)
            else:  # F0ADD o F0UPD
                success = self._execute_add_update(hik_manager, persona_id, hik_ip, operation)
            
            # Marcar como procesado
            self._mark_as_processed(item_id)
            
            status = "OK" if success else "ERROR"
            self.log(f"Comando {comando} procesado: {status}")
            
        except Exception as e:
            self.log(f"ERROR procesando item {item_id}: {e}")
            self._mark_as_processed(item_id)
    
    def _get_device_config(self, hik_ip):
        """Obtener configuracion de dispositivo desde dbo.mdl"""
        try:
            sql = """
                SELECT 
                    HikIP, 
                    HikUsuario, 
                    HikPassword, 
                    HikPuertoHTTP,
                    HikPuertoHTTPS,
                    HikPuertoRTSP,
                    HikPuertoSVR,
                    HikEnable
                FROM dbo.mdl
                WHERE HikIP = ? AND HikEnable = 1
            """
            
            result = self.db_manager.execute_query(sql, (hik_ip,))
            
            if result and len(result) > 0:
                row = result[0]
                return {
                    'ip': row[0],
                    'usuario': row[1] or 'admin',
                    'password': row[2] or '',
                    'puerto_http': row[3] or 80,
                    'puerto_https': row[4] or 443,
                    'puerto_rtsp': row[5] or 554,
                    'puerto_svr': row[6] or 8000,
                    'enabled': bool(row[7])
                }
            
            return None
            
        except Exception as e:
            self.log(f"Error obteniendo config de dispositivo: {e}")
            return None
    
    def _get_persona_data(self, persona_id):
        """Obtener datos de persona desde dbo.per"""
        try:
            sql = """
                SELECT Nombre, Apellido, FechaInicio, FechaFin
                FROM dbo.per
                WHERE PersonaID = ?
            """
            
            result = self.db_manager.execute_query(sql, (persona_id,))
            
            if result and len(result) > 0:
                row = result[0]
                return {
                    'nombre': row[0] or '',
                    'apellido': row[1] or '',
                    'fecha_inicio': row[2],
                    'fecha_fin': row[3]
                }
            
            return None
            
        except Exception as e:
            self.log(f"Error obteniendo datos de persona: {e}")
            return None
    
    def _get_image_path(self, persona_id):
        """Obtener path de imagen de persona"""
        if not self.path_imagenes:
            return None
        
        # Intentar con extension .jpg
        image_path = Path(self.path_imagenes) / f"{persona_id}.jpg"
        
        if image_path.exists():
            return str(image_path)
        
        # Intentar con extension .jpeg
        image_path = Path(self.path_imagenes) / f"{persona_id}.jpeg"
        
        if image_path.exists():
            return str(image_path)
        
        return None
    
    def _execute_add_update(self, hik_manager, persona_id, hik_ip, operation):
        """Ejecutar operacion de alta o actualizacion"""
        try:
            # Obtener datos de persona
            persona_data = self._get_persona_data(persona_id)
            if not persona_data:
                self.log(f"ERROR: No se encontro persona ID {persona_id}")
                return False
            
            # Construir nombre completo
            nombre_completo = f"{persona_data['nombre']} {persona_data['apellido']}".strip()
            
            # Obtener path de imagen
            image_path = self._get_image_path(persona_id)
            
            if not image_path:
                self.log(f"WARNING: No se encontro imagen para persona {persona_id}")
                # Continuar sin imagen
            
            # Formatear fechas
            fecha_inicio = None
            fecha_fin = None
            
            if persona_data['fecha_inicio']:
                fecha_inicio = persona_data['fecha_inicio'].strftime("%Y-%m-%d")
            
            if persona_data['fecha_fin']:
                fecha_fin = persona_data['fecha_fin'].strftime("%Y-%m-%d")
            
            # Ejecutar alta/actualizacion en Hikvision
            self.log(f"Ejecutando {operation} en {hik_ip} para {nombre_completo} (ID: {persona_id})")
            
            success, message = hik_manager.create_or_update_user_in_device(
                employee_id=persona_id,
                name=nombre_completo,
                enabled=True,
                start_date=fecha_inicio,
                end_date=fecha_fin,
                image_path=image_path
            )
            
            if success:
                self.log(f"OK: {message}")
                return True
            else:
                self.log(f"ERROR: {message}")
                return False
                
        except Exception as e:
            self.log(f"ERROR ejecutando {operation}: {e}")
            return False
    
    def _execute_delete(self, hik_manager, persona_id, hik_ip):
        """Ejecutar operacion de baja"""
        try:
            self.log(f"Ejecutando F0DEL en {hik_ip} para persona ID {persona_id}")
            
            success, message = hik_manager.delete_user_from_device(persona_id)
            
            if success:
                self.log(f"OK: {message}")
                return True
            else:
                self.log(f"ERROR: {message}")
                return False
                
        except Exception as e:
            self.log(f"ERROR ejecutando F0DEL: {e}")
            return False
    
    def _mark_as_processed(self, item_id):
        """Marcar item como procesado (eliminarlo de la cola)"""
        try:
            sql = "DELETE FROM dbo.cola_comunicacion WHERE id = ?"
            rows = self.db_manager.execute_command(sql, (item_id,))
            
            if rows > 0:
                self.log(f"Item {item_id} eliminado de cola")
            else:
                self.log(f"WARNING: No se pudo eliminar item {item_id}")
                
        except Exception as e:
            self.log(f"ERROR eliminando item {item_id}: {e}")