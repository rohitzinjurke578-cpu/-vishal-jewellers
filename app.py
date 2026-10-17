
import os, csv, io, json, uuid, secrets
from datetime import datetime, date, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "static" / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

@app.template_filter("from_json")
def from_json_filter(value):
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except (ValueError, TypeError):
        return []
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-production-" + secrets.token_hex(8))
database_url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'shop.db'}")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
db = SQLAlchemy(app)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False, default=0)
    mrp = db.Column(db.Float, nullable=False, default=0)
    category = db.Column(db.String(100), default="General")
    subcategory = db.Column(db.String(100), default="")
    size = db.Column(db.String(180), default="")
    color = db.Column(db.String(180), default="")
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(500), default="")
    media_json = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def media(self):
        try:
            items = json.loads(self.media_json or "[]")
            return items if isinstance(items, list) else []
        except (ValueError, TypeError):
            return []

    @property
    def discount(self):
        if self.mrp > 0 and self.mrp > self.price:
            return round((self.mrp - self.price) * 100 / self.mrp)
        return 0

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), default="Customer")
    phone = db.Column(db.String(30), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    items_json = db.Column(db.Text, default="[]")
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(40), default="Pending")
    payment_method = db.Column(db.String(40), default="Cash on Delivery")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, default="")

def get_setting(key, default=""):
    item = Setting.query.filter_by(key=key).first()
    return item.value if item else default

def set_setting(key, value):
    item = Setting.query.filter_by(key=key).first()
    if item:
        item.value = value
    else:
        db.session.add(Setting(key=key, value=value))

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploads(files_in):
    saved = []
    for file in files_in:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            raise ValueError("केवल JPG, PNG, WEBP, GIF और MP4/WEBM/MOV फाइलें स्वीकार हैं।")
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
        file.save(UPLOAD_DIR / filename)
        saved.append(url_for("static", filename=f"uploads/{filename}"))
    return saved

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    return {"shop_name": get_setting("shop_name", "Vishal Mart"),
            "announcement": get_setting("announcement", "Shop Smart • Save More"),
            "cart_count": len(session.get("cart", {}))}

@app.route("/")
def index():
    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()
    query = Product.query
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    products = query.order_by(Product.created_at.desc()).all()
    categories = [r[0] for r in db.session.query(Product.category).distinct().all() if r[0]]
    return render_template("index.html", products=products, categories=categories, search=search, selected_category=category)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("product.html", product=product)

@app.route("/cart")
def cart():
    cart_data = session.get("cart", {})
    items, total = [], 0
    for product_id, qty in cart_data.items():
        product = db.session.get(Product, int(product_id))
        if product:
            subtotal = product.price * int(qty)
            items.append({"product": product, "qty": int(qty), "subtotal": subtotal})
            total += subtotal
    return render_template("cart.html", items=items, total=total)

@app.post("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    if product.stock < 1:
        flash("यह प्रोडक्ट अभी स्टॉक में नहीं है।", "error")
        return redirect(request.referrer or url_for("index"))
    cart_data = session.get("cart", {})
    current = int(cart_data.get(str(product_id), 0))
    cart_data[str(product_id)] = min(current + 1, product.stock)
    session["cart"] = cart_data
    flash("प्रोडक्ट कार्ट में जोड़ दिया गया।", "success")
    return redirect(request.referrer or url_for("cart"))

@app.post("/cart/remove/<int:product_id>")
def remove_from_cart(product_id):
    cart_data = session.get("cart", {})
    cart_data.pop(str(product_id), None)
    session["cart"] = cart_data
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart_data = session.get("cart", {})
    if not cart_data:
        flash("पहले कार्ट में प्रोडक्ट जोड़ें।", "error")
        return redirect(url_for("index"))
    items, total = [], 0
    for product_id, qty in cart_data.items():
        product = db.session.get(Product, int(product_id))
        if product:
            qty = int(qty)
            if qty > product.stock:
                flash(f"{product.name} का स्टॉक कम है।", "error")
                return redirect(url_for("cart"))
            items.append((product, qty))
            total += product.price * qty
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        payment = request.form.get("payment_method", "Cash on Delivery")
        if not name or not phone or not address:
            flash("नाम, फोन और पता भरें।", "error")
            return redirect(url_for("checkout"))
        order_items = []
        for product, qty in items:
            order_items.append({"id": product.id, "name": product.name, "price": product.price, "qty": qty})
            product.stock -= qty
        order = Order(customer_name=name, phone=phone, address=address,
                      items_json=json.dumps(order_items, ensure_ascii=False), total=total,
                      payment_method=payment)
        db.session.add(order)
        if not Customer.query.filter_by(phone=phone).first():
            db.session.add(Customer(name=name, phone=phone))
        db.session.commit()
        session["cart"] = {}
        return render_template("order_success.html", order=order)
    return render_template("checkout.html", items=items, total=total)

@app.route("/my-orders", methods=["GET", "POST"])
def my_orders():
    orders = []
    phone = request.values.get("phone", "").strip()
    if phone:
        orders = Order.query.filter_by(phone=phone).order_by(Order.created_at.desc()).all()
    return render_template("my_orders.html", orders=orders, phone=phone)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        expected_user = os.environ.get("ADMIN_USERNAME", "admin")
        expected_password = os.environ.get("ADMIN_PASSWORD", "")
        # Set ADMIN_PASSWORD in Render environment. Local demo fallback is admin12345.
        if not expected_password:
            expected_password = "admin12345"
        if secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password):
            session.clear()
            session["is_admin"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Username या password गलत है।", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    start_month = today.replace(day=1)
    orders = Order.query.order_by(Order.created_at.desc()).all()
    total_sales = sum(o.total for o in orders if o.status not in ("Cancelled", "Refunded"))
    today_sales = sum(o.total for o in orders if o.created_at.date() == today and o.status not in ("Cancelled", "Refunded"))
    week_sales = sum(o.total for o in orders if o.created_at.date() >= start_week and o.status not in ("Cancelled", "Refunded"))
    month_sales = sum(o.total for o in orders if o.created_at.date() >= start_month and o.status not in ("Cancelled", "Refunded"))
    pending = Order.query.filter_by(status="Pending").count()
    # Build a reliable 7-day order-sales series without DB-specific JSON functions.
    graph_labels, graph_values = [], []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        graph_labels.append(d.strftime("%d %b"))
        graph_values.append(round(sum(o.total for o in orders if o.created_at.date() == d and o.status not in ("Cancelled", "Refunded")), 2))
    product_sales = {}
    for order in orders:
        if order.status in ("Cancelled", "Refunded"):
            continue
        try:
            for item in json.loads(order.items_json or "[]"):
                product_sales[item.get("id")] = product_sales.get(item.get("id"), 0) + int(item.get("qty", 0))
        except (ValueError, TypeError):
            pass
    best_products = sorted(Product.query.all(), key=lambda p: product_sales.get(p.id, 0), reverse=True)[:5]
    return render_template("admin_dashboard.html", products_count=Product.query.count(),
        customers_count=Customer.query.count(), orders_count=Order.query.count(), pending=pending,
        total_sales=total_sales, today_sales=today_sales, week_sales=week_sales, month_sales=month_sales,
        low_stock=Product.query.filter(Product.stock <= 5).order_by(Product.stock.asc()).limit(8).all(),
        recent_orders=orders[:8], best_products=best_products, graph_labels=json.dumps(graph_labels),
        graph_values=json.dumps(graph_values))

@app.route("/admin/products")
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin_products.html", products=products)

@app.route("/admin/products/new", methods=["GET", "POST"])
@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_form(product_id=None):
    product = db.session.get(Product, product_id) if product_id else Product()
    if product_id and not product:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Product name जरूरी है।", "error")
            return redirect(request.url)
        try:
            price = max(0, float(request.form.get("price", "0") or 0))
            mrp = max(0, float(request.form.get("mrp", "0") or 0))
            stock = max(0, int(request.form.get("stock", "0") or 0))
        except ValueError:
            flash("Price, MRP और stock में सही संख्या भरें।", "error")
            return redirect(request.url)
        product.name = name
        product.description = request.form.get("description", "").strip()
        product.price, product.mrp, product.stock = price, mrp, stock
        product.category = request.form.get("category", "General").strip() or "General"
        product.subcategory = request.form.get("subcategory", "").strip()
        product.size = request.form.get("size", "").strip()
        product.color = request.form.get("color", "").strip()
        existing_media = product.media
        try:
            new_media = save_uploads(request.files.getlist("media"))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(request.url)
        media = existing_media + new_media
        remove_media = request.form.getlist("remove_media")
        media = [m for m in media if m not in remove_media]
        product.media_json = json.dumps(media, ensure_ascii=False)
        product.image = next((m for m in media if m.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))), "")
        if not product_id:
            db.session.add(product)
        db.session.commit()
        flash("प्रोडक्ट सेव हो गया।", "success")
        return redirect(url_for("admin_products"))
    return render_template("admin_product_form.html", product=product, is_new=not bool(product_id))

@app.post("/admin/products/<int:product_id>/delete")
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("प्रोडक्ट डिलीट हो गया।", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/products/import", methods=["GET", "POST"])
@admin_required
def import_products():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename.lower().endswith(".csv"):
            flash("CSV फाइल चुनें।", "error")
            return redirect(request.url)
        try:
            text_data = io.StringIO(file.stream.read().decode("utf-8-sig"))
            reader = csv.DictReader(text_data)
            added = 0
            for row in reader:
                name = (row.get("name") or row.get("Name") or "").strip()
                if not name:
                    continue
                p = Product(name=name, description=row.get("description", ""),
                    price=float(row.get("price") or 0), mrp=float(row.get("mrp") or 0),
                    category=row.get("category") or "General", subcategory=row.get("subcategory") or "",
                    size=row.get("size") or "", color=row.get("color") or "", stock=max(0, int(float(row.get("stock") or 0))))
                db.session.add(p)
                added += 1
            db.session.commit()
            flash(f"{added} products import हो गए। CSV import में फोटो URL नहीं, फोटो बाद में edit करके अपलोड करें।", "success")
        except Exception:
            db.session.rollback()
            flash("CSV पढ़ने में समस्या। price, mrp और stock में सही संख्या रखें।", "error")
        return redirect(url_for("admin_products"))
    return render_template("admin_import.html")

@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin_orders.html", orders=orders, statuses=["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Refunded"])

@app.post("/admin/orders/<int:order_id>/status")
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    status = request.form.get("status", "")
    valid = {"Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Refunded"}
    if status in valid:
        order.status = status
        db.session.commit()
        flash("Order status अपडेट हो गया।", "success")
    return redirect(url_for("admin_orders"))

@app.route("/admin/customers")
@admin_required
def admin_customers():
    customers = Customer.query.order_by(Customer.created_at.desc()).all()
    return render_template("admin_customers.html", customers=customers)

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        set_setting("shop_name", request.form.get("shop_name", "Vishal Mart").strip() or "Vishal Mart")
        set_setting("announcement", request.form.get("announcement", "").strip())
        set_setting("whatsapp", request.form.get("whatsapp", "").strip())
        set_setting("upi_id", request.form.get("upi_id", "").strip())
        db.session.commit()
        flash("Settings सेव हो गईं।", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html",
        shop_name=get_setting("shop_name", "Vishal Mart"),
        announcement=get_setting("announcement", "Shop Smart • Save More"),
        whatsapp=get_setting("whatsapp", ""), upi_id=get_setting("upi_id", ""))

@app.route("/health")
def health():
    return jsonify(status="ok", app="Vishal Mart")

@app.errorhandler(413)
def too_large(e):
    flash("फाइल 20 MB से छोटी होनी चाहिए।", "error")
    return redirect(request.referrer or url_for("admin_products"))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
