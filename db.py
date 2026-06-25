import mysql.connector

connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="kapil26",
    database="vegetable_billing"
)

cursor = connection.cursor(dictionary=True)