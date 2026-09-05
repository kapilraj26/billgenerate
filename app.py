from flask import (
    Flask,
    render_template,
    request,
    session,
    jsonify,
    send_file
)

from datetime import datetime
from io import BytesIO
import os

import mysql.connector
from xml.sax.saxutils import escape

from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "vegetable_secret"
)


# =========================================================
# SHOP DETAILS
# =========================================================

SHOP_NAME = "MANOGARAN"
SHOP_PHONE = "9094415150"


# =========================================================
# DATABASE CONNECTION - AIVEN MYSQL
# =========================================================

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER", "avnadmin")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "defaultdb")


if not DB_HOST:
    raise RuntimeError(
        "DB_HOST is not set. Please set your Aiven MySQL host."
    )

if not DB_PORT:
    raise RuntimeError(
        "DB_PORT is not set. Please set your Aiven MySQL port."
    )

if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD is not set. Please set your Aiven MySQL password."
    )


try:

    db = mysql.connector.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True
    )

    cursor = db.cursor(dictionary=True)

except mysql.connector.Error as e:

    raise RuntimeError(
        f"Database connection failed: {e}"
    )


# =========================================================
# HOME / BILLING PAGE
# LOGIN REMOVED
# =========================================================

@app.route("/", methods=["GET", "POST"])
def index():

    if request.method == "POST":

        customer = request.form.get(
            "customer",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        received = float(
            request.form.get("received") or 0
        )

        # -------------------------------------------------
        # CUSTOMER SEARCH
        # -------------------------------------------------

        cursor.execute(
            """
            SELECT *
            FROM customers
            WHERE phone=%s
            """,
            (phone,)
        )

        customer_data = cursor.fetchone()


        # -------------------------------------------------
        # EXISTING CUSTOMER
        # -------------------------------------------------

        if customer_data:

            customer_id = customer_data["id"]

            pending = float(
                customer_data["pending_balance"] or 0
            )


        # -------------------------------------------------
        # NEW CUSTOMER
        # -------------------------------------------------

        else:

            cursor.execute(
                """
                INSERT INTO customers
                (
                    customer_name,
                    phone,
                    pending_balance
                )
                VALUES (%s,%s,%s)
                """,
                (
                    customer,
                    phone,
                    0
                )
            )

            db.commit()

            customer_id = cursor.lastrowid

            pending = 0


        # -------------------------------------------------
        # PRODUCTS
        # -------------------------------------------------

        products = request.form.getlist(
            "product[]"
        )

        qtys = request.form.getlist(
            "qty[]"
        )

        rates = request.form.getlist(
            "rate[]"
        )


        items = []

        total_qty = 0

        grand_total = 0


        # -------------------------------------------------
        # CALCULATE BILL
        # -------------------------------------------------

        for p, q, r in zip(
            products,
            qtys,
            rates
        ):

            if not p.strip():
                continue


            qty = float(q or 0)

            rate = float(r or 0)

            amount = qty * rate


            total_qty += qty

            grand_total += amount


            items.append(
                {
                    "product": p.strip(),
                    "qty": qty,
                    "rate": rate,
                    "amount": amount
                }
            )


        # -------------------------------------------------
        # BALANCE
        # -------------------------------------------------

        net_bill = (
            grand_total +
            pending
        )

        balance = (
            net_bill -
            received
        )


        # -------------------------------------------------
        # BILL NUMBER
        # -------------------------------------------------

        bill_no = datetime.now().strftime(
            "%d%m%H%M%S"
        )


        today = datetime.now().date()


        display_date = datetime.now().strftime(
            "%d/%m/%Y"
        )


        # -------------------------------------------------
        # SAVE BILL
        # -------------------------------------------------

        cursor.execute(
            """
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
            """,
            (
                bill_no,
                customer_id,
                today,
                total_qty,
                grand_total,
                received,
                balance
            )
        )

        db.commit()


        bill_id = cursor.lastrowid


        # -------------------------------------------------
        # SAVE BILL ITEMS
        # -------------------------------------------------

        for item in items:

            cursor.execute(
                """
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
                """,
                (
                    bill_id,
                    item["product"],
                    item["qty"],
                    item["rate"],
                    item["amount"]
                )
            )


        db.commit()


        # -------------------------------------------------
        # UPDATE CUSTOMER BALANCE
        # -------------------------------------------------

        cursor.execute(
            """
            UPDATE customers
            SET pending_balance=%s
            WHERE id=%s
            """,
            (
                balance,
                customer_id
            )
        )

        db.commit()


        # =================================================
        # SAVE SESSION FOR PDF
        # =================================================

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


        # =================================================
        # INVOICE PAGE
        # =================================================

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


    # =====================================================
    # DIRECT BILLING PAGE
    # =====================================================

    return render_template(
        "index.html"
    )


# =========================================================
# CUSTOMER SEARCH
# =========================================================

@app.route("/customer/<phone>")
def customer(phone):

    cursor.execute(
        """
        SELECT *
        FROM customers
        WHERE phone=%s
        """,
        (phone,)
    )

    customer_data = cursor.fetchone()


    if customer_data:

        return jsonify(
            {
                "name":
                    customer_data[
                        "customer_name"
                    ],

                "balance":
                    float(
                        customer_data[
                            "pending_balance"
                        ] or 0
                    )
            }
        )


    return jsonify(
        {
            "name": "",
            "balance": 0
        }
    )


# =========================================================
# BILL HISTORY
# =========================================================

@app.route("/history")
def history():

    cursor.execute(
        """
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
        """
    )

    bills = cursor.fetchall()


    return render_template(
        "history.html",
        bills=bills
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    today = datetime.now().date()


    cursor.execute(
        """
        SELECT
            COUNT(*) AS bills,
            SUM(grand_total) AS sales,
            SUM(received) AS received,
            SUM(balance) AS balance
        FROM bills
        WHERE bill_date=%s
        """,
        (today,)
    )


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


# =========================================================
# TAMIL FONT SETUP
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

FONT_DIR = os.path.join(
    BASE_DIR,
    "fonts"
)


TAMIL_REGULAR = os.path.join(
    FONT_DIR,
    "NotoSansTamil-Regular.ttf"
)


TAMIL_BOLD = os.path.join(
    FONT_DIR,
    "NotoSansTamil-Bold.ttf"
)


# =========================================================
# REGISTER TAMIL FONTS
# =========================================================

if os.path.exists(TAMIL_REGULAR):

    pdfmetrics.registerFont(
        TTFont(
            "NotoTamil",
            TAMIL_REGULAR
        )
    )


if os.path.exists(TAMIL_BOLD):

    pdfmetrics.registerFont(
        TTFont(
            "NotoTamilBold",
            TAMIL_BOLD
        )
    )


# =========================================================
# PDF
# =========================================================

@app.route("/pdf")
def pdf():

    buffer = BytesIO()


    # -----------------------------------------------------
    # FONT
    # -----------------------------------------------------

    if os.path.exists(TAMIL_REGULAR):

        FONT_NORMAL = "NotoTamil"

    else:

        FONT_NORMAL = "Helvetica"


    if os.path.exists(TAMIL_BOLD):

        FONT_BOLD = "NotoTamilBold"

    else:

        FONT_BOLD = "Helvetica-Bold"


    # -----------------------------------------------------
    # SESSION DATA
    # -----------------------------------------------------

    customer = session.get(
        "customer",
        ""
    )

    phone = session.get(
        "phone",
        ""
    )

    items = session.get(
        "items",
        []
    )


    bill_no = session.get(
        "bill_no",
        "0001"
    )


    bill_date = session.get(
        "today",
        datetime.now().strftime(
            "%d/%m/%Y"
        )
    )


    pending = float(
        session.get(
            "pending",
            0
        ) or 0
    )


    received = float(
        session.get(
            "received",
            0
        ) or 0
    )


    total_qty = float(
        session.get(
            "total_qty",
            0
        ) or 0
    )


    grand_total = float(
        session.get(
            "grand_total",
            0
        ) or 0
    )


    net_bill = float(
        session.get(
            "net_bill",
            grand_total + pending
        ) or 0
    )


    balance = float(
        session.get(
            "balance",
            net_bill - received
        ) or 0
    )


    # -----------------------------------------------------
    # SHOP DETAILS
    # -----------------------------------------------------

    shop_tamil_name = "ஸ்ரீ கருப்பையா துணை"

    shop_name = "G. மனோகாரன்"

    shop_phone = "9094415150"


    # -----------------------------------------------------
    # PDF PAGE
    # -----------------------------------------------------

    doc = SimpleDocTemplate(
        buffer,

        pagesize=A4,

        rightMargin=8 * mm,

        leftMargin=8 * mm,

        topMargin=7 * mm,

        bottomMargin=7 * mm
    )


    elements = []


    # =====================================================
    # STYLES
    # =====================================================

    title_style = ParagraphStyle(
        "TamilTitle",

        fontName=FONT_BOLD,

        fontSize=18,

        leading=22,

        alignment=TA_CENTER,

        textColor=colors.HexColor(
            "#4B0082"
        ),

        spaceAfter=2
    )


    shop_style = ParagraphStyle(
        "ShopName",

        fontName=FONT_BOLD,

        fontSize=11,

        leading=14,

        alignment=TA_CENTER,

        textColor=colors.red
    )


    phone_style = ParagraphStyle(
        "ShopPhone",

        fontName=FONT_BOLD,

        fontSize=11,

        leading=14,

        alignment=TA_CENTER,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    normal_style = ParagraphStyle(
        "NormalTamil",

        fontName=FONT_NORMAL,

        fontSize=9.5,

        leading=13
    )


    header_style = ParagraphStyle(
        "Header",

        fontName=FONT_BOLD,

        fontSize=9.5,

        leading=12,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    table_header_style = ParagraphStyle(
        "TableHeader",

        fontName=FONT_BOLD,

        fontSize=9.5,

        leading=12,

        alignment=TA_CENTER,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    product_style = ParagraphStyle(
        "Product",

        fontName=FONT_NORMAL,

        fontSize=9.5,

        leading=13,

        alignment=TA_LEFT
    )


    center_style = ParagraphStyle(
        "Center",

        fontName=FONT_NORMAL,

        fontSize=9.5,

        leading=13,

        alignment=TA_CENTER
    )


    right_style = ParagraphStyle(
        "Right",

        fontName=FONT_NORMAL,

        fontSize=9.5,

        leading=13,

        alignment=TA_RIGHT
    )


    summary_label_style = ParagraphStyle(
        "SummaryLabel",

        fontName=FONT_BOLD,

        fontSize=9.5,

        leading=13,

        alignment=TA_LEFT,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    summary_value_style = ParagraphStyle(
        "SummaryValue",

        fontName=FONT_BOLD,

        fontSize=9.5,

        leading=13,

        alignment=TA_RIGHT
    )


    # =====================================================
    # DATE + BILL NUMBER
    # =====================================================

    bill_no_style = ParagraphStyle(
        "BillNo",

        fontName=FONT_BOLD,

        fontSize=9.5,

        leading=12,

        alignment=TA_RIGHT,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    top_data = [
        [
            Paragraph(
                f"<b>Date :</b> "
                f"{escape(str(bill_date))}",

                header_style
            ),

            Paragraph(
                f"<b>Bill No. :</b> "
                f"{escape(str(bill_no))}",

                bill_no_style
            )
        ]
    ]


    top_table = Table(
        top_data,

        colWidths=[
            90 * mm,
            90 * mm
        ]
    )


    top_table.setStyle(
        TableStyle(
            [
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP"
                ),

                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0
                ),

                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0
                )
            ]
        )
    )


    elements.append(
        top_table
    )

    elements.append(
        Spacer(1, 3)
    )


    # =====================================================
    # SHOP HEADER
    # =====================================================

    elements.append(
        Paragraph(
            shop_tamil_name,
            title_style
        )
    )


    elements.append(
        Paragraph(
            shop_name,
            shop_style
        )
    )


    elements.append(
        Paragraph(
            shop_phone,
            phone_style
        )
    )


    elements.append(
        Spacer(1, 7)
    )


    # =====================================================
    # CUSTOMER DETAILS
    # =====================================================

    customer_text = escape(
        str(customer)
    )

    phone_text = escape(
        str(phone)
    )


    customer_table = Table(
        [
            [
                Paragraph(
                    f"<b>Name :</b> "
                    f"{customer_text}",

                    normal_style
                )
            ],

            [
                Paragraph(
                    f"<b>Ph. No. :</b> "
                    f"{phone_text}",

                    normal_style
                )
            ]
        ],

        colWidths=[
            180 * mm
        ]
    )


    customer_table.setStyle(
        TableStyle(
            [
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    0.8,
                    colors.black
                ),

                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0
                ),

                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    4
                )
            ]
        )
    )


    elements.append(
        customer_table
    )

    elements.append(
        Spacer(1, 5)
    )


    # =====================================================
    # PRODUCT TABLE
    # =====================================================

    data = [
        [
            Paragraph(
                "Item",
                table_header_style
            ),

            Paragraph(
                "Qty.",
                table_header_style
            ),

            Paragraph(
                "Rate",
                table_header_style
            ),

            Paragraph(
                "Total",
                table_header_style
            )
        ]
    ]


    calculated_qty = 0

    calculated_total = 0


    for item in items:

        product = escape(
            str(
                item.get(
                    "product",
                    ""
                )
            )
        )


        qty = float(
            item.get(
                "qty",
                0
            ) or 0
        )


        rate = float(
            item.get(
                "rate",
                0
            ) or 0
        )


        amount = float(
            item.get(
                "amount",
                qty * rate
            ) or 0
        )


        calculated_qty += qty

        calculated_total += amount


        data.append(
            [
                Paragraph(
                    product,
                    product_style
                ),

                Paragraph(
                    f"{qty:g}",
                    center_style
                ),

                Paragraph(
                    f"{rate:g}",
                    center_style
                ),

                Paragraph(
                    f"{amount:.2f}",
                    right_style
                )
            ]
        )


    # Empty row
    data.append(
        [
            "",
            "",
            "",
            ""
        ]
    )


    product_table = Table(
        data,

        colWidths=[
            60 * mm,
            30 * mm,
            30 * mm,
            60 * mm
        ],

        repeatRows=1
    )


    product_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(
                        "#E5E5E7"
                    )
                ),

                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.black
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),

                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    3
                ),

                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    3
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5
                )
            ]
        )
    )


    elements.append(
        product_table
    )

    elements.append(
        Spacer(1, 4)
    )


    # =====================================================
    # TOTAL
    # =====================================================

    total_row = Table(
        [
            [
                Paragraph(
                    f"<b>Total Qty. : "
                    f"{calculated_qty:.2f}</b>",

                    summary_label_style
                ),

                Paragraph(
                    "<b>Total :</b>",

                    summary_label_style
                ),

                Paragraph(
                    f"<b>"
                    f"{calculated_total:.2f}"
                    f"</b>",

                    summary_value_style
                )
            ]
        ],

        colWidths=[
            75 * mm,
            45 * mm,
            60 * mm
        ]
    )


    total_row.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor(
                        "#FCE4D6"
                    )
                ),

                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.black
                ),

                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.black
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                )
            ]
        )
    )


    elements.append(
        total_row
    )


    # =====================================================
    # BALANCE SUMMARY
    # DISCOUNT / GST REMOVED
    # =====================================================

    balance_label_style = ParagraphStyle(
        "BalanceLabel",

        fontName=FONT_BOLD,

        fontSize=10.5,

        leading=14,

        alignment=TA_LEFT,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    balance_value_style = ParagraphStyle(
        "BalanceValue",

        fontName=FONT_BOLD,

        fontSize=10.5,

        leading=14,

        alignment=TA_RIGHT,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    summary_table = Table(
        [
            [
                Paragraph(
                    "Previous Balance :",
                    summary_label_style
                ),

                Paragraph(
                    f"{pending:.2f}",
                    summary_value_style
                )
            ],

            [
                Paragraph(
                    "Net Bill Amount :",
                    summary_label_style
                ),

                Paragraph(
                    f"{net_bill:.2f}",
                    summary_value_style
                )
            ],

            [
                Paragraph(
                    "Received :",
                    summary_label_style
                ),

                Paragraph(
                    f"{received:.2f}",
                    summary_value_style
                )
            ],

            [
                Paragraph(
                    "Balance :",
                    balance_label_style
                ),

                Paragraph(
                    f"<b>{balance:.2f}</b>",
                    balance_value_style
                )
            ]
        ],

        colWidths=[
            90 * mm,
            90 * mm
        ]
    )


    summary_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor(
                        "#FCE4D6"
                    )
                ),

                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.black
                ),

                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    colors.black
                ),

                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),

                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                ),

                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                )
            ]
        )
    )


    elements.append(
        summary_table
    )

    elements.append(
        Spacer(1, 7)
    )


    # =====================================================
    # FOOTER
    # =====================================================

    footer_style = ParagraphStyle(
        "Footer",

        fontName=FONT_BOLD,

        fontSize=9.5,

        leading=13,

        alignment=TA_CENTER,

        textColor=colors.HexColor(
            "#4B0082"
        )
    )


    elements.append(
        Paragraph(
            "நன்றி / Thank You",
            footer_style
        )
    )


    # =====================================================
    # BUILD PDF
    # =====================================================

    doc.build(
        elements
    )


    buffer.seek(0)


    return send_file(
        buffer,

        as_attachment=True,

        download_name="invoice.pdf",

        mimetype="application/pdf"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
