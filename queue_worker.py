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
from PIL import Image
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
    
    def _optimize_image(self, image_path, max_width=600, max_height=900, max_size_kb=150):
        """
        Optimizar imagen para Hikvision manteniendo aspect ratio
        
        Args:
            image_path: Path de imagen original
            max_width: Ancho maximo en pixels (Hikvision: 600)
            max_height: Alto maximo en pixels (Hikvision: 900)
            max_size_kb: Tamano maximo en KB (Hikvision: 150)
            
        Returns:
            Path de imagen optimizada (temporal) o None si falla
        """
        try:
            # Abrir imagen
            img = Image.open(image_path)
            
            # Obtener dimensiones originales
            orig_width, orig_height = img.size
            file_size_kb = os.path.getsize(image_path) / 1024
            
            self.log(f"Imagen original: {orig_width}x{orig_height} ({file_size_kb:.1f}KB)")
            
            # Verificar si necesita optimizacion
            needs_resize = orig_width > max_width or orig_height > max_height
            needs_compress = file_size_kb > max_size_kb
            
            if not needs_resize and not needs_compress:
                self.log("Imagen ya tiene tamano optimo")
                return image_path
            
            # Calcular nuevas dimensiones manteniendo aspect ratio
            if needs_resize:
                ratio = min(max_width / orig_width, max_height / orig_height)
                new_width = int(orig_width * ratio)
                new_height = int(orig_height * ratio)
                
                self.log(f"Redimensionando a {new_width}x{new_height} (ratio: {ratio:.2f})")
                
                # Redimensionar con calidad alta
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convertir a RGB si es necesario (Hikvision no acepta RGBA)
            if img.mode in ('RGBA', 'LA', 'P'):
                self.log(f"Convirtiendo de {img.mode} a RGB")
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            # Guardar temporalmente con compresion
            temp_path = os.path.join(os.path.dirname(image_path), f"temp_{os.path.basename(image_path)}")
            
            # Ajustar calidad inicial segun tamano necesario
            quality = 90  # Empezar con 90% para archivos mas pequenos
            if needs_compress or file_size_kb > max_size_kb:
                quality = 80  # Empezar mas bajo si ya sabemos que es grande
            
            img.save(temp_path, 'JPEG', quality=quality, optimize=True)
            
            # Verificar tamano final
            final_size_kb = os.path.getsize(temp_path) / 1024
            self.log(f"Imagen optimizada: {img.size[0]}x{img.size[1]} ({final_size_kb:.1f}KB, Q={quality})")
            
            # Compresion iterativa si aun es muy grande
            attempts = 0
            max_attempts = 5
            
            while final_size_kb > max_size_kb and quality > 50 and attempts < max_attempts:
                attempts += 1
                quality = max(50, quality - 10)  # Reducir de 10 en 10, minimo 50
                
                self.log(f"Recomprimiendo intento {attempts} con calidad {quality}%...")
                img.save(temp_path, 'JPEG', quality=quality, optimize=True)
                final_size_kb = os.path.getsize(temp_path) / 1024
                self.log(f"Resultado: {final_size_kb:.1f}KB")
            
            # Verificacion final
            if final_size_kb > max_size_kb:
                self.log(f"ADVERTENCIA: Imagen final ({final_size_kb:.1f}KB) aun supera limite ({max_size_kb}KB)")
                self.log("Puede fallar en subida. Considere imagen con menor resolucion original.")
            else:
                self.log(f"Imagen final: {final_size_kb:.1f}KB (dentro del limite)")
            
            return temp_path
            
        except Exception as e:
            self.log(f"Error optimizando imagen: {e}")
            return None
    
    def _execute_add_update(self, hik_manager, persona_id, hik_ip, operation):
        """Ejecutar operacion de alta o actualizacion"""
        optimized_image_path = None
        
        try:
            # Obtener datos de persona
            persona_data = self._get_persona_data(persona_id)
            if not persona_data:
                self.log(f"ERROR: No se encontro persona ID {persona_id}")
                return False
            
            # Construir nombre completo
            nombre_completo = f"{persona_data['nombre']} {persona_data['apellido']}".strip()
            
            # Obtener path de imagen original
            original_image_path = self._get_image_path(persona_id)
            
            if not original_image_path:
                self.log(f"WARNING: No se encontro imagen para persona {persona_id}")
                # Continuar sin imagen
                image_path_to_use = None
            else:
                # Optimizar imagen
                self.log(f"Optimizando imagen para persona {persona_id}...")
                optimized_image_path = self._optimize_image(original_image_path)
                
                if optimized_image_path:
                    image_path_to_use = optimized_image_path
                else:
                    self.log("WARNING: Error optimizando imagen, intentando con original")
                    image_path_to_use = original_image_path
            
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
                image_path=image_path_to_use
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
        finally:
            # Limpiar imagen temporal si existe
            if optimized_image_path and optimized_image_path != original_image_path:
                try:
                    if os.path.exists(optimized_image_path):
                        os.remove(optimized_image_path)
                        self.log("Imagen temporal eliminada")
                except Exception as e:
                    self.log(f"Error eliminando temporal: {e}")
    
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
