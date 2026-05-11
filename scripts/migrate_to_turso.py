import sqlite3
import libsql

def migrate():
    print('Connecting to local DB...')
    local_conn = sqlite3.connect('data/local_db/asistencia_local.db')
    local_cursor = local_conn.cursor()
    
    print('Connecting to remote Turso DB...')
    url = 'libsql://asistenciaaguacol-ichidoro.aws-us-east-1.turso.io'
    token = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3Nzg0NjQ2MjEsImlkIjoiMDE5ZTE0YzAtNjYwMS03YzUyLWFhZjMtMzk5ZTFlNjM5ZWEyIiwicmlkIjoiODZmMjkyYTUtMjMzZC00ZmYyLThmN2ItMmJkNTQ2MmY1MDYwIn0.HyHa_-uEPS_2YswqpWrSvX3CyqwkB5bj-uGOA549ug68cPgVK5TXBSMMjo1e0NJWwMQa8deBHL5UREuJKKyACA'
    remote_conn = libsql.connect(database=url, auth_token=token)
    remote_cursor = remote_conn.cursor()

    # 1. Dump schema from local
    local_cursor.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name != 'sqlite_sequence';")
    schemas = local_cursor.fetchall()
    
    print('Creating schemas on remote...')
    for (schema,) in schemas:
        try:
            remote_cursor.execute(schema)
        except Exception as e:
            print('Error creating schema:', schema, '->', e)

    # 2. Dump data from local
    local_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence';")
    tables = [r[0] for r in local_cursor.fetchall()]
    
    for table in tables:
        print(f'Migrating table {table}...')
        local_cursor.execute(f'SELECT * FROM {table}')
        rows = local_cursor.fetchall()
        if not rows:
            continue
            
        # Get column names
        local_cursor.execute(f'PRAGMA table_info({table})')
        cols = [r[1] for r in local_cursor.fetchall()]
        
        placeholders = ','.join(['?'] * len(cols))
        insert_sql = f'INSERT INTO {table} ({",".join(cols)}) VALUES ({placeholders})'
        
        try:
            remote_cursor.executemany(insert_sql, rows)
            print(f'Inserted {len(rows)} rows into {table}.')
        except Exception as e:
            print(f'Error inserting data into {table}:', e)

    remote_conn.commit()
    print('Migration complete!')

migrate()
