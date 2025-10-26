#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database_connection.py
Modulo para conexion a base de datos SQL Server usando archivo UDL
"""

import pyodbc
from pathlib import Path

class DatabaseManager:
    """Gestor de conexion a base de datos usando archivo UDL"""
    
    def __init__(self, udl_file="videoman.udl"):
        self.udl_file = udl_file
        self.conn = None
        self.connection_string = self.parse_udl_file()

    def parse_udl_file(self):
        """Leer archivo UDL y crear connection string"""
        udl_path = Path(self.udl_file)
        
        if not udl_path.exists():
            self.create_default_udl()
        
        try:
            # Intentar diferentes codificaciones para archivos UDL
            encodings = ['utf-8-sig', 'utf-16', 'latin1', 'cp1252']
            content = None
            
            for encoding in encodings:
                try:
                    with open(udl_path, 'r', encoding=encoding) as file:
                        content = file.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                print("No se pudo leer el archivo UDL con ninguna codificacion")
                return self.get_default_connection_string()
                
            return self.build_connection_string(content)
            
        except Exception as e:
            print(f"Error leyendo UDL: {e}")
            return self.get_default_connection_string()
    
    def build_connection_string(self, udl_content):
        """Construir connection string desde UDL"""
        params = {}
        
        # Buscar la linea que contiene los parametros de conexion
        lines = udl_content.replace('\r\n', '\n').split('\n')
        for line in lines:
            if line.startswith('Provider=') and ';' in line:
                # Esta es la linea de conexion principal
                parts = line.split(';')
                for part in parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        params[key.strip()] = value.strip()
                break
        
        # Extraer parametros especificos del UDL
        server = params.get('Data Source', 'localhost\\SQLEXPRESS')
        database = params.get('Initial Catalog', 'RobleJoven')
        user = params.get('User ID', 'sa')
        password = params.get('Password', 'Oem2017*')
        
        # Crear connection string
        connection_string = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={user};PWD={password};TrustServerCertificate=yes;"
        
        return connection_string

    def get_default_connection_string(self):
        """Connection string por defecto basado en configuracion estandar"""
        return "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=RobleJoven;UID=sa;PWD=Oem2017*;TrustServerCertificate=yes;"
    
    def create_default_udl(self):
        """Crear archivo UDL por defecto"""
        default_udl = """[oledb]
; Everything after this line is an OLE DB initstring
Provider=SQLOLEDB.1;Password=Oem2017*;Persist Security Info=True;User ID=sa;Initial Catalog=RobleJoven;Data Source=localhost\\SQLEXPRESS
"""
        with open(self.udl_file, 'w', encoding='utf-8') as file:
            file.write(default_udl)
    
    def connect(self):
        """Conectar a SQL Server probando diferentes drivers"""
        # Lista de drivers para probar en orden de preferencia
        drivers = [
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 13 for SQL Server", 
            "SQL Server Native Client 11.0",
            "SQL Server"
        ]
        
        # Extraer datos base del connection string
        if "SERVER=" in self.connection_string:
            parts = self.connection_string.split(';')
            server = database = uid = pwd = ""
            
            for part in parts:
                if "SERVER=" in part:
                    server = part.split('=')[1]
                elif "DATABASE=" in part:
                    database = part.split('=')[1]
                elif "UID=" in part:
                    uid = part.split('=')[1]
                elif "PWD=" in part:
                    pwd = part.split('=')[1]
        else:
            # Valores por defecto
            server = "localhost\\SQLEXPRESS"
            database = "RobleJoven"
            uid = "sa"
            pwd = "Oem2017*"
        
        print(f"Intentando conectar a {server}\\{database}...")
        
        # Probar cada driver hasta que uno funcione
        for driver in drivers:
            try:
                conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate=yes;"
                print(f"Probando driver: {driver}")
                
                self.conn = pyodbc.connect(conn_str, timeout=10)
                print(f"Conexion exitosa con {driver}")
                return self.conn
                
            except pyodbc.Error as e:
                print(f"Error con {driver}: {str(e)[:100]}...")
                continue
            except Exception as e:
                print(f"Error general con {driver}: {str(e)[:100]}...")
                continue
        
        # Si todos los drivers fallan
        print("No se pudo conectar con ningun driver disponible")
        return None
    
    def disconnect(self):
        """Desconectar base de datos"""
        if self.conn:
            try:
                self.conn.close()
                print("Conexion a base de datos cerrada")
            except Exception as e:
                print(f"Error cerrando conexion: {e}")
            finally:
                self.conn = None
    
    def execute_query(self, query, params=None):
        """Ejecutar consulta SELECT y retornar resultados"""
        try:
            if not self.conn:
                print("No hay conexion activa a la base de datos")
                return []
                
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            results = cursor.fetchall()
            cursor.close()
            return results
            
        except Exception as e:
            print(f"Error en consulta: {e}")
            return []
    
    def execute_command(self, command, params=None):
        """Ejecutar comando INSERT/UPDATE/DELETE y retornar filas afectadas"""
        try:
            if not self.conn:
                print("No hay conexion activa a la base de datos")
                return 0
                
            cursor = self.conn.cursor()
            if params:
                cursor.execute(command, params)
            else:
                cursor.execute(command)
            
            rows_affected = cursor.rowcount
            self.conn.commit()
            cursor.close()
            return rows_affected
            
        except Exception as e:
            print(f"Error en comando: {e}")
            try:
                self.conn.rollback()
            except:
                pass
            return 0
    
    def get_connection(self):
        """Obtener conexion directa para transacciones manuales"""
        return self.conn
    
    def test_connection(self):
        """Probar conexion a la base de datos"""
        try:
            test_query = "SELECT 1 AS test"
            result = self.execute_query(test_query)
            return len(result) > 0 and result[0][0] == 1
        except Exception as e:
            print(f"Error probando conexion: {e}")
            return False
