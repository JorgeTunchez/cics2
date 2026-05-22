/* =========================================
   LIMPIEZA EN ORDEN DE DEPENDENCIAS
   ========================================= */
IF OBJECT_ID('dbo.cics_dumps', 'U') IS NOT NULL
    DROP TABLE dbo.cics_dumps;
GO

IF OBJECT_ID('dbo.cics_trace_status', 'U') IS NOT NULL
    DROP TABLE dbo.cics_trace_status;
GO

IF OBJECT_ID('dbo.cics_statistics', 'U') IS NOT NULL
    DROP TABLE dbo.cics_statistics;
GO

IF OBJECT_ID('dbo.cics_monitoring', 'U') IS NOT NULL
    DROP TABLE dbo.cics_monitoring;
GO

IF OBJECT_ID('dbo.cics_system_status', 'U') IS NOT NULL
    DROP TABLE dbo.cics_system_status;
GO

IF OBJECT_ID('dbo.cics_storage_program_subpool', 'U') IS NOT NULL
    DROP TABLE dbo.cics_storage_program_subpool;
GO

IF OBJECT_ID('dbo.cics_transaction_manager', 'U') IS NOT NULL
    DROP TABLE dbo.cics_transaction_manager;
GO

IF OBJECT_ID('dbo.cics_storage_domain_subpool', 'U') IS NOT NULL
    DROP TABLE dbo.cics_storage_domain_subpool;
GO

IF OBJECT_ID('dbo.cics_files', 'U') IS NOT NULL
    DROP TABLE dbo.cics_files;
GO

IF OBJECT_ID('dbo.cics_temporary_storage_queues', 'U') IS NOT NULL
    DROP TABLE dbo.cics_temporary_storage_queues;
GO

IF OBJECT_ID('dbo.cics_transactions', 'U') IS NOT NULL
    DROP TABLE dbo.cics_transactions;
GO

IF OBJECT_ID('dbo.cics_programs', 'U') IS NOT NULL
    DROP TABLE dbo.cics_programs;
GO

IF OBJECT_ID('dbo.cics_cargas', 'U') IS NOT NULL
    DROP TABLE dbo.cics_cargas;
GO

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
ON dbo.cics_archivos(archivo);
GO


/* =========================================
   TABLA: segmento
   ========================================= */
IF OBJECT_ID('dbo.cics_segmento', 'U') IS NOT NULL
    DROP TABLE dbo.cics_segmento;
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


/* =========================================
   TABLA: cics_storage_domain_subpool
   ========================================= */
IF OBJECT_ID('dbo.cics_storage_domain_subpool', 'U') IS NOT NULL
    DROP TABLE dbo.cics_storage_domain_subpool;
GO

CREATE TABLE dbo.cics_storage_domain_subpool
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    subPoolName NVARCHAR(100) NOT NULL,
    location NVARCHAR(50) NULL,
    access NVARCHAR(50) NULL,
    elementType NVARCHAR(50) NULL,
    elementLength INT NULL,
    initialFree NVARCHAR(30) NULL,
    currentElements INT NULL,
    currentElementStg INT NULL,
    currentPageStg NVARCHAR(30) NULL,
    percentOfDSA DECIMAL(10,2) NULL,
    peakPageStg NVARCHAR(30) NULL
);
GO

CREATE INDEX IX_cics_storage_domain_subpool_archivo_fecha
ON dbo.cics_storage_domain_subpool(archivo, fecha);
GO

CREATE INDEX IX_cics_storage_domain_subpool_subPoolName
ON dbo.cics_storage_domain_subpool(subPoolName);
GO

CREATE UNIQUE INDEX UX_cics_storage_domain_subpool_archivo_fecha_subPoolName
ON dbo.cics_storage_domain_subpool(archivo, fecha, subPoolName, location, access);
GO

ALTER TABLE dbo.cics_storage_domain_subpool
ADD CONSTRAINT FK_cics_storage_domain_subpool_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO


/* =========================================
   TABLA: cics_storage_program_subpool
   ========================================= */
IF OBJECT_ID('dbo.cics_storage_program_subpool', 'U') IS NOT NULL
    DROP TABLE dbo.cics_storage_program_subpool;
GO

CREATE TABLE dbo.cics_storage_program_subpool
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    subPoolName NVARCHAR(100) NOT NULL,
    location NVARCHAR(50) NULL,
    currentStorage NVARCHAR(30) NULL,
    peakStorage NVARCHAR(30) NULL
);
GO

CREATE INDEX IX_cics_storage_program_subpool_archivo_fecha
ON dbo.cics_storage_program_subpool(archivo, fecha);
GO

CREATE INDEX IX_cics_storage_program_subpool_subPoolName
ON dbo.cics_storage_program_subpool(subPoolName);
GO

CREATE UNIQUE INDEX UX_cics_storage_program_subpool_archivo_fecha_subPoolName
ON dbo.cics_storage_program_subpool(archivo, fecha, subPoolName, location);
GO

ALTER TABLE dbo.cics_storage_program_subpool
ADD CONSTRAINT FK_cics_storage_program_subpool_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO


/* =========================================
   TABLA: cics_system_status
   Un registro por archivo y fecha
   ========================================= */
IF OBJECT_ID('dbo.cics_system_status', 'U') IS NOT NULL
    DROP TABLE dbo.cics_system_status;
GO

CREATE TABLE dbo.cics_system_status
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    mvsProductName NVARCHAR(100) NULL,
    cicsStartup NVARCHAR(30) NULL,
    cicsStatus NVARCHAR(30) NULL,
    cecMachineType NVARCHAR(50) NULL,
    vtamOpenStatus NVARCHAR(30) NULL,
    ircStatus NVARCHAR(30) NULL,
    ircXcfGroupName NVARCHAR(100) NULL,
    storageProtection NVARCHAR(30) NULL,
    transactionIsolation NVARCHAR(30) NULL,
    reentrantPrograms NVARCHAR(50) NULL,
    execStorageCommandChecking NVARCHAR(30) NULL,
    forceQuasiReentrant NVARCHAR(30) NULL,
    programAutoinstall NVARCHAR(30) NULL,
    terminalAutoinstall NVARCHAR(30) NULL,
    activityKeypointFrequency INT NULL,
    logstreamDeferredForceInterval INT NULL,
    rlsStatus NVARCHAR(50) NULL,
    rrmsMvsStatus NVARCHAR(50) NULL,
    db2ConnectionName NVARCHAR(100) NULL,
    cicsTsLevel NVARCHAR(30) NULL,
    wlmMode NVARCHAR(30) NULL,
    wlmServer NVARCHAR(30) NULL,
    wlmManageRegionGoals NVARCHAR(100) NULL,
    wlmWorkloadName NVARCHAR(100) NULL,
    wlmServiceClass NVARCHAR(100) NULL,
    wlmReportClass NVARCHAR(100) NULL,
    wlmResourceGroup NVARCHAR(100) NULL,
    wlmGoalType NVARCHAR(50) NULL,
    wlmGoalValue INT NULL,
    wlmGoalImportance INT NULL,
    wlmCpuCritical NVARCHAR(20) NULL,
    wlmStorageCritical NVARCHAR(20) NULL,
    tcpIpStatus NVARCHAR(30) NULL,
    maxIpSockets INT NULL,
    activeIpSockets INT NULL,
    webGarbageCollectionInterval INT NULL,
    terminalInputTimeoutInterval INT NULL,

    CONSTRAINT UX_cics_system_status_archivo_fecha UNIQUE (archivo, fecha)
);
GO

CREATE INDEX IX_cics_system_status_archivo_fecha
ON dbo.cics_system_status(archivo, fecha);
GO

ALTER TABLE dbo.cics_system_status
ADD CONSTRAINT FK_cics_system_status_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO


/* =========================================
   TABLA: cics_transaction_manager
   Un registro por archivo y fecha
   ========================================= */
IF OBJECT_ID('dbo.cics_transaction_manager', 'U') IS NOT NULL
    DROP TABLE dbo.cics_transaction_manager;
GO

CREATE TABLE dbo.cics_transaction_manager
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,

    totalAccumulatedTransactionsSoFar BIGINT NULL,
    accumulatedTransactionsSinceReset BIGINT NULL,
    transactionRatePerSecond DECIMAL(10,2) NULL,
    maximumTransactionsAllowedMxt INT NULL,
    timeMxtLastChanged DATETIME NULL,
    timesAtMxt BIGINT NULL,
    timeMxtLastReached DATETIME NULL,
    currentActiveUserTransactions INT NULL,
    currentlyAtMxt NVARCHAR(20) NULL,
    peakActiveUserTransactions INT NULL,
    totalActiveUserTransactions BIGINT NULL,
    timeLastTransactionAttached DATETIME NULL,
    currentRunningTransactions INT NULL,
    currentDispatchableTransactions INT NULL,
    currentSuspendedTransactions INT NULL,
    currentSystemTransactions INT NULL,
    transactionsDelayedByMxt INT NULL,
    totalMxtQueueingTime NVARCHAR(30) NULL,
    averageMxtQueueingTime NVARCHAR(30) NULL,
    currentQueuedUserTransactions INT NULL,
    peakQueuedUserTransactions INT NULL,
    totalQueueingTimeForCurrentQueued NVARCHAR(30) NULL,
    averageQueueingTimeForCurrentQueued NVARCHAR(30) NULL,

    CONSTRAINT UX_cics_transaction_manager_archivo_fecha UNIQUE (archivo, fecha)
);
GO

CREATE INDEX IX_cics_transaction_manager_archivo_fecha
ON dbo.cics_transaction_manager(archivo, fecha);
GO

ALTER TABLE dbo.cics_transaction_manager
ADD CONSTRAINT FK_cics_transaction_manager_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO


/* =========================================
   TABLA: cics_monitoring
   Un registro por archivo y fecha
   ========================================= */
IF OBJECT_ID('dbo.cics_monitoring', 'U') IS NOT NULL
    DROP TABLE dbo.cics_monitoring;
GO

CREATE TABLE dbo.cics_monitoring
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    monitoring NVARCHAR(20) NULL,
    exceptionClass NVARCHAR(20) NULL,
    performanceClass NVARCHAR(20) NULL,
    resourceClass NVARCHAR(20) NULL,
    identityClass NVARCHAR(20) NULL,
    dataCompressionOption NVARCHAR(20) NULL,
    applicationNaming NVARCHAR(20) NULL,
    rmiOption NVARCHAR(20) NULL,
    converseOption NVARCHAR(20) NULL,
    syncpointOption NVARCHAR(20) NULL,
    timeOption NVARCHAR(20) NULL,
    frequency NVARCHAR(30) NULL,
    mctProgramName NVARCHAR(100) NULL,
    dplResourceLimit INT NULL,
    fileResourceLimit INT NULL,
    tsqueueResourceLimit INT NULL,
    urimapResourceLimit INT NULL,
    webserviceResourceLimit INT NULL,
    exceptionClassRecords BIGINT NULL,
    exceptionRecordsSuppressed BIGINT NULL,
    performanceClassRecords BIGINT NULL,
    performanceRecordsSuppressed BIGINT NULL,
    resourceClassRecords BIGINT NULL,
    resourceRecordsSuppressed BIGINT NULL,
    identityClassRecords BIGINT NULL,
    identityRecordsSuppressed BIGINT NULL,
    monitoringSmfRecords BIGINT NULL,
    monitoringSmfErrors BIGINT NULL,
    monitoringSmfRecordsCompressed BIGINT NULL,
    monitoringSmfRecordsNotCompressed BIGINT NULL,
    percentageSmfRecordsCompressed DECIMAL(5,2) NULL,

    CONSTRAINT UX_cics_monitoring_archivo_fecha UNIQUE (archivo, fecha)
);
GO

CREATE INDEX IX_cics_monitoring_archivo_fecha
ON dbo.cics_monitoring(archivo, fecha);
GO

ALTER TABLE dbo.cics_monitoring
ADD CONSTRAINT FK_cics_monitoring_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO

/* =========================================
   TABLA: cics_trace_status
   Un registro por archivo y fecha
   ========================================= */
CREATE TABLE dbo.cics_trace_status
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,

    internalTraceStatus    NVARCHAR(30)  NULL,
    auxiliaryTraceStatus   NVARCHAR(30)  NULL,
    gtfTraceStatus         NVARCHAR(30)  NULL,
    internalTraceTableSize NVARCHAR(30)  NULL,
    currentAuxiliaryDataset NVARCHAR(10) NULL,
    auxiliarySwitchStatus  NVARCHAR(30)  NULL
);
GO

CREATE UNIQUE INDEX UX_cics_trace_status_archivo_fecha
ON dbo.cics_trace_status(archivo, fecha);
GO

ALTER TABLE dbo.cics_trace_status
ADD CONSTRAINT FK_cics_trace_status_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO

/* =========================================
    TABLA: cics_dumps
   Un registro por archivo y fecha
   ========================================= */
CREATE TABLE dbo.cics_dumps
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,
    systemDumps INT NULL,
    systemDumpsSuppressed INT NULL,
    transactionDumps INT NULL,
    transactionDumpsSuppressed INT NULL
);
GO

CREATE UNIQUE INDEX UX_cics_dumps_archivo_fecha
ON dbo.cics_dumps(archivo, fecha);
GO

ALTER TABLE dbo.cics_dumps
ADD CONSTRAINT FK_cics_dumps_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO

CREATE TABLE dbo.cics_cargas
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    fecha DATE NOT NULL,
    carpeta NVARCHAR(100) NOT NULL,
    fecha_proceso DATETIME NOT NULL DEFAULT GETDATE(),
    estado NVARCHAR(20) NOT NULL DEFAULT 'PROCESADO'
);
GO

CREATE UNIQUE INDEX UX_cics_cargas_fecha_carpeta
ON dbo.cics_cargas(fecha, carpeta);
GO


/* =========================================
   TABLA: cics_statistics
   Un registro por archivo y fecha
   ========================================= */
IF OBJECT_ID('dbo.cics_statistics', 'U') IS NOT NULL
    DROP TABLE dbo.cics_statistics;
GO

CREATE TABLE dbo.cics_statistics
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    archivo INT NOT NULL,
    fecha DATE NOT NULL,

    statisticsRecording NVARCHAR(20) NULL,
    statisticsLastResetDateTime DATETIME NULL,
    elapsedTimeSinceReset NVARCHAR(30) NULL,
    statisticsInterval NVARCHAR(30) NULL,
    nextStatisticsCollection NVARCHAR(30) NULL,
    statisticsEndOfDayTime NVARCHAR(30) NULL,
    statisticsStartDateTime DATETIME NULL,
    statisticsSmfRecords BIGINT NULL,
    statisticsSmfWritesSuppressed BIGINT NULL,
    statisticsSmfErrors BIGINT NULL,
    currentTasksAtLastAttach INT NULL,
    mxtValueAtLastAttach INT NULL,
    timeLastUserTransactionAttached DATETIME NULL,
    timeLastUserTransactionEnded DATETIME NULL,
    systemTransactionsEnded BIGINT NULL,
    userTransactionsEnded BIGINT NULL,
    totalTransactionsEnded BIGINT NULL,
    averageUserTransactionRespTime NVARCHAR(30) NULL,
    peakUserTransactionRespTime NVARCHAR(30) NULL,
    peakUserTransactionRespTimeAt DATETIME NULL,
    totalTransactionCpuTime NVARCHAR(30) NULL,
    totalTransactionCpuTimeOnCp NVARCHAR(30) NULL,
    totalTransactionCpuOffloadOnCp NVARCHAR(30) NULL,
    averageCompressedRecordLength INT NULL,
    averageUncompressedRecordLength INT NULL,
    averageRecordCompressionPercent DECIMAL(5,2) NULL,

    CONSTRAINT UX_cics_statistics_archivo_fecha UNIQUE (archivo, fecha)
);
GO

CREATE INDEX IX_cics_statistics_archivo_fecha
ON dbo.cics_statistics(archivo, fecha);
GO

ALTER TABLE dbo.cics_statistics
ADD CONSTRAINT FK_cics_statistics_archivo
FOREIGN KEY (archivo) REFERENCES dbo.cics_archivos(id);
GO
