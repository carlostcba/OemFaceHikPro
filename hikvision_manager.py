#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hikvision_manager.py
Modulo para comunicacion con dispositivos Hikvision AccessControl
Maneja todas las operaciones ISAPI del dispositivo
"""

import requests
import json
from requests.auth import HTTPDigestAuth
import urllib3
import os
from datetime import datetime, timedelta

# Deshabilitar warnings SSL para dispositivos locales
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HikvisionManager:
    """Gestor de comunicacion con dispositivos Hikvision AccessControl"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.device_ip = ""
        self.device_user = ""
        self.device_password = ""
        self.session = None
        self.fdid = '1'  # ID biblioteca facial por defecto
        self.is_connected = False
        
    def load_device_config_from_db(self):
        """Cargar configuracion del dispositivo desde la base de datos"""
        try:
            sql = """
                SELECT TOP 1 IP, Usuario, Password 
                FROM hikvision 
                WHERE Tipo = 'AccessControl' AND Activo = 1
                ORDER BY ID
            """
            device_records = self.db_manager.execute_query(sql)
            
            if device_records:
                self.device_ip = device_records[0][0].strip()
                self.device_user = device_records[0][1].strip()
                self.device_password = device_records[0][2].strip()
                print(f"Configuracion cargada: {self.device_ip} - Usuario: {self.device_user}")
                return True
            else:
                print("No se encontro dispositivo AccessControl configurado en BD")
                return False
                
        except Exception as e:
            print(f"Error cargando configuracion del dispositivo: {e}")
            return False
    
    def set_device_config_manual(self, ip, user, password):
        """Configurar dispositivo manualmente (sin BD)"""
        self.device_ip = ip.strip()
        self.device_user = user.strip()
        self.device_password = password.strip()
        print(f"Configuracion manual: {self.device_ip} - Usuario: {self.device_user}")
        return True
    
    def create_session(self):
        """Crear sesion HTTP con autenticacion digest"""
        try:
            if not self.device_ip or not self.device_user or not self.device_password:
                print("Configuracion de dispositivo incompleta")
                return None
                
            session = requests.Session()
            session.auth = HTTPDigestAuth(self.device_user, self.device_password)
            session.headers.update({
                'User-Agent': 'Hikvision CRUD Client v1.0',
                'Accept': 'application/xml, application/json',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache'
            })
            session.verify = False
            
            print("Sesion HTTP creada correctamente")
            return session
            
        except Exception as e:
            print(f"Error creando sesion HTTP: {e}")
            return None
    
    def test_connection(self):
        """Probar conexion con el dispositivo"""
        try:
            print(f"Probando conexion con {self.device_ip}...")
            
            self.session = self.create_session()
            if not self.session:
                return False, "No se pudo crear sesion HTTP"
                
            url = f"http://{self.device_ip}/ISAPI/System/deviceInfo"
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                print("Conexion exitosa con dispositivo")
                self.is_connected = True
                
                # Intentar obtener informacion del dispositivo
                try:
                    device_info = self._parse_device_info(response.text)
                    return True, f"Conectado exitosamente. {device_info}"
                except:
                    return True, "Conectado exitosamente"
            else:
                error_msg = f"Error HTTP {response.status_code}"
                print(f"Error de conexion: {error_msg}")
                self.is_connected = False
                return False, error_msg
                
        except requests.exceptions.Timeout:
            error_msg = "Timeout de conexion (15s)"
            print(f"Error: {error_msg}")
            self.is_connected = False
            return False, error_msg
        except requests.exceptions.ConnectionError:
            error_msg = "No se pudo conectar al dispositivo"
            print(f"Error: {error_msg}")
            self.is_connected = False
            return False, error_msg
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            print(f"Error: {error_msg}")
            self.is_connected = False
            return False, error_msg
    
    def _parse_device_info(self, xml_response):
        """Extraer informacion basica del dispositivo desde XML"""
        try:
            # Buscar informacion basica en el XML
            if "<deviceName>" in xml_response:
                start = xml_response.find("<deviceName>") + 12
                end = xml_response.find("</deviceName>")
                device_name = xml_response[start:end]
                return f"Dispositivo: {device_name}"
            return "Informacion del dispositivo obtenida"
        except:
            return "Dispositivo conectado"
    
    def ensure_face_library_exists(self):
        """Verificar y crear biblioteca facial si no existe"""
        try:
            if not self.session:
                return False, "No hay sesion activa"
            
            print("Verificando biblioteca facial...")
            
            url = f"http://{self.device_ip}/ISAPI/Intelligent/FDLib?format=json"
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                libraries = data.get('FPLibListInfo', {}).get('FPLib', [])
                
                # Buscar biblioteca blackFD
                for lib in libraries:
                    if lib.get('faceLibType') == 'blackFD':
                        self.fdid = lib.get('FDID', '1')
                        print(f"Biblioteca facial encontrada: ID {self.fdid}")
                        return True, f"Biblioteca facial activa (ID: {self.fdid})"
            
            # Si no existe, crear biblioteca por defecto
            print("Creando biblioteca facial por defecto...")
            create_data = {
                "FPLibInfo": {
                    "faceLibType": "blackFD",
                    "name": "Default Face Library",
                    "customInfo": "Biblioteca creada por aplicacion CRUD",
                    "libArmingType": "armingLib",
                    "libAttribute": "blackList"
                }
            }
            
            response = self.session.post(url, json=create_data, timeout=15)
            if response.status_code in [200, 201]:
                result = response.json()
                self.fdid = result.get('FPLibInfo', {}).get('FDID', '1')
                print(f"Biblioteca facial creada: ID {self.fdid}")
                return True, f"Biblioteca facial creada (ID: {self.fdid})"
            else:
                self.fdid = '1'
                print("Usando biblioteca por defecto ID=1")
                return True, "Usando biblioteca facial por defecto"
                
        except Exception as e:
            print(f"Error con biblioteca facial: {e}")
            self.fdid = '1'
            return True, "Usando biblioteca facial por defecto"
    
    def user_exists_in_device(self, employee_id):
        """Verificar si un usuario existe en el dispositivo"""
        try:
            if not self.session:
                self.session = self.create_session()
                
            url = f"http://{self.device_ip}/ISAPI/AccessControl/UserInfo/Search?format=json"
            search_data = {
                "UserInfoSearchCond": {
                    "searchID": "1",
                    "maxResults": 1000,
                    "searchResultPosition": 0,
                    "EmployeeNoList": [{"employeeNo": str(employee_id)}]
                }
            }
            
            response = self.session.post(url, json=search_data, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('UserInfoSearch', {}).get('UserInfo', [])
                exists = len(users) > 0
                print(f"Usuario {employee_id}: {'EXISTE' if exists else 'NO EXISTE'} en dispositivo")
                return exists
            else:
                print(f"Error verificando usuario: HTTP {response.status_code}")
                return False
            
        except Exception as e:
            print(f"Error verificando usuario en dispositivo: {e}")
            return False
    
    def create_or_update_user_in_device(self, employee_id, name, enabled=True, start_date=None, end_date=None, image_path=None):
        """Crear o actualizar usuario en dispositivo Hikvision"""
        try:
            if not self.session:
                self.session = self.create_session()
                if not self.session:
                    return False, "No se pudo crear sesion"
                
            # Configurar fechas por defecto
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            if not end_date:
                end_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
                
            user_exists = self.user_exists_in_device(employee_id)
            
            user_data = {
                "UserInfo": {
                    "employeeNo": str(employee_id),
                    "name": name,
                    "userType": "normal",
                    "Valid": {
                        "enable": enabled,
                        "beginTime": f"{start_date}T00:00:00",
                        "endTime": f"{end_date}T23:59:59"
                    },
                    "doorRight": "1",
                    "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}],
                    "maxFingerPrintNum": 0,
                    "maxFaceNum": 1
                }
            }
            
            if user_exists:
                # Actualizar usuario existente
                print(f"Actualizando usuario existente: {name} (ID: {employee_id})")
                url = f"http://{self.device_ip}/ISAPI/AccessControl/UserInfo/Modify?format=json"
                response = self.session.put(url, json=user_data, timeout=30)
                operation = "actualizado"
            else:
                # Crear nuevo usuario
                print(f"Creando nuevo usuario: {name} (ID: {employee_id})")
                url = f"http://{self.device_ip}/ISAPI/AccessControl/UserInfo/Record?format=json"
                response = self.session.post(url, json=user_data, timeout=30)
                operation = "creado"
            
            if response.status_code in [200, 201]:
                print(f"Usuario {operation} exitosamente en dispositivo")
                
                # Si hay imagen, subirla
                if image_path and os.path.exists(image_path):
                    image_success, image_msg = self.upload_face_image(employee_id, name, image_path)
                    if image_success:
                        return True, f"Usuario {operation} con imagen facial exitosamente"
                    else:
                        return True, f"Usuario {operation} pero fallo la imagen: {image_msg}"
                else:
                    return True, f"Usuario {operation} exitosamente (sin imagen)"
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text[:200]}"
                print(f"Error en operacion de usuario: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error creando/actualizando usuario: {str(e)}"
            print(error_msg)
            return False, error_msg
    
    def upload_face_image(self, employee_id, name, image_path):
        """Subir imagen facial al dispositivo usando multipart form"""
        try:
            if not os.path.exists(image_path):
                return False, "Archivo de imagen no encontrado"
                
            # Verificar tamaño de archivo
            file_size = os.path.getsize(image_path)
            if file_size > 500 * 1024:  # 500KB limite
                print(f"Advertencia: Imagen grande ({file_size/1024:.1f}KB)")
            
            print(f"Subiendo imagen facial para usuario {employee_id}...")
            
            url = f"http://{self.device_ip}/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json"
            
            # Preparar metadata JSON
            face_data = {
                "faceLibType": "blackFD",
                "FDID": self.fdid,
                "FPID": str(employee_id),
                "name": name
            }
            
            # Leer archivo de imagen
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
            
            # Crear boundary para multipart
            boundary = '---------------------------7e13971310878'
            
            # Construir multipart body segun documentacion ISAPI
            body_parts = []
            
            # Parte 1: Metadata JSON
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="FaceDataRecord"')
            body_parts.append('Content-Type: application/json')
            body_parts.append('')
            body_parts.append(json.dumps(face_data))
            
            # Parte 2: Imagen
            body_parts.append(f'--{boundary}')
            body_parts.append('Content-Disposition: form-data; name="FaceImage"')
            body_parts.append('Content-Type: image/jpeg')
            body_parts.append('')
            
            # Unir partes de texto
            body_text = '\r\n'.join(body_parts) + '\r\n'
            
            # Crear body completo: texto + imagen + cierre
            body_bytes = body_text.encode('utf-8') + image_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')
            
            headers = {
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(body_bytes))
            }
            
            response = self.session.post(url, data=body_bytes, headers=headers, timeout=45)
            
            if response.status_code in [200, 201]:
                print("Imagen facial subida exitosamente")
                return True, "Imagen facial cargada correctamente"
            else:
                error_msg = f"Error HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'statusString' in error_data:
                        error_msg += f": {error_data['statusString']}"
                except:
                    error_msg += f": {response.text[:100]}"
                
                print(f"Error subiendo imagen: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error subiendo imagen facial: {str(e)}"
            print(error_msg)
            return False, error_msg
    
    def delete_user_from_device(self, employee_id):
        """Eliminar usuario del dispositivo"""
        try:
            if not self.session:
                self.session = self.create_session()
                if not self.session:
                    return False, "No se pudo crear sesion"
                
            print(f"Eliminando usuario {employee_id} del dispositivo...")
            
            url = f"http://{self.device_ip}/ISAPI/AccessControl/UserInfo/Delete?format=json"
            
            # Estructura correcta segun documentacion ISAPI
            delete_data = {
                "UserInfoDelCond": {
                    "EmployeeNoList": [{
                        "employeeNo": str(employee_id)
                    }]
                }
            }
            
            response = self.session.put(url, json=delete_data, timeout=30)
            
            if response.status_code in [200, 201]:
                print(f"Usuario {employee_id} eliminado exitosamente del dispositivo")
                return True, "Usuario eliminado del dispositivo correctamente"
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text[:200]}"
                print(f"Error eliminando usuario: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error eliminando usuario del dispositivo: {str(e)}"
            print(error_msg)
            return False, error_msg
    
    def list_all_users(self, max_results=100):
        """Listar todos los usuarios en el dispositivo"""
        try:
            if not self.session:
                self.session = self.create_session()
                if not self.session:
                    return False, "No se pudo crear sesion", []
                
            print(f"Obteniendo lista de usuarios (max: {max_results})...")
            
            url = f"http://{self.device_ip}/ISAPI/AccessControl/UserInfo/Search?format=json"
            search_data = {
                "UserInfoSearchCond": {
                    "searchID": "1",
                    "maxResults": max_results,
                    "searchResultPosition": 0
                }
            }
            
            response = self.session.post(url, json=search_data, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('UserInfoSearch', {}).get('UserInfo', [])
                
                # Procesar lista de usuarios
                user_list = []
                for user in users:
                    user_info = {
                        'employee_id': user.get('employeeNo', 'Sin ID'),
                        'name': user.get('name', 'Sin nombre'),
                        'enabled': user.get('Valid', {}).get('enable', False),
                        'begin_time': user.get('Valid', {}).get('beginTime', ''),
                        'end_time': user.get('Valid', {}).get('endTime', ''),
                        'user_type': user.get('userType', 'normal')
                    }
                    user_list.append(user_info)
                
                print(f"Se obtuvieron {len(user_list)} usuarios del dispositivo")
                return True, f"Se encontraron {len(user_list)} usuarios", user_list
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text[:200]}"
                print(f"Error listando usuarios: {error_msg}")
                return False, error_msg, []
                
        except Exception as e:
            error_msg = f"Error listando usuarios del dispositivo: {str(e)}"
            print(error_msg)
            return False, error_msg, []
    
    def get_device_status(self):
        """Obtener estado general del dispositivo"""
        try:
            if not self.session:
                self.session = self.create_session()
                if not self.session:
                    return False, "No hay sesion activa", {}
                
            # Obtener informacion del dispositivo
            url = f"http://{self.device_ip}/ISAPI/System/deviceInfo"
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                # Obtener capacidades del sistema
                capabilities_url = f"http://{self.device_ip}/ISAPI/System/capabilities"
                
                status_info = {
                    'ip': self.device_ip,
                    'connected': True,
                    'device_info': 'Conectado y operativo',
                    'face_library_id': self.fdid
                }
                
                return True, "Dispositivo operativo", status_info
            else:
                return False, f"Error de estado: HTTP {response.status_code}", {}
                
        except Exception as e:
            error_msg = f"Error obteniendo estado del dispositivo: {str(e)}"
            print(error_msg)
            return False, error_msg, {}
    
    def cleanup_session(self):
        """Limpiar sesion HTTP"""
        try:
            if self.session:
                self.session.close()
                self.session = None
                self.is_connected = False
                print("Sesion HTTP cerrada")
        except Exception as e:
            print(f"Error cerrando sesion: {e}")
    
    def get_face_library_info(self):
        """Obtener informacion de las bibliotecas faciales"""
        try:
            if not self.session:
                return False, "No hay sesion activa", []
                
            url = f"http://{self.device_ip}/ISAPI/Intelligent/FDLib?format=json"
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                libraries = data.get('FPLibListInfo', {}).get('FPLib', [])
                
                lib_info = []
                for lib in libraries:
                    info = {
                        'id': lib.get('FDID', ''),
                        'name': lib.get('name', ''),
                        'type': lib.get('faceLibType', ''),
                        'size': lib.get('size', 0),
                        'attribute': lib.get('libAttribute', '')
                    }
                    lib_info.append(info)
                
                return True, f"Se encontraron {len(lib_info)} bibliotecas", lib_info
            else:
                return False, f"Error HTTP {response.status_code}", []
                
        except Exception as e:
            return False, f"Error obteniendo bibliotecas: {str(e)}", []
                