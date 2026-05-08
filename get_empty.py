import sqlite3
c = sqlite3.connect('C:\\Users\\danie\\Proyectos_Python\\Asistencia\\rescued.db')
tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
empty = [t for t in tables if c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0]
for t in empty: print(t)
