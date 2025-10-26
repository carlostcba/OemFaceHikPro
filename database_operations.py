#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
database_operations.py
Modulo para operaciones CRUD especificas de rostros faciales en la base de datos
"""

import io
from PIL import Image

class FacialDatabaseOperations:
    """Operaciones especificas para gestion de rostros faciales en BD"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def search_persons(self, filter_text):
        """Buscar personas por nombre o apellido"""
        try:
            sql = """
                SELECT PersonaID, Nombre, Apellido 
                FROM dbo.per 
                WHERE Nombre LIKE ? OR Apellido LIKE ?
                ORDER BY Nombre, Apellido
            """
            filter_param = f"%{filter_text}%"
            return self.db_manager.execute_query(sql, (filter_param, filter_param))
        except Exception as e:
            print(f"Error buscando personas: {e}")
            return []
    
    def get_person_facial_data(self, persona_id):
        """Obtener datos faciales de una persona especifica"""
        try:
            sql = """
                SELECT f.FacialID, f.Activo, f.TemplateData 
                FROM face f 
                INNER JOIN perface pf ON f.FacialID = pf.FacialID 
                WHERE pf.PersonaID = ?
            """
            result = self.db_manager.execute_query(sql, (persona_id,))
            
            if result:
                return {
                    'facial_id': result[0][0],
                    'activo': bool(result[0][1]),
                    'template_data': result[0][2]
                }
            return None
        except Exception as e:
            print(f"Error obteniendo datos faciales: {e}")
            return None
    
    def facial_exists_for_person(self, persona_id):
        """Verificar si una persona ya tiene rostro facial asignado"""
        try:
            sql = "SELECT FacialID FROM perface WHERE PersonaID = ?"
            result = self.db_manager.execute_query(sql, (persona_id,))
            return len(result) > 0, result[0][0] if result else None
        except Exception as e:
            print(f"Error verificando rostro existente: {e}")
            return False, None
    
    def get_next_facial_id(self):
        """Obtener el siguiente ID facial disponible"""
        try:
            sql = "SELECT ISNULL(MAX(FacialID), 0) + 1 AS NuevoID FROM dbo.face"
            result = self.db_manager.execute_query(sql)
            return result[0][0] if result else 1
        except Exception as e:
            print(f"Error obteniendo siguiente ID facial: {e}")
            return 1
    
    def create_facial_record(self, persona_id, image_bytes, activo=True):
        """Crear nuevo registro facial completo"""
        conn = self.db_manager.get_connection()
        if not conn:
            return False, "No hay conexion a la base de datos"
        
        cursor = conn.cursor()
        
        try:
            # Verificar si ya existe rostro para esta persona
            exists, existing_id = self.facial_exists_for_person(persona_id)
            if exists:
                return False, f"La persona ya tiene un rostro asignado (ID: {existing_id})"
            
            # Obtener nuevo FacialID
            facial_id = self.get_next_facial_id()
            
            # Iniciar transaccion
            cursor.execute("BEGIN TRANSACTION")
            
            # 1. Insertar registro en face
            cursor.execute(
                "INSERT INTO face (FacialID, TemplateData, Activo) VALUES (?, ?, ?)",
                (facial_id, image_bytes, 1 if activo else 0)
            )
            
            # 2. Insertar en perface (relacion persona-rostro)
            cursor.execute(
                "INSERT INTO perface (PersonaID, FacialID) VALUES (?, ?)",
                (persona_id, facial_id)
            )
            
            # 3. Insertar categorias fijas en facecatval
            cursor.execute(
                "INSERT INTO facecatval (FacialID, CategoriaID, ValorID) VALUES (?, 3, 7)",
                (facial_id,)
            )
            cursor.execute(
                "INSERT INTO facecatval (FacialID, CategoriaID, ValorID) VALUES (?, 16, 1)",
                (facial_id,)
            )
            
            # Confirmar transaccion
            cursor.execute("COMMIT TRANSACTION")
            cursor.close()
            
            return True, facial_id
            
        except Exception as e:
            try:
                cursor.execute("ROLLBACK TRANSACTION")
            except:
                pass
            cursor.close()
            return False, f"Error creando registro facial: {str(e)}"
    
    def update_facial_record(self, facial_id, image_bytes, activo=True):
        """Actualizar registro facial existente"""
        conn = self.db_manager.get_connection()
        if not conn:
            return False, "No hay conexion a la base de datos"
        
        cursor = conn.cursor()
        
        try:
            # Iniciar transaccion
            cursor.execute("BEGIN TRANSACTION")
            
            # 1. Actualizar tabla face
            cursor.execute(
                "UPDATE face SET TemplateData = ?, Activo = ? WHERE FacialID = ?",
                (image_bytes, 1 if activo else 0, facial_id)
            )
            
            # 2. Actualizar facecatval (eliminar y reinsertar valores fijos)
            cursor.execute("DELETE FROM facecatval WHERE FacialID = ?", (facial_id,))
            cursor.execute(
                "INSERT INTO facecatval (FacialID, CategoriaID, ValorID) VALUES (?, 3, 7)",
                (facial_id,)
            )
            cursor.execute(
                "INSERT INTO facecatval (FacialID, CategoriaID, ValorID) VALUES (?, 16, 1)",
                (facial_id,)
            )
            
            # Confirmar transaccion
            cursor.execute("COMMIT TRANSACTION")
            cursor.close()
            
            return True, "Registro actualizado correctamente"
            
        except Exception as e:
            try:
                cursor.execute("ROLLBACK TRANSACTION")
            except:
                pass
            cursor.close()
            return False, f"Error actualizando registro facial: {str(e)}"
    
    def delete_facial_record(self, facial_id):
        """Eliminar registro facial completo"""
        conn = self.db_manager.get_connection()
        if not conn:
            return False, "No hay conexion a la base de datos"
        
        cursor = conn.cursor()
        
        try:
            # Verificar que el registro existe
            cursor.execute("SELECT COUNT(*) FROM face WHERE FacialID = ?", (facial_id,))
            if cursor.fetchone()[0] == 0:
                cursor.close()
                return False, "El registro facial no existe"
            
            # Iniciar transaccion
            cursor.execute("BEGIN TRANSACTION")
            
            # Eliminar en orden inverso por integridad referencial
            cursor.execute("DELETE FROM facecatval WHERE FacialID = ?", (facial_id,))
            cursor.execute("DELETE FROM perface WHERE FacialID = ?", (facial_id,))
            cursor.execute("DELETE FROM face WHERE FacialID = ?", (facial_id,))
            
            # Confirmar transaccion
            cursor.execute("COMMIT TRANSACTION")
            cursor.close()
            
            return True, "Registro eliminado correctamente"
            
        except Exception as e:
            try:
                cursor.execute("ROLLBACK TRANSACTION")
            except:
                pass
            cursor.close()
            return False, f"Error eliminando registro facial: {str(e)}"
    
    def get_facial_record_with_person_info(self, facial_id):
        """Obtener informacion completa del registro facial incluyendo datos de persona"""
        try:
            sql = """
                SELECT 
                    f.FacialID,
                    f.Activo,
                    f.TemplateData,
                    p.PersonaID,
                    p.Nombre,
                    p.Apellido
                FROM face f 
                INNER JOIN perface pf ON f.FacialID = pf.FacialID 
                INNER JOIN per p ON pf.PersonaID = p.PersonaID 
                WHERE f.FacialID = ?
            """
            result = self.db_manager.execute_query(sql, (facial_id,))
            
            if result:
                row = result[0]
                return {
                    'facial_id': row[0],
                    'activo': bool(row[1]),
                    'template_data': row[2],
                    'persona_id': row[3],
                    'nombre': row[4],
                    'apellido': row[5]
                }
            return None
        except Exception as e:
            print(f"Error obteniendo informacion completa: {e}")
            return None
    
    def validate_image_data(self, image_bytes):
        """Validar que los datos de imagen son validos"""
        try:
            # Intentar abrir la imagen para validar
            image_stream = io.BytesIO(image_bytes)
            image = Image.open(image_stream)
            
            # Verificar formato
            if image.format not in ['JPEG', 'JPG']:
                return False, "La imagen debe estar en formato JPG"
            
            # Verificar tamaño
            width, height = image.size
            if width < 100 or height < 100:
                return False, "La imagen es demasiado pequeña (minimo 100x100)"
            
            if width > 2000 or height > 2000:
                return False, "La imagen es demasiado grande (maximo 2000x2000)"
            
            # Verificar tamaño de archivo (200KB max recomendado)
            size_kb = len(image_bytes) / 1024
            if size_kb > 500:
                return False, f"Imagen muy grande ({size_kb:.1f}KB, maximo recomendado: 500KB)"
            
            return True, "Imagen valida"
            
        except Exception as e:
            return False, f"Error validando imagen: {str(e)}"
    
    def get_all_facial_records(self, limit=100):
        """Obtener lista de todos los registros faciales con informacion basica"""
        try:
            sql = """
                SELECT TOP (?) 
                    f.FacialID,
                    p.PersonaID,
                    p.Nombre,
                    p.Apellido,
                    f.Activo
                FROM face f 
                INNER JOIN perface pf ON f.FacialID = pf.FacialID 
                INNER JOIN per p ON pf.PersonaID = p.PersonaID 
                ORDER BY f.FacialID DESC
            """
            return self.db_manager.execute_query(sql, (limit,))
        except Exception as e:
            print(f"Error obteniendo lista de registros: {e}")
            return []
    
    def get_facial_statistics(self):
        """Obtener estadisticas de registros faciales"""
        try:
            stats = {}
            
            # Total de registros
            result = self.db_manager.execute_query("SELECT COUNT(*) FROM face")
            stats['total_registros'] = result[0][0] if result else 0
            
            # Registros activos
            result = self.db_manager.execute_query("SELECT COUNT(*) FROM face WHERE Activo = 1")
            stats['registros_activos'] = result[0][0] if result else 0
            
            # Registros inactivos
            result = self.db_manager.execute_query("SELECT COUNT(*) FROM face WHERE Activo = 0")
            stats['registros_inactivos'] = result[0][0] if result else 0
            
            # Personas con rostro asignado
            result = self.db_manager.execute_query("SELECT COUNT(DISTINCT PersonaID) FROM perface")
            stats['personas_con_rostro'] = result[0][0] if result else 0
            
            # Total de personas
            result = self.db_manager.execute_query("SELECT COUNT(*) FROM per")
            stats['total_personas'] = result[0][0] if result else 0
            
            return stats
        except Exception as e:
            print(f"Error obteniendo estadisticas: {e}")
            return {}
