from flask import Flask, render_template, request, redirect, url_for, session
from database import get_connection, create_tables

app = Flask(__name__)

# Secret key is required for Flask sessions.
# Change this to your own random secret before production.
app.secret_key = "studyplanner-development-secret-key"

create_tables()


def get_logged_in_student():
    """Return the currently logged-in student, or None."""
    student_id = session.get("student_id")

    if not student_id:
        return None

    connection = get_connection()

    student = connection.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    connection.close()

    return student


def login_required():
    """Redirect to login if no student is logged in."""
    if "student_id" not in session:
        return redirect(url_for("login"))

    return None


@app.route("/")
def home():
    if "student_id" in session:
        return redirect(url_for("dashboard"))

    return """
    <h1>AI Study Planner</h1>

    <a href="/register">Student Registration</a>
    <br><br>

    <a href="/login">Student Login</a>
    """


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        course = request.form["course"]
        semester = request.form["semester"]

        connection = get_connection()

        try:

            connection.execute(
                """
                INSERT INTO students
                (name, email, password, course, semester)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, password, course, semester)
            )

            connection.commit()

            return """
            <h1>Registration Successful!</h1>
            <p>Your account has been created.</p>
            <a href="/login">Go to Login</a>
            """

        except Exception as error:

            return f"""
            <h1>Registration Failed</h1>
            <p>{error}</p>
            <a href="/register">Go Back</a>
            """

        finally:
            connection.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = get_connection()

        student = connection.execute(
            """
            SELECT *
            FROM students
            WHERE email = ? AND password = ?
            """,
            (email, password)
        ).fetchone()

        connection.close()

        if student:

            session["student_id"] = student["id"]
            session["student_name"] = student["name"]

            return redirect(url_for("dashboard"))

        return """
        <h1>Login Failed</h1>

        <p>Invalid email or password.</p>

        <a href="/login">Try Again</a>
        """

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():

    redirect_response = login_required()

    if redirect_response:
        return redirect_response

    student = get_logged_in_student()

    if not student:
        session.clear()
        return redirect(url_for("login"))

    student_id = student["id"]

    connection = get_connection()

    subjects = connection.execute(
        """
        SELECT
            subjects.id,
            subjects.student_id,
            subjects.subject_name,
            subjects.total_hours,
            COALESCE(
                SUM(
                    CASE
                        WHEN tasks.completed = 1
                        THEN tasks.estimated_hours
                        ELSE 0
                    END
                ),
                0
            ) AS completed_hours
        FROM subjects
        LEFT JOIN tasks
            ON subjects.id = tasks.subject_id
        WHERE subjects.student_id = ?
        GROUP BY
            subjects.id,
            subjects.student_id,
            subjects.subject_name,
            subjects.total_hours
        """,
        (student_id,)
    ).fetchall()

    tasks = connection.execute(
        """
        SELECT
            tasks.*,
            subjects.subject_name
        FROM tasks
        JOIN subjects
            ON tasks.subject_id = subjects.id
        WHERE tasks.student_id = ?
        ORDER BY tasks.completed ASC, tasks.id ASC
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    total_tasks = len(tasks)

    completed_tasks = sum(
        1
        for task in tasks
        if task["completed"] == 1
    )

    pending_tasks = total_tasks - completed_tasks

    total_study_hours = sum(
        float(task["estimated_hours"])
        for task in tasks
    )

    completed_study_hours = sum(
        float(task["estimated_hours"])
        for task in tasks
        if task["completed"] == 1
    )

    if total_tasks > 0:
        progress = (completed_tasks / total_tasks) * 100
    else:
        progress = 0

    return render_template(
        "dashboard.html",
        student=student,
        subjects=subjects,
        tasks=tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        total_study_hours=total_study_hours,
        completed_study_hours=completed_study_hours,
        progress=progress
    )

@app.route("/subjects", methods=["GET", "POST"])
def subjects():

    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    connection = get_connection()

    if request.method == "POST":

        subject_name = request.form["subject_name"]
        total_hours = request.form["total_hours"]

        connection.execute(
            """
            INSERT INTO subjects
            (student_id, subject_name, total_hours)
            VALUES (?, ?, ?)
            """,
            (
                student_id,
                subject_name,
                total_hours
            )
        )

        connection.commit()

    subjects_list = connection.execute(
    """
    SELECT
        subjects.id,
        subjects.student_id,
        subjects.subject_name,
        subjects.total_hours,
        COALESCE(
            SUM(
                CASE
                    WHEN tasks.completed = 1
                    THEN tasks.estimated_hours
                    ELSE 0
                END
            ),
            0
        ) AS completed_hours
    FROM subjects
    LEFT JOIN tasks
        ON subjects.id = tasks.subject_id
    WHERE subjects.student_id = ?
    GROUP BY
        subjects.id,
        subjects.student_id,
        subjects.subject_name,
        subjects.total_hours
    ORDER BY subjects.id DESC
    """,
    (student_id,)
).fetchall()

    connection.close()

    return render_template(
        "subjects.html",
        subjects=subjects_list
    )

def tasks():

    redirect_response = login_required()

    if redirect_response:
        return redirect_response

    student_id = session["student_id"]

    connection = get_connection()

    if request.method == "POST":

        subject_id = request.form["subject_id"]
        task_name = request.form["task_name"]
        estimated_hours = request.form["estimated_hours"]

        # Make sure the selected subject belongs to this student.
        subject = connection.execute(
            """
            SELECT id
            FROM subjects
            WHERE id = ? AND student_id = ?
            """,
            (subject_id, student_id)
        ).fetchone()

        if not subject:
            connection.close()

            return """
            <h1>Invalid Subject</h1>
            <p>This subject does not belong to your account.</p>
            <a href="/tasks">Go Back</a>
            """

        connection.execute(
            """
            INSERT INTO tasks
            (student_id, subject_id, task_name, estimated_hours)
            VALUES (?, ?, ?, ?)
            """,
            (
                student_id,
                subject_id,
                task_name,
                estimated_hours
            )
        )

        connection.commit()
        connection.close()

        return redirect(url_for("dashboard"))

    subjects_list = connection.execute(
        """
        SELECT *
        FROM subjects
        WHERE student_id = ?
        ORDER BY subject_name
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    return render_template(
        "tasks.html",
        subjects=subjects_list
    )
@app.route("/edit_subject/<int:subject_id>", methods=["GET", "POST"])
def edit_subject(subject_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    connection = get_connection()

    subject = connection.execute(
        """
        SELECT *
        FROM subjects
        WHERE id = ? AND student_id = ?
        """,
        (subject_id, student_id)
    ).fetchone()

    if not subject:
        connection.close()
        return "Subject not found."

    if request.method == "POST":

        subject_name = request.form["subject_name"]
        total_hours = request.form["total_hours"]

        connection.execute(
            """
            UPDATE subjects
            SET subject_name = ?, total_hours = ?
            WHERE id = ? AND student_id = ?
            """,
            (
                subject_name,
                total_hours,
                subject_id,
                student_id
            )
        )

        connection.commit()
        connection.close()

        return redirect(url_for("subjects"))

    connection.close()

    return render_template(
        "edit_subject.html",
        subject=subject
    )

@app.route("/delete_subject/<int:subject_id>", methods=["POST"])
def delete_subject(subject_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    connection = get_connection()

    # Make sure this subject belongs to the logged-in student
    subject = connection.execute(
        """
        SELECT id
        FROM subjects
        WHERE id = ? AND student_id = ?
        """,
        (subject_id, student_id)
    ).fetchone()

    if not subject:
        connection.close()
        return "Subject not found."

    # Delete tasks belonging to this subject first
    connection.execute(
        """
        DELETE FROM tasks
        WHERE subject_id = ? AND student_id = ?
        """,
        (subject_id, student_id)
    )

    # Then delete the subject
    connection.execute(
        """
        DELETE FROM subjects
        WHERE id = ? AND student_id = ?
        """,
        (subject_id, student_id)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("subjects"))

@app.route("/tasks", methods=["GET", "POST"])
def tasks():

    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    connection = get_connection()

    if request.method == "POST":

        subject_id = request.form["subject_id"]
        task_name = request.form["task_name"]
        estimated_hours = request.form["estimated_hours"]

        # Make sure the selected subject belongs to this student
        subject = connection.execute(
            """
            SELECT id
            FROM subjects
            WHERE id = ? AND student_id = ?
            """,
            (subject_id, student_id)
        ).fetchone()

        if not subject:
            connection.close()
            return "Invalid subject."

        connection.execute(
            """
            INSERT INTO tasks
            (student_id, subject_id, task_name, estimated_hours)
            VALUES (?, ?, ?, ?)
            """,
            (
                student_id,
                subject_id,
                task_name,
                estimated_hours
            )
        )

        connection.commit()

    subjects_list = connection.execute(
        """
        SELECT *
        FROM subjects
        WHERE student_id = ?
        ORDER BY subject_name ASC
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    return render_template(
        "tasks.html",
        subjects=subjects_list
    )
@app.route("/edit_task/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_connection()

    task = connection.execute(
        """
        SELECT *
        FROM tasks
        WHERE id = ? AND student_id = ?
        """,
        (task_id, session["student_id"])
    ).fetchone()

    if not task:
        connection.close()
        return "Task not found."

    if request.method == "POST":

        task_name = request.form["task_name"]
        estimated_hours = request.form["estimated_hours"]

        connection.execute(
            """
            UPDATE tasks
            SET task_name = ?, estimated_hours = ?
            WHERE id = ? AND student_id = ?
            """,
            (
                task_name,
                estimated_hours,
                task_id,
                session["student_id"]
            )
        )

        connection.commit()
        connection.close()

        return redirect(url_for("dashboard"))

    connection.close()

    return render_template(
        "edit_task.html",
        task=task
    )

@app.route("/delete_task/<int:task_id>", methods=["POST"])
def delete_task(task_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_connection()

    connection.execute(
        """
        DELETE FROM tasks
        WHERE id = ? AND student_id = ?
        """,
        (task_id, session["student_id"])
    )

    connection.commit()
    connection.close()

    return redirect(url_for("dashboard"))

@app.route("/complete_task/<int:task_id>")

@app.route("/complete_task/<int:task_id>")
def complete_task(task_id):

    redirect_response = login_required()

    if redirect_response:
        return redirect_response

    student_id = session["student_id"]

    connection = get_connection()

    connection.execute(
        """
        UPDATE tasks
        SET completed = 1
        WHERE id = ? AND student_id = ?
        """,
        (task_id, student_id)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("dashboard"))


@app.route("/schedule")
def schedule():

    redirect_response = login_required()

    if redirect_response:
        return redirect_response

    student_id = session["student_id"]

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT
            tasks.*,
            subjects.subject_name
        FROM tasks
        JOIN subjects
            ON tasks.subject_id = subjects.id
        WHERE tasks.student_id = ?
        ORDER BY tasks.completed ASC, tasks.id ASC
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    return render_template(
        "schedule.html",
        tasks=tasks
    )


@app.route("/recommendations")
def recommendations():

    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT tasks.*, subjects.subject_name,
               subjects.total_hours AS subject_total,
               subjects.completed_hours AS subject_completed
        FROM tasks
        JOIN subjects ON tasks.subject_id = subjects.id
        WHERE tasks.student_id = ?
        """,
        (student_id,)
    ).fetchall()

    subjects = connection.execute(
        """
        SELECT *
        FROM subjects
        WHERE student_id = ?
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    recommendations = []

    pending_tasks = [
        task for task in tasks
        if task["completed"] == 0
    ]

    completed_tasks = [
        task for task in tasks
        if task["completed"] == 1
    ]

    if not tasks:
        recommendations.append(
            "📚 Start by adding your first study task. "
            "Small daily goals help build consistency."
        )

    elif pending_tasks:

        def priority_score(task):

            estimated = float(task["estimated_hours"] or 0)

            total = float(task["subject_total"] or 0)
            completed = float(task["subject_completed"] or 0)

            if total > 0:
                progress = completed / total
            else:
                progress = 0

            low_progress_score = (1 - progress) * 50
            duration_score = min(estimated * 10, 30)

            return low_progress_score + duration_score

        best_task = max(
            pending_tasks,
            key=priority_score
        )

        score = priority_score(best_task)

        recommendations.append(
            f"🎯 Study '{best_task['task_name']}' next. "
            f"It has a priority score of {score:.0f}/80."
        )

        recommendations.append(
            f"📚 Subject: {best_task['subject_name']}. "
            f"Estimated time: "
            f"{float(best_task['estimated_hours'] or 0):.1f} hours."
        )

        total = float(best_task["subject_total"] or 0)
        completed = float(best_task["subject_completed"] or 0)

        if total > 0:
            progress = (completed / total) * 100

            recommendations.append(
                f"📈 {best_task['subject_name']} is currently "
                f"{progress:.0f}% complete. "
                "Improving this subject should be a priority."
            )

        if float(best_task["estimated_hours"] or 0) >= 2:
            recommendations.append(
                "⏱️ This is a large task. "
                "Try studying it in 25–50 minute sessions "
                "with short breaks."
            )

        if len(pending_tasks) > 1:
            recommendations.append(
                f"📋 You have {len(pending_tasks)} pending tasks. "
                "Finish the recommended task before moving to the next one."
            )

    if completed_tasks:
        recommendations.append(
            f"✅ You have completed {len(completed_tasks)} task(s). "
            "Keep your momentum going!"
        )

    for subject in subjects:

        total = float(subject["total_hours"] or 0)
        completed = float(subject["completed_hours"] or 0)

        if total > 0:

            progress = (completed / total) * 100

            if progress == 0:
                recommendations.append(
                    f"🚨 {subject['subject_name']} has 0% progress. "
                    "Consider studying this subject today."
                )

            elif progress >= 75:
                recommendations.append(
                    f"🌟 Excellent progress in "
                    f"{subject['subject_name']} ({progress:.0f}%). "
                    "You're close to your goal!"
                )

    return render_template(
        "recommendations.html",
        recommendations=recommendations
    )


def recommendations():

    redirect_response = login_required()

    if redirect_response:
        return redirect_response

    student_id = session["student_id"]

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT
            tasks.*,
            subjects.subject_name
        FROM tasks
        JOIN subjects
            ON tasks.subject_id = subjects.id
        WHERE tasks.student_id = ?
        ORDER BY tasks.completed ASC, tasks.id ASC
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    recommendations_list = []

    if not tasks:

        recommendations_list.append(
            "Add your first study task so I can create "
            "a personalized recommendation."
        )

    else:

        completed = sum(
            1
            for task in tasks
            if task["completed"] == 1
        )

        pending = len(tasks) - completed

        if pending > 0:

            recommendations_list.append(
                f"You have {pending} pending study task(s). "
                "Try completing one task today before "
                "starting a new topic."
            )

        if completed > 0:

            recommendations_list.append(
                f"Great work! You have completed {completed} "
                "study task(s). Keep up the consistency."
            )

        for task in tasks:

            if task["completed"] == 0:

                recommendations_list.append(
                    f"Focus on {task['subject_name']}: "
                    f"{task['task_name']} for about "
                    f"{task['estimated_hours']} hour(s)."
                )

    return render_template(
        "recommendations.html",
        recommendations=recommendations_list
    )



    session.clear()

    return redirect(url_for("login"))
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/timer")
def timer():
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT tasks.*, subjects.subject_name
        FROM tasks
        JOIN subjects ON tasks.subject_id = subjects.id
        WHERE tasks.student_id = ?
        ORDER BY tasks.completed ASC, tasks.id ASC
        """,
        (session["student_id"],)
    ).fetchall()

    connection.close()

    return render_template("timer.html", tasks=tasks)


@app.route("/save_session", methods=["POST"])
def save_session():
    if "student_id" not in session:
        return redirect(url_for("login"))

    task_id = request.form.get("task_id")
    duration = request.form.get("duration")

    try:
        task_id = int(task_id)
        duration = int(duration)
    except (TypeError, ValueError):
        return redirect(url_for("timer"))

    if duration <= 0:
        return redirect(url_for("timer"))

    connection = get_connection()

    task = connection.execute(
        """
        SELECT id
        FROM tasks
        WHERE id = ? AND student_id = ?
        """,
        (task_id, session["student_id"])
    ).fetchone()

    if task:
        connection.execute(
            """
            INSERT INTO study_sessions
            (student_id, task_id, duration_minutes, session_date)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (session["student_id"], task_id, duration)
        )

        connection.execute(
            """
            UPDATE tasks
            SET actual_hours = COALESCE(actual_hours, 0) + ?
            WHERE id = ? AND student_id = ?
            """,
            (duration / 60, task_id, session["student_id"])
        )

    connection.commit()
    connection.close()

    return redirect(url_for("timer"))

@app.route("/analytics")
def analytics():

    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]

    connection = get_connection()

    stats = connection.execute(
        """
        SELECT
            COUNT(*) AS total_sessions,
            COALESCE(SUM(duration_minutes), 0) AS total_minutes
        FROM study_sessions
        WHERE student_id = ?
        """,
        (student_id,)
    ).fetchone()

    tasks = connection.execute(
        """
        SELECT
            COUNT(*) AS total_tasks,
            COALESCE(SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END), 0)
                AS completed_tasks
        FROM tasks
        WHERE student_id = ?
        """,
        (student_id,)
    ).fetchone()

    subjects = connection.execute(
        """
        SELECT
            subjects.subject_name,
            subjects.total_hours,
            COALESCE(
                SUM(
                    CASE
                        WHEN tasks.completed = 1
                        THEN tasks.estimated_hours
                        ELSE 0
                    END
                ), 0
            ) AS completed_hours
        FROM subjects
        LEFT JOIN tasks
            ON subjects.id = tasks.subject_id
        WHERE subjects.student_id = ?
        GROUP BY subjects.id
        ORDER BY subjects.subject_name
        """,
        (student_id,)
    ).fetchall()

    recent_sessions = connection.execute(
        """
        SELECT
            study_sessions.duration_minutes,
            study_sessions.session_date,
            tasks.task_name,
            subjects.subject_name
        FROM study_sessions
        JOIN tasks
            ON study_sessions.task_id = tasks.id
        JOIN subjects
            ON tasks.subject_id = subjects.id
        WHERE study_sessions.student_id = ?
        ORDER BY study_sessions.id DESC
        LIMIT 10
        """,
        (student_id,)
    ).fetchall()

    connection.close()

    total_minutes = stats["total_minutes"]
    total_hours = total_minutes / 60

    total_tasks = tasks["total_tasks"]
    completed_tasks = tasks["completed_tasks"]

    task_progress = (
        (completed_tasks / total_tasks) * 100
        if total_tasks > 0 else 0
    )

    return render_template(
        "analytics.html",
        total_sessions=stats["total_sessions"],
        total_minutes=total_minutes,
        total_hours=total_hours,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        task_progress=task_progress,
        subjects=subjects,
        recent_sessions=recent_sessions
    )

if __name__ == "__main__":
    app.run(debug=True)

