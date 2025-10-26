/* 1) Crear la tabla dbo.cola_comunicacion si no existe */
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE t.name = 'cola_comunicacion' AND s.name = 'dbo'
)
BEGIN
    CREATE TABLE dbo.cola_comunicacion (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        transmision VARCHAR(50) NULL,
        recepcion   VARCHAR(150) NULL,
        FieldName   VARCHAR(30) NULL,
        createdAt   DATETIME NOT NULL DEFAULT (GETDATE())
    );
END
GO

/* 2) Agregar columnas a dbo.mdl solo si no existen */
-- IDENTIFICACION
IF COL_LENGTH('dbo.mdl', 'HikID') IS NULL
    ALTER TABLE dbo.mdl ADD HikID VARCHAR(50) NULL;

-- CONEXION
IF COL_LENGTH('dbo.mdl', 'IP') IS NULL
    ALTER TABLE dbo.mdl ADD HikIP VARCHAR(45) NULL;

IF COL_LENGTH('dbo.mdl', 'Usuario') IS NULL
    ALTER TABLE dbo.mdl ADD HikUsuario VARCHAR(32) NULL;

IF COL_LENGTH('dbo.mdl', 'Password') IS NULL
    ALTER TABLE dbo.mdl ADD [HikPassword] VARCHAR(255) NULL;

-- PUERTOS
IF COL_LENGTH('dbo.mdl', 'PuertoHTTP') IS NULL
    ALTER TABLE dbo.mdl ADD HikPuertoHTTP INT NULL;

IF COL_LENGTH('dbo.mdl', 'PuertoHTTPS') IS NULL
    ALTER TABLE dbo.mdl ADD HikPuertoHTTPS INT NULL;

IF COL_LENGTH('dbo.mdl', 'PuertoRTSP') IS NULL
    ALTER TABLE dbo.mdl ADD HikPuertoRTSP INT NULL;

IF COL_LENGTH('dbo.mdl', 'PuertoSVR') IS NULL
    ALTER TABLE dbo.mdl ADD HikPuertoSVR INT NULL;

-- ESTADO
IF COL_LENGTH('dbo.mdl', 'HikEnable') IS NULL
    ALTER TABLE dbo.mdl ADD HikEnable INT NULL;
GO
