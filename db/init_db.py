from sqlalchemy import create_engine
from db.session import engine
from models import Base

def init_db():
    """
    Initialize the database by creating all tables.
    """
    # Create all tables for user and document models
    # Note: This will fail if database is not available, but it's OK for app startup
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Database initialization failed: {e}")
        print("Make sure your database server is running.")

if __name__ == "__main__":
    init_db()