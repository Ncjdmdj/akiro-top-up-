import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """បង្កើត Table orders ប្រសិនបើវាមិនទាន់មាន"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                game_id VARCHAR(50),
                user_id VARCHAR(100),
                product_code VARCHAR(100),
                status VARCHAR(50),
                response_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")