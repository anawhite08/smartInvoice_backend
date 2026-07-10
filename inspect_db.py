import os
import sys
from app.extensions import get_engine
from sqlalchemy import text

# Force stdout/stderr to use UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def inspect_db():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Get list of tables
            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            result = conn.execute(query).fetchall()
            print("--- EXISTING TABLES ---")
            for row in result:
                print(row[0])
                
            # Get columns of usuarios
            print("\n--- COLUMNS IN 'usuarios' ---")
            columns_query = text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'usuarios';
            """)
            col_result = conn.execute(columns_query).fetchall()
            for col in col_result:
                print(f"{col[0]}: {col[1]}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sys.path.append(os.path.abspath(os.path.dirname(__file__)))
    inspect_db()
