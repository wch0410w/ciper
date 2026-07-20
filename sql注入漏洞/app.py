from flask import Flask, render_template, request, redirect, session
import sqlite3, os

app = Flask(__name__)
app.secret_key = "dev-key-2025"

USERS = {
    "admin": {
        "username": "admin",
        "password": "admin123",
        "role": "admin",
        "email": "admin@example.com",
        "phone": "13800138000",
        "balance": 99999
    },
    "alice": {
        "username": "alice",
        "password": "alice2025",
        "role": "user",
        "email": "alice@example.com",
        "phone": "13900139001",
        "balance": 100
    }
}


def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT,
        phone TEXT
    )''')
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone) VALUES ('admin', 'admin123', 'admin@example.com', '13800138000')")
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone) VALUES ('alice', 'alice2025', 'alice@example.com', '13900139001')")
    conn.commit()
    conn.close()


@app.route("/")
def index():
    username = session.get("username")
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
    return render_template("index.html", username=username, user=user_info)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username in USERS and USERS[username]["password"] == password:
            session["username"] = username
            user_info = USERS[username]
            return render_template("index.html", username=username, user=user_info)

        return render_template("login.html", error="用户名或密码错误")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")

        conn = sqlite3.connect('data/users.db')
        c = conn.cursor()
        sql = f"INSERT INTO users (username, password, email, phone) VALUES ('{username}', '{password}', '{email}', '{phone}')"
        print(f"[SQL] {sql}")
        c.execute(sql)
        conn.commit()
        conn.close()
        return render_template("login.html", error="注册成功，请登录")

    return render_template("register.html")


@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    results = []
    if keyword:
        conn = sqlite3.connect('data/users.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        sql = f"SELECT * FROM users WHERE username LIKE '%{keyword}%' OR email LIKE '%{keyword}%'"
        print(f"[SQL] {sql}")
        c.execute(sql)
        rows = c.fetchall()
        results = [dict(row) for row in rows]
        conn.close()

    username = session.get("username")
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
    return render_template("index.html", username=username, user=user_info, keyword=keyword, results=results)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
