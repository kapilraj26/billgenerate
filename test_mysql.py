import mysql.connector

try:
    db = mysql.connector.connect(
        host="reseau.proxy.rlwy.net",
        port=26811,
        user="root",
        password="ZEcmLtSTaYcgKTlBgoVevaiiwzhGOYIz",
        database="railway"
    )

    print("✅ Connected successfully!")

    cursor = db.cursor()
    cursor.execute("SELECT VERSION();")
    print(cursor.fetchone())

    db.close()

except Exception as e:
    print("❌ Error:", e)