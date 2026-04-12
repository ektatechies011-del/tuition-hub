import sqlite3

def init_db():
    conn = sqlite3.connect("students.db")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            class TEXT,
            subject TEXT,
            phone TEXT
        )
    """)

    conn.commit()
    conn.close()

def insert_student(name, student_class, subject, phone):
    conn = sqlite3.connect("students.db")
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO students (name, class, subject, phone)
        VALUES (?, ?, ?, ?)
    """, (name, student_class, subject, phone))

    conn.commit()
    conn.close()