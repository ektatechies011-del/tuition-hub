from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "students.db")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)
app.secret_key = "tuition_secret_key"


# ======================
# DATABASE CONNECTION
# ======================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ======================
# DATABASE SETUP
# ======================
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            class TEXT,
            school TEXT,
            joining_date TEXT,
            fee INTEGER,
            phone TEXT,
            username TEXT UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            subject TEXT,
            class TEXT,
            due_date TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT,
            subject TEXT,
            class TEXT,
            test_date TEXT
        )
    """)

    conn.commit()
    conn.close()


# ======================
# DEFAULT USERS
# ======================
def seed_users():
    conn = get_connection()
    cur = conn.cursor()

    # default admin
    cur.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    admin_user = cur.fetchone()

    if not admin_user:
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", "1234", "admin")
        )

    conn.commit()
    conn.close()


# ======================
# STARTUP
# ======================
def ensure_database_ready():
    init_db()
    seed_users()


ensure_database_ready()


# ======================
# HELPERS
# ======================
def login_required():
    return "role" in session and "user" in session


def admin_required():
    return login_required() and session.get("role") == "admin"


def student_required():
    return login_required() and session.get("role") == "student"


# ======================
# HEALTH CHECK
# ======================
@app.route("/health")
def health():
    try:
        ensure_database_ready()
        return "OK"
    except Exception as e:
        return f"ERROR: {str(e)}", 500


# ======================
# HOME
# ======================
@app.route("/")
def home():
    if not login_required():
        return redirect(url_for("login"))

    if session.get("role") == "admin":
        return redirect(url_for("admin"))

    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("logout"))


# ======================
# LOGIN
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_database_ready()
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            error = "Please enter both username and password."
            return render_template("login.html", error=error)

        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute("""
                SELECT * FROM users
                WHERE username = ? AND password = ?
            """, (username, password))

            user = cur.fetchone()
            conn.close()

            if user:
                session["user"] = user["username"]
                session["role"] = user["role"]

                if user["role"] == "admin":
                    return redirect(url_for("admin"))
                else:
                    return redirect(url_for("student_dashboard"))

            error = "Invalid username or password."
            return render_template("login.html", error=error)

        except Exception as e:
            error = f"Login error: {str(e)}"
            return render_template("login.html", error=error)

    return render_template("login.html", error=error)


# ======================
# CONTACT
# ======================
@app.route("/contact")
def contact():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("contact.html")


# ======================
# PAY PAGE
# ======================
@app.route("/pay")
def pay():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("pay.html")


# ======================
# ADD STUDENT
# ======================
@app.route("/submit", methods=["POST"])
def submit():
    if not admin_required():
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    student_class = request.form.get("class", "").strip()
    school = request.form.get("school", "").strip()
    joining_date = request.form.get("joining_date", "").strip()
    fee = request.form.get("fee", "").strip()
    phone = request.form.get("phone", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not all([name, student_class, school, joining_date, fee, phone, username, password]):
        return "❌ All fields are required"

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO students (name, class, school, joining_date, fee, phone, username)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, student_class, school, joining_date, fee, phone, username))

        cur.execute("""
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, (username, password, "student"))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return "❌ Username already exists"

    conn.close()
    return redirect(url_for("admin"))


# ======================
# FIX MISSING STUDENT USERS
# ======================
@app.route("/fix-student-users")
def fix_student_users():
    if not admin_required():
        return redirect(url_for("home"))

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT username FROM students WHERE username IS NOT NULL AND username != ''")
    student_usernames = cur.fetchall()

    added = 0

    for row in student_usernames:
        username = row["username"]

        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        existing_user = cur.fetchone()

        if not existing_user:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, "1234", "student")
            )
            added += 1

    conn.commit()
    conn.close()

    return f"✅ Fixed student users. Added {added} missing student login accounts. Default password is 1234."


# ======================
# ADMIN DASHBOARD
# ======================
@app.route("/admin")
def admin():
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM students")
    students = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM assignments")
    total_assignments = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM tests")
    total_tests = cur.fetchone()[0]

    conn.close()

    return render_template(
        "admin.html",
        students=students,
        total_assignments=total_assignments,
        total_tests=total_tests,
        class5=len([s for s in students if s["class"] == "5"]),
        class6=len([s for s in students if s["class"] == "6"]),
        class7=len([s for s in students if s["class"] == "7"]),
        class8=len([s for s in students if s["class"] == "8"]),
        class9=len([s for s in students if s["class"] == "9"]),
        class10=len([s for s in students if s["class"] == "10"])
    )


# ======================
# STUDENT DASHBOARD
# ======================
@app.route("/student")
def student_dashboard():
    if not student_required():
        return redirect(url_for("login"))

    username = session["user"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM students WHERE username = ?", (username,))
    student = cur.fetchone()

    if not student:
        conn.close()
        return "❌ Student record not found."

    cur.execute("SELECT * FROM assignments WHERE class = ?", (student["class"],))
    assignments = cur.fetchall()

    cur.execute("SELECT * FROM tests WHERE class = ?", (student["class"],))
    tests = cur.fetchall()

    conn.close()

    return render_template(
        "student.html",
        student=student,
        assignments=assignments,
        tests=tests
    )


# ======================
# STUDY ASSISTANT
# ======================
@app.route("/student/assistant", methods=["GET", "POST"])
def student_assistant():
    if not student_required():
        return redirect(url_for("login"))

    answer = ""

    if request.method == "POST":
        question = request.form.get("question", "").lower().strip()

        if "hello" in question:
            answer = "Hello 👋 How can I help you?"
        elif "math" in question:
            answer = "Practice daily and focus on concepts."
        elif question == "":
            answer = "Please enter a question first."
        else:
            answer = "I am your study assistant 🤖"

    return render_template("student_assistant.html", answer=answer)


# ======================
# LOGOUT
# ======================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ======================
# RUN
# ======================
if __name__ == "__main__":
    ensure_database_ready()
    app.run(debug=True)