from functools import wraps
from flask import Flask, request, session, redirect, url_for, render_template_string, flash

from app.config import ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY, SHOP_NAME
from app.db import SessionLocal
from app.models import ShopOrder
from app.services import approve_order

PAGE = """
<!doctype html><meta charset="utf-8"><title>{{ shop }} Admin</title>
<style>
body{font-family:sans-serif;margin:24px;background:#f5f6f8}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px;text-align:left}
th{background:#222;color:#fff}
.msg{background:#e8f5e9;padding:8px;margin-bottom:12px}
</style>
<h2>{{ shop }} - Orders</h2>
<a href="{{ url_for('logout') }}">Logout</a>
{% for m in get_flashed_messages() %}<div class="msg">{{ m }}</div>{% endfor %}
<table>
<tr><th>ID</th><th>Ref</th><th>User</th><th>Game</th><th>Package</th><th>Player</th><th>Price</th><th>Status</th><th>Created</th><th></th></tr>
{% for o in orders %}
<tr><td>{{ o.id }}</td><td>{{ o.order_ref }}</td><td>{{ o.username or o.telegram_id }}</td>
<td>{{ o.game_name }}</td><td>{{ o.package_name }}</td>
<td>{{ o.player_id }}{% if o.server_id %} ({{ o.server_id }}){% endif %}</td>
<td>${{ '%.2f'|format(o.sell_price) }}</td><td>{{ o.status }}</td><td>{{ o.created_at }}</td>
<td>{% if o.status in ('payment_submitted','awaiting_payment') %}
<form method="post" action="{{ url_for('approve', order_id=o.id) }}"><button>Approve</button></form>
{% endif %}</td></tr>
{% endfor %}
</table>
"""

LOGIN = """
<!doctype html><meta charset="utf-8"><title>Login</title>
<form method="post" style="max-width:300px;margin:80px auto;font-family:sans-serif">
<h3>Admin Login</h3>{% for m in get_flashed_messages() %}<p style="color:red">{{ m }}</p>{% endfor %}
<p><input name="username" placeholder="Username" style="width:100%"></p>
<p><input name="password" type="password" placeholder="Password" style="width:100%"></p>
<button>Login</button></form>
"""


def create_admin_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("ok"):
                return redirect(url_for("login"))
            return fn(*a, **kw)
        return wrapper

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
                session["ok"] = True
                return redirect(url_for("index"))
            flash("Wrong username or password")
        return render_template_string(LOGIN)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        db = SessionLocal()
        try:
            orders = db.query(ShopOrder).order_by(ShopOrder.id.desc()).limit(200).all()
            return render_template_string(PAGE, orders=orders, shop=SHOP_NAME)
        finally:
            db.close()

    @app.route("/approve/<int:order_id>", methods=["POST"])
    @login_required
    def approve(order_id):
        db = SessionLocal()
        try:
            o = db.get(ShopOrder, order_id)
            if o and o.status == "awaiting_payment":
                o.status = "payment_submitted"
                db.commit()
        finally:
            db.close()
        try:
            _, ref, status, _ = approve_order(order_id)
            flash(f"{ref}: {status}")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))

    return app