from db import get_connection


def login_user(
    username,
    password
):

    conn = get_connection()

    cursor = conn.cursor(
        dictionary=True
    )

    sql = """
    SELECT *
    FROM users
    WHERE username=%s
    AND password=%s
    """

    cursor.execute(
        sql,
        (
            username,
            password
        )
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return user