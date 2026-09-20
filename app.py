from flask import Flask, render_template, request, redirect, session
from datetime import date, timedelta , datetime
import mysql.connector

app = Flask(__name__)
app.secret_key = "caretrack_secret_key"
def get_db_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="thrishnapc2004",
        database="caretrack"
    )
def auto_cancel_missed_appointments(cursor):

    cursor.execute("""
        UPDATE tokens t
        JOIN appointments a
            ON t.appointment_id = a.appointment_id
        SET
            t.status = 'cancelled',
            a.status = 'cancelled'
        WHERE a.status = 'booked'
          AND t.status = 'waiting'
          AND (
                a.appointment_date < CURDATE()
                OR (
                    a.appointment_date = CURDATE()
                    AND ADDTIME(
                        a.appointment_time,
                        '00:10:00'
                    ) <= CURTIME()
                )
          )
    """)

@app.route("/", methods=["GET", "POST"])
def home():

    message = ""

    if request.method == "POST":

        email = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id, name, email, password, role
            FROM users
            WHERE email = %s
              AND password = %s
              AND role = %s
        """, (email, password, role))

        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user:

            session["user_id"] = user["user_id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect("/admin_dashboard")

            elif user["role"] == "doctor":
                return redirect("/doctor_dashboard")

            elif user["role"] == "patient":
                return redirect("/patient_dashboard")

        else:
            message = "Invalid email, password or role."

    return render_template("login.html", message=message)


@app.route("/patients", methods=["GET", "POST"])
def patients():

    db = get_db_connection()
    cursor = db.cursor()

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        age = request.form.get("age")
        gender = request.form.get("gender")
        address = request.form.get("address")
        try:
            # Create user account
            password = name + "123"

            cursor.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (%s, %s, %s, %s)
            """, (name, email, password, "patient"))

            user_id = cursor.lastrowid

            # Create patient record
            cursor.execute("""
                INSERT INTO patients
                (user_id, date_of_birth, gender, phone, address)
                VALUES
                (%s, DATE_SUB(CURDATE(), INTERVAL %s YEAR), %s, %s, %s)
            """, (user_id, age, gender, phone, address))

            db.commit()

            cursor.close()
            db.close()

            return render_template(
                "login.html",
                message="Registration Successful! Please login.",
                success=True
            )

        except Exception as e:
            db.rollback()
            print("Error:", e)

    cursor.close()
    db.close()

    return render_template("patients.html")
@app.route("/appointments", methods=["GET", "POST"])
def appointments():

    if session.get("role") not in ["admin", "patient"]:
        return redirect("/")

    message = ""
    message_type = ""

    db = get_db_connection()
    cursor = db.cursor(buffered=True)

    # Get patients
    if session.get("role") == "patient":

        cursor.execute("""
            SELECT
                p.patient_id,
                u.name
            FROM patients p
            JOIN users u
                ON p.user_id = u.user_id
            WHERE p.user_id = %s
        """, (session["user_id"],))

    else:

        cursor.execute("""
            SELECT
                p.patient_id,
                u.name
            FROM patients p
            JOIN users u
                ON p.user_id = u.user_id
            ORDER BY u.name
        """)

    patients = cursor.fetchall()


    # Get doctors
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()


    # Book appointment
    if request.method == "POST":

        doctor_id = request.form["doctor_id"]
        appointment_date = request.form["appointment_date"]
        appointment_time = request.form["appointment_time"]

        # Patient can book only for own account
        if session.get("role") == "patient":

            cursor.execute("""
                SELECT patient_id
                FROM patients
                WHERE user_id = %s
            """, (session["user_id"],))

            patient = cursor.fetchone()

            if not patient:
                cursor.close()
                db.close()
                return redirect("/")

            patient_id = patient[0]

        else:

            patient_id = request.form["patient_id"]


        # Check whether the selected doctor/time is already booked
        cursor.execute("""
            SELECT appointment_id
            FROM appointments
            WHERE doctor_id = %s
              AND appointment_date = %s
              AND appointment_time = %s
              AND status = 'booked'
        """, (
            doctor_id,
            appointment_date,
            appointment_time
        ))

        existing = cursor.fetchone()


        if existing:

            message = "This time slot is already booked. Please select another time."
            message_type = "error"

        else:

            # Get next token number
            cursor.execute("""
                SELECT COALESCE(MAX(token_number), 100) + 1
                FROM tokens
            """)

            token_result = cursor.fetchone()
            token_number = token_result[0]


            # Insert appointment
            cursor.execute("""
                INSERT INTO appointments
                (
                    patient_id,
                    doctor_id,
                    appointment_date,
                    appointment_time,
                    status
                )
                VALUES (%s, %s, %s, %s, 'booked')
            """, (
                patient_id,
                doctor_id,
                appointment_date,
                appointment_time
            ))

            appointment_id = cursor.lastrowid


            # Insert token
            cursor.execute("""
                INSERT INTO tokens
                (
                    appointment_id,
                    token_number,
                    status
                )
                VALUES (%s, %s, 'waiting')
            """, (
                appointment_id,
                token_number
            ))

            db.commit()

            message = "Appointment booked successfully."
            message_type = "success"


    # Appointment information
    if session.get("role") == "patient":

        cursor.execute("""
            SELECT
                a.appointment_id,
                pu.name AS patient_name,
                du.name AS doctor_name,
                DATE_FORMAT(a.appointment_date, '%d-%m-%Y') AS appointment_date,
               DATE_FORMAT(a.appointment_time, '%h:%i %p') AS appointment_time,
                t.token_number,
                a.status
            FROM appointments a
            JOIN patients p
                ON a.patient_id = p.patient_id
            JOIN users pu
                ON p.user_id = pu.user_id
            JOIN doctors d
                ON a.doctor_id = d.doctor_id
            JOIN users du
                ON d.user_id = du.user_id
            LEFT JOIN tokens t
                ON a.appointment_id = t.appointment_id
            WHERE p.user_id = %s
            ORDER BY a.appointment_date, a.appointment_time
        """, (session["user_id"],))

    else:

        cursor.execute("""
            SELECT
                a.appointment_id,
                pu.name AS patient_name,
                du.name AS doctor_name,
                a.appointment_date,
                a.appointment_time,
                t.token_number,
                a.status
            FROM appointments a
            JOIN patients p
                ON a.patient_id = p.patient_id
            JOIN users pu
                ON p.user_id = pu.user_id
            JOIN doctors d
                ON a.doctor_id = d.doctor_id
            JOIN users du
                ON d.user_id = du.user_id
            LEFT JOIN tokens t
                ON a.appointment_id = t.appointment_id
            ORDER BY a.appointment_date, a.appointment_time
        """)

    appointments = cursor.fetchall()


    cursor.close()
    db.close()


    return render_template(
        "appointments.html",
        patients=patients,
        doctors=doctors,
        appointments=appointments,
        message=message,
        message_type=message_type
    )
@app.route("/consultation")
def consultation():

    if session.get("role") != "doctor":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get logged-in doctor
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name AS doctor_name
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE d.user_id = %s
          AND u.role = 'doctor'
    """, (session["user_id"],))

    doctor = cursor.fetchone()

    if not doctor:
        cursor.close()
        db.close()
        return redirect("/doctor_dashboard")

    doctor_id = doctor["doctor_id"]
    # Automatically cancel missed waiting appointments
    cursor.execute("""
            UPDATE tokens t
            JOIN appointments a
                ON t.appointment_id = a.appointment_id
            SET
                t.status = 'cancelled',
                a.status = 'cancelled'
            WHERE a.doctor_id = %s
            AND a.status = 'booked'
            AND t.status = 'waiting'
            AND (
                    a.appointment_date < CURDATE()
                    OR (
                        a.appointment_date = CURDATE()
                        AND ADDTIME(a.appointment_time, '00:10:00') <= CURTIME()
                    )
                )
        """, (doctor_id,))

    db.commit()
    # Get all appointments for this doctor
    cursor.execute("""
        SELECT
            a.appointment_id,
            pu.name AS patient_name,

            DATE_FORMAT(
                a.appointment_date,
                '%d-%m-%Y'
            ) AS appointment_date,

            DAYNAME(a.appointment_date) AS appointment_day,

            TIME_FORMAT(
                a.appointment_time,
                '%h:%i %p'
            ) AS appointment_time,

            t.token_number,
            t.status AS token_status,
            a.status AS appointment_status

        FROM appointments a

        JOIN patients p
            ON a.patient_id = p.patient_id

        JOIN users pu
            ON p.user_id = pu.user_id

        LEFT JOIN tokens t
            ON a.appointment_id = t.appointment_id

        WHERE a.doctor_id = %s

        ORDER BY
            a.appointment_date,
            a.appointment_time,
            t.token_number
    """, (doctor_id,))

    appointments = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "consultation.html",
        doctor=doctor,
        appointments=appointments
    )


@app.route("/consultation/<int:appointment_id>", methods=["GET", "POST"])
def consultation_detail(appointment_id):

    if session.get("role") != "doctor":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    try:

        # ------------------------------------------------
        # LOGGED-IN DOCTOR
        # ------------------------------------------------

        cursor.execute("""
            SELECT
                d.doctor_id,
                u.name AS doctor_name
            FROM doctors d
            JOIN users u
                ON d.user_id = u.user_id
            WHERE d.user_id = %s
              AND u.role = 'doctor'
        """, (session["user_id"],))

        doctor = cursor.fetchone()

        if not doctor:
            return redirect("/doctor_dashboard")

        doctor_id = doctor["doctor_id"]

        # ------------------------------------------------
        # SELECTED APPOINTMENT
        # ------------------------------------------------

        cursor.execute("""
            SELECT
                a.appointment_id,
                a.patient_id,
                a.doctor_id,
                a.appointment_date,
                a.appointment_time,
                a.status AS appointment_status,

                pu.name AS patient_name,

                t.token_number,
                t.status AS token_status

            FROM appointments a

            JOIN patients p
                ON a.patient_id = p.patient_id

            JOIN users pu
                ON p.user_id = pu.user_id

            LEFT JOIN tokens t
                ON a.appointment_id = t.appointment_id

            WHERE a.appointment_id = %s
              AND a.doctor_id = %s
        """, (appointment_id, doctor_id))

        appointment = cursor.fetchone()

        if not appointment:
            return redirect("/doctor_appointments")
        

        # ------------------------------------------------
        # CONSULTATION ONLY ON APPOINTMENT DATE
        # ------------------------------------------------

        today = date.today()

        if appointment["appointment_date"] != today:
            return redirect("/doctor_appointments")

        # ------------------------------------------------
        # COMPLETED / CANCELLED CANNOT BE CONSULTED AGAIN
        # ------------------------------------------------

        if appointment["appointment_status"] == "completed":
            return redirect("/doctor_appointments")

        if appointment["token_status"] == "cancelled":
            return redirect("/doctor_appointments")

        # ------------------------------------------------
        # SAVE CONSULTATION
        # ------------------------------------------------

        message = ""
        success = False

        if request.method == "POST":

            diagnosis = request.form.get(
                "diagnosis", ""
            ).strip()

            prescription = request.form.get(
                "prescription", ""
            ).strip()

            treatment = request.form.get(
                "treatment", ""
            ).strip()

            # --------------------------------------------
            # SAVE MEDICAL RECORD
            # --------------------------------------------

            cursor.execute("""
                INSERT INTO medical_records
                (
                    patient_id,
                    doctor_id,
                    diagnosis,
                    prescription,
                    treatment,
                    record_date
                )
                VALUES (%s, %s, %s, %s, %s, CURDATE())
            """, (
                appointment["patient_id"],
                doctor_id,
                diagnosis,
                prescription,
                treatment
            ))

            # --------------------------------------------
            # COMPLETE TOKEN
            # --------------------------------------------

            cursor.execute("""
                UPDATE tokens
                SET status = 'completed'
                WHERE appointment_id = %s
            """, (appointment_id,))

            # --------------------------------------------
            # COMPLETE APPOINTMENT
            # --------------------------------------------

            cursor.execute("""
                UPDATE appointments
                SET status = 'completed'
                WHERE appointment_id = %s
            """, (appointment_id,))

            db.commit()

            # --------------------------------------------
            # FIND NEXT PATIENT
            # --------------------------------------------

            cursor.execute("""
                SELECT
                    a.appointment_id,
                    pu.name AS patient_name,
                    t.token_number
                FROM appointments a

                JOIN patients p
                    ON a.patient_id = p.patient_id

                JOIN users pu
                    ON p.user_id = pu.user_id

                JOIN tokens t
                    ON a.appointment_id = t.appointment_id

                WHERE a.doctor_id = %s
                  AND a.appointment_date = %s
                  AND a.status != 'completed'
                  AND t.status = 'waiting'

                ORDER BY t.token_number

                LIMIT 1
            """, (doctor_id, today))

            next_patient = cursor.fetchone()

            # --------------------------------------------
            # AUTOMATICALLY OPEN NEXT CONSULTATION
            # --------------------------------------------

            if next_patient:

                return redirect(
                    "/consultation/{}".format(
                        next_patient["appointment_id"]
                    )
                )

            # --------------------------------------------
            # NO MORE PATIENTS
            # --------------------------------------------

            success = True
            message = "Consultation completed successfully. All consultations for today are completed."

        # ------------------------------------------------
        # DATE / DAY
        # ------------------------------------------------

        appointment["appointment_day"] = (
            appointment["appointment_date"].strftime("%A")
        )

        # ------------------------------------------------
        # TIME FORMAT
        # ------------------------------------------------

        appointment_time = appointment["appointment_time"]

        if isinstance(appointment_time, timedelta):

            appointment_time = (
                datetime.min + appointment_time
            ).time()

        appointment["display_time"] = (
            appointment_time.strftime("%I:%M %p")
        )

        return render_template(
            "consultation_details.html",
            appointment=appointment,
            doctor_name=doctor["doctor_name"],
            message=message,
            success=success
        )

    except Exception:
        db.rollback()
        raise

    finally:
        cursor.close()
        db.close()
@app.route("/report")
def report():

    patient_id = request.args.get("patient_id")

    report_data = None
    searched = False

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
    SELECT DISTINCT
        p.patient_id,
        u.name
    FROM patients p
    JOIN users u
        ON p.user_id = u.user_id
    JOIN medical_records mr
        ON mr.patient_id = p.patient_id
    ORDER BY u.name
""")

    patient_list = cursor.fetchall()
    if patient_id:

        searched = True

        cursor.execute("""
            SELECT
                u.name AS patient_name,
                du.name AS doctor_name,
                mr.diagnosis,
                mr.prescription,
                mr.treatment,
                DATE_FORMAT(mr.record_date, '%d-%m-%Y') AS record_date
            FROM medical_records mr
            JOIN patients p
                ON mr.patient_id = p.patient_id
            JOIN users u
                ON p.user_id = u.user_id
            JOIN doctors d
                ON mr.doctor_id = d.doctor_id
            JOIN users du
                ON d.user_id = du.user_id
            WHERE mr.patient_id = %s
            ORDER BY mr.record_id DESC
            LIMIT 1
        """, (patient_id,))

        report_data = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template(
        "report.html",
        patients=patient_list,
        report=report_data,
        searched=searched
    )
@app.route("/medical_records")
def medical_records():

    if session.get("role") == "patient":

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                mr.record_id,
                pu.name AS patient_name,
                du.name AS doctor_name,
                mr.diagnosis,
                mr.prescription,
                mr.treatment,
                mr.record_date
            FROM medical_records mr
            JOIN patients p
                ON mr.patient_id = p.patient_id
            JOIN users pu
                ON p.user_id = pu.user_id
            JOIN doctors d
                ON mr.doctor_id = d.doctor_id
            JOIN users du
                ON d.user_id = du.user_id
            WHERE p.user_id = %s
            ORDER BY mr.record_date DESC
        """, (session["user_id"],))

        records = cursor.fetchall()

        cursor.close()
        db.close()

        return render_template(
            "medical_records.html",
            records=records
        )

    else:

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                mr.record_id,
                pu.name AS patient_name,
                du.name AS doctor_name,
                mr.diagnosis,
                mr.prescription,
                mr.treatment,
                mr.record_date
            FROM medical_records mr
            JOIN patients p
                ON mr.patient_id = p.patient_id
            JOIN users pu
                ON p.user_id = pu.user_id
            JOIN doctors d
                ON mr.doctor_id = d.doctor_id
            JOIN users du
                ON d.user_id = du.user_id
            ORDER BY mr.record_date DESC
        """)

        records = cursor.fetchall()

        cursor.close()
        db.close()

        return render_template(
            "medical_records.html",
            records=records
        )
@app.route("/admin_doctor_manage", methods=["GET", "POST"])
def admin_doctor_manage():

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    message = ""
    message_type = ""
    

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        specialization = request.form.get("specialization", "").strip()
        department = request.form.get("department", "").strip()
        phone = request.form.get("phone", "").strip()

        # New availability fields
        availability_dates = request.form.getlist("availability_date[]")
        start_times = request.form.getlist("start_time[]")
        end_times = request.form.getlist("end_time[]")

        try:

            # Check email already exists
            cursor.execute("""
                SELECT user_id
                FROM users
                WHERE email = %s
            """, (email,))

            existing_user = cursor.fetchone()

            if existing_user:

                message = "A user with this email already exists."
                message_type = "error"

            elif not name or not email or not password:

                message = "Please fill all required doctor details."
                message_type = "error"

            elif len(availability_dates) == 0:

                message = "Please add at least one availability."
                message_type = "error"

            else:

                # Add doctor user
                cursor.execute("""
                    INSERT INTO users
                    (name, email, password, role)
                    VALUES (%s, %s, %s, 'doctor')
                """, (
                    name,
                    email,
                    password
                ))

                user_id = cursor.lastrowid

                # Add doctor profile
                cursor.execute("""
                    INSERT INTO doctors
                    (user_id, specialization, phone, department)
                    VALUES (%s, %s, %s, %s)
                """, (
                    user_id,
                    specialization,
                    phone,
                    department
                ))

                doctor_id = cursor.lastrowid

                # Add all availability rows
                for i in range(len(availability_dates)):

                    availability_date = availability_dates[i]
                    start_time = start_times[i] if i < len(start_times) else ""
                    end_time = end_times[i] if i < len(end_times) else ""

                    if availability_date and start_time and end_time:

                        # Convert selected date to automatic day
                        selected_date = date.fromisoformat(
                            availability_date
                        )

                        day = selected_date.strftime("%A")

                        cursor.execute("""
                            INSERT INTO doctor_schedule
                            (doctor_id, day_of_week, start_time, end_time)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            doctor_id,
                            day,
                            start_time,
                            end_time
                        ))

                db.commit()

                message = "Doctor added successfully."
                message_type = "success"

        except Exception as e:

            db.rollback()

            print("Doctor Add Error:", e)

            message = "Unable to add doctor. Please check the details."
            message_type = "error"

    # Doctor list
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name,
            u.email,
            d.department,
            d.specialization,
            d.phone
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE u.role = 'doctor'
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "admin_doctor_manage.html",
        doctors=doctors,
        message=message,
        message_type=message_type
    )
@app.route("/delete_doctor/<int:doctor_id>", methods=["POST", "GET"])
def delete_doctor(doctor_id):

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Check whether doctor has appointments
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE doctor_id = %s
        """, (doctor_id,))

        appointment_count = cursor.fetchone()[0]

        if appointment_count > 0:
            cursor.close()
            db.close()
            return redirect("/admin_doctor_manage")

        # Delete doctor availability first
        cursor.execute("""
            DELETE FROM doctor_schedule
            WHERE doctor_id = %s
        """, (doctor_id,))

        # Get linked user_id
        cursor.execute("""
            SELECT user_id
            FROM doctors
            WHERE doctor_id = %s
        """, (doctor_id,))

        doctor = cursor.fetchone()

        if doctor:
            user_id = doctor[0]

            # Delete doctor
            cursor.execute("""
                DELETE FROM doctors
                WHERE doctor_id = %s
            """, (doctor_id,))

            # Delete linked doctor user
            cursor.execute("""
                DELETE FROM users
                WHERE user_id = %s
                  AND role = 'doctor'
            """, (user_id,))

        db.commit()

    except Exception as e:
        db.rollback()
        print("Delete doctor error:", e)

    cursor.close()
    db.close()

    return redirect("/admin_doctor_manage")
@app.route("/doctor_availability/<int:doctor_id>", methods=["GET", "POST"])
def doctor_availability(doctor_id):

    if session.get("role") != "admin":
        return redirect("/")

    message = ""
    message_type = ""

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # -------------------------------------------------
    # DOCTOR DETAILS
    # -------------------------------------------------
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name,
            d.department,
            d.specialization
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE d.doctor_id = %s
          AND u.role = 'doctor'
        LIMIT 1
    """, (doctor_id,))

    doctor = cursor.fetchone()

    if not doctor:
        cursor.close()
        db.close()
        return redirect("/admin_doctor_manage")

    # -------------------------------------------------
    # POST ACTIONS
    # -------------------------------------------------
    if request.method == "POST":

        action = request.form.get("action")

        try:

            # =================================================
            # REMOVE AVAILABILITY
            # =================================================
            if action == "remove":

                schedule_id = request.form.get("schedule_id")

                cursor.execute("""
                    DELETE FROM doctor_schedule
                    WHERE schedule_id = %s
                      AND doctor_id = %s
                """, (schedule_id, doctor_id))

                db.commit()

                message = "Availability removed successfully."
                message_type = "success"

            # =================================================
            # UPDATE AVAILABILITY
            # =================================================
            elif action == "update":

                schedule_id = request.form.get("schedule_id")
                selected_date = request.form.get("available_date")
                start_time = request.form.get("start_time")
                end_time = request.form.get("end_time")

                if not selected_date or not start_time or not end_time:
                    message = "Please fill all fields."
                    message_type = "error"

                elif start_time == end_time:
                    message = "Start time and end time cannot be the same."
                    message_type = "error"

                else:

                    selected_date_obj = datetime.strptime(
                        selected_date,
                        "%Y-%m-%d"
                    )

                    day = selected_date_obj.strftime("%A")

                    cursor.execute("""
                        UPDATE doctor_schedule
                        SET
                            day_of_week = %s,
                            start_time = %s,
                            end_time = %s
                        WHERE schedule_id = %s
                          AND doctor_id = %s
                    """, (
                        day,
                        start_time,
                        end_time,
                        schedule_id,
                        doctor_id
                    ))

                    db.commit()

                    message = "Availability updated successfully."
                    message_type = "success"

            # =================================================
            # ADD NEW AVAILABILITY
            # =================================================
            elif action == "add":

                available_dates = request.form.getlist(
                    "available_date[]"
                )

                start_times = request.form.getlist(
                    "start_time[]"
                )

                end_times = request.form.getlist(
                    "end_time[]"
                )

                added_count = 0

                for selected_date, start_time, end_time in zip(
                    available_dates,
                    start_times,
                    end_times
                ):

                    if not selected_date or not start_time or not end_time:
                        continue

                    selected_date_obj = datetime.strptime(
                        selected_date,
                        "%Y-%m-%d"
                    )

                    day = selected_date_obj.strftime("%A")

                    if start_time == end_time:
                        message = (
                            "Start time and end time cannot be the same."
                        )
                        message_type = "error"
                        break
                    # Duplicate check
                    cursor.execute("""
                        SELECT schedule_id
                        FROM doctor_schedule
                        WHERE doctor_id = %s
                          AND day_of_week = %s
                          AND start_time = %s
                          AND end_time = %s
                        LIMIT 1
                    """, (
                        doctor_id,
                        day,
                        start_time,
                        end_time
                    ))

                    existing = cursor.fetchone()

                    if existing:
                        continue

                    cursor.execute("""
                        INSERT INTO doctor_schedule
                        (
                            doctor_id,
                            day_of_week,
                            start_time,
                            end_time
                        )
                        VALUES (%s, %s, %s, %s)
                    """, (
                        doctor_id,
                        day,
                        start_time,
                        end_time
                    ))

                    added_count += 1

                if message_type != "error":

                    db.commit()

                    if added_count > 0:
                        message = (
                            "Availability added successfully."
                        )
                    else:
                        message = (
                            "No new availability was added."
                        )

                    message_type = "success"

        except Exception as e:

            db.rollback()

            print("Availability Error:", e)

            message = "Unable to update availability."
            message_type = "error"

    # -------------------------------------------------
    # GET CURRENT AVAILABILITY
    # -------------------------------------------------
    cursor.execute("""
        SELECT
            schedule_id,
            day_of_week,
            start_time,
            end_time
        FROM doctor_schedule
        WHERE doctor_id = %s
        ORDER BY
            FIELD(
                day_of_week,
                'Monday',
                'Tuesday',
                'Wednesday',
                'Thursday',
                'Friday',
                'Saturday',
                'Sunday'
            ),
            start_time
    """, (doctor_id,))

    schedules = cursor.fetchall()

    # -------------------------------------------------
    # NEXT DATE + TIME FORMAT
    # -------------------------------------------------
    today = datetime.today().date()

    day_numbers = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6
    }

    for schedule in schedules:

        # Convert time
        start_time = schedule["start_time"]
        end_time = schedule["end_time"]

        if isinstance(start_time, timedelta):
            start_time = (datetime.min + start_time).time()

        if isinstance(end_time, timedelta):
            end_time = (datetime.min + end_time).time()

        schedule["start_time_display"] = start_time.strftime(
            "%I:%M %p"
        )

        schedule["end_time_display"] = end_time.strftime(
            "%I:%M %p"
        )

        # Next occurrence of this weekday
        target_day = day_numbers[schedule["day_of_week"]]
        current_day = today.weekday()

        days_ahead = (target_day - current_day) % 7

        next_date = today + timedelta(days=days_ahead)

        schedule["next_date"] = next_date
        schedule["next_date_display"] = next_date.strftime(
            "%d-%m-%Y"
        )

    cursor.close()
    db.close()

    return render_template(
        "doctor_availability.html",
        doctor=doctor,
        schedules=schedules,
        message=message,
        message_type=message_type
    )
@app.route("/delete_availability/<int:schedule_id>", methods=["POST"])
def delete_availability(schedule_id):

    if session.get("role") != "admin":
        return redirect("/")


    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)


    cursor.execute("""
        SELECT
            schedule_id,
            doctor_id
        FROM doctor_schedule
        WHERE schedule_id = %s
    """, (schedule_id,))

    schedule = cursor.fetchone()


    if not schedule:

        cursor.close()
        db.close()

        return redirect("/admin_doctor_manage")


    doctor_id = schedule["doctor_id"]


    cursor.execute("""
        DELETE FROM doctor_schedule
        WHERE schedule_id = %s
    """, (schedule_id,))


    db.commit()

    cursor.close()
    db.close()


    return redirect(
        f"/doctor_availability/{doctor_id}"
    )
@app.route("/admin_doctor_delete/<int:doctor_id>", methods=["POST"])
def admin_doctor_delete(doctor_id):

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get doctor user_id
    cursor.execute("""
        SELECT user_id
        FROM doctors
        WHERE doctor_id = %s
    """, (doctor_id,))

    doctor = cursor.fetchone()

    if not doctor:

        cursor.close()
        db.close()

        return redirect("/admin_doctor_manage")


    # Check whether this doctor has appointments

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM appointments
        WHERE doctor_id = %s
    """, (doctor_id,))

    appointment_count = cursor.fetchone()["total"]


    # Doctor has appointments
    if appointment_count > 0:

        cursor.execute("""
            SELECT
                d.doctor_id,
                u.name,
                u.email,
                d.specialization,
                d.phone
            FROM doctors d
            JOIN users u
                ON d.user_id = u.user_id
            WHERE u.role = 'doctor'
            ORDER BY u.name
        """)

        doctors = cursor.fetchall()

        cursor.close()
        db.close()

        return render_template(
            "admin_doctor_manage.html",
            doctors=doctors,
            message="This doctor cannot be deleted because appointments exist.",
            message_type="error"
        )


    # Delete doctor
    cursor.execute("""
        DELETE FROM doctors
        WHERE doctor_id = %s
    """, (doctor_id,))


    # Delete doctor user account
    cursor.execute("""
        DELETE FROM users
        WHERE user_id = %s
    """, (doctor["user_id"],))


    db.commit()

    cursor.close()
    db.close()

    return redirect("/admin_doctor_manage")   
@app.route("/admin_appointments")
def admin_appointments():

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get doctors for filter
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()

    # Get selected filters
    selected_doctor_id = request.args.get("doctor_id")
    selected_date = request.args.get("appointment_date")
    selected_status = request.args.get("status")

    appointments = []
    searched = False

    # At least one filter must be selected
    if selected_doctor_id or selected_date or selected_status:

        searched = True

        query = """
            SELECT
                pu.name AS patient_name,
                du.name AS doctor_name,
                DATE_FORMAT(
                    a.appointment_date,
                    '%d-%m-%Y'
                ) AS appointment_date,
                TIME_FORMAT(
                    a.appointment_time,
                    '%h:%i %p'
                ) AS appointment_time,
                t.token_number,
                a.status
            FROM appointments a

            JOIN patients p
                ON a.patient_id = p.patient_id

            JOIN users pu
                ON p.user_id = pu.user_id

            JOIN doctors d
                ON a.doctor_id = d.doctor_id

            JOIN users du
                ON d.user_id = du.user_id

            LEFT JOIN tokens t
                ON a.appointment_id = t.appointment_id

            WHERE 1 = 1
        """

        params = []

        # Doctor filter
        if selected_doctor_id:
            query += """
                AND a.doctor_id = %s
            """
            params.append(selected_doctor_id)

        # Date filter
        if selected_date:
            query += """
                AND a.appointment_date = %s
            """
            params.append(selected_date)

        # Status filter
        if selected_status:
            query += """
                AND a.status = %s
            """
            params.append(selected_status)

        query += """
            ORDER BY
                a.appointment_date,
                a.appointment_time
        """

        cursor.execute(query, tuple(params))

        appointments = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "admin_appointments.html",
        doctors=doctors,
        appointments=appointments,
        selected_doctor_id=selected_doctor_id,
        selected_date=selected_date,
        selected_status=selected_status,
        searched=searched
    )
@app.route("/admin_tracking")
def admin_tracking():

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # -----------------------------
    # ALL DOCTORS
    # -----------------------------
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name AS doctor_name,
            d.department,
            d.specialization
        FROM doctors d
        JOIN users u ON d.user_id = u.user_id
        WHERE u.role = 'doctor'
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()

    doctor_id = request.args.get("doctor_id", type=int)
    selected_date = request.args.get("selected_date", "")

    availability = []
    next_available = None
    appointments = []

    # -----------------------------
    # DOCTOR DETAILS + AVAILABILITY
    # -----------------------------
    if doctor_id:

        cursor.execute("""
            SELECT
                d.doctor_id,
                u.name AS doctor_name,
                d.department,
                d.specialization
            FROM doctors d
            JOIN users u ON d.user_id = u.user_id
            WHERE d.doctor_id = %s
              AND u.role = 'doctor'
        """, (doctor_id,))

        selected_doctor = cursor.fetchone()

        if selected_doctor:

            cursor.execute("""
                SELECT day_of_week, start_time, end_time
                FROM doctor_schedule
                WHERE doctor_id = %s
                ORDER BY
                    FIELD(
                        day_of_week,
                        'Monday',
                        'Tuesday',
                        'Wednesday',
                        'Thursday',
                        'Friday',
                        'Saturday',
                        'Sunday'
                    ),
                    start_time
            """, (doctor_id,))

            schedules = cursor.fetchall()

            today = date.today()

            for schedule in schedules:

                day_name = schedule["day_of_week"]

                start_time = schedule["start_time"]
                end_time = schedule["end_time"]

                # MySQL TIME may come as timedelta
                if isinstance(start_time, timedelta):
                    start_time = (
                        datetime.min + start_time
                    ).time()

                if isinstance(end_time, timedelta):
                    end_time = (
                        datetime.min + end_time
                    ).time()

                # -----------------------------
                # FIND NEXT ACTUAL DATE
                # -----------------------------
                weekday_number = [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday"
                ].index(day_name)

                days_ahead = (
                    weekday_number - today.weekday()
                ) % 7

                available_date = (
                    today + timedelta(days=days_ahead)
                )

                # If today's schedule is already over,
                # move to next week's occurrence.
                if available_date == today:

                    if datetime.now().time() >= end_time:
                        available_date = (
                            available_date +
                            timedelta(days=7)
                        )

                availability.append({
                    "day": day_name,
                    "start_time": start_time.strftime("%I:%M %p"),
                    "end_time": end_time.strftime("%I:%M %p"),
                    "next_date": available_date.strftime("%d-%m-%Y")
                })

            # First upcoming availability
            if availability:
                sorted_availability = sorted(
                    availability,
                    key=lambda x: datetime.strptime(
                        x["next_date"],
                        "%d-%m-%Y"
                    )
                )

                next_available = sorted_availability[0]

            # -----------------------------
            # TOKEN TRACKING DATE
            # -----------------------------
            # Dates come from ACTUAL appointments.
            # Past + today + future are all allowed.
            cursor.execute("""
                SELECT DISTINCT appointment_date
                FROM appointments
                WHERE doctor_id = %s
                ORDER BY appointment_date DESC
            """, (doctor_id,))

            date_rows = cursor.fetchall()

            appointment_dates = []

            for row in date_rows:

                appointment_date = row["appointment_date"]

                appointment_dates.append({
                    "value": appointment_date.strftime("%Y-%m-%d"),
                    "display": appointment_date.strftime("%d-%m-%Y")
                })

            # -----------------------------
            # SELECTED DATE TOKEN DATA
            # -----------------------------
            if selected_date:

                cursor.execute("""
                    SELECT
                        a.appointment_id,
                        u.name AS patient_name,
                        a.appointment_date,
                        a.appointment_time,
                        t.token_number,
                        t.status AS token_status,
                        a.status AS appointment_status
                    FROM appointments a
                    JOIN patients p
                        ON a.patient_id = p.patient_id
                    JOIN users u
                        ON p.user_id = u.user_id
                    LEFT JOIN tokens t
                        ON a.appointment_id = t.appointment_id
                    WHERE a.doctor_id = %s
                      AND a.appointment_date = %s
                    ORDER BY
                        t.token_number,
                        a.appointment_time
                """, (doctor_id, selected_date))

                appointments = cursor.fetchall()

                for appointment in appointments:

                    appointment_time = appointment["appointment_time"]

                    if isinstance(appointment_time, timedelta):
                        appointment_time = (
                            datetime.min + appointment_time
                        ).time()

                    appointment["appointment_time"] = (
                        appointment_time.strftime("%I:%M %p")
                    )

                    appointment["appointment_date"] = (
                        appointment["appointment_date"]
                        .strftime("%d-%m-%Y")
                    )

    else:
        selected_doctor = None
        appointment_dates = []

    cursor.close()
    db.close()

    return render_template(
        "admin_tracking.html",
        doctors=doctors,
        selected_doctor=selected_doctor,
        doctor_id=doctor_id,
        availability=availability,
        next_available=next_available,
        appointment_dates=appointment_dates,
        selected_date=selected_date,
        appointments=appointments
    )
@app.route("/doctor_appointments")
def doctor_appointments():

    if session.get("role") != "doctor":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)
    auto_cancel_missed_appointments(cursor)
    db.commit()

    # Logged-in doctor
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name AS doctor_name
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE d.user_id = %s
          AND u.role = 'doctor'
    """, (session["user_id"],))

    doctor = cursor.fetchone()

    if not doctor:
        cursor.close()
        db.close()
        return redirect("/doctor_dashboard")

    doctor_id = doctor["doctor_id"]

    today = date.today()

    # ------------------------------------------------
    # TODAY'S DOCTOR SCHEDULE
    # ------------------------------------------------

    today_day = today.strftime("%A")

    cursor.execute("""
        SELECT
            start_time,
            end_time
        FROM doctor_schedule
        WHERE doctor_id = %s
          AND day_of_week = %s
        ORDER BY start_time
        LIMIT 1
    """, (doctor_id, today_day))

    today_schedule = cursor.fetchone()

    # ------------------------------------------------
    # TODAY'S APPOINTMENTS
    # ------------------------------------------------

    cursor.execute("""
        SELECT
            a.appointment_id,
            a.patient_id,
            a.appointment_date,
            a.appointment_time,
            a.status AS appointment_status,

            pu.name AS patient_name,

            t.token_number,
            t.status AS token_status

        FROM appointments a

        JOIN patients p
            ON a.patient_id = p.patient_id

        JOIN users pu
            ON p.user_id = pu.user_id

        LEFT JOIN tokens t
            ON a.appointment_id = t.appointment_id

        WHERE a.doctor_id = %s
          AND a.appointment_date = %s

        ORDER BY
            t.token_number,
            a.appointment_time
    """, (doctor_id, today))

    today_appointments = cursor.fetchall()

    for appointment in today_appointments:

        appointment_time = appointment["appointment_time"]

        if isinstance(appointment_time, timedelta):
            appointment_time = (
                datetime.min + appointment_time
            ).time()

        appointment["time_display"] = appointment_time.strftime(
            "%I:%M %p"
        )

    # ------------------------------------------------
    # HISTORY SEARCH
    # ------------------------------------------------

    history_date = request.args.get("history_date")
    history_date_display = None
    history_appointments = []

    if history_date:

        try:
            selected_date = date.fromisoformat(history_date)
            history_date_display = selected_date.strftime("%d-%m-%Y")
            cursor.execute("""
                SELECT
                    a.appointment_id,
                    a.patient_id,
                    a.appointment_date,
                    a.appointment_time,
                    a.status AS appointment_status,

                    pu.name AS patient_name,

                    t.token_number,
                    t.status AS token_status

                FROM appointments a

                JOIN patients p
                    ON a.patient_id = p.patient_id

                JOIN users pu
                    ON p.user_id = pu.user_id

                LEFT JOIN tokens t
                    ON a.appointment_id = t.appointment_id

                WHERE a.doctor_id = %s
                  AND a.appointment_date = %s

                ORDER BY
                    t.token_number,
                    a.appointment_time
            """, (doctor_id, selected_date))

            history_appointments = cursor.fetchall()

            for appointment in history_appointments:

                appointment_time = appointment["appointment_time"]

                if isinstance(appointment_time, timedelta):
                    appointment_time = (
                        datetime.min + appointment_time
                    ).time()

                appointment["time_display"] = appointment_time.strftime(
                    "%I:%M %p"
                )

        except ValueError:
            history_date = None

    cursor.close()
    db.close()

    return render_template(
        "doctor_appointments.html",
        doctor=doctor,
        today=today,
        today_schedule=today_schedule,
        today_appointments=today_appointments,
        history_date=history_date,
        history_date_display=history_date_display,
        history_appointments=history_appointments
    )
@app.route("/tracking")
def tracking():

    if session.get("role") != "patient":
        return redirect("/")

    from datetime import date

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    try:

        # =========================================================
        # LOGGED-IN PATIENT
        # =========================================================

        cursor.execute("""
            SELECT patient_id
            FROM patients
            WHERE user_id = %s
        """, (session["user_id"],))

        patient = cursor.fetchone()

        if not patient:
            return redirect("/patient_dashboard")

        patient_id = patient["patient_id"]

        auto_cancel_missed_appointments(cursor)
        db.commit()


        # =========================================================
        # PATIENT APPOINTMENTS
        # =========================================================

        cursor.execute("""
            SELECT
                a.appointment_id,
                a.doctor_id,

                du.name AS doctor_name,

                d.department,
                d.specialization,

                a.appointment_date AS actual_date,

                DATE_FORMAT(
                    a.appointment_date,
                    '%d-%m-%Y'
                ) AS appointment_date,

                TIME_FORMAT(
                    a.appointment_time,
                    '%h:%i %p'
                ) AS appointment_time,

                t.token_number,
                t.status AS token_status,

                a.status AS appointment_status

            FROM appointments a

            JOIN doctors d
                ON a.doctor_id = d.doctor_id

            JOIN users du
                ON d.user_id = du.user_id

            LEFT JOIN tokens t
                ON a.appointment_id = t.appointment_id

            WHERE a.patient_id = %s

            ORDER BY
                a.appointment_date DESC,
                a.appointment_time ASC
        """, (patient_id,))

        appointments = cursor.fetchall()

        today = date.today()

        # =========================================================
        # CACHE QUEUE DATA
        # =========================================================

        queue_cache = {}


        # =========================================================
        # PREPARE EVERY APPOINTMENT
        # =========================================================

        for appointment in appointments:

            appointment["is_today"] = (
                appointment["actual_date"] == today
            )

            appointment["is_past"] = (
                appointment["actual_date"] < today
            )

            appointment["is_upcoming"] = (
                appointment["actual_date"] > today
            )

            appointment["queue_data"] = []

            appointment["patients_ahead"] = 0

            appointment["now_serving"] = None

            appointment["status_text"] = ""


            token_number = appointment["token_number"]

            doctor_id = appointment["doctor_id"]

            appointment_date = appointment["actual_date"]


            # -----------------------------------------------------
            # NO TOKEN
            # -----------------------------------------------------

            if token_number is None:

                if appointment["is_upcoming"]:

                    appointment["status_text"] = (
                        "Upcoming Appointment"
                    )

                else:

                    appointment["status_text"] = (
                        "Token Not Available"
                    )

                continue


            # -----------------------------------------------------
            # QUEUE CACHE KEY
            # -----------------------------------------------------

            cache_key = (
                doctor_id,
                appointment_date, token_number
            )


            # -----------------------------------------------------
            # GET QUEUE
            # -----------------------------------------------------

            if cache_key not in queue_cache:

                cursor.execute("""
                    SELECT
                        t.token_number,
                        t.status

                    FROM tokens t

                    JOIN appointments a
                        ON t.appointment_id = a.appointment_id

                    WHERE a.doctor_id = %s
                    AND a.appointment_date = %s
                    AND t.token_number <= %s

                    ORDER BY t.token_number
                """, (
                    doctor_id,
                    appointment_date,
                    token_number
                ))

                queue_cache[cache_key] = cursor.fetchall()


            queue_data = queue_cache[cache_key]

            appointment["queue_data"] = queue_data


            # -----------------------------------------------------
            # CURRENTLY SERVING
            # -----------------------------------------------------

            now_serving = None

            for item in queue_data:

                if item["status"] == "serving":

                    now_serving = item["token_number"]

                    break

            appointment["now_serving"] = now_serving


            # -----------------------------------------------------
            # PATIENTS AHEAD
            # -----------------------------------------------------

            patients_ahead = 0

            for item in queue_data:

                if item["token_number"] < token_number:

                    if item["status"] in [
                        "waiting",
                        "serving"
                    ]:

                        patients_ahead += 1

            appointment["patients_ahead"] = patients_ahead


            # =====================================================
            # TODAY STATUS
            # =====================================================

            if appointment["is_today"]:

                if appointment["token_status"] == "completed":

                    appointment["status_text"] = (
                        "Consultation Completed"
                    )

                elif appointment["token_status"] == "serving":

                    appointment["status_text"] = (
                        "In Consultation"
                    )

                elif (
                    appointment["token_status"] == "cancelled"
                    or
                    appointment["appointment_status"] == "cancelled"
                ):

                    appointment["status_text"] = "Cancelled"

                elif appointment["token_status"] == "waiting":

                    if now_serving is None:

                        appointment["status_text"] = (
                            "Queue Not Started"
                        )

                    elif patients_ahead == 0:

                        appointment["status_text"] = (
                            "Your Turn Is Next"
                        )

                    else:

                        appointment["status_text"] = (
                            "Waiting for Consultation"
                        )

                else:

                    appointment["status_text"] = (
                        "Waiting for Consultation"
                    )


            # =====================================================
            # PREVIOUS
            # =====================================================

            elif appointment["is_past"]:

                if appointment["token_status"] == "completed":

                    appointment["status_text"] = (
                        "Consultation Completed"
                    )

                elif (
                    appointment["token_status"] == "cancelled"
                    or
                    appointment["appointment_status"] == "cancelled"
                ):

                    appointment["status_text"] = "Cancelled"

                else:

                    appointment["status_text"] = (
                        "Previous Appointment"
                    )


            # =====================================================
            # UPCOMING
            # =====================================================

            elif appointment["is_upcoming"]:

                appointment["status_text"] = (
                    "Upcoming Appointment"
                )


        # =========================================================
        # SHOW TRACKING PAGE
        # =========================================================

        return render_template(
            "tracking.html",
            appointments=appointments
        )


    except Exception as e:

        print("TRACKING ERROR:", e)

        return "Tracking Error: " + str(e)


    finally:

        cursor.close()

        db.close()

@app.route("/tracking_details/<int:appointment_id>")
def tracking_details(appointment_id):

    if session.get("role") != "patient":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get only the logged-in patient's appointment
    cursor.execute("""
        SELECT
            a.appointment_id,
            a.doctor_id,
            a.appointment_date AS actual_date,
            du.name AS doctor_name,

            d.department,
            d.specialization,

            DATE_FORMAT(
                a.appointment_date,
                '%d-%m-%Y'
            ) AS appointment_date,

            TIME_FORMAT(
                a.appointment_time,
                '%h:%i %p'
            ) AS appointment_time,

            t.token_number,
            t.status AS token_status,

            a.status AS appointment_status,

            mr.diagnosis,
            mr.prescription,
            mr.treatment,

            CASE
                WHEN mr.record_id IS NOT NULL THEN 1
                ELSE 0
            END AS record_exists

        FROM appointments a

        JOIN patients p
            ON a.patient_id = p.patient_id

        JOIN doctors d
            ON a.doctor_id = d.doctor_id

        JOIN users du
            ON d.user_id = du.user_id

        LEFT JOIN tokens t
            ON a.appointment_id = t.appointment_id

        LEFT JOIN medical_records mr
            ON mr.patient_id = p.patient_id
            AND mr.doctor_id = d.doctor_id

        WHERE a.appointment_id = %s
          AND p.user_id = %s

        ORDER BY mr.record_id DESC

        LIMIT 1
    """, (
        appointment_id,
        session["user_id"]
    ))

    appointment = cursor.fetchone()

    if not appointment:

        cursor.close()
        db.close()

        return redirect("/tracking")

    auto_cancel_missed_appointments(cursor)
    db.commit()

    cursor.execute("""
        SELECT
            a.appointment_id,
            a.doctor_id,
            a.appointment_date AS actual_date,
            du.name AS doctor_name,

            d.department,
            d.specialization,

            DATE_FORMAT(
                a.appointment_date,
                '%d-%m-%Y'
            ) AS appointment_date,

            TIME_FORMAT(
                a.appointment_time,
                '%h:%i %p'
            ) AS appointment_time,

            t.token_number,
            t.status AS token_status,

            a.status AS appointment_status,

            mr.diagnosis,
            mr.prescription,
            mr.treatment,

            CASE
                WHEN mr.record_id IS NOT NULL THEN 1
                ELSE 0
            END AS record_exists

        FROM appointments a

        JOIN patients p
            ON a.patient_id = p.patient_id

        JOIN doctors d
            ON a.doctor_id = d.doctor_id

        JOIN users du
            ON d.user_id = du.user_id

        LEFT JOIN tokens t
            ON a.appointment_id = t.appointment_id

        LEFT JOIN medical_records mr
            ON mr.patient_id = p.patient_id
            AND mr.doctor_id = d.doctor_id

        WHERE a.appointment_id = %s
          AND p.user_id = %s

        ORDER BY mr.record_id DESC

        LIMIT 1
    """, (
        appointment_id,
        session["user_id"]
    ))

    appointment = cursor.fetchone()

    if not appointment:

        cursor.close()
        db.close()

        return redirect("/tracking")

    token_number = appointment["token_number"]

    if token_number is None:

        cursor.close()
        db.close()

        return redirect("/tracking")

    doctor_id = appointment["doctor_id"]

    # Get today's queue status for this doctor/date
    cursor.execute("""
    SELECT
        t.token_number,
        t.status
    FROM tokens t

    JOIN appointments a
        ON t.appointment_id = a.appointment_id

    WHERE a.doctor_id = %s
      AND a.appointment_date = %s
      AND t.token_number <= %s

    ORDER BY t.token_number
""", (
    doctor_id,
    appointment["actual_date"],
    token_number
))
    queue_data = cursor.fetchall()

    # Find token currently in consultation
    now_serving = None

    for item in queue_data:

        if item["status"] == "in_consultation":

            now_serving = item["token_number"]
            break

    # Find next waiting token
    next_token = None

    for item in queue_data:

        if item["status"] == "waiting":

            next_token = item["token_number"]
            break

    # Count patients ahead
    patients_ahead = 0

    for item in queue_data:

        if item["token_number"] < token_number:

            if item["status"] in [
                "waiting",
                "in_consultation"
            ]:

                patients_ahead += 1

    # Determine patient status
    patient_status = appointment["token_status"]

    if patient_status == "waiting":

        if now_serving is None:

            status_text = "Queue Not Started"

        elif patients_ahead == 0:

            status_text = "Your Turn Is Next"

        else:

            status_text = "Waiting for Consultation"

    elif patient_status == "in_consultation":

        status_text = "In Consultation"

    elif patient_status == "completed":

        status_text = "Consultation Completed"

    elif patient_status == "cancelled":

        status_text = "Cancelled"

    else:

        status_text = "Waiting for Consultation"

    cursor.close()
    db.close()

    return render_template(
        "tracking_details.html",

        appointment=appointment,

        queue_data=queue_data,

        now_serving=now_serving,

        next_token=next_token,

        patients_ahead=patients_ahead,

        status_text=status_text
    )
@app.route("/admin_medical_records")
def admin_medical_records():

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get doctors
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE u.role = 'doctor'
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()

    selected_doctor_id = request.args.get("doctor_id")
    selected_patient_id = request.args.get("patient_id")

    # Get patients
    # If a doctor is selected, show only patients
    # who have an appointment with that doctor.
    if selected_doctor_id:

        cursor.execute("""
            SELECT DISTINCT
                p.patient_id,
                u.name
            FROM patients p

            JOIN users u
                ON p.user_id = u.user_id

            JOIN appointments a
                ON a.patient_id = p.patient_id

            WHERE a.doctor_id = %s

            ORDER BY u.name
        """, (selected_doctor_id,))

    else:

        cursor.execute("""
            SELECT
                p.patient_id,
                u.name
            FROM patients p
            JOIN users u
                ON p.user_id = u.user_id
            ORDER BY u.name
        """)

    patients = cursor.fetchall()

    records = []

    searched = False

    # Search records only after a filter is selected
    if selected_doctor_id or selected_patient_id:

        searched = True

        query = """
            SELECT
                pu.name AS patient_name,
                du.name AS doctor_name,

                mr.diagnosis,
                mr.prescription,
                mr.treatment,

                DATE_FORMAT(
                    mr.record_date,
                    '%d-%m-%Y'
                ) AS record_date

            FROM medical_records mr

            JOIN patients p
                ON mr.patient_id = p.patient_id

            JOIN users pu
                ON p.user_id = pu.user_id

            JOIN doctors d
                ON mr.doctor_id = d.doctor_id

            JOIN users du
                ON d.user_id = du.user_id

            WHERE 1 = 1
        """

        params = []

        if selected_doctor_id:

            query += """
                AND mr.doctor_id = %s
            """

            params.append(selected_doctor_id)

        if selected_patient_id:

            query += """
                AND mr.patient_id = %s
            """

            params.append(selected_patient_id)

        query += """
            ORDER BY mr.record_date DESC
        """

        cursor.execute(query, tuple(params))

        records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "admin_medical_records.html",

        doctors=doctors,

        patients=patients,

        records=records,

        selected_doctor_id=selected_doctor_id,

        selected_patient_id=selected_patient_id,

        searched=searched
    )
@app.route("/admin_dashboard")
def admin_dashboard():

    if session.get("role") != "admin":
        return redirect("/")

    return render_template("index.html")
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/doctor_dashboard")
def doctor_dashboard():

    if session.get("role") != "doctor":
        return redirect("/")

    return render_template("doctor_dashboard.html")
@app.route("/admin_patients")
def admin_patients():

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    selected_patient_id = request.args.get("patient_id")

    query = """
        SELECT
            p.patient_id,
            u.name,
            u.email,
            p.phone,
            p.date_of_birth,
            TIMESTAMPDIFF(
                YEAR,
                p.date_of_birth,
                CURDATE()
            ) AS age,
            p.gender,
            p.address
        FROM patients p
        JOIN users u
            ON p.user_id = u.user_id
        WHERE TIMESTAMPDIFF(
            YEAR,
            p.date_of_birth,
            CURDATE()
        ) > 0
    """

    params = []

    if selected_patient_id:
        query += """
            AND p.patient_id = %s
        """
        params.append(selected_patient_id)

    query += """
        ORDER BY u.name
    """

    cursor.execute(query, tuple(params))
    patients = cursor.fetchall()

    cursor.execute("""
        SELECT
            p.patient_id,
            u.name
        FROM patients p
        JOIN users u
            ON p.user_id = u.user_id
        WHERE TIMESTAMPDIFF(
            YEAR,
            p.date_of_birth,
            CURDATE()
        ) > 0
        ORDER BY u.name
    """)

    patient_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "admin_patients.html",
        patients=patients,
        patient_list=patient_list,
        selected_patient_id=selected_patient_id
    )


@app.route("/admin_patient_details/<int:patient_id>")
def admin_patient_details(patient_id):

    if session.get("role") != "admin":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT
            u.name,
            u.email,
            p.phone,
            p.date_of_birth,
            TIMESTAMPDIFF(
                YEAR,
                p.date_of_birth,
                CURDATE()
            ) AS age,
            p.gender,
            p.address
        FROM patients p
        JOIN users u
            ON p.user_id = u.user_id
        WHERE p.patient_id = %s
    """, (patient_id,))

    patient = cursor.fetchone()

    cursor.close()
    db.close()

    return render_template(
        "admin_patient_details.html",
        patient=patient
    )
@app.route("/patient_dashboard")
def patient_dashboard():

    if session.get("role") != "patient":
        return redirect("/")

    return render_template("patient_dashboard.html")
@app.route("/doctor_medical_records")
def doctor_medical_records():

    if session.get("role") != "doctor":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT doctor_id
        FROM doctors
        WHERE user_id = %s
    """, (session["user_id"],))

    doctor = cursor.fetchone()

    if not doctor:
        cursor.close()
        db.close()
        return redirect("/doctor_dashboard")

    doctor_id = doctor["doctor_id"]

    patient_id = request.args.get("patient_id")

    # Patients who have records with this doctor
    cursor.execute("""
        SELECT DISTINCT
            p.patient_id,
            u.name AS patient_name
        FROM medical_records mr

        JOIN patients p
            ON mr.patient_id = p.patient_id

        JOIN users u
            ON p.user_id = u.user_id

        WHERE mr.doctor_id = %s

        ORDER BY u.name
    """, (doctor_id,))

    patients = cursor.fetchall()

    if patient_id:

        cursor.execute("""
            SELECT
                u.name AS patient_name,
                mr.diagnosis,
                mr.prescription,
                mr.treatment,
                mr.record_date

            FROM medical_records mr

            JOIN patients p
                ON mr.patient_id = p.patient_id

            JOIN users u
                ON p.user_id = u.user_id

            WHERE mr.doctor_id = %s
              AND mr.patient_id = %s

            ORDER BY mr.record_date DESC
        """, (doctor_id, patient_id))

    else:

        cursor.execute("""
            SELECT
                u.name AS patient_name,
                mr.diagnosis,
                mr.prescription,
                mr.treatment,
                mr.record_date

            FROM medical_records mr

            JOIN patients p
                ON mr.patient_id = p.patient_id

            JOIN users u
                ON p.user_id = u.user_id

            WHERE mr.doctor_id = %s

            ORDER BY mr.record_date DESC
        """, (doctor_id,))

    records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "doctor_medical_records.html",
        patients=patients,
        records=records,
        selected_patient=patient_id
    )
@app.route("/doctor_details")
def doctor_details():

    if session.get("role") != "patient":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get all doctors
    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name,
            d.department,
            d.specialization
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE u.role = 'doctor'
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()

    today = date.today()

    day_numbers = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6
    }

    # Get availability for each doctor
    for doctor in doctors:

        cursor.execute("""
            SELECT
                day_of_week,
                start_time,
                end_time
            FROM doctor_schedule
            WHERE doctor_id = %s
            ORDER BY
                FIELD(
                    day_of_week,
                    'Monday',
                    'Tuesday',
                    'Wednesday',
                    'Thursday',
                    'Friday',
                    'Saturday',
                    'Sunday'
                ),
                start_time
        """, (doctor["doctor_id"],))

        schedules = cursor.fetchall()

        doctor["availability"] = []

        for schedule in schedules:

            target_day = day_numbers[schedule["day_of_week"]]

            days_ahead = (
                target_day - today.weekday()
            ) % 7

            available_date = (
                today + timedelta(days=days_ahead)
            )

            # Convert MySQL TIME values if returned as timedelta
            start_time = schedule["start_time"]
            end_time = schedule["end_time"]

            if isinstance(start_time, timedelta):
                start_time = (
                    datetime.min + start_time
                ).time()

            if isinstance(end_time, timedelta):
                end_time = (
                    datetime.min + end_time
                ).time()

            # If today's working time is already over,
            # show the next occurrence of that working day.
            if available_date == today:

                current_time = datetime.now().time()

                if current_time >= end_time:

                    available_date = (
                        available_date + timedelta(days=7)
                    )

            start_time_display = start_time.strftime(
                "%I:%M %p"
            )

            end_time_display = end_time.strftime(
                "%I:%M %p"
            )

            doctor["availability"].append({
                "day": schedule["day_of_week"],
                "date": available_date.strftime("%d-%m-%Y"),
                "time": (
                    start_time_display
                    + " - "
                    + end_time_display
                )
            })

    cursor.close()
    db.close()

    return render_template(
        "doctor_details.html",
        doctors=doctors
    )
    
@app.route("/patient_book_appointment", methods=["GET", "POST"])
def patient_book_appointment():

    if session.get("role") != "patient":
        return redirect("/")

    message = ""
    message_type = ""

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # -----------------------------------
    # LOGGED-IN PATIENT
    # -----------------------------------

    cursor.execute("""
        SELECT name
        FROM users
        WHERE user_id = %s
          AND role = 'patient'
    """, (session["user_id"],))

    logged_patient = cursor.fetchone()

    patient_name = ""

    if logged_patient:
        patient_name = logged_patient["name"]

    # -----------------------------------
    # DEPARTMENTS
    # -----------------------------------

    cursor.execute("""
        SELECT DISTINCT department
        FROM doctors
        WHERE department IS NOT NULL
          AND department != ''
        ORDER BY department
    """)

    departments_data = cursor.fetchall()

    departments = [
        row["department"]
        for row in departments_data
    ]

    # -----------------------------------
    # DOCTORS
    # -----------------------------------

    cursor.execute("""
        SELECT
            d.doctor_id,
            u.name,
            d.department,
            d.specialization
        FROM doctors d
        JOIN users u
            ON d.user_id = u.user_id
        WHERE u.role = 'doctor'
        ORDER BY u.name
    """)

    doctors = cursor.fetchall()

    # -----------------------------------
    # BOOKING
    # -----------------------------------

    if request.method == "POST":

        doctor_id = request.form.get("doctor_id")
        appointment_date = request.form.get("appointment_date")
        appointment_time = request.form.get("appointment_time")

        # -----------------------------------
        # CHECK REQUIRED FIELDS
        # -----------------------------------

        if not doctor_id or not appointment_date or not appointment_time:

            message = "Please select doctor, date and appointment time."
            message_type = "error"

        else:

            # -----------------------------------
            # LOGGED-IN PATIENT
            # -----------------------------------

            cursor.execute("""
                SELECT patient_id
                FROM patients
                WHERE user_id = %s
            """, (session["user_id"],))

            patient = cursor.fetchone()

            if not patient:

                message = "Patient profile not found."
                message_type = "error"

            else:

                patient_id = patient["patient_id"]

                # -----------------------------------
                # CHECK DOCTOR
                # -----------------------------------

                cursor.execute("""
                    SELECT
                        d.doctor_id,
                        d.department,
                        d.specialization
                    FROM doctors d
                    JOIN users u
                        ON d.user_id = u.user_id
                    WHERE d.doctor_id = %s
                      AND u.role = 'doctor'
                """, (doctor_id,))

                doctor = cursor.fetchone()

                if not doctor:

                    message = "Invalid doctor selected."
                    message_type = "error"

                else:

                    # -----------------------------------
                    # SELECTED DATE
                    # -----------------------------------

                    try:
                        selected_date = date.fromisoformat(
                            appointment_date
                        )
                    except ValueError:

                        selected_date = None
                        message = "Invalid appointment date."
                        message_type = "error"

                    if selected_date:

                        selected_day = selected_date.strftime("%A")

                        # -----------------------------------
                        # CHECK PAST DATE
                        # -----------------------------------

                        if selected_date < date.today():

                            message = (
                                "You cannot book an appointment "
                                "for a past date."
                            )
                            message_type = "error"

                        else:

                            # -----------------------------------
                            # GET DOCTOR SCHEDULE
                            # -----------------------------------

                            cursor.execute("""
                                SELECT
                                    start_time,
                                    end_time
                                FROM doctor_schedule
                                WHERE doctor_id = %s
                                  AND day_of_week = %s
                            """, (
                                doctor_id,
                                selected_day
                            ))

                            schedule = cursor.fetchone()

                            if not schedule:

                                message = (
                                    "Doctor is not available "
                                    "on the selected date."
                                )
                                message_type = "error"

                            else:

                                # -----------------------------------
                                # CONVERT SELECTED TIME
                                # -----------------------------------

                                try:

                                    selected_time_obj = datetime.strptime(
                                        appointment_time,
                                        "%H:%M"
                                    ).time()

                                except ValueError:

                                    try:

                                        selected_time_obj = datetime.strptime(
                                            appointment_time,
                                            "%H:%M:%S"
                                        ).time()

                                    except ValueError:

                                        selected_time_obj = None
                                        message = "Invalid appointment time."
                                        message_type = "error"

                                if selected_time_obj:

                                    # -----------------------------------
                                    # CONVERT START TIME
                                    # -----------------------------------

                                    start_time = schedule["start_time"]

                                    if isinstance(start_time, timedelta):

                                        start_time = (
                                            datetime.min + start_time
                                        ).time()

                                    elif not hasattr(start_time, "hour"):

                                        start_time = datetime.strptime(
                                            str(start_time),
                                            "%H:%M:%S"
                                        ).time()

                                    # -----------------------------------
                                    # CONVERT END TIME
                                    # -----------------------------------

                                    end_time = schedule["end_time"]

                                    if isinstance(end_time, timedelta):

                                        end_time = (
                                            datetime.min + end_time
                                        ).time()

                                    elif not hasattr(end_time, "hour"):

                                        end_time = datetime.strptime(
                                            str(end_time),
                                            "%H:%M:%S"
                                        ).time()

                                    # -----------------------------------
                                    # CHECK DOCTOR AVAILABLE HOURS
                                    # -----------------------------------

                                    if not (
                                        start_time
                                        <= selected_time_obj
                                        < end_time
                                    ):

                                        message = (
                                            "Selected time is outside "
                                            "the doctor's available hours."
                                        )
                                        message_type = "error"

                                    # -----------------------------------
                                    # CHECK TODAY'S PAST TIME
                                    # -----------------------------------

                                    elif selected_date == date.today():

                                        current_time = datetime.now().time()

                                        if selected_time_obj <= current_time:

                                            message = (
                                                "This time slot has already "
                                                "passed. Please select another time."
                                            )
                                            message_type = "error"

                                    # -----------------------------------
                                    # CHECK DUPLICATE BOOKING
                                    # -----------------------------------

                                    if message_type != "error":

                                        cursor.execute("""
                                            SELECT appointment_id
                                            FROM appointments
                                            WHERE doctor_id = %s
                                              AND appointment_date = %s
                                              AND appointment_time = %s
                                              AND status = 'booked'
                                        """, (
                                            doctor_id,
                                            appointment_date,
                                            selected_time_obj
                                        ))

                                        existing = cursor.fetchone()

                                        if existing:

                                            message = (
                                                "This time slot is already booked. "
                                                "Please select another time."
                                            )
                                            message_type = "error"

                                    # -----------------------------------
                                    # BOOK APPOINTMENT
                                    # -----------------------------------

                                    if message_type != "error":

                                        # -----------------------------------
                                        # FIND NEXT TOKEN FOR THIS DOCTOR
                                        # AND DATE
                                        # -----------------------------------

                                        cursor.execute("""
                                            SELECT
                                                MAX(t.token_number) AS max_token
                                            FROM tokens t
                                            JOIN appointments a
                                                ON t.appointment_id = a.appointment_id
                                            WHERE a.doctor_id = %s
                                              AND a.appointment_date = %s
                                        """, (
                                            doctor_id,
                                            appointment_date
                                        ))

                                        token_data = cursor.fetchone()

                                        if (
                                            token_data
                                            and token_data["max_token"]
                                        ):

                                            token_number = (
                                                int(token_data["max_token"]) + 1
                                            )

                                        else:

                                            token_number = 101

                                        # -----------------------------------
                                        # INSERT APPOINTMENT
                                        # -----------------------------------

                                        cursor.execute("""
                                            INSERT INTO appointments
                                            (
                                                patient_id,
                                                doctor_id,
                                                appointment_date,
                                                appointment_time,
                                                status
                                            )
                                            VALUES
                                            (
                                                %s,
                                                %s,
                                                %s,
                                                %s,
                                                'booked'
                                            )
                                        """, (
                                            patient_id,
                                            doctor_id,
                                            appointment_date,
                                            selected_time_obj
                                        ))

                                        appointment_id = cursor.lastrowid

                                        # -----------------------------------
                                        # INSERT TOKEN
                                        # -----------------------------------

                                        cursor.execute("""
                                            INSERT INTO tokens
                                            (
                                                appointment_id,
                                                token_number,
                                                status
                                            )
                                            VALUES
                                            (
                                                %s,
                                                %s,
                                                'waiting'
                                            )
                                        """, (
                                            appointment_id,
                                            token_number
                                        ))

                                        db.commit()

                                        message = (
                                            "Appointment booked successfully. "
                                            f"Your token number is {token_number}."
                                        )

                                        message_type = "success"

    # -----------------------------------
    # PATIENT'S APPOINTMENTS
    # -----------------------------------

    cursor.execute("""
        SELECT
            a.appointment_id,

            du.name AS doctor_name,

            DATE_FORMAT(
                a.appointment_date,
                '%d-%m-%Y'
            ) AS appointment_date,

            TIME_FORMAT(
                a.appointment_time,
                '%h:%i %p'
            ) AS appointment_time,

            t.token_number,

            a.status

        FROM appointments a

        JOIN doctors d
            ON a.doctor_id = d.doctor_id

        JOIN users du
            ON d.user_id = du.user_id

        LEFT JOIN tokens t
            ON a.appointment_id = t.appointment_id

        JOIN patients p
            ON a.patient_id = p.patient_id

        WHERE p.user_id = %s

        ORDER BY
            a.appointment_date,
            a.appointment_time

    """, (session["user_id"],))

    appointments_data = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "patient_book_appointment.html",
        departments=departments,
        doctors=doctors,
        appointments=appointments_data,
        message=message,
        message_type=message_type,
        patient_name=patient_name
    )
@app.route("/available_times")
def available_times():

    if session.get("role") != "patient":
        return {"times": []}

    doctor_id = request.args.get("doctor_id")
    appointment_date = request.args.get("appointment_date")

    if not doctor_id or not appointment_date:
        return {"times": []}

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    try:

        selected_date = date.fromisoformat(appointment_date)

        selected_day = selected_date.strftime("%A")

        # Get doctor's working schedule
        cursor.execute("""
            SELECT start_time, end_time
            FROM doctor_schedule
            WHERE doctor_id = %s
              AND day_of_week = %s
            LIMIT 1
        """, (
            doctor_id,
            selected_day
        ))

        schedule = cursor.fetchone()

        if not schedule:
            return {"times": []}

        # Convert MySQL TIME values safely
        start_time = schedule["start_time"]
        end_time = schedule["end_time"]

        if isinstance(start_time, timedelta):
            start_seconds = int(start_time.total_seconds())
            start_hour = start_seconds // 3600
            start_minute = (start_seconds % 3600) // 60

        else:
            start_hour = start_time.hour
            start_minute = start_time.minute

        if isinstance(end_time, timedelta):
            end_seconds = int(end_time.total_seconds())
            end_hour = end_seconds // 3600
            end_minute = (end_seconds % 3600) // 60

        else:
            end_hour = end_time.hour
            end_minute = end_time.minute

        current_time = datetime(
            selected_date.year,
            selected_date.month,
            selected_date.day,
            start_hour,
            start_minute
        )

        ending_time = datetime(
            selected_date.year,
            selected_date.month,
            selected_date.day,
            end_hour,
            end_minute
        )

        # Get already booked appointment times
        cursor.execute("""
            SELECT appointment_time
            FROM appointments
            WHERE doctor_id = %s
              AND appointment_date = %s
              AND status = 'booked'
        """, (
            doctor_id,
            appointment_date
        ))

        booked_rows = cursor.fetchall()

        booked_times = set()

        for row in booked_rows:

            booked_time = row["appointment_time"]

            if isinstance(booked_time, timedelta):

                total_seconds = int(
                    booked_time.total_seconds()
                )

                booked_hour = total_seconds // 3600

                booked_minute = (
                    total_seconds % 3600
                ) // 60

                booked_times.add(
                    f"{booked_hour:02d}:{booked_minute:02d}"
                )

            else:

                booked_times.add(
                    booked_time.strftime("%H:%M")
                )

        times = []

        # Create 30-minute slots
        while current_time < ending_time:

            time_value = current_time.strftime("%H:%M")

            time_label = current_time.strftime("%I:%M %p")

            if time_value not in booked_times:

                times.append({
                    "value": time_value,
                    "label": time_label
                })

            current_time += timedelta(minutes=10)

        return {"times": times}

    finally:

        cursor.close()
        db.close()
@app.route("/patient_medical_history")
def patient_medical_history():

    # Only logged-in patients can access this page
    if session.get("role") != "patient":
        return redirect("/")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get only the logged-in patient's medical history
    cursor.execute("""
        SELECT
            mr.record_id,
            mr.diagnosis,
            mr.prescription,
            mr.treatment,
            DATE_FORMAT(
                mr.record_date,
                '%d-%m-%Y'
            ) AS record_date,
            du.name AS doctor_name
        FROM medical_records mr

        JOIN patients p
            ON mr.patient_id = p.patient_id

        JOIN doctors d
            ON mr.doctor_id = d.doctor_id

        JOIN users du
            ON d.user_id = du.user_id

        WHERE p.user_id = %s

        ORDER BY mr.record_date DESC, mr.record_id DESC
    """, (session["user_id"],))

    records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "patient_medical_history.html",
        records=records,
        patient_name=session.get("name")
    )
if __name__ == "__main__":
    app.run(debug=True)