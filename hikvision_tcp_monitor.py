#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hikvision_tcp_monitor_integrated.py
Monitor de eventos Hikvision + Worker de Cola Automatico
Con soporte para System Tray
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import urllib3
import threading
from datetime import datetime
import socket
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from http.server import HTTPServer
import queue
import time
from concurrent.futures import ThreadPoolExecutor
import traceback
from database_connection import DatabaseManager
from queue_worker import QueueWorker
import pystray
from PIL import Image
import os
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer que maneja multiples conexiones concurrentes automaticamente"""
    daemon_threads = True
    allow_reuse_address = True

class ConcurrentEventHandler(BaseHTTPRequestHandler):
    """Manejador de eventos HTTP optimizado para concurrencia"""
    
    def __init__(self, app_instance, *args, **kwargs):
        self.app = app_instance
        super().__init__(*args, **kwargs)
    
    def do_POST(self):
        """Maneja eventos POST con procesamiento asincrono"""
        start_time = time.time()
        client_ip = self.client_address[0]
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            content_type = self.headers.get('Content-Type', '')
            
            self.app.log_connection(f"Conexion desde {client_ip}")
            
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                self.app.enqueue_event_processing(post_data, content_type, client_ip)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b'{"status": "OK"}')
            
            processing_time = (time.time() - start_time) * 1000
            self.app.log_performance(f"Respuesta en {processing_time:.1f}ms desde {client_ip}")
            
        except Exception as e:
            self.app.log_event(f"Error en servidor HTTP desde {client_ip}: {e}")
            self.send_response(500)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suprimir logs del servidor HTTP"""
        pass

class HikvisionIntegratedMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor Hikvision + Worker de Cola")
        self.root.geometry("750x550")
        self.root.resizable(True, True)
        
        # System Tray
        self.tray_icon = None
        self.is_visible = True
        
        # Servidor HTTP
        self.event_server = None
        self.event_server_thread = None
        self.server_port = 8080
        
        # Procesamiento asincrono
        self.event_queue = queue.Queue()
        self.processing_thread = None
        self.is_processing = False
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # Base de Datos
        self.db_manager = DatabaseManager(udl_file="videoman.udl")
        self.db_manager.connect()
        
        # Queue Worker
        self.queue_worker = QueueWorker(self.db_manager, log_callback=self.log_worker)
        
        # Estadisticas
        self.active_connections = 0
        self.total_events_processed = 0
        self.devices_connected = set()
        self.filtered_events_count = 0
        
        self.setup_ui()
        self.start_event_processor()
        self.root.after(100, self.start_server)
        self.root.after(300, self.start_worker)  # Iniciar worker automaticamente
        
        # Configurar icono de ventana
        self.load_window_icon()
        
        # Configurar System Tray
        self.root.after(500, self.setup_system_tray)
        
        # Interceptar cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        # Iniciar minimizado
        self.root.after(600, self.minimize_to_tray)

    def load_window_icon(self):
        """Cargar icono para la ventana"""
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
                self.log_message(f"Icono cargado: {icon_path}")
            else:
                self.log_message(f"Icono no encontrado: {icon_path}")
        except Exception as e:
            self.log_message(f"Error cargando icono de ventana: {e}")

    def setup_system_tray(self):
        """Configurar icono en System Tray"""
        try:
            # Cargar icono
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            
            if os.path.exists(icon_path):
                image = Image.open(icon_path)
            else:
                # Crear icono por defecto si no existe
                image = Image.new('RGB', (64, 64), color='darkblue')
                self.log_message("Usando icono por defecto - icon.ico no encontrado")
            
            # Crear menu del tray
            menu = pystray.Menu(
                pystray.MenuItem("Mostrar", self.show_window, default=True),
                pystray.MenuItem("Ocultar", self.hide_window),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", self.quit_application)
            )
            
            # Crear icono del tray
            self.tray_icon = pystray.Icon(
                "hikvision_monitor",
                image,
                "Monitor Hikvision + Worker",
                menu
            )
            
            # Ejecutar icono en thread separado
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
            self.log_message("System Tray inicializado correctamente")
            
        except Exception as e:
            self.log_message(f"Error configurando System Tray: {e}")
            traceback.print_exc()

    def show_window(self, icon=None, item=None):
        """Mostrar ventana principal"""
        self.root.after(0, self._show_window_impl)
    
    def _show_window_impl(self):
        """Implementacion de mostrar ventana (debe ejecutarse en main thread)"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.is_visible = True
        self.log_message("Ventana mostrada")

    def hide_window(self, icon=None, item=None):
        """Ocultar ventana al system tray"""
        self.root.withdraw()
        self.is_visible = False
        self.log_message("Ventana minimizada al system tray")

    def minimize_to_tray(self):
        """Minimizar al tray al iniciar"""
        self.hide_window()
        self.log_message("Aplicacion iniciada en system tray")

    def quit_application(self, icon=None, item=None):
        """Salir completamente de la aplicacion"""
        self.log_message("Cerrando aplicacion...")
        
        # Detener tray icon
        if self.tray_icon:
            self.tray_icon.stop()
        
        # Detener servicios
        if self.event_server:
            self.stop_server()
        
        if self.queue_worker.is_running:
            self.stop_worker()
        
        if self.db_manager:
            self.db_manager.disconnect()
        
        self.executor.shutdown(wait=True)
        
        # Cerrar ventana
        self.root.quit()
        self.root.destroy()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Informacion del sistema
        info_frame = ttk.LabelFrame(main_frame, text="Informacion del Sistema", padding="10")
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        local_ip = self.get_local_ip()
        ttk.Label(info_frame, text=f"IP Local: {local_ip}").grid(row=0, column=0, sticky=tk.W)
        
        db_status = "CONECTADA" if self.db_manager.get_connection() else "DESCONECTADA"
        db_color = "green" if db_status == "CONECTADA" else "red"
        self.db_status_label = ttk.Label(info_frame, text=f"DB: {db_status}", foreground=db_color)
        self.db_status_label.grid(row=0, column=1, sticky=tk.W, padx=(20, 0))
        
        self.stats_label = ttk.Label(info_frame, text="Dispositivos: 0 | Eventos: 0 | Activas: 0")
        self.stats_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        # Servidor HTTP
        server_frame = ttk.LabelFrame(main_frame, text="Servidor HTTP Eventos", padding="10")
        server_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        server_control_frame = ttk.Frame(server_frame)
        server_control_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(server_control_frame, text="Puerto:").pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value="8080")
        ttk.Entry(server_control_frame, textvariable=self.port_var, width=8, state=tk.DISABLED).pack(side=tk.LEFT, padx=(5, 10))

        self.start_server_btn = ttk.Button(server_control_frame, text="Iniciar", command=self.start_server, state=tk.DISABLED)
        self.start_server_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_server_btn = ttk.Button(server_control_frame, text="Detener", command=self.stop_server, state=tk.DISABLED)
        self.stop_server_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.server_status_label = ttk.Label(server_control_frame, text="Servidor: Detenido", foreground="red")
        self.server_status_label.pack(side=tk.RIGHT)

        # Worker de Cola
        worker_frame = ttk.LabelFrame(main_frame, text="Worker de Cola Automatico", padding="10")
        worker_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        worker_control_frame = ttk.Frame(worker_frame)
        worker_control_frame.pack(fill=tk.X, pady=(0, 5))

        self.start_worker_btn = ttk.Button(worker_control_frame, text="Iniciar Worker", command=self.start_worker)
        self.start_worker_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_worker_btn = ttk.Button(worker_control_frame, text="Detener Worker", command=self.stop_worker, state=tk.DISABLED)
        self.stop_worker_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(worker_control_frame, text="Ver Cola", command=self.show_queue).pack(side=tk.LEFT, padx=(5, 0))

        self.worker_status_label = ttk.Label(worker_control_frame, text="Worker: Detenido", foreground="red")
        self.worker_status_label.pack(side=tk.RIGHT)

        # Log de eventos
        event_frame = ttk.LabelFrame(main_frame, text="Log de Eventos HTTP", padding="5")
        event_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        self.event_text = scrolledtext.ScrolledText(event_frame, height=8, width=70)
        self.event_text.pack(fill=tk.BOTH, expand=True)

        # Log de worker
        worker_log_frame = ttk.LabelFrame(main_frame, text="Log de Worker", padding="5")
        worker_log_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.worker_log_text = scrolledtext.ScrolledText(worker_log_frame, height=6, width=70)
        self.worker_log_text.pack(fill=tk.BOTH, expand=True)

        # Log de sistema
        system_frame = ttk.LabelFrame(main_frame, text="Log de Sistema", padding="5")
        system_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(system_frame, height=3, width=70)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configurar grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

    def insert_event_into_db(self, event_message):
        """Inserta un evento en la tabla cola_comunicacion."""
        if not self.db_manager or not self.db_manager.get_connection():
            self.log_message("DB no conectada - evento no guardado")
            return False
        
        try:
            sql = "INSERT INTO cola_comunicacion (transmision) VALUES (?)"
            rows_affected = self.db_manager.execute_command(sql, (event_message,))
            
            if rows_affected > 0:
                self.log_message(f"DB GUARDADO: {event_message}")
                return True
            else:
                self.log_message(f"DB: No se pudo guardar: {event_message}")
                return False
        except Exception as e:
            self.log_message(f"Error guardando en DB: {e}")
            return False

    def start_server(self):
        """Inicia el servidor HTTP"""
        if self.event_server:
            return
        try:
            self.server_port = int(self.port_var.get())
            
            def handler(*args, **kwargs):
                ConcurrentEventHandler(self, *args, **kwargs)
            
            self.event_server = ThreadingHTTPServer(('', self.server_port), handler)
            
            def run_server():
                self.log_message(f"Servidor iniciado en puerto {self.server_port}")
                self.event_server.serve_forever()
            
            self.event_server_thread = threading.Thread(target=run_server, daemon=True)
            self.event_server_thread.start()
            
            self.start_server_btn.config(state=tk.DISABLED)
            self.stop_server_btn.config(state=tk.NORMAL)
            self.server_status_label.config(text="Servidor: ACTIVO", foreground="green")
            
            local_ip = self.get_local_ip()
            self.log_event(f"Servidor HTTP en http://{local_ip}:{self.server_port}")
            
        except Exception as e:
            self.log_message(f"Error iniciando servidor: {e}")

    def stop_server(self):
        """Detiene el servidor HTTP"""
        if self.event_server:
            self.event_server.shutdown()
            self.event_server.server_close()
            self.event_server = None
        
        self.is_processing = False
        self.start_server_btn.config(state=tk.NORMAL)
        self.stop_server_btn.config(state=tk.DISABLED)
        self.server_status_label.config(text="Servidor: Detenido", foreground="red")
        
        self.log_message("Servidor detenido")

    def start_worker(self):
        """Iniciar worker de cola"""
        try:
            self.log_worker("Iniciando worker de cola...")
            self.queue_worker.start()
            
            self.start_worker_btn.config(state=tk.DISABLED)
            self.stop_worker_btn.config(state=tk.NORMAL)
            self.worker_status_label.config(text="Worker: ACTIVO", foreground="green")
            
            self.log_worker("Worker iniciado correctamente")
        except Exception as e:
            self.log_worker(f"Error iniciando worker: {e}")
            messagebox.showerror("Error", f"No se pudo iniciar worker:\n{e}")

    def stop_worker(self):
        """Detener worker de cola"""
        try:
            self.log_worker("Deteniendo worker...")
            self.queue_worker.stop()
            
            self.start_worker_btn.config(state=tk.NORMAL)
            self.stop_worker_btn.config(state=tk.DISABLED)
            self.worker_status_label.config(text="Worker: Detenido", foreground="red")
            
            self.log_worker("Worker detenido")
        except Exception as e:
            self.log_worker(f"Error deteniendo worker: {e}")

    def show_queue(self):
        """Mostrar items pendientes en la cola"""
        try:
            sql = """
                SELECT id, recepcion, createdAt
                FROM dbo.cola_comunicacion
                WHERE recepcion IS NOT NULL
                ORDER BY createdAt ASC
            """
            
            items = self.db_manager.execute_query(sql)
            
            if items:
                msg = f"Items pendientes en cola: {len(items)}\n\n"
                for item in items[:10]:
                    msg += f"ID: {item[0]} | {item[1]} | {item[2]}\n"
                
                if len(items) > 10:
                    msg += f"\n... y {len(items) - 10} mas"
                
                messagebox.showinfo("Cola de Comunicacion", msg)
            else:
                messagebox.showinfo("Cola Vacia", "No hay items pendientes en la cola")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error consultando cola:\n{e}")

    def start_event_processor(self):
        """Inicia el procesador de eventos asincrono"""
        self.is_processing = True
        
        def process_events():
            while self.is_processing:
                try:
                    event_item = self.event_queue.get(timeout=1)
                    self.executor.submit(self.process_event_async, event_item)
                except queue.Empty:
                    continue
                except Exception as e:
                    self.log_message(f"Error en procesador: {e}")
        
        self.processing_thread = threading.Thread(target=process_events, daemon=True)
        self.processing_thread.start()

    def enqueue_event_processing(self, post_data, content_type, client_ip):
        """Encola evento para procesamiento"""
        event_item = {
            'data': post_data,
            'content_type': content_type,
            'client_ip': client_ip,
            'timestamp': datetime.now()
        }
        self.event_queue.put(event_item)

    def process_event_async(self, event_item):
        """Procesa un evento de forma asincrona"""
        try:
            client_ip = event_item['client_ip']
            self.devices_connected.add(client_ip)
            self.active_connections += 1
            self.update_stats()
            
            if 'multipart' in event_item['content_type'].lower():
                self.process_multipart_event(event_item['data'], event_item['content_type'], client_ip)
            else:
                try:
                    event_data = json.loads(event_item['data'].decode('utf-8'))
                    self.process_access_event(event_data, client_ip)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self.process_multipart_event(event_item['data'], event_item['content_type'], client_ip)
            
            self.total_events_processed += 1
            
        except Exception as e:
            self.log_event(f"Error procesando evento de {client_ip}: {e}")
            traceback.print_exc()
        finally:
            self.active_connections -= 1
            self.update_stats()

    def process_multipart_event(self, data, content_type="", client_ip=None):
        """Procesa eventos multipart"""
        try:
            boundary = None
            if 'boundary=' in content_type:
                boundary = content_type.split('boundary=')[1].split(';')[0]
            
            if not boundary:
                data_start = data[:500]
                for line in data_start.split(b'\r\n'):
                    if line.startswith(b'--') and len(line) > 10:
                        boundary = line[2:].decode('ascii', errors='ignore')
                        break
            
            if boundary:
                parts = data.split(f'--{boundary}'.encode())
                
                for part in parts:
                    if b'application/json' in part:
                        try:
                            if b'\r\n\r\n' in part:
                                _, content = part.split(b'\r\n\r\n', 1)
                                content_str = content.decode('utf-8', errors='ignore')
                                json_start = content_str.find('{')
                                json_end = content_str.rfind('}') + 1
                                
                                if json_start != -1 and json_end > json_start:
                                    json_str = content_str[json_start:json_end]
                                    event_data = json.loads(json_str)
                                    self.process_access_event(event_data, client_ip)
                                    return
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
            
            self.extract_json_from_binary(data, client_ip)
                
        except Exception as e:
            self.log_event(f"Error procesando multipart: {e}")

    def extract_json_from_binary(self, data, client_ip=None):
        """Extrae JSON de datos binarios"""
        try:
            json_patterns = [b'{"', b'{\r\n', b'{\n', b'{ "']
            
            start_pos = -1
            for pattern in json_patterns:
                pos = data.find(pattern)
                if pos != -1:
                    start_pos = pos
                    break
            
            if start_pos == -1:
                self.log_event("Evento recibido (sin JSON detectable)")
                return
            
            json_data = data[start_pos:]
            brace_count = 0
            end_pos = -1
            in_string = False
            escape_next = False
            
            for i, byte in enumerate(json_data):
                char = chr(byte) if byte < 128 else '?'
                
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"':
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
            
            if end_pos > 0:
                json_bytes = json_data[:end_pos]
                json_str = json_bytes.decode('utf-8', errors='replace')
                
                try:
                    event_data = json.loads(json_str)
                    self.process_access_event(event_data, client_ip)
                except json.JSONDecodeError as e:
                    self.log_event(f"JSON invalido: {e}")
            else:
                self.log_event("Evento recibido (JSON incompleto)")
                
        except Exception as e:
            self.log_event(f"Error extrayendo JSON: {e}")

    def process_access_event(self, event_data, client_ip=None):
        """Procesa eventos de Hikvision"""
        try:
            event_type = event_data.get('eventType', '')
            hik_ip = event_data.get('ipAddress', client_ip or 'unknown')

            if event_type == 'heartBeat':
                self.log_event(f"HeartBeat del dispositivo {hik_ip}")
                return
            
            if 'AccessControllerEvent' in event_data:
                acc_event = event_data['AccessControllerEvent']
                major_type = acc_event.get('majorEventType', 0)
                minor_type = acc_event.get('subEventType', 0)
                date_time = event_data.get('dateTime', datetime.now().isoformat())
                employee_no = acc_event.get('employeeNoString', '')
                name = acc_event.get('name', '')
                verify_mode = acc_event.get('currentVerifyMode', 'N/A')
                
            elif 'majorEventType' in event_data and 'subEventType' in event_data:
                major_type = event_data.get('majorEventType', 0)
                minor_type = event_data.get('subEventType', 0)
                date_time = event_data.get('dateTime', datetime.now().isoformat())
                employee_no = event_data.get('employeeNoString', '')
                name = event_data.get('name', '')
                verify_mode = event_data.get('currentVerifyMode', 'N/A')
                
            else:
                self.log_event(f"Evento desconocido: {event_type} de {hik_ip}")
                return
            
            self.log_event(f"EVENTO: {major_type}-{minor_type} de {hik_ip}")
            self.log_event(f"Tiempo: {date_time}")
            if employee_no:
                self.log_event(f"Usuario: {employee_no}")
            if name:
                self.log_event(f"Nombre: {name}")
            self.log_event(f"Metodo: {verify_mode}")
            
            if major_type == 5 and minor_type in [75, 76]:
                if minor_type == 75:
                    event_description = "ACCESO CORRECTO"
                else:
                    event_description = "ACCESO DENEGADO"
                
                system_log_entry = self.generate_system_log_entry(minor_type, date_time, employee_no, hik_ip)
                if system_log_entry:
                    self.log_message(f"LOG SISTEMA: {system_log_entry}")
                    self.insert_event_into_db(system_log_entry)
                
                self.log_event(f"{event_description} - GUARDADO EN DB")
            else:
                self.filtered_events_count += 1
                self.log_event(f"Evento registrado (no 5-75/5-76)")
            
            self.log_event("-" * 60)

        except Exception as e:
            self.log_event(f"Error procesando evento: {e}")
            traceback.print_exc()

    def generate_system_log_entry(self, minor_type, date_time, employee_no, hik_ip):
        """Genera entrada para log de sistema"""
        try:
            if 'T' in date_time:
                date_part, time_part = date_time.split('T')
                date_clean = date_part.replace('-', '')
                time_clean = time_part.split('-')[0].split('+')[0].replace(':', '')
                formatted_datetime = f"{date_clean}T{time_clean}"
            else:
                dt = datetime.now()
                formatted_datetime = dt.strftime("%Y%m%dT%H%M%S")
            
            ip_to_log = hik_ip if hik_ip else "UNKNOWN_IP"

            if minor_type == 75:
                return f"F575-{ip_to_log}-{formatted_datetime}-{employee_no}"
            elif minor_type == 76:
                return f"F576-{ip_to_log}-{formatted_datetime}"
            else:
                return None
                
        except Exception as e:
            self.log_message(f"Error generando log: {e}")
            return None

    def update_stats(self):
        """Actualiza estadisticas"""
        stats_text = f"Dispositivos: {len(self.devices_connected)} | Eventos: {self.total_events_processed} | Activas: {self.active_connections}"
        self.stats_label.config(text=stats_text)

    def get_local_ip(self):
        """Obtiene IP local"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def log_connection(self, message):
        """Log de conexiones"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def log_performance(self, message):
        """Log de rendimiento"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def log_message(self, message):
        """Log de sistema"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def log_event(self, message):
        """Log de eventos"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.event_text.see(tk.END)
        self.root.update_idletasks()

    def log_worker(self, message):
        """Log de worker"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.worker_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.worker_log_text.see(tk.END)
        self.root.update_idletasks()

    def on_closing(self):
        """Cierre de aplicacion (no usado, ahora se usa quit_application)"""
        self.quit_application()

if __name__ == "__main__":
    root = tk.Tk()
    app = HikvisionIntegratedMonitor(root)
    root.mainloop()
