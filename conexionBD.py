import pyodbc

def conectar_base_datos():
    conn = pyodbc.connect('DRIVER={SQL Server};' \
    'SERVER=10.2.214.69;' \
    'DATABASE=DB_base_conocimiento_2;' \
    'UID=C3;' \
    'PWD=R3s1l13nc14C0d1g02024.')
    return conn 
