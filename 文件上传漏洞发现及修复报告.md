# 文件上传漏洞发现及修复报告

## 一、报告概述

| 项目 | 内容 |
|------|------|
| **漏洞名称** | 任意文件上传漏洞（Unrestricted File Upload） |
| **漏洞文件** | `app.py` |
| **漏洞位置** | `/upload` 路由（第 118-134 行） |
| **危害等级** | **高危（High）** |
| **发现日期** | 2026-07-21 |

---

## 二、漏洞描述

文件上传漏洞是指 Web 应用程序在处理用户上传的文件时，未对上传文件的类型、内容、大小、文件名等关键属性进行充分的安全校验，导致攻击者可以上传恶意文件，从而控制服务器、窃取数据或进行其他恶意操作。

在本项目中，`/upload` 文件上传接口存在**多项安全缺陷**，攻击者可以利用这些缺陷上传 WebShell、木马程序、钓鱼页面等恶意文件，进而获取服务器权限。

---

## 三、漏洞代码分析

### 3.1 存在漏洞的代码

```python
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":
        f = request.files.get("file")
        if f and f.filename:
            save_dir = "static/uploads"
            os.makedirs(save_dir, exist_ok=True)
            filepath = os.path.join(save_dir, f.filename)  # 问题3：直接使用用户上传的原始文件名
            f.save(filepath)                                 # 问题1：未检查文件类型
            url = f"/static/uploads/{f.filename}"
            return render_template("upload.html", url=url)
        return render_template("upload.html", error="请选择要上传的文件")

    return render_template("upload.html")
```

### 3.2 具体安全问题

#### 问题 1：未校验文件类型

代码中没有对上传文件的扩展名、MIME 类型、文件头魔术数字进行任何检查。攻击者可以上传任意类型的文件。

#### 问题 2：未校验文件内容

即使通过扩展名检查（如果添加了），攻击者也可以伪造文件头，将恶意代码隐藏在看似安全的文件中。

#### 问题 3：直接使用用户提供的原始文件名

`f.filename` 是客户端提供的文件名，攻击者可以伪造恶意文件名，如：
- **路径穿越攻击**：`../../../etc/passwd`、`..\\..\\Windows\\System32\\config\\SAM`
- **XSS 攻击**：文件名中包含 `<script>alert(1)</script>` 等 Payload
- **特殊字符覆盖**：利用空字符截断（`shell.php%00.jpg`）绕过扩展名校验

#### 问题 4：文件存储在公开可访问目录

上传文件保存在 `static/uploads/` 目录下，该目录可通过 URL 直接访问。如果攻击者上传了一个 PHP、JSP、ASPX 等脚本文件（取决于服务器环境），且 Web 服务器配置为解析这些文件，攻击者就能直接执行服务器端代码。

#### 问题 5：缺少文件大小限制（路由层面）

虽然全局设置了 `MAX_CONTENT_LENGTH = 16MB`，但路由本身没有做额外的尺寸校验。攻击者可以通过发送接近限制大小的文件进行拒绝服务（DoS）攻击。

#### 问题 6：缺少文件名长度限制

没有限制文件名的长度，超长文件名可能导致缓冲区溢出或文件系统错误。

#### 问题 7：无 CSRF 防护

上传接口没有 CSRF Token 防护，攻击者可以构造一个恶意的自动提交表单，诱导已登录用户点击后，以该用户的身份上传文件。

---

## 四、攻击场景演示

### 场景 1：上传 WebShell 获取服务器控制权

```bash
# 攻击者创建一个 webshell.py 文件
echo 'import os; os.system("whoami")' > webshell.py

# 通过上传接口上传
curl -X POST http://target-server:5000/upload \
  -F "file=@webshell.py" \
  -b "session=xxx"

# 文件被保存到 /static/uploads/webshell.py
# 如果服务器支持 Python CGI 或通过其他方式能触发执行，即可获取服务器权限
```

### 场景 2：上传 HTML 钓鱼页面

```bash
# 攻击者上传一个伪装成登录页的 HTML 文件
# 用户访问 http://target-server:5000/static/uploads/fake_login.html
# 输入的凭据将被发往攻击者的服务器
```

### 场景 3：路径穿越攻击

```bash
# 攻击者修改文件名进行路径穿越
curl -X POST http://target-server:5000/upload \
  -F "file=@evil.txt;filename=../../../app.py" \
  -b "session=xxx"

# 如果路径穿越成功，可能覆盖 app.py 导致应用被篡改
```

---

## 五、攻击危害

| 危害类别 | 影响描述 |
|----------|----------|
| **远程代码执行（RCE）** | 上传 WebShell 后执行任意系统命令，完全控制服务器 |
| **数据泄露** | 读取服务器上的敏感文件（数据库、配置文件、密钥等） |
| **网页篡改** | 替换网站正常页面，挂上恶意内容或钓鱼页面 |
| **拒绝服务（DoS）** | 上传大量大文件耗尽服务器磁盘空间 |
| **客户端攻击** | 上传带有恶意脚本的文件，对访问用户进行 XSS 攻击 |
| **横向移动** | 以被攻陷的服务器为跳板，攻击内网其他主机 |
| **供应链攻击** | 篡改模板文件或静态资源，在项目下次部署时加载恶意代码 |

---

## 六、修复方案

### 6.1 修复后的安全代码

```python
import os
import uuid
import imghdr
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, session

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

    # 常见图片格式的魔术数字
    magic_numbers = {
        b'\xff\xd8\xff': 'jpg',      # JPEG
        b'\x89PNG\r\n\x1a\n': 'png', # PNG
        b'GIF87a': 'gif',            # GIF89a
        b'GIF89a': 'gif',            # GIF87a
        b'RIFF': 'webp',             # WebP (需进一步检查 WEBP 标识)
    }

    for magic, file_type in magic_numbers.items():
        if header.startswith(magic):
            return True, file_type

    return False, None

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

        # 5. 检查文件大小（Content-Length 预检 + 实际大小校验）
        content_length = request.content_length
        if content_length and content_length > MAX_FILE_SIZE:
            return render_template("upload.html", error="文件大小超过限制（最大 2MB）")

        # 6. 使用安全文件名并添加随机前缀避免冲突和路径穿越
        original_ext = f.filename.rsplit('.', 1)[1].lower()
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

        # 9. 保存文件到磁盘（同时检查大小，避免流式上传超过限制）
        f.seek(0, os.SEEK_END)
        actual_size = f.tell()
        f.seek(0)
        if actual_size > MAX_FILE_SIZE:
            return render_template("upload.html", error="文件大小超过限制（最大 2MB）")

        f.save(filepath)
        url = f"/static/uploads/{safe_filename}"
        return render_template("upload.html", url=url)

    return render_template("upload.html")
```

### 6.2 修复要点总结

| 序号 | 修复措施 | 解决的问题 |
|------|----------|------------|
| 1 | **扩展名白名单校验** | 只允许特定后缀（png/jpg/gif/webp），拒绝所有不可信的文件类型 |
| 2 | **文件头魔术数字检查** | 验证文件内容的真实类型，防止伪造扩展名绕过检查 |
| 3 | **文件大小双重校验** | Content-Length 预检 + 实际大小校验，防止大文件消耗服务器资源 |
| 4 | **安全文件名处理** | 使用 `secure_filename()` 和 UUID 生成安全的文件名，防止路径穿越和文件名冲突 |
| 5 | **路径穿越防护** | 使用 `os.path.realpath()` 确认最终路径在允许的目录内 |
| 6 | **保存目录隔离** | 将上传目录设置到应用目录下而非相对于工作目录，避免路径穿越 |
| 7 | **文件名长度限制** | 限制文件名总长度不超过 255 字符，防止缓冲区异常 |

### 6.3 服务器层面加固建议

| 措施 | 说明 |
|------|------|
| **禁止上传目录的脚本执行** | 在 Web 服务器配置中，对 `uploads` 目录禁用脚本引擎（如 PHP-FPM、mod_python） |
| **添加 Content-Security-Policy 头** | 限制可执行脚本的来源，降低 XSS 风险 |
| **添加 X-Content-Type-Options: nosniff** | 阻止浏览器 MIME 类型嗅探，防止将上传的图片当作脚本执行 |
| **设置合理的磁盘配额** | 限制上传目录的总大小，防止磁盘被写满 |
| **定期清理上传目录** | 使用定时任务清理过期或无用的上传文件 |

---

## 七、验证方法

### 7.1 渗透测试验证

使用以下方法验证漏洞是否已修复：

```bash
# 测试1：上传非图片文件，预期被拒绝
curl -X POST http://localhost:5000/upload \
  -F "file=@evil.php;filename=shell.php" \
  -b "session=xxx"

# 测试2：上传图片文件，预期成功
curl -X POST http://localhost:5000/upload \
  -F "file=@avatar.png" \
  -b "session=xxx"

# 测试3：路径穿越攻击，预期被拒绝
curl -X POST http://localhost:5000/upload \
  -F "file=@evil.txt;filename=../../../etc/passwd" \
  -b "session=xxx"

# 测试4：双扩展名绕过，预期被拒绝
curl -X POST http://localhost:5000/upload \
  -F "file=@evil.php;filename=shell.php.jpg" \
  -b "session=xxx"

# 测试5：空字节截断，预期被拒绝
curl -X POST http://localhost:5000/upload \
  -F "file=@evil.php;filename=shell.php%00.jpg" \
  -b "session=xxx"
```

### 7.2 代码审计验证

逐一检查以下安全控制点是否到位：

- [ ] 文件扩展名是否使用白名单（而非黑名单）
- [ ] 是否使用文件头魔术数字验证文件真实类型
- [ ] 是否对文件名做了 `secure_filename()` / `basename()` 处理
- [ ] 是否限制了文件大小
- [ ] 是否防止了路径穿越
- [ ] 上传目录是否禁止脚本执行
- [ ] 文件访问权限是否严格限制（只读）

---

## 八、总结

本项目 `/upload` 文件上传接口存在严重的**任意文件上传漏洞**，缺少文件类型校验、文件名安全处理、路径穿越防护等关键安全措施。攻击者可通过上传 WebShell、木马或钓鱼文件，获取服务器控制权或造成数据泄露等严重后果。

建议按照本报告的修复方案，从**扩展名白名单校验**、**文件内容验证**、**文件名安全处理**、**路径穿越防护**、**服务器配置加固**五个层面进行系统化修复，并配合自动化安全测试确保修复有效。
