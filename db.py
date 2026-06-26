import mysql.connector

db = mysql.connector.connect(
    host="mysql.railway.internal",
    port=3306,
    user="root",
    password="ZEcmLtSTaYcgKTlBgoVevaiiwzhGOYIz",
    database="railway"
)

cursor = db.cursor(dictionary=True)