from flask import Flask, render_template, request, redirect, session
import sqlite3, os, uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "dev-key-2025"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

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


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB


def allowed_file(filename):
    """检查文件扩展名是否在白名单内"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_image_content(file_stream):
    """验证文件内容是否为真实图片（检查文件头魔术数字）"""
    header = file_stream.read(16)
    file_stream.seek(0)  # 重置文件指针

    magic_numbers = {
        b'\xff\xd8\xff': 'jpg',
        b'\x89PNG\r\n\x1a\n': 'png',
        b'GIF87a': 'gif',
        b'GIF89a': 'gif',
        b'RIFF': 'webp',
    }

    for magic, file_type in magic_numbers.items():
        if header.startswith(magic):
            return True, file_type

    return False, None


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


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":
        f = request.files.get("file")

        # 1. 检查是否选择了文件
        if not f or not f.filename:
            return render_template("upload.html", error="请选择要上传的文件")

        # 2. 检查文件名是否为空
        if f.filename == '':
            return render_template("upload.html", error="文件名不能为空")

        # 3. 校验文件扩展名（白名单方式）
        if not allowed_file(f.filename):
            return render_template("upload.html",
                error=f"不支持的文件类型，仅允许上传：{', '.join(ALLOWED_EXTENSIONS)}")

        # 4. 校验文件内容（文件头魔术数字）
        is_valid, detected_type = validate_image_content(f.stream)
        if not is_valid:
            return render_template("upload.html", error="文件内容验证失败，请上传真实的图片文件")

        # 5. 检查文件大小（Content-Length 预检）
        content_length = request.content_length
        if content_length and content_length > MAX_FILE_SIZE:
            return render_template("upload.html", error="文件大小超过限制（最大 2MB）")

        # 6. 使用安全文件名并添加随机前缀避免冲突和路径穿越
        original_ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else ''
        safe_filename = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"

        # 7. 限制文件名长度
        if len(safe_filename) > 255:
            safe_filename = f"{uuid.uuid4().hex}.{original_ext}"

        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, safe_filename)

        # 8. 额外防护：确保最终路径在允许的目录内（防止路径穿越）
        real_filepath = os.path.realpath(filepath)
        real_save_dir = os.path.realpath(save_dir)
        if not real_filepath.startswith(real_save_dir + os.sep):
            return render_template("upload.html", error="非法的文件路径")

        # 9. 保存文件到磁盘（同时检查实际大小）
        f.seek(0, os.SEEK_END)
        actual_size = f.tell()
        f.seek(0)
        if actual_size > MAX_FILE_SIZE:
            return render_template("upload.html", error="文件大小超过限制（最大 2MB）")

        f.save(filepath)
        url = f"/static/uploads/{safe_filename}"
        return render_template("upload.html", url=url)

    return render_template("upload.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
