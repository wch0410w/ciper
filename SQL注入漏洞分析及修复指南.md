# SQL 注入漏洞分析及修复指南

## 一、应用概述

本项目是一个基于 **Flask + SQLite3** 的用户管理系统，提供登录、注册、用户搜索等功能。

| 文件 | 作用 |
|------|------|
| `app.py` | 主应用，定义路由和数据库操作 |
| `data/users.db` | SQLite3 数据库，存储用户表 |
| `templates/` | Jinja2 前端模板 |
| `static/css/style.css` | 样式文件 |

---

## 二、漏洞发现过程

### 2.1 代码审计方法

审计 `app.py` 时，重点关注所有与数据库交互的代码行。SQL 注入的核心特征是：**用户输入直接拼接到 SQL 语句中，未经任何过滤或参数化处理**。

关键审计点：
- 所有 `execute()` 调用
- 所有包含 `f"..."` 或 `"..." + 变量` 拼接的字符串
- `cursor.execute()` 的参数传递方式

### 2.2 发现的漏洞点

经过逐行审查，共发现 **2 处 SQL 注入漏洞**：

---

## 三、漏洞详情及攻击演示

### 漏洞 1：注册接口 — INSERT 型 SQL 注入

**文件位置**：`app.py` 第 85 行

**漏洞代码**：

```python
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")

        conn = sqlite3.connect('data/users.db')
        c = conn.cursor()
        # ⚠️ 直接使用 f-string 拼接用户输入
        sql = f"INSERT INTO users (username, password, email, phone) VALUES ('{username}', '{password}', '{email}', '{phone}')"
        c.execute(sql)
        conn.commit()
        conn.close()
```

**问题分析**：

所有四个字段（`username`、`password`、`email`、`phone`）均直接通过 f-string 拼接到 SQL 语句中，攻击者可以在任意字段中注入恶意 SQL。

**攻击演示 1：多行注入**

攻击者在 `username` 字段中输入：

```
attacker', 'pass', 'evil@hack.com', '123'); DROP TABLE users; --
```

此时拼接后的 SQL 变为：

```sql
INSERT INTO users (username, password, email, phone) VALUES ('attacker', 'pass', 'evil@hack.com', '123'); DROP TABLE users; --', '', '', '')
```

效果：
1. 先插入一条恶意用户记录
2. 接着执行 `DROP TABLE users` 删除整个用户表
3. `--` 注释掉后续内容，保证语法正确

**攻击演示 2：覆盖管理员密码**

攻击者在 `username` 字段中输入：

```
hacker', 'newpass', 'hack@hack.com', '999'); UPDATE users SET password='hacked' WHERE username='admin'; --
```

拼接后 SQL：

```sql
INSERT INTO users (username, password, email, phone) VALUES ('hacker', 'newpass', 'hack@hack.com', '999'); UPDATE users SET password='hacked' WHERE username='admin'; --', '', '', '')
```

效果：攻击者注册账号的同时，将管理员密码篡改为 `hacked`。

> **注意**：由于 Python 的 `sqlite3` 模块默认不支持一条 `execute()` 执行多条 SQL 语句，上述多语句攻击在实际 SQLite 环境中会被拦截。但漏洞仍然存在，可通过以下方式利用。

**攻击演示 3：子查询提取数据**

攻击者在 `email` 字段中输入：

```
' || (SELECT password FROM users WHERE username='admin') || '
```

拼接后 SQL：

```sql
INSERT INTO users (username, password, email, phone) VALUES ('attacker', 'pass', '' || (SELECT password FROM users WHERE username='admin') || '', '123')
```

效果：注册成功后，新用户的 `email` 字段中将包含 `admin` 的密码，登录后即可在个人资料页看到。

**攻击演示 4：SQLite 系统信息泄露**

攻击者在 `phone` 字段中输入：

```
' || (SELECT sql FROM sqlite_master WHERE type='table' LIMIT 1) || '
```

效果：获得数据库中所有表的结构信息。

---

### 漏洞 2：搜索接口 — SELECT 型 SQL 注入

**文件位置**：`app.py` 第 103 行

**漏洞代码**：

```python
@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    results = []
    if keyword:
        conn = sqlite3.connect('data/users.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # ⚠️ 直接使用 f-string 拼接用户输入
        sql = f"SELECT * FROM users WHERE username LIKE '%{keyword}%' OR email LIKE '%{keyword}%'"
        c.execute(sql)
        rows = c.fetchall()
```

**问题分析**：

搜索关键词通过 URL 参数传入（GET 请求），直接拼接到 `LIKE` 查询中。这是最典型的 SQL 注入场景，由于结果会回显在搜索结果表格中，非常适合 **UNION 注入**。

**攻击演示 1：利用 UNION 获取管理员密码**

攻击者直接在 URL 中输入：

```
http://localhost:5000/search?keyword=' UNION SELECT 1, username, password, email, phone FROM users WHERE '1'='1
```

拼接后的 SQL：

```sql
SELECT * FROM users WHERE username LIKE '%' UNION SELECT 1, username, password, email, phone FROM users WHERE '1'='1%' OR email LIKE '%' UNION SELECT 1, username, password, email, phone FROM users WHERE '1'='1%'
```

效果：搜索结果表格中会直接展示所有用户的用户名和密码（包括 `admin` 的密码 `admin123`）。

**攻击演示 2：获取数据库结构**

```
http://localhost:5000/search?keyword=' UNION SELECT 1, name, sql, '', '' FROM sqlite_master WHERE type='table' --
```

效果：在搜索结果中直接看到建表 SQL 语句，掌握完整数据库结构。

**攻击演示 3：布尔盲注（当回显受限时）**

```
http://localhost:5000/search?keyword=admin' AND SUBSTR((SELECT password FROM users LIMIT 1),1,1)='a' --
```

通过判断搜索结果是否包含 `admin`，逐字符猜解密码。如果返回 `admin` 则条件为真，否则为假。

**攻击演示 4：时间盲注（SQLite）**

```
http://localhost:5000/search?keyword=' OR (SELECT CASE WHEN (SUBSTR(password,1,1)='a') THEN RANDOMBLOB(100000000) ELSE 0 END FROM users WHERE username='admin') --
```

通过响应时间差异判断猜解是否正确。

---

## 四、漏洞总结

| 漏洞点 | 类型 | 风险等级 | 影响 |
|--------|------|----------|------|
| `/register` (POST) | INSERT 型 SQL 注入 | **高危** | 数据篡改、信息泄露、数据库破坏 |
| `/search` (GET) | SELECT 型 SQL 注入 | **严重** | 全库数据泄露（含密码）、数据库结构泄露 |

**危害汇总**：
- 可获取所有用户的用户名和明文密码
- 可获取数据库完整结构（表名、字段名）
- 可篡改任意用户数据（包括管理员密码）
- 可破坏数据库（删除表/数据）
- `/search` 注入点位于 GET 参数中，攻击者可直接在浏览器地址栏操作，利用门槛极低

---

## 五、修复方案

### 5.1 核心原则：使用参数化查询（Parameterized Query）

**绝对不要再使用 f-string、`%` 格式化、`+` 拼接等方式将用户输入嵌入 SQL 语句。**

SQLite3 的 `execute()` 方法原生支持参数化查询，将用户输入作为第二个参数的元组传入即可。数据库驱动会自动对参数做转义处理，确保输入被当作"纯数据"而非"SQL 代码"执行。

### 5.2 修复 `/register` 接口

**修复前**：

```python
username = request.form.get("username", "")
password = request.form.get("password", "")
email = request.form.get("email", "")
phone = request.form.get("phone", "")

conn = sqlite3.connect('data/users.db')
c = conn.cursor()
sql = f"INSERT INTO users (username, password, email, phone) VALUES ('{username}', '{password}', '{email}', '{phone}')"
c.execute(sql)
conn.commit()
conn.close()
```

**修复后**：

```python
username = request.form.get("username", "")
password = request.form.get("password", "")
email = request.form.get("email", "")
phone = request.form.get("phone", "")

conn = sqlite3.connect('data/users.db')
c = conn.cursor()
sql = "INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)"
c.execute(sql, (username, password, email, phone))
conn.commit()
conn.close()
```

**关键变化**：
1. SQL 语句中的 `'{username}'` → 替换为占位符 `?`
2. `c.execute(sql)` → 改为 `c.execute(sql, (参数元组))`
3. 数据库驱动自动处理转义，用户的恶意输入被当作纯字符串存储，永远不会被解释为 SQL 命令

### 5.3 修复 `/search` 接口

**修复前**：

```python
keyword = request.args.get("keyword", "")
if keyword:
    conn = sqlite3.connect('data/users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    sql = f"SELECT * FROM users WHERE username LIKE '%{keyword}%' OR email LIKE '%{keyword}%'"
    c.execute(sql)
    rows = c.fetchall()
```

**修复后**：

```python
keyword = request.args.get("keyword", "")
if keyword:
    conn = sqlite3.connect('data/users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    sql = "SELECT * FROM users WHERE username LIKE ? OR email LIKE ?"
    search_pattern = f"%{keyword}%"
    c.execute(sql, (search_pattern, search_pattern))
    rows = c.fetchall()
```

**关键变化**：
1. `'%{keyword}%'` 不再在 SQL 字符串中拼接
2. 先在 Python 端构造好 `%keyword%` 模式字符串
3. 将模式字符串作为参数传入 `execute()`
4. 数据库驱动会将整个 `%keyword%` 当作一个完整的字符串值，即时其中包含 `'` 或 `--` 等字符也不会影响 SQL 语义

### 5.4 修复后的完整代码示例

以下是两个路由修复后的完整代码：

```python
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")

        conn = sqlite3.connect('data/users.db')
        c = conn.cursor()
        sql = "INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)"
        c.execute(sql, (username, password, email, phone))
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
        sql = "SELECT * FROM users WHERE username LIKE ? OR email LIKE ?"
        search_pattern = f"%{keyword}%"
        c.execute(sql, (search_pattern, search_pattern))
        rows = c.fetchall()
        results = [dict(row) for row in rows]
        conn.close()

    username = session.get("username")
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
    return render_template("index.html", username=username, user=user_info, keyword=keyword, results=results)
```

---

## 六、补充安全建议

### 6.1 密码安全

当前系统密码以**明文**存储在数据库和内存字典中，建议：

- 使用 `werkzeug.security` 中的 `generate_password_hash()` 和 `check_password_hash()` 进行密码哈希存储
- 切勿在页面展示用户密码（`templates/index.html` 第 11 行暴露了密码）

```python
from werkzeug.security import generate_password_hash, check_password_hash

# 注册时存储哈希
password_hash = generate_password_hash(password)
c.execute("INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)",
          (username, password_hash, email, phone))

# 登录时验证哈希
if check_password_hash(stored_hash, input_password):
    # 登录成功
```

### 6.2 输入校验

即使使用了参数化查询，仍建议增加输入校验层：

```python
import re

def validate_input(value, field_type="text"):
    if not value or len(value) > 100:
        return False
    if field_type == "username":
        return bool(re.match(r'^[a-zA-Z0-9_]{3,20}$', value))
    if field_type == "email":
        return bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', value))
    if field_type == "phone":
        return bool(re.match(r'^[0-9]{6,15}$', value))
    return True
```

### 6.3 最小权限原则

- 应用连接数据库时使用受限账号（如只赋予 SELECT、INSERT、UPDATE 权限，不赋予 DROP、ALTER 权限）
- 生产环境关闭 `debug=True`，避免错误信息泄露

```python
# 生产环境配置
app.run(debug=False, host="127.0.0.1", port=5000)
```

### 6.4 日志及监控

- 记录所有数据库操作日志（当前 `print(f"[SQL] {sql}")` 仅输出到控制台，生产环境应写入日志文件）
- 对异常数据库操作（如包含 `DROP`、`UNION`、`--` 等关键字的 SQL）进行告警

---

## 七、修复方案总结

| 修复项 | 方法 |
|--------|------|
| SQL 注入（核心） | 所有 `c.execute()` 使用 `?` 占位符 + 参数元组 |
| 密码明文存储 | 使用 `werkzeug.security` 哈希 |
| 调试模式 | 生产环境关闭 `debug=True` |
| 数据库权限 | 使用最小权限账号 |
| 输入校验 | 增加长度和格式校验 |
| 页面信息泄露 | 移除密码字段展示 |

**一句话总结**：永远不要拼接用户输入到 SQL 语句中，始终使用参数化查询（`?` 占位符 + 参数元组）。
