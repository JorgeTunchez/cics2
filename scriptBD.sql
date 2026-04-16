/* =========================================
   TABLA: archivos
   ========================================= */
IF OBJECT_ID('dbo.cics_archivos', 'U') IS NOT NULL
    DROP TABLE dbo.cics_archivos;
GO

CREATE TABLE dbo.cics_archivos
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo NVARCHAR(255) NOT NULL
);
GO

CREATE UNIQUE INDEX UX_archivos_archivo
ON dbo.archivos(archivo);
GO


/* =========================================
   TABLA: segmento
   ========================================= */
IF OBJECT_ID('dbo.cics_segmento', 'U') IS NOT NULL
    DROP TABLE dbo.segmento;
GO

CREATE TABLE dbo.cics_segmento
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    segmento NVARCHAR(255) NOT NULL
);
GO

CREATE UNIQUE INDEX UX_segmento_segmento
ON dbo.cics_segmento(segmento);
GO


/* =========================================
   TABLA: programs
   ========================================= */
IF OBJECT_ID('dbo.cics_programs', 'U') IS NOT NULL
    DROP TABLE dbo.cics_programs;
GO

CREATE TABLE dbo.cics_programs
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    programName NVARCHAR(100) NULL,
    dataLocExecKey NVARCHAR(50) NULL,
    timesUsed INT NULL,
    timesFetched INT NULL,
    totalFecthTime NVARCHAR(50) NULL,
    AverageFetchTime NVARCHAR(50) NULL,
    libraryName NVARCHAR(100) NULL,
    libraryOffset INT NULL,
    timesNewCopy INT NULL,
    timesRemoved INT NULL,
    programSize INT NULL,
    progLocn NVARCHAR(50) NULL
);
GO

CREATE INDEX IX_programs_archivo_fecha
ON dbo.cics_programs(archivo, fecha);
GO

CREATE INDEX IX_programs_programName
ON dbo.cics_programs(programName);
GO

CREATE UNIQUE INDEX UX_programs_archivo_fecha_programName
ON dbo.cics_programs(archivo, fecha, programName);
GO


/* =========================================
   TABLA: transactions
   ========================================= */
IF OBJECT_ID('dbo.cics_transactions', 'U') IS NOT NULL
    DROP TABLE dbo.cics_transactions;
GO

CREATE TABLE dbo.cics_transactions
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,

    tranId NVARCHAR(50) NULL,
    tranClass NVARCHAR(50) NULL,
    programName NVARCHAR(255) NULL,
    dynamic NVARCHAR(50) NULL,
    isolate NVARCHAR(50) NULL,
    taskDataLocationKey NVARCHAR(255) NULL,
    attachCount INT NULL,
    restartCount INT NULL,
    dynamicLocal INT NULL,
    remoteStarts INT NULL,
    storageViols INT NULL,
    abendCount INT NULL
);
GO

CREATE INDEX IX_transactions_archivo_fecha
ON dbo.cics_transactions(archivo, fecha);
GO

CREATE INDEX IX_transactions_tranId
ON dbo.cics_transactions(tranId);
GO

CREATE INDEX IX_transactions_programName
ON dbo.cics_transactions(programName);
GO

CREATE UNIQUE INDEX UX_transactions_archivo_fecha_tranId
ON dbo.cics_transactions(archivo, fecha, tranId);
GO


/* =========================================
   FOREIGN KEYS (opcional)
   ========================================= */
ALTER TABLE dbo.cics_programs
ADD CONSTRAINT FK_programs_archivos
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO

ALTER TABLE dbo.cics_transactions
ADD CONSTRAINT FK_transactions_archivos
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO



/* =========================================
   TABLA: cics_temporary_storage_queues
   ========================================= */


IF OBJECT_ID('dbo.cics_temporary_storage_queues', 'U') IS NOT NULL
    DROP TABLE dbo.cics_temporary_storage_queues;
GO

CREATE TABLE dbo.cics_temporary_storage_queues
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    tsQueueName NVARCHAR(100) NULL,
    tsqueueLocation NVARCHAR(50) NULL,
    numberOfItems INT NULL,
    minItemLength INT NULL,
    maxItemLength INT NULL,
    tsqueueFlength INT NULL,
    tranId NVARCHAR(50) NULL,
    lastusedInterval NVARCHAR(50) NULL,
    recoverable NVARCHAR(20) NULL,
    expiryInterval NVARCHAR(50) NULL
);
GO

CREATE INDEX IX_cics_temporary_storage_queues_archivo_fecha
ON dbo.cics_temporary_storage_queues(archivo, fecha);
GO

CREATE INDEX IX_cics_temporary_storage_queues_tsQueueName
ON dbo.cics_temporary_storage_queues(tsQueueName);
GO

ALTER TABLE dbo.cics_temporary_storage_queues
ADD CONSTRAINT FK_cics_temporary_storage_queues_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO


IF OBJECT_ID('dbo.cics_files', 'U') IS NOT NULL
    DROP TABLE dbo.cics_files;
GO

CREATE TABLE dbo.cics_files
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    fileName NVARCHAR(150) NULL,
    accessMethod NVARCHAR(50) NULL,
    fileType NVARCHAR(50) NULL,
    remoteFileName NVARCHAR(150) NULL,
    remoteSystem NVARCHAR(100) NULL,
    lsrPool NVARCHAR(50) NULL,
    rls NVARCHAR(20) NULL,
    dataTableType NVARCHAR(50) NULL,
    cfdtPoolName NVARCHAR(100) NULL,
    recoveryStatus NVARCHAR(50) NULL,
    strings INT NULL,
    buffersIndex INT NULL,
    buffersData INT NULL
);


GO


CREATE INDEX IX_cics_files_archivo_fecha
ON dbo.cics_files(archivo, fecha);
GO

CREATE INDEX IX_cics_files_fileName
ON dbo.cics_files(fileName);
GO

ALTER TABLE dbo.cics_files
ADD CONSTRAINT FK_cics_files_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO
