from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
import cloudinary
import cloudinary.uploader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg"}

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)

app.secret_key = os.environ.get("SECRET_KEY", "tuition_secret_key")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL and "sslmode=" not in DATABASE_URL:
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

# Cloudinary config
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)


# ======================
# DATABASE CONNECTION
# ======================
def get_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing. Add it in Render environment variables.")
    return psycopg2.connect(DATABASE_URL)


# ======================
# HELPERS
# ======================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_extension(filename):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def get_cloudinary_resource_type(filename):
    ext = get_file_extension(filename)

    if ext in {"png", "jpg", "jpeg"}:
        return "image"

    if ext in {"pdf", "doc", "docx"}:
        return "raw"

    return "raw"


def fetch_one_dict(cur):
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_all_dicts(cur):
    rows = cur.fetchall()
    return [dict(row) for row in rows]


def column_exists(table_name, column_name):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table_name, column_name))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists


def add_column_if_missing(table_name, column_name, column_type="TEXT"):
    if not column_exists(table_name, column_name):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'
        )
        conn.commit()
        cur.close()
        conn.close()


def student_to_tuple(student):
    if not student:
        return None
    return (
        student["id"],
        student["name"],
        student["class"],
        student["school"],
        student["joining_date"],
        student["fee"],
        student["phone"],
        student["username"],
    )


def students_to_tuples(students):
    return [student_to_tuple(s) for s in students]


def assignments_to_tuples(assignments):
    result = []
    for a in assignments:
        result.append((
            a["id"],
            a["title"],
            a["subject"],
            a["class"],
            a["due_date"],
            a.get("filename") or "",
        ))
    return result


def tests_to_tuples(tests):
    result = []
    for t in tests:
        result.append((
            t["id"],
            t["test_name"],
            t["subject"],
            t["class"],
            t["test_date"],
            t.get("filename") or "",
        ))
    return result


def upload_to_cloudinary(file, folder_name):
    resource_type = get_cloudinary_resource_type(file.filename)

    upload_result = cloudinary.uploader.upload(
        file,
        resource_type=resource_type,
        folder=folder_name,
        use_filename=True,
        unique_filename=True,
        overwrite=False
    )

    return {
        "file_url": upload_result.get("secure_url", ""),
        "public_id": upload_result.get("public_id", ""),
        "resource_type": upload_result.get("resource_type", resource_type),
        "original_filename": file.filename
    }


def destroy_from_cloudinary(public_id, resource_type):
    if public_id:
        cloudinary.uploader.destroy(
            public_id,
            resource_type=resource_type or "raw",
            invalidate=True
        )


# ======================
# DATABASE SETUP
# ======================
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id BIGSERIAL PRIMARY KEY,
            name TEXT,
            "class" TEXT,
            school TEXT,
            joining_date TEXT,
            fee INTEGER,
            phone TEXT,
            username TEXT UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id BIGSERIAL PRIMARY KEY,
            title TEXT,
            subject TEXT,
            "class" TEXT,
            due_date TEXT,
            file_url TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            id BIGSERIAL PRIMARY KEY,
            test_name TEXT,
            subject TEXT,
            "class" TEXT,
            test_date TEXT,
            file_url TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

    add_column_if_missing("assignments", "original_filename", "TEXT")
    add_column_if_missing("assignments", "public_id", "TEXT")
    add_column_if_missing("assignments", "resource_type", "TEXT")
    add_column_if_missing("tests", "original_filename", "TEXT")
    add_column_if_missing("tests", "public_id", "TEXT")
    add_column_if_missing("tests", "resource_type", "TEXT")


# ======================
# DEFAULT USERS
# ======================
def seed_users():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM users WHERE username = %s", ("admin",))
    admin_user = cur.fetchone()

    if not admin_user:
        cur2 = conn.cursor()
        cur2.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            ("admin", "1234", "admin")
        )
        conn.commit()
        cur2.close()

    cur.close()
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
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT * FROM users
                WHERE username = %s AND password = %s
            """, (username, password))

            user = fetch_one_dict(cur)
            cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user = fetch_one_dict(cur)
        if existing_user:
            cur.close()
            conn.close()
            return "❌ Username already exists in users table"

        cur.execute("SELECT * FROM students WHERE username = %s", (username,))
        existing_student = fetch_one_dict(cur)
        if existing_student:
            cur.close()
            conn.close()
            return "❌ Username already exists in students table"

        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO students (name, "class", school, joining_date, fee, phone, username)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, student_class, school, joining_date, fee, phone, username))

        cur2.execute("""
            INSERT INTO users (username, password, role)
            VALUES (%s, %s, %s)
        """, (username, password, "student"))

        conn.commit()
        cur2.close()
        cur.close()
        conn.close()
        return redirect(url_for("admin"))

    except Exception as e:
        conn.rollback()
        cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute('SELECT username FROM students WHERE username IS NOT NULL AND username != ""')
    student_usernames = fetch_all_dicts(cur)

    added = 0

    for row in student_usernames:
        username = row["username"]
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user = fetch_one_dict(cur)

        if not existing_user:
            cur2 = conn.cursor()
            cur2.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, "1234", "student")
            )
            cur2.close()
            added += 1

    conn.commit()
    cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT username, password, role FROM users ORDER BY username")
    users = fetch_all_dicts(cur)
    cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    search = request.args.get("search", "").strip()

    if search:
        query = f"%{search}%"
        cur.execute("""
            SELECT * FROM students
            WHERE name ILIKE %s
               OR "class" ILIKE %s
               OR school ILIKE %s
               OR phone ILIKE %s
               OR username ILIKE %s
               OR CAST(fee AS TEXT) ILIKE %s
            ORDER BY id
        """, (query, query, query, query, query, query))
        students_dict = fetch_all_dicts(cur)
    else:
        cur.execute("SELECT * FROM students ORDER BY id")
        students_dict = fetch_all_dicts(cur)

    cur.execute("SELECT COUNT(*) AS total FROM assignments")
    total_assignments = fetch_one_dict(cur)["total"]

    cur.execute("SELECT COUNT(*) AS total FROM tests")
    total_tests = fetch_one_dict(cur)["total"]

    cur.close()
    conn.close()

    students = students_to_tuples(students_dict)

    return render_template(
        "admin.html",
        students=students,
        search=search,
        total_assignments=total_assignments,
        total_tests=total_tests,
        class5=len([s for s in students_dict if s["class"] == "5"]),
        class6=len([s for s in students_dict if s["class"] == "6"]),
        class7=len([s for s in students_dict if s["class"] == "7"]),
        class8=len([s for s in students_dict if s["class"] == "8"]),
        class9=len([s for s in students_dict if s["class"] == "9"]),
        class10=len([s for s in students_dict if s["class"] == "10"])
    )


# ======================
# ADMIN ASSIGNMENTS PAGE
# ======================
@app.route("/admin/assignments", methods=["GET", "POST"])
def admin_assignments():
    if not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        subject = request.form.get("subject", "").strip()
        student_class = request.form.get("class", "").strip()
        due_date = request.form.get("due_date", "").strip()
        file = request.files.get("file")

        if not title or not subject or not student_class or not due_date:
            flash("Please fill all fields.", "danger")
            cur.close()
            conn.close()
            return redirect(url_for("admin_assignments"))

        uploaded = {
            "file_url": "",
            "public_id": "",
            "resource_type": "",
            "original_filename": ""
        }

        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid file type. Allowed: pdf, doc, docx, png, jpg, jpeg", "danger")
                cur.close()
                conn.close()
                return redirect(url_for("admin_assignments"))

            try:
                uploaded = upload_to_cloudinary(file, "tuition_hub/assignments")
            except Exception as e:
                flash(f"File upload failed: {str(e)}", "danger")
                cur.close()
                conn.close()
                return redirect(url_for("admin_assignments"))

        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO assignments (
                title, subject, "class", due_date, file_url, created_at,
                original_filename, public_id, resource_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            title,
            subject,
            student_class,
            due_date,
            uploaded["file_url"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            uploaded["original_filename"],
            uploaded["public_id"],
            uploaded["resource_type"]
        ))

        conn.commit()
        cur2.close()
        flash("Assignment added successfully.", "success")
        cur.close()
        conn.close()
        return redirect(url_for("admin_assignments"))

    cur.execute("""
        SELECT
            id, title, subject, "class" AS class, due_date,
            COALESCE(original_filename, '') AS filename,
            file_url,
            created_at
        FROM assignments
        ORDER BY id DESC
    """)
    assignments = fetch_all_dicts(cur)
    cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":
        test_name = request.form.get("test_name", "").strip()
        subject = request.form.get("subject", "").strip()
        student_class = request.form.get("class", "").strip()
        test_date = request.form.get("test_date", "").strip()
        file = request.files.get("file")

        if not test_name or not subject or not student_class or not test_date:
            flash("Please fill all fields.", "danger")
            cur.close()
            conn.close()
            return redirect(url_for("admin_tests"))

        uploaded = {
            "file_url": "",
            "public_id": "",
            "resource_type": "",
            "original_filename": ""
        }

        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid file type. Allowed: pdf, doc, docx, png, jpg, jpeg", "danger")
                cur.close()
                conn.close()
                return redirect(url_for("admin_tests"))

            try:
                uploaded = upload_to_cloudinary(file, "tuition_hub/tests")
            except Exception as e:
                flash(f"File upload failed: {str(e)}", "danger")
                cur.close()
                conn.close()
                return redirect(url_for("admin_tests"))

        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO tests (
                test_name, subject, "class", test_date, file_url, created_at,
                original_filename, public_id, resource_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            test_name,
            subject,
            student_class,
            test_date,
            uploaded["file_url"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            uploaded["original_filename"],
            uploaded["public_id"],
            uploaded["resource_type"]
        ))

        conn.commit()
        cur2.close()
        flash("Test added successfully.", "success")
        cur.close()
        conn.close()
        return redirect(url_for("admin_tests"))

    cur.execute("""
        SELECT
            id, test_name, subject, "class" AS class, test_date,
            COALESCE(original_filename, '') AS filename,
            file_url,
            created_at
        FROM tests
        ORDER BY id DESC
    """)
    tests = fetch_all_dicts(cur)
    cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM students WHERE username = %s", (username,))
    student_dict = fetch_one_dict(cur)

    if not student_dict:
        cur.close()
        conn.close()
        return "❌ Student record not found."

    cur.execute("""
        SELECT
            id, title, subject, "class" AS class, due_date,
            COALESCE(original_filename, '') AS filename
        FROM assignments
        WHERE "class" = %s
        ORDER BY id DESC
    """, (student_dict["class"],))
    assignments_dict = fetch_all_dicts(cur)

    cur.execute("""
        SELECT
            id, test_name, subject, "class" AS class, test_date,
            COALESCE(original_filename, '') AS filename
        FROM tests
        WHERE "class" = %s
        ORDER BY id DESC
    """, (student_dict["class"],))
    tests_dict = fetch_all_dicts(cur)

    cur.close()
    conn.close()

    return render_template(
        "student.html",
        student=student_to_tuple(student_dict),
        assignments=assignments_to_tuples(assignments_dict),
        tests=tests_to_tuples(tests_dict)
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM students WHERE username = %s", (username,))
    student = fetch_one_dict(cur)

    if not student:
        cur.close()
        conn.close()
        return "❌ Student record not found."

    cur.execute("""
        SELECT
            id, title, subject, "class" AS class, due_date,
            COALESCE(original_filename, '') AS filename,
            file_url
        FROM assignments
        WHERE "class" = %s
        ORDER BY id DESC
    """, (student["class"],))
    assignments = fetch_all_dicts(cur)

    cur.close()
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
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM students WHERE username = %s", (username,))
    student = fetch_one_dict(cur)

    if not student:
        cur.close()
        conn.close()
        return "❌ Student record not found."

    cur.execute("""
        SELECT
            id, test_name, subject, "class" AS class, test_date,
            COALESCE(original_filename, '') AS filename,
            file_url
        FROM tests
        WHERE "class" = %s
        ORDER BY id DESC
    """, (student["class"],))
    tests = fetch_all_dicts(cur)

    cur.close()
    conn.close()

    return render_template("student_tests.html", student=student, tests=tests)


# ======================
# VIEW FILES
# ======================
@app.route("/view/assignment/<int:assignment_id>")
def view_assignment(assignment_id):
    if not student_required() and not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, title, file_url, original_filename
        FROM assignments
        WHERE id = %s
    """, (assignment_id,))
    assignment = fetch_one_dict(cur)

    cur.close()
    conn.close()

    if not assignment:
        return "❌ Assignment not found"

    if not assignment.get("file_url"):
        return "❌ File URL missing for this assignment"

    return redirect(assignment["file_url"], code=302)


@app.route("/view/test/<int:test_id>")
def view_test(test_id):
    if not student_required() and not admin_required():
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, test_name, file_url, original_filename
        FROM tests
        WHERE id = %s
    """, (test_id,))
    test = fetch_one_dict(cur)

    cur.close()
    conn.close()

    if not test:
        return "❌ Test not found"

    if not test.get("file_url"):
        return "❌ File URL missing for this test"

    return redirect(test["file_url"], code=302)


# ======================
# DOWNLOAD FILES
# ======================
@app.route("/download/assignment/<int:assignment_id>")
def download_assignment(assignment_id):
    if not student_required() and not admin_required():
        return redirect(url_for("login"))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT file_url
            FROM assignments
            WHERE id = %s
        """, (assignment_id,))
        assignment = fetch_one_dict(cur)

        cur.close()
        conn.close()

        if not assignment:
            return "❌ Assignment not found"

        if not assignment.get("file_url"):
            return "❌ File URL missing for this assignment"

        return redirect(assignment["file_url"], code=302)

    except Exception as e:
        return f"❌ Download error: {str(e)}"


@app.route("/download/test/<int:test_id>")
def download_test(test_id):
    if not student_required() and not admin_required():
        return redirect(url_for("login"))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT file_url
            FROM tests
            WHERE id = %s
        """, (test_id,))
        test = fetch_one_dict(cur)

        cur.close()
        conn.close()

        if not test:
            return "❌ Test not found"

        if not test.get("file_url"):
            return "❌ File URL missing for this test"

        return redirect(test["file_url"], code=302)

    except Exception as e:
        return f"❌ Download error: {str(e)}"


# ======================
# DELETE ASSIGNMENT
# ======================
@app.route("/delete-assignment/<int:assignment_id>")
def delete_assignment(assignment_id):
    if not admin_required():
        return redirect(url_for("login"))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT public_id, resource_type
            FROM assignments
            WHERE id = %s
        """, (assignment_id,))
        assignment = fetch_one_dict(cur)

        if assignment:
            try:
                if assignment.get("public_id"):
                    destroy_from_cloudinary(
                        assignment.get("public_id"),
                        assignment.get("resource_type")
                    )
            except Exception as cloud_err:
                print("Cloudinary delete error:", str(cloud_err))

            cur2 = conn.cursor()
            cur2.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
            conn.commit()
            cur2.close()
            flash("Assignment deleted successfully.", "success")
        else:
            flash("Assignment not found.", "danger")

        cur.close()
        conn.close()
        return redirect(url_for("admin_assignments"))

    except Exception as e:
        return f"❌ Delete assignment error: {str(e)}"


# ======================
# DELETE TEST
# ======================
@app.route("/delete-test/<int:test_id>")
def delete_test(test_id):
    if not admin_required():
        return redirect(url_for("login"))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT public_id, resource_type
            FROM tests
            WHERE id = %s
        """, (test_id,))
        test = fetch_one_dict(cur)

        if test:
            try:
                if test.get("public_id"):
                    destroy_from_cloudinary(
                        test.get("public_id"),
                        test.get("resource_type")
                    )
            except Exception as cloud_err:
                print("Cloudinary delete error:", str(cloud_err))

            cur2 = conn.cursor()
            cur2.execute("DELETE FROM tests WHERE id = %s", (test_id,))
            conn.commit()
            cur2.close()
            flash("Test deleted successfully.", "success")
        else:
            flash("Test not found.", "danger")

        cur.close()
        conn.close()
        return redirect(url_for("admin_tests"))

    except Exception as e:
        return f"❌ Delete test error: {str(e)}"


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