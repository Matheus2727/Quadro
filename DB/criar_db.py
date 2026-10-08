import sqlite3
from pathlib import Path

db_path = Path('DB') / 'DB.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Datatypes:
# NULL
# INTEGER
# REAL
# TEXT
# BLOB

cursor.execute("""
create table Configs (
               ID_Config INTEGER PRIMARY KEY AUTOINCREMENT,
               Tempo INTEGER
)
""")

conn.commit()

cursor.execute("""
create table Photos (
               ID_Photo TEXT PRIMARY KEY,
               Extension_Photo TEXT,
               Data_Photo TEXT,
               Width INTEGER,
               Height INTEGER
)
""")

conn.commit()

cursor.execute("""
create table Tags (
               ID_Tag_Photo INTEGER PRIMARY KEY AUTOINCREMENT,
               ID_Photo TEXT,
               Tag TEXT
)
""")

conn.commit()

conn.close()