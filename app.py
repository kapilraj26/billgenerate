from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for,
    jsonify,
    send_file
)

from datetime import datetime
from io import BytesIO
import mysql.connector

from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "vegetable_secret"

SHOP_NAME = "J45 MANO"
SHOP_PHONE = "9094415150"

# ==========================
# DATABASE CONNECTION
# ==========================


import os
import mysql.connector

db = mysql.connector.connect(
    host=os.getenv("MYSQLHOST"),
    port=int(os.getenv("MYSQLPORT")),
    user=os.getenv("MYSQLUSER"),
    password=os.getenv("MYSQLPASSWORD"),
    database=os.getenv("MYSQLDATABASE"),
    autocommit=True
)

cursor = db.cursor(dictionary=True)

# ==========================
# LOGIN
# ==========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        cursor.execute("""
            SELECT *
            FROM users
            WHERE username=%s
            AND password=%s
        """, (username, password))

        user = cursor.fetchone()

        if user:

            session["user"] = username

            return redirect("/")

        return render_template(
            "login.html",
            error="Invalid Login"
        )

    return render_template("login.html")


# ==========================
# LOGOUT
# ==========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ==========================
# HOME PAGE
# ==========================

@app.route("/", methods=["GET", "POST"])
def index():

    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":

        customer = request.form["customer"]
        phone = request.form["phone"]

        received = float(
            request.form.get("received") or 0
        )

        # Customer Search

        cursor.execute(
            "SELECT * FROM customers WHERE phone=%s",
            (phone,)
        )

        customer_data = cursor.fetchone()

        if customer_data:

            customer_id = customer_data["id"]

            pending = float(
                customer_data["pending_balance"]
            )

        else:

            cursor.execute("""
                INSERT INTO customers
                (
                    customer_name,
                    phone,
                    pending_balance
                )
                VALUES (%s,%s,%s)
            """, (
                customer,
                phone,
                0
            ))

            db.commit()

            customer_id = cursor.lastrowid

            pending = 0

        products = request.form.getlist("product[]")
        qtys = request.form.getlist("qty[]")
        rates = request.form.getlist("rate[]")

        items = []

        total_qty = 0
        grand_total = 0

        for p, q, r in zip(
            products,
            qtys,
            rates
        ):

            if p.strip() == "":
                continue

            qty = float(q or 0)
            rate = float(r or 0)

            amount = qty * rate

            total_qty += qty
            grand_total += amount

            items.append({
                "product": p,
                "qty": qty,
                "rate": rate,
                "amount": amount
            })

        net_bill = grand_total + pending

        balance = net_bill - received

        bill_no = datetime.now().strftime(
            "%d%m%H%M%S"
        )

        today = datetime.now().date()

        display_date = datetime.now().strftime(
            "%d/%m/%Y"
        )

        # Save Bill

        cursor.execute("""
            INSERT INTO bills
            (
                bill_no,
                customer_id,
                bill_date,
                total_qty,
                grand_total,
                received,
                balance
            )
            VALUES
            (%s,%s,%s,%s,%s,%s,%s)
        """, (
            bill_no,
            customer_id,
            today,
            total_qty,
            grand_total,
            received,
            balance
        ))

        db.commit()

        bill_id = cursor.lastrowid

        # Save Products

        for item in items:

            cursor.execute("""
                INSERT INTO bill_items
                (
                    bill_id,
                    product,
                    quantity,
                    rate,
                    amount
                )
                VALUES
                (%s,%s,%s,%s,%s)
            """, (
                bill_id,
                item["product"],
                item["qty"],
                item["rate"],
                item["amount"]
            ))

        db.commit()

        # Update Balance

        cursor.execute("""
            UPDATE customers
            SET pending_balance=%s
            WHERE id=%s
        """, (
            balance,
            customer_id
        ))

        db.commit()

        # Session for PDF

        session["bill_no"] = bill_no
        session["today"] = display_date
        session["customer"] = customer
        session["phone"] = phone
        session["items"] = items
        session["total_qty"] = total_qty
        session["grand_total"] = grand_total
        session["pending"] = pending
        session["received"] = received
        session["net_bill"] = net_bill
        session["balance"] = balance

        return render_template(
            "invoice.html",
            shop=SHOP_NAME,
            shop_phone=SHOP_PHONE,
            today=display_date,
            bill_no=bill_no,
            customer=customer,
            phone=phone,
            items=items,
            total_qty=total_qty,
            grand_total=grand_total,
            pending=pending,
            received=received,
            net_bill=net_bill,
            balance=balance
        )

    return render_template("index.html")


# ==========================
# CUSTOMER SEARCH
# ==========================

@app.route("/customer/<phone>")
def customer(phone):

    cursor.execute(
        "SELECT * FROM customers WHERE phone=%s",
        (phone,)
    )

    customer = cursor.fetchone()

    if customer:

        return jsonify({
            "name": customer["customer_name"],
            "balance": float(
                customer["pending_balance"]
            )
        })

    return jsonify({
        "name": "",
        "balance": 0
    })


# ==========================
# BILL HISTORY
# ==========================

@app.route("/history")
def history():

    cursor.execute("""
        SELECT
            bills.bill_no,
            customers.customer_name,
            bills.bill_date,
            bills.grand_total,
            bills.balance
        FROM bills
        JOIN customers
        ON bills.customer_id =
        customers.id
        ORDER BY bills.id DESC
    """)

    bills = cursor.fetchall()

    return render_template(
        "history.html",
        bills=bills
    )


# ==========================
# DASHBOARD
# ==========================

@app.route("/dashboard")
def dashboard():

    today = datetime.now().date()

    cursor.execute("""
        SELECT
            COUNT(*) AS bills,
            SUM(grand_total) AS sales,
            SUM(received) AS received,
            SUM(balance) AS balance
        FROM bills
        WHERE bill_date=%s
    """, (today,))

    report = cursor.fetchone()

    if report["sales"] is None:
        report["sales"] = 0

    if report["received"] is None:
        report["received"] = 0

    if report["balance"] is None:
        report["balance"] = 0

    return render_template(
        "dashboard.html",
        report=report,
        today=today
    )


# ==========================
# PDF
# ==========================

@app.route("/pdf")
def pdf():

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    elements = []

    elements.append(
        Paragraph(
            SHOP_NAME,
            styles["Title"]
        )
    )

    elements.append(
        Paragraph(
            SHOP_PHONE,
            styles["Heading2"]
        )
    )

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            f"Customer : {session['customer']}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"Phone : {session['phone']}",
            styles["Normal"]
        )
    )

    elements.append(Spacer(1, 20))

    data = [
        ["Product", "Qty", "Rate", "Amount"]
    ]

    for item in session["items"]:

        data.append([
            item["product"],
            item["qty"],
            item["rate"],
            item["amount"]
        ])

    table = Table(data)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0),
         colors.lightgrey),

        ("GRID", (0,0), (-1,-1),
         1, colors.black),

        ("ALIGN", (0,0), (-1,-1),
         "CENTER")
    ]))

    elements.append(table)

    elements.append(Spacer(1, 20))

    elements.append(
        Paragraph(
            f"Balance : ₹{session['balance']}",
            styles["Heading2"]
        )
    )

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="invoice.pdf",
        mimetype="application/pdf"
    )


if __name__ == "__main__":
    app.run(debug=True)