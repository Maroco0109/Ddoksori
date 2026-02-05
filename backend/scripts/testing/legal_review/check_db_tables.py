
import os
import sys
import psycopg2
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

from app.common.config import get_config

def list_tables():
    print("=== Listing DB Tables ===")
    config = get_config()
    db_config = config.database.get_connection_dict()
    
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        tables = cur.fetchall()
        print(f"Found {len(tables)} tables:")
        for t in tables:
            print(f"- {t[0]}")
            
            # Check columns if table resembles 'chunk'
            if 'chunk' in t[0] or 'doc' in t[0]:
                print(f"  [Columns of {t[0]}]:")
                cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t[0]}' ORDER BY ordinal_position")
                cols = cur.fetchall()
                print(f"  {', '.join([c[0] for c in cols])}")
            
            if t[0] == 'vector_chunks':
                print("  !!! vector_chunks FOUND !!!")
            
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_tables()
