from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "students.db")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

ASSIGNMENTS_UPLOAD_FOLDER = os.path.join(STATIC_DIR, "uploads", "assignments")
TESTS_UPLOAD_FOLDER = os.path.join(STATIC_DIR, "uploads", "tests")

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg"}

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)
app.secret_key = "tuition_secret_key"

app.config["ASSIGNMENTS_UPLOAD_FOLDER"] = ASSIGNMENTS_UPLOAD_FOLDER
app.config["TESTS_UPLOAD_FOLDER"] = TESTS_UPLOAD_FOLDER

os.makedirs(app.config["ASSIGNMENTS_UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["TESTS_UPLOAD_FOLDER"], exist_ok=True)


# ======================
# DATABASE CONNECTION
# ======================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ======================
# HELPERS
# ======================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def unique_filename(filename):
    safe_name = secure_filename(filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{timestamp}_{safe_name}"


def column_exists(table_name, column_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cur.fetchall()]
    conn.close()
    return column_name in columns


def add_column_if_missing(table_name, column_name, column_type="TEXT"):
    if not column_exists(table_name, column_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        conn.commit()
        conn.close()


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
            due_date TEXT,
            filename TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT,
            subject TEXT,
            class TEXT,
            test_date TEXT,
            filename TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()

    add_column_if_missing("assignments", "filename", "TEXT")
    add_column_if_missing("assignments", "created_at", "TEXT")
    add_column_if_missing("tests", "filename", "TEXT")
    add_column_if_missing("tests", "created_at", "TEXT")


# ======================
# DEFAULT USERS
# ======================
def seed_users():
    conn = get_connection()
    cur = conn.cursor()

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
# AUTH HELPERS
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
# ROOT ROUTE
# ======================
@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))

    if session.get("role") == "admin":
        return redirect(url_for("admin"))

    if session.get("role") == "student":
        return redirect(url_for("home"))

    return redirect(url_for("logout"))


# ======================
# STUDENT HOME PAGE
# ======================
@app.route("/home")
def home():
    if not student_required():
        return redirect(url_for("login"))
    return render_template("home.html")


# ======================
# LOGIN
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_database_ready()
    error = None

    if login_required():
        if session.get("role") == "admin":
            return redirect(url_for("admin"))
        elif session.get("role") == "student":
            return redirect(url_for("home"))

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
                    return redirect(url_for("home"))

            error = "Invalid username or password."
            return render_template("login.html", error=error)

        except Exception as e:
            error = f"Login error: {str(e)}"
            return render_template("login.html", error=error)

    return render_template("login.html", error=error)


# ======================
# CONTACT PAGE
# ======================
@app.route("/contact")
def contact():
    if not login_required():
        return redirect(url_for("login"))

    teacher_name = "Ekta Ma'am"
    teacher_phone = "6284967921"
    whatsapp_number = "916284967921"
    available_time = "Before 8:00 PM (Sunday after 5:00 PM)"
    contact_note = (
        "Please call only during the allowed time. "
        "If one call is missed, callback will be done later. "
        "Repeated calls are not allowed."
    )

    return render_template(
        "contact.html",
        teacher_name=teacher_name,
        teacher_phone=teacher_phone,
        whatsapp_number=whatsapp_number,
        available_time=available_time,
        contact_note=contact_note
    )


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
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        existing_user = cur.fetchone()
        if existing_user:
            conn.close()
            return "❌ Username already exists in users table"

        cur.execute("SELECT * FROM students WHERE username = ?", (username,))
        existing_student = cur.fetchone()
        if existing_student:
            conn.close()
            return "❌ Username already exists in students table"

        cur.execute("""
            INSERT INTO students (name, class, school, joining_date, fee, phone, username)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, student_class, school, joining_date, fee, phone, username))

        cur.execute("""
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, (username, password, "student"))

        conn.commit()
        conn.close()
        return redirect(url_for("admin"))

    except Exception as e:
        conn.rollback()
        conn.close()
        return f"❌ Error while adding student: {str(e)}"


# ======================
# FIX MISSING STUDENT USERS
# ======================
@app.route("/fix-student-users")
def fix_student_users():
    if not admin_required():
        return redirect(url_for("login"))

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
# DEBUG USERS
# ======================
@app.route("/debug-users")
def debug_users():
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT username, password, role FROM users ORDER BY username")
    users = cur.fetchall()
    conn.close()

    output = "<h2>Users Table</h2><ul>"
    for u in users:
        output += f"<li>{u['username']} | {u['password']} | {u['role']}</li>"
    output += "</ul>"
    return output


# ======================
# ADMIN DASHBOARD
# ======================
@app.route("/admin")
def admin():
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    search = request.args.get("search", "").strip()

    if search:
        query = f"%{search}%"
        cur.execute("""
            SELECT * FROM students
            WHERE name LIKE ?
               OR class LIKE ?
               OR school LIKE ?
               OR phone LIKE ?
               OR username LIKE ?
               OR CAST(fee AS TEXT) LIKE ?
        """, (query, query, query, query, query, query))
        students = cur.fetchall()
    else:
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
        search=search,
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
# ADMIN ASSIGNMENTS PAGE
# ======================
@app.route("/admin/assignments", methods=["GET", "POST"])
def admin_assignments():
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        student_class = request.form.get("class", "").strip()
        due_date = request.form.get("due_date", "").strip()
        file = request.files.get("file")

        if not title or not subject or not student_class or not due_date:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("admin_assignments"))

        filename = ""
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid file type. Allowed: pdf, doc, docx, png, jpg, jpeg", "danger")
                return redirect(url_for("admin_assignments"))

            filename = unique_filename(file.filename)
            file.save(os.path.join(app.config["ASSIGNMENTS_UPLOAD_FOLDER"], filename))

        cur.execute("""
            INSERT INTO assignments (title, subject, class, due_date, filename, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, subject, student_class, due_date, filename, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        flash("Assignment added successfully.", "success")
        return redirect(url_for("admin_assignments"))

    cur.execute("SELECT * FROM assignments ORDER BY id DESC")
    assignments = cur.fetchall()
    conn.close()

    return render_template("admin_assignments.html", assignments=assignments)


# ======================
# ADMIN TESTS PAGE
# ======================
@app.route("/admin/tests", methods=["GET", "POST"])
def admin_tests():
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        test_name = request.form.get("test_name", "").strip()
        subject = request.form.get("subject", "").strip()
        student_class = request.form.get("class", "").strip()
        test_date = request.form.get("test_date", "").strip()
        file = request.files.get("file")

        if not test_name or not subject or not student_class or not test_date:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("admin_tests"))

        filename = ""
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid file type. Allowed: pdf, doc, docx, png, jpg, jpeg", "danger")
                return redirect(url_for("admin_tests"))

            filename = unique_filename(file.filename)
            file.save(os.path.join(app.config["TESTS_UPLOAD_FOLDER"], filename))

        cur.execute("""
            INSERT INTO tests (test_name, subject, class, test_date, filename, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (test_name, subject, student_class, test_date, filename, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        flash("Test added successfully.", "success")
        return redirect(url_for("admin_tests"))

    cur.execute("SELECT * FROM tests ORDER BY id DESC")
    tests = cur.fetchall()
    conn.close()

    return render_template("admin_tests.html", tests=tests)


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

    cur.execute("SELECT * FROM assignments WHERE class = ? ORDER BY id DESC", (student["class"],))
    assignments = cur.fetchall()

    cur.execute("SELECT * FROM tests WHERE class = ? ORDER BY id DESC", (student["class"],))
    tests = cur.fetchall()

    conn.close()

    return render_template(
        "student.html",
        student=student,
        assignments=assignments,
        tests=tests
    )


# ======================
# STUDENT ASSIGNMENTS PAGE
# ======================
@app.route("/student/assignments")
def student_assignments():
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

    cur.execute("""
        SELECT * FROM assignments
        WHERE class = ?
        ORDER BY id DESC
    """, (student["class"],))
    assignments = cur.fetchall()
    conn.close()

    return render_template("student_assignments.html", student=student, assignments=assignments)


# ======================
# STUDENT TESTS PAGE
# ======================
@app.route("/student/tests")
def student_tests():
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

    cur.execute("""
        SELECT * FROM tests
        WHERE class = ?
        ORDER BY id DESC
    """, (student["class"],))
    tests = cur.fetchall()
    conn.close()

    return render_template("student_tests.html", student=student, tests=tests)


# ======================
# VIEW FILES
# ======================
@app.route("/view/assignment/<filename>")
def view_assignment(filename):
    if not login_required():
        return redirect(url_for("login"))
    return send_from_directory(app.config["ASSIGNMENTS_UPLOAD_FOLDER"], filename)


@app.route("/view/test/<filename>")
def view_test(filename):
    if not login_required():
        return redirect(url_for("login"))
    return send_from_directory(app.config["TESTS_UPLOAD_FOLDER"], filename)


# ======================
# DOWNLOAD FILES
# ======================
@app.route("/download/assignment/<filename>")
def download_assignment(filename):
    if not login_required():
        return redirect(url_for("login"))
    return send_from_directory(app.config["ASSIGNMENTS_UPLOAD_FOLDER"], filename, as_attachment=True)


@app.route("/download/test/<filename>")
def download_test(filename):
    if not login_required():
        return redirect(url_for("login"))
    return send_from_directory(app.config["TESTS_UPLOAD_FOLDER"], filename, as_attachment=True)


# ======================
# DELETE ASSIGNMENT
# ======================
@app.route("/delete-assignment/<int:assignment_id>")
def delete_assignment(assignment_id):
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
    assignment = cur.fetchone()

    if assignment:
        filename = assignment["filename"]
        if filename:
            file_path = os.path.join(app.config["ASSIGNMENTS_UPLOAD_FOLDER"], filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        cur.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
        conn.commit()
        flash("Assignment deleted successfully.", "success")

    conn.close()
    return redirect(url_for("admin_assignments"))


# ======================
# DELETE TEST
# ======================
@app.route("/delete-test/<int:test_id>")
def delete_test(test_id):
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
    test = cur.fetchone()

    if test:
        filename = test["filename"]
        if filename:
            file_path = os.path.join(app.config["TESTS_UPLOAD_FOLDER"], filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        cur.execute("DELETE FROM tests WHERE id = ?", (test_id,))
        conn.commit()
        flash("Test deleted successfully.", "success")

    conn.close()
    return redirect(url_for("admin_tests"))


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