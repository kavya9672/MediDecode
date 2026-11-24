"""backend/database.py

SQLite database helper for the Automated Medicine Prescription Decoder.
Provides functions to initialize the database, obtain connections, and perform
basic CRUD operations. The module initializes the database automatically when
imported.

The schema includes two tables:

* ``medicines`` – stores medicine metadata.
* ``interactions`` – stores pairwise interactions between medicines.

Both tables include primary keys, foreign keys and useful indexes. All SQL
statements use parameterised queries to avoid SQL injection.
"""

import os
import sqlite3
import datetime
from typing import Any, Dict

# Path to the SQLite file – placed next to this module for simplicity.
DB_PATH = os.path.join(os.path.dirname(__file__), "medicine.db")


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database.

    The connection uses ``row_factory`` so rows behave like dictionaries.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and indexes if they do not already exist."""
    conn = get_connection()
    cur = conn.cursor()

    # Medicines table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL,
            active_ingredient TEXT NOT NULL,
            strength TEXT,
            dosage_form TEXT,
            route TEXT,
            manufacturer TEXT,
            price REAL,
            price_source TEXT,
            verification_date TEXT,
            verification_status TEXT
        )
        """
    )
    # Indexes for fast lookup
    cur.execute("CREATE INDEX IF NOT EXISTS idx_medicines_brand ON medicines(brand_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_medicines_active ON medicines(active_ingredient)")

    # Interactions table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_a_id INTEGER NOT NULL,
            medicine_b_id INTEGER NOT NULL,
            severity TEXT,
            description TEXT,
            source TEXT,
            verification_date TEXT,
            verification_status TEXT,
            FOREIGN KEY(medicine_a_id) REFERENCES medicines(id) ON DELETE CASCADE,
            FOREIGN KEY(medicine_b_id) REFERENCES medicines(id) ON DELETE CASCADE
        )
        """
    )
    # Indexes for fast joins
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_a ON interactions(medicine_a_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_interactions_b ON interactions(medicine_b_id)")

    conn.commit()
    conn.close()

# Initialise the DB as soon as the module is imported.
init_db()

# ---------------------------------------------------------------------------
# Helper functions for basic insert / read / delete – useful for other modules.
# ---------------------------------------------------------------------------

def insert_medicine(conn: sqlite3.Connection, data: Dict[str, Any]) -> int:
    """Insert a medicine record and return its generated ``id``.

    ``data`` keys correspond to column names (except ``id``). All values are
    passed as parameters to keep the query safe.
    """
    columns = [k for k in data.keys() if k != "id"]
    placeholders = ", ".join(["?" for _ in columns])
    sql = f"INSERT INTO medicines ({', '.join(columns)}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.execute(sql, tuple(data[col] for col in columns))
    conn.commit()
    return cur.lastrowid


def insert_interaction(conn: sqlite3.Connection, data: Dict[str, Any]) -> int:
    """Insert an interaction record and return its ``id``."""
    columns = [k for k in data.keys() if k != "id"]
    placeholders = ", ".join(["?" for _ in columns])
    sql = f"INSERT INTO interactions ({', '.join(columns)}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.execute(sql, tuple(data[col] for col in columns))
    conn.commit()
    return cur.lastrowid


def get_medicine_by_id(conn: sqlite3.Connection, med_id: int) -> sqlite3.Row:
    cur = conn.cursor()
    cur.execute("SELECT * FROM medicines WHERE id = ?", (med_id,))
    return cur.fetchone()


def get_interaction_by_id(conn: sqlite3.Connection, int_id: int) -> sqlite3.Row:
    cur = conn.cursor()
    cur.execute("SELECT * FROM interactions WHERE id = ?", (int_id,))
    return cur.fetchone()


def delete_medicine(conn: sqlite3.Connection, med_id: int) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM medicines WHERE id = ?", (med_id,))
    conn.commit()


def delete_interaction(conn: sqlite3.Connection, int_id: int) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM interactions WHERE id = ?", (int_id,))
    conn.commit()

# ---------------------------------------------------------------------------
# Simple self‑test that runs when executing the module directly.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    conn = get_connection()

    # Insert a temporary medicine record
    med_data = {
        "brand_name": "TestMed",
        "active_ingredient": "Acetaminophen",
        "strength": "500 mg",
        "dosage_form": "Tablet",
        "route": "Oral",
        "manufacturer": "TestPharma",
        "price": 9.99,
        "price_source": "TestSource",
        "verification_date": datetime.date.today().isoformat(),
        "verification_status": "verified",
    }
    med_id = insert_medicine(conn, med_data)
    print(f"Inserted medicine id: {med_id}")

    # Insert a second temporary medicine
    med2_data = med_data.copy()
    med2_data["brand_name"] = "TestMed2"
    med2_id = insert_medicine(conn, med2_data)
    print(f"Inserted second medicine id: {med2_id}")

    # Insert a temporary interaction between the two medicines
    int_data = {
        "medicine_a_id": med_id,
        "medicine_b_id": med2_id,
        "severity": "moderate",
        "description": "Test interaction description",
        "source": "UnitTest",
        "verification_date": datetime.date.today().isoformat(),
        "verification_status": "verified",
    }
    int_id = insert_interaction(conn, int_data)
    print(f"Inserted interaction id: {int_id}")

    # Read back and display
    print("Read back medicine:", dict(get_medicine_by_id(conn, med_id)))
    print("Read back interaction:", dict(get_interaction_by_id(conn, int_id)))

    # Cleanup temporary records
    delete_interaction(conn, int_id)
    delete_medicine(conn, med_id)
    delete_medicine(conn, med2_id)
    print("Temporary records removed.")

    conn.close()
