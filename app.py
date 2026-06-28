from flask import(Flask, render_template, request, redirect, session, flash, send_file,
send_from_directory)
from models import db, Evidence, User, CustodyLog
import os
import hashlib
import uuid
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask import send_file
app = Flask(__name__)

# ---------------- CONFIG ----------------
app.secret_key = "evidence_guard_secret_key"

app.config["UPLOAD_FOLDER"] = "uploads"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///evidence.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)

with app.app_context():
    db.create_all()


# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            return "Username already exists"

        user = User(username=username)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        return redirect("/login")

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):

            session["username"] = username
            flash("Login successful!", "success")

            return redirect("/dashboard")

        return "Invalid Username or Password"

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():

    session.clear()
    flash("Logged out successfully!", "info")

    return redirect("/login")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.all()

    total_evidence = Evidence.query.count()
    total_logs = CustodyLog.query.count()
    total_users = User.query.count()

    return render_template(
        "dashboard.html",
        evidence=evidence,
        total_evidence=total_evidence,
        total_logs=total_logs,
        total_users=total_users
    )


# ---------------- UPLOAD ----------------
# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():

    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":

        if "evidence" not in request.files:
            return "No file selected"

        file = request.files["evidence"]

        if file.filename == "":
            return "Please select a file"

        # Generate unique filename
        unique_name = str(uuid.uuid4()) + "_" + file.filename

        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            unique_name
        )

        file.save(filepath)

        # Generate SHA-256 hash
        sha256 = hashlib.sha256()

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(4096)

                if not chunk:
                    break

                sha256.update(chunk)

        file_hash = sha256.hexdigest()

        # Save evidence
        new_file = Evidence(
            filename=unique_name,
            file_hash=file_hash
        )

        db.session.add(new_file)
        db.session.commit()

        # Save custody log
        log = CustodyLog(
            evidence_id=new_file.id,
            action="Uploaded",
            username=session["username"]
        )

        db.session.add(log)
        db.session.commit()

        flash("Evidence uploaded successfully!", "success")

        return redirect("/dashboard")

    return render_template("upload.html")
# ---------------- VERIFY ----------------
@app.route("/verify/<int:id>")
def verify(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        evidence.filename
    )

    if not os.path.exists(filepath):
        return "File not found"

    sha256 = hashlib.sha256()

    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(4096)

            if not chunk:
                break

            sha256.update(chunk)

    current_hash = sha256.hexdigest()

    if current_hash == evidence.file_hash:
        status = "✅ Evidence Verified"
    else:
        status = "❌ Evidence Modified"

    # Chain of Custody Log
    log = CustodyLog(
        evidence_id=evidence.id,
        action="Verified",
        username=session["username"]
    )

    db.session.add(log)
    db.session.commit()
    flash("Evidence verified successfully!", "success")

    return render_template(
        "result.html",
        filename=evidence.filename,
        file_hash=current_hash,
        status=status
    )


# ---------------- LOGS ----------------
@app.route("/logs")
def logs():

    if "username" not in session:
        return redirect("/login")

    logs = CustodyLog.query.all()

    return render_template(
        "logs.html",
        logs=logs
    )


# ---------------- RUN ----------------
@app.route("/search", methods=["GET"])
def search():

    if "username" not in session:
        return redirect("/login")

    query = request.args.get("query")

    if query:
        evidence = Evidence.query.filter(
            Evidence.filename.ilike(f"%{query}%")
        ).all()
    else:
        evidence = Evidence.query.all()

    return render_template(
        "search.html",
        evidence=evidence,
        query=query
    )
@app.route("/download/<int:id>")
def download(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    pdf_name = f"Evidence_{evidence.id}.pdf"

    c = canvas.Canvas(pdf_name, pagesize=letter)

    c.setFont("Helvetica-Bold", 18)
    c.drawString(180, 760, "Evidence Report")

    c.setFont("Helvetica", 12)

    c.drawString(50,720,f"Evidence ID : {evidence.id}")
    c.drawString(50,700,f"Filename : {evidence.filename}")
    c.drawString(50,680,f"SHA256 Hash : {evidence.file_hash}")
    c.drawString(50,660,f"Uploaded : {evidence.upload_time}")

    y = 620

    c.setFont("Helvetica-Bold",14)
    c.drawString(50,y,"Chain of Custody")

    y -= 30

    logs = CustodyLog.query.filter_by(
        evidence_id=evidence.id
    ).all()

    c.setFont("Helvetica",12)

    for log in logs:

        c.drawString(
            50,
            y,
            f"{log.timestamp} | {log.action} | {log.username}"
        )

        y -= 20

    c.save()

    return send_file(
        pdf_name,
        as_attachment=True
    )
from flask import send_from_directory

@app.route("/view/<int:id>")
def view_file(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        evidence.filename
    )
@app.route("/details/<int:id>")
def details(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    logs = CustodyLog.query.filter_by(
        evidence_id=evidence.id
    ).all()

    return render_template(
        "details.html",
        evidence=evidence,
        logs=logs
    )
@app.route("/delete/<int:id>")
def delete(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    filepath = os.path.join(
        app.config["UPLOAD_FOLDER"],
        evidence.filename
    )

    if os.path.exists(filepath):
        os.remove(filepath)

    CustodyLog.query.filter_by(
        evidence_id=evidence.id
    ).delete()

    db.session.delete(evidence)
    db.session.commit()

    flash("Evidence deleted successfully!", "danger")
    return redirect("/dashboard")

# ---------------- EDIT EVIDENCE ----------------
# ---------------- EDIT EVIDENCE ----------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    if request.method == "POST":

        evidence.filename = request.form["filename"]

        db.session.commit()

        # Add custody log
        log = CustodyLog(
            evidence_id=evidence.id,
            action="Edited",
            username=session["username"]
        )

        db.session.add(log)
        db.session.commit()

        flash("Evidence updated successfully!", "success")
        return redirect("/dashboard")
    return render_template(
        "edit.html",
        evidence=evidence
    )
# ---------------- HISTORY ----------------
@app.route("/history/<int:id>")
def history(id):

    if "username" not in session:
        return redirect("/login")

    evidence = Evidence.query.get_or_404(id)

    logs = CustodyLog.query.filter_by(
        evidence_id=evidence.id
    ).order_by(CustodyLog.timestamp.desc()).all()

    return render_template(
        "history.html",
        evidence=evidence,
        logs=logs
    )
@app.route("/about")
def about():

    if "username" not in session:
        return redirect("/login")

    return render_template("about.html")
@app.route("/profile")
def profile():

    if "username" not in session:
        return redirect("/login")

    return render_template(
        "profile.html",
        username=session["username"]
    )
@app.route("/contact", methods=["GET", "POST"])
def contact():

    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":
        return "<h3>Thank you! Your message has been received.</h3>"

    return render_template("contact.html")

@app.route("/settings", methods=["GET", "POST"])
def settings():

    if "username" not in session:
        return redirect("/login")

    user = User.query.filter_by(username=session["username"]).first()

    if request.method == "POST":

        current = request.form["current_password"]
        new = request.form["new_password"]

        if not user.check_password(current):
            return "Current password is incorrect."

        user.set_password(new)
        db.session.commit()

        flash("Password changed successfully!", "success")
        return redirect("/profile")

    return render_template("settings.html")
@app.route("/admin")
def admin():

    if "username" not in session:
        return redirect("/login")

    total_users = User.query.count()
    total_evidence = Evidence.query.count()
    total_logs = CustodyLog.query.count()

    recent_logs = CustodyLog.query.order_by(
        CustodyLog.timestamp.desc()
    ).limit(10).all()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_evidence=total_evidence,
        total_logs=total_logs,
        recent_logs=recent_logs
    )
# ---------------- USERS ----------------
@app.route("/users")
def users():

    if "username" not in session:
        return redirect("/login")

    users = User.query.all()

    return render_template(
        "users.html",
        users=users
    )
# ---------------- DATABASE BACKUP ----------------
@app.route("/backup")
def backup():

    if "username" not in session:
        return redirect("/login")

    db_path = os.path.join("instance", "evidence.db")

    return send_file(
        db_path,
        as_attachment=True,
        download_name="EvidenceGuard_Backup.db"
    )
# ---------------- REPORTS ----------------
@app.route("/reports")
def reports():

    if "username" not in session:
        return redirect("/login")

    return render_template(
        "reports.html",
        total_users=User.query.count(),
        total_evidence=Evidence.query.count(),
        total_logs=CustodyLog.query.count()
    )
# ---------------- SYSTEM INFO ----------------
@app.route("/system")
def system():

    if "username" not in session:
        return redirect("/login")

    return render_template("system.html")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)