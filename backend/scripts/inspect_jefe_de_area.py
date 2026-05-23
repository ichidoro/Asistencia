import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.database import db

async def inspect():
    await db.connect()
    
    # 1. List roles
    roles = await db.fetch_all("SELECT * FROM roles")
    print("=== ROLES IN DATABASE ===")
    for r in roles:
        print(f"ID: {r['id']} | Nombre: {r['nombre']} | Alcance Global: {r['alcance_global']}")
    
    # 2. Find Jefe de Area role id
    jefe_role = await db.fetch_one("SELECT * FROM roles WHERE nombre LIKE '%Jefe%' OR nombre LIKE '%jefe%'")
    if not jefe_role:
        print("\n❌ No role with 'Jefe' found in database.")
        await db.disconnect()
        return
        
    print(f"\n=== INSPECTING ROLE: {jefe_role['nombre']} (ID: {jefe_role['id']}) ===")
    
    # 3. Get permissions for this role
    perms = await db.fetch_all("""
        SELECT p.id, p.modulo, p.descripcion 
        FROM rol_permisos rp
        JOIN permisos p ON rp.permiso_id = p.id
        WHERE rp.rol_id = ?
        ORDER BY p.modulo, p.id
    """, (jefe_role['id'],))
    
    print(f"Total permissions: {len(perms)}")
    for p in perms:
        print(f" - [{p['modulo']}] {p['id']}: {p['descripcion']}")
        
    # 4. Check if there are any users with this role
    users = await db.fetch_all("""
        SELECT u.id, u.username, u.nombre_completo, u.activo, u.areas_json
        FROM usuarios u
        WHERE u.rol_id = ?
    """, (jefe_role['id'],))
    
    print(f"\n=== USERS WITH THIS ROLE ===")
    for u in users:
        print(f"ID: {u['id']} | Username: {u['username']} | Nombre: {u['nombre_completo']} | Activo: {u['activo']} | Areas: {u['areas_json']}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(inspect())
