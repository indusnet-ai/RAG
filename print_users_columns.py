from sqlalchemy import text
from db import engine

def inspect_users_table():
    with engine.connect() as conn:
        # Get columns
        columns_res = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users';
        """))
        print("Columns in 'users' table:")
        for row in columns_res:
            print(f"- {row.column_name}: {row.data_type}")
            
        # Get count of users
        count_res = conn.execute(text("SELECT COUNT(*) FROM users;"))
        count = count_res.scalar()
        print(f"Total rows in 'users': {count}")
        
        if count > 0:
            users_res = conn.execute(text("SELECT id, name, email, role FROM users LIMIT 5;"))
            print("Sample users:")
            for row in users_res:
                print(f"  {row.id} | {row.name} | {row.email} | {row.role}")

if __name__ == "__main__":
    inspect_users_table()
