import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

app = Flask(__name__)
app.secret_key = 'digital-record-management-secret-key-2026'
app.config['SESSION_COOKIE_HTTPONLY'] = True

LOW_STOCK_THRESHOLDS = {
    'kg': 1,
    'litre': 1,
    'bag': 1,
    'piece': 4,
    'box': 1,
    'packet': 1,
    'ton': 1,
    'other': 0,
}
ALLOWED_UNITS = ['kg', 'litre', 'bag', 'piece', 'box', 'packet', 'ton', 'other']
PAYMENT_METHODS = ['Cash', 'Bank Transfer', 'UPI', 'Cheque', 'Credit']
CUSTOMER_PAYMENT_MODES = ['UPI', 'Cash on Delivery', 'Card']


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_user_type_column():
    conn = get_db_connection()
    columns = conn.execute('PRAGMA table_info(users)').fetchall()
    column_names = [col['name'] for col in columns]
    if 'user_type' not in column_names:
        conn.execute("ALTER TABLE users ADD COLUMN user_type TEXT DEFAULT 'shop_owner'")
    conn.commit()
    conn.close()


def init_db():
    conn = get_db_connection()
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            shop_name TEXT NOT NULL,
            address TEXT NOT NULL,
            mobile TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            user_type TEXT DEFAULT 'shop_owner',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS raw_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            material_name TEXT NOT NULL,
            unit TEXT NOT NULL,
            total_stock REAL NOT NULL,
            today_usage REAL NOT NULL DEFAULT 0,
            remaining_stock REAL NOT NULL,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            supplier_name TEXT NOT NULL,
            invoice_no TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            paid_amount REAL NOT NULL,
            remaining_amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT NOT NULL,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS password_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            delivery_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS customer_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            shop_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            delivery_address TEXT NOT NULL,
            payment_mode TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES users(id),
            FOREIGN KEY (shop_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
        '''
    )

    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS customer_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
        '''
    )

    conn.commit()
    conn.close()
    ensure_user_type_column()
    seed_demo_data()


def seed_demo_data():
    conn = get_db_connection()
    owner_exists = conn.execute("SELECT id FROM users WHERE username = ?", ('shopowner',)).fetchone()
    if owner_exists is None:
        conn.execute(
            'INSERT INTO users (username, shop_name, address, mobile, password_hash, user_type) VALUES (?, ?, ?, ?, ?, ?)',
            (
                'shopowner',
                'Appu Adagaradu',
                'Market Road, Chennai',
                '+919876543210',
                generate_password_hash('shop123'),
                'shop_owner',
            ),
        )
    conn.commit()
    owner_id = conn.execute("SELECT id FROM users WHERE username = ?", ('shopowner',)).fetchone()['id']

    existing_products = conn.execute('SELECT COUNT(*) AS count FROM products').fetchone()['count']
    if existing_products == 0:
        conn.execute(
            'INSERT INTO products (user_id, product_name, category, price, stock, description, delivery_time) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (owner_id, 'Rice Bag', 'Groceries', 1200.00, 50, 'Premium quality rice packed for daily needs.', 'Same day delivery')
        )
        conn.execute(
            'INSERT INTO products (user_id, product_name, category, price, stock, description, delivery_time) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (owner_id, 'Fresh Coconut Oil', 'Home Essentials', 260.00, 32, 'Pure coconut oil delivered fresh and sealed.', '2-3 days delivery')
        )
        conn.execute(
            'INSERT INTO products (user_id, product_name, category, price, stock, description, delivery_time) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (owner_id, 'Toothpaste Pack', 'Daily Care', 85.00, 80, 'Family care toothpaste with mint freshness.', 'Same day delivery')
        )
    conn.commit()
    conn.close()


def validate_password(password):
    if len(password) < 6:
        return False
    if not any(char.isalpha() for char in password):
        return False
    if not any(char.isdigit() for char in password):
        return False
    return True


def send_otp_to_mobile(mobile, otp_code):
    """Send the OTP via SMS if a provider is configured.

    This app does not ship with an SMS gateway key or service credentials, so in a
    local/dev environment we log the code and surface it as a flash message to avoid
    a silent failure. Production deployments can integrate a real gateway here.
    """
    has_sms_config = any(
        os.environ.get(key)
        for key in (
            'TWILIO_ACCOUNT_SID',
            'TWILIO_AUTH_TOKEN',
            'TWILIO_PHONE_NUMBER',
            'TEXTLOCAL_API_KEY',
            'SMS_GATEWAY_URL',
        )
    )

    if has_sms_config:
        print(f'[SMS OTP] Mobile: {mobile} | OTP: {otp_code}')
        return True

    print(f'[DEV OTP] Mobile: {mobile} | OTP: {otp_code}')
    flash(f'Development mode: OTP for {mobile} is {otp_code}. Use this code to continue testing.', 'info')
    return False


def create_or_update_otp_record(user_id, otp_code):
    otp_hash = generate_password_hash(otp_code)
    expires_at = (datetime.now() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db_connection()
    try:
        existing = conn.execute(
            'SELECT id FROM password_otps WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
            (user_id,),
        ).fetchone()

        if existing is None:
            conn.execute(
                'INSERT INTO password_otps (user_id, otp_hash, expires_at, attempts, verified, created_at) VALUES (?, ?, ?, 0, 0, ?)',
                (user_id, otp_hash, expires_at, created_at),
            )
        else:
            conn.execute(
                'UPDATE password_otps SET otp_hash = ?, expires_at = ?, attempts = 0, verified = 0, created_at = ? WHERE user_id = ?',
                (otp_hash, expires_at, created_at, user_id),
            )

        conn.commit()
    finally:
        conn.close()


def _generate_new_otp(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()

    if user is None:
        flash('User not found.', 'error')
        return redirect(url_for('forgot_password'))

    otp_code = str(secrets.randbelow(900000) + 100000)
    create_or_update_otp_record(user_id, otp_code)
    send_otp_to_mobile(user['mobile'], otp_code)
    flash('A new OTP has been generated.', 'success')
    return redirect(url_for('verify_otp'))


def validate_mobile(mobile):
    return bool(re.fullmatch(r'\+?[0-9]{10,15}', mobile.strip()))


def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username.strip(),)).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user


def get_materials_for_user(user_id):
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT * FROM raw_materials WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_payments_for_user(user_id):
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def calculate_remaining_stock(total_stock, today_usage):
    return round(float(total_stock) - float(today_usage), 2)


def is_low_stock(unit, remaining_stock):
    threshold = LOW_STOCK_THRESHOLDS.get(unit.lower(), 0)
    return float(remaining_stock) <= float(threshold)


def payment_status_for(total_amount, paid_amount):
    remaining = float(total_amount) - float(paid_amount)
    if abs(remaining) < 0.0001:
        return 'PAID'
    if float(paid_amount) > 0 and remaining > 0:
        return 'PARTIAL'
    return 'PENDING'


def login_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'error')
            return redirect(url_for('login'))
        return view_function(*args, **kwargs)

    return wrapper


def customer_login_required(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        return view_function(*args, **kwargs)

    return wrapper


def get_guest_customer_user():
    guest = get_user_by_username('guestcustomer')
    if guest is not None:
        return guest

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO users (username, shop_name, address, mobile, password_hash, user_type) VALUES (?, ?, ?, ?, ?, ?)',
        ('guestcustomer', 'Guest Customer', 'Guest Address', '0000000000', generate_password_hash('guestpass'), 'customer'),
    )
    conn.commit()
    conn.close()
    return get_user_by_username('guestcustomer')


def get_all_products():
    conn = get_db_connection()
    rows = conn.execute(
        '''
        SELECT p.*, u.shop_name, u.address, u.mobile
        FROM products p
        JOIN users u ON u.id = p.user_id
        WHERE u.user_type != 'customer'
        ORDER BY p.created_at DESC
        '''
    ).fetchall()
    conn.close()
    return rows


def get_product_by_id(product_id):
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    return row


def get_shop_owner_count():
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*) AS total FROM users WHERE user_type != 'customer'").fetchone()
    conn.close()
    return row['total'] if row else 0


def get_reviews_for_product(product_id):
    conn = get_db_connection()
    rows = conn.execute(
        '''
        SELECT r.*, u.username AS customer_name
        FROM customer_reviews r
        JOIN users u ON u.id = r.customer_id
        WHERE r.product_id = ?
        ORDER BY r.created_at DESC
        ''',
        (product_id,),
    ).fetchall()
    conn.close()
    return rows


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if 'customer_id' in session:
        return redirect(url_for('customer_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Invalid username or password', 'error')
            return render_template('login.html', shop_owner_count=get_shop_owner_count())

        user = get_user_by_username(username)
        if user is None or user['user_type'] == 'customer' or not check_password_hash(user['password_hash'], password):
            flash('Invalid username or password', 'error')
            return render_template('login.html', shop_owner_count=get_shop_owner_count())

        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['user_type'] = 'shop_owner'
        return redirect(url_for('dashboard'))

    return render_template('login.html', shop_owner_count=get_shop_owner_count())


@app.route('/customer-login', methods=['GET', 'POST'])
def customer_login():
    return redirect(url_for('customer_dashboard'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        shop_name = request.form.get('shop_name', '').strip()
        address = request.form.get('address', '').strip()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not all([username, shop_name, address, mobile, password, confirm_password]):
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if get_user_by_username(username) is not None:
            flash('Username already exists', 'error')
            return render_template('register.html')

        if not validate_mobile(mobile):
            flash('Invalid mobile number', 'error')
            return render_template('register.html')

        if not validate_password(password):
            flash('Set a strong password', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO users (username, shop_name, address, mobile, password_hash, user_type) VALUES (?, ?, ?, ?, ?, ?)',
            (username, shop_name, address, mobile, generate_password_hash(password), 'shop_owner'),
        )
        conn.commit()
        conn.close()

        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/customer-register', methods=['GET', 'POST'])
def customer_register():
    return redirect(url_for('customer_dashboard'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        mobile = request.form.get('mobile', '').strip()

        if not username or not mobile:
            flash('Username or mobile number is incorrect', 'error')
            return render_template('forgot_password.html')

        user = get_user_by_username(username)
        if user is None or user['mobile'] != mobile:
            flash('Username or mobile number is incorrect', 'error')
            return render_template('forgot_password.html')

        otp_code = str(secrets.randbelow(900000) + 100000)
        create_or_update_otp_record(user['id'], otp_code)
        send_otp_to_mobile(user['mobile'], otp_code)

        session['recovery_user_id'] = user['id']
        session['otp_verified'] = False
        return redirect(url_for('verify_otp'))

    return render_template('forgot_password.html')


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'recovery_user_id' not in session:
        flash('Please request a password reset first.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'resend':
            return _generate_new_otp(session['recovery_user_id'])

        entered_otp = request.form.get('otp', '').strip()
        conn = get_db_connection()
        otp_record = conn.execute(
            'SELECT * FROM password_otps WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
            (session['recovery_user_id'],),
        ).fetchone()

        if otp_record is None:
            conn.close()
            flash('Invalid or expired OTP', 'error')
            return render_template('verify_otp.html')

        expires_at = datetime.strptime(otp_record['expires_at'], '%Y-%m-%d %H:%M:%S')
        if expires_at < datetime.now():
            conn.close()
            flash('Invalid or expired OTP', 'error')
            return render_template('verify_otp.html')

        if otp_record['attempts'] >= 3:
            conn.close()
            flash('Too many invalid OTP attempts. Please request a new OTP.', 'error')
            return redirect(url_for('forgot_password'))

        if not re.fullmatch(r'\d{6}', entered_otp):
            conn.execute('UPDATE password_otps SET attempts = attempts + 1 WHERE id = ?', (otp_record['id'],))
            conn.commit()
            conn.close()
            flash('Invalid or expired OTP', 'error')
            return render_template('verify_otp.html')

        if check_password_hash(otp_record['otp_hash'], entered_otp):
            conn.execute('UPDATE password_otps SET verified = 1 WHERE id = ?', (otp_record['id'],))
            conn.commit()
            conn.close()
            session['otp_verified'] = True
            flash('OTP verified successfully', 'success')
            return redirect(url_for('reset_password'))

        conn.execute('UPDATE password_otps SET attempts = attempts + 1 WHERE id = ?', (otp_record['id'],))
        conn.commit()
        conn.close()
        flash('Invalid or expired OTP', 'error')
        return render_template('verify_otp.html')

    return render_template('verify_otp.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if 'recovery_user_id' not in session or not session.get('otp_verified'):
        flash('Please verify the OTP before resetting your password.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not validate_password(new_password):
            flash('Set a strong password', 'error')
            return render_template('reset_password.html')

        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('reset_password.html')

        user_id = session['recovery_user_id']
        conn = get_db_connection()
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (generate_password_hash(new_password), user_id),
        )
        conn.execute(
            'UPDATE password_otps SET expires_at = ?, verified = 1 WHERE user_id = ?',
            ((datetime.now() - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'), user_id),
        )
        conn.commit()
        conn.close()

        session.pop('recovery_user_id', None)
        session.pop('otp_verified', None)
        flash('Password reset successfully. Please login with your new password.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    conn = get_db_connection()

    conn.execute(
        'DELETE FROM customer_reviews WHERE customer_id = ? OR product_id IN (SELECT id FROM products WHERE user_id = ?)',
        (user_id, user_id),
    )
    conn.execute(
        'DELETE FROM customer_orders WHERE customer_id = ? OR shop_id = ?',
        (user_id, user_id),
    )
    conn.execute('DELETE FROM raw_materials WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM payments WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM password_otps WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM products WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

    session.clear()
    flash('Your account has been deleted successfully.', 'success')
    return redirect(url_for('login'))


@app.route('/customer-logout')
def customer_logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('customer_dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    materials = get_materials_for_user(user['id'])
    return render_template(
        'dashboard.html',
        user=user,
        materials=materials,
        low_stock_thresholds=LOW_STOCK_THRESHOLDS,
    )


@app.route('/add-material', methods=['POST'])
@login_required
def add_material():
    user_id = session['user_id']
    material_name = request.form.get('material_name', '').strip()
    unit = request.form.get('unit', '').strip().lower()
    total_stock = request.form.get('total_stock', '0')
    today_usage = request.form.get('today_usage', '0')
    remarks = request.form.get('remarks', '').strip()

    if not all([material_name, unit]):
        flash('Raw material name and unit are required.', 'error')
        return redirect(url_for('dashboard'))

    if unit not in ALLOWED_UNITS:
        flash('Invalid unit selected.', 'error')
        return redirect(url_for('dashboard'))

    try:
        total_stock_value = float(total_stock)
        today_usage_value = float(today_usage)
    except ValueError:
        flash('Please enter valid numeric stock values.', 'error')
        return redirect(url_for('dashboard'))

    if total_stock_value < 0 or today_usage_value < 0:
        flash('Stock values cannot be negative.', 'error')
        return redirect(url_for('dashboard'))

    if today_usage_value > total_stock_value:
        flash('Today\'s usage cannot be greater than total stock.', 'error')
        return redirect(url_for('dashboard'))

    remaining_stock = calculate_remaining_stock(total_stock_value, today_usage_value)
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO raw_materials (user_id, material_name, unit, total_stock, today_usage, remaining_stock, remarks) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (user_id, material_name, unit, total_stock_value, today_usage_value, remaining_stock, remarks),
    )
    conn.commit()
    conn.close()

    flash('Raw material added successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/edit-material/<int:material_id>', methods=['GET', 'POST'])
@login_required
def edit_material(material_id):
    user_id = session['user_id']
    conn = get_db_connection()
    material = conn.execute(
        'SELECT * FROM raw_materials WHERE id = ? AND user_id = ?',
        (material_id, user_id),
    ).fetchone()
    conn.close()

    if material is None:
        flash('Invalid raw material ID.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        material_name = request.form.get('material_name', '').strip()
        unit = request.form.get('unit', '').strip().lower()
        total_stock = request.form.get('total_stock', '0')
        today_usage = request.form.get('today_usage', '0')
        remarks = request.form.get('remarks', '').strip()

        if not material_name or not unit:
            flash('Material name and unit are required.', 'error')
            return redirect(url_for('dashboard'))

        if unit not in ALLOWED_UNITS:
            flash('Invalid unit selected.', 'error')
            return redirect(url_for('dashboard'))

        try:
            total_stock_value = float(total_stock)
            today_usage_value = float(today_usage)
        except ValueError:
            flash('Please enter valid numeric stock values.', 'error')
            return redirect(url_for('dashboard'))

        if total_stock_value < 0 or today_usage_value < 0:
            flash('Stock values cannot be negative.', 'error')
            return redirect(url_for('dashboard'))

        if today_usage_value > total_stock_value:
            flash('Today\'s usage cannot be greater than total stock.', 'error')
            return redirect(url_for('dashboard'))

        remaining_stock = calculate_remaining_stock(total_stock_value, today_usage_value)
        conn = get_db_connection()
        conn.execute(
            'UPDATE raw_materials SET material_name = ?, unit = ?, total_stock = ?, today_usage = ?, remaining_stock = ?, remarks = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
            (material_name, unit, total_stock_value, today_usage_value, remaining_stock, remarks, material_id, user_id),
        )
        conn.commit()
        conn.close()

        flash('Raw material updated successfully.', 'success')
        return redirect(url_for('dashboard'))

    user = get_user_by_id(user_id)
    materials = get_materials_for_user(user_id)
    return render_template('dashboard.html', user=user, materials=materials, editing_material=material, low_stock_thresholds=LOW_STOCK_THRESHOLDS)


@app.route('/delete-material/<int:material_id>', methods=['POST'])
@login_required
def delete_material(material_id):
    user_id = session['user_id']
    conn = get_db_connection()
    result = conn.execute('DELETE FROM raw_materials WHERE id = ? AND user_id = ?', (material_id, user_id))
    conn.commit()
    conn.close()
    if result.rowcount > 0:
        flash('Raw material deleted successfully.', 'success')
    else:
        flash('Invalid raw material ID.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/payments')
@login_required
def payments():
    user = get_user_by_id(session['user_id'])
    payment_rows = get_payments_for_user(user['id'])
    total_supplier_amount = sum(float(row['total_amount']) for row in payment_rows)
    total_paid = sum(float(row['paid_amount']) for row in payment_rows)
    total_pending = sum(
        float(row['remaining_amount'])
        for row in payment_rows if row['status'] in ('PENDING', 'PARTIAL')
    )
    return render_template(
        'payments.html',
        user=user,
        payments=payment_rows,
        total_supplier_amount=total_supplier_amount,
        total_paid=total_paid,
        total_pending=total_pending,
        payment_methods=PAYMENT_METHODS,
        print_mode=False,
    )


@app.route('/add-payment', methods=['POST'])
@login_required
def add_payment():
    user_id = session['user_id']
    supplier_name = request.form.get('supplier_name', '').strip()
    invoice_no = request.form.get('invoice_no', '').strip()
    payment_date = request.form.get('payment_date', '').strip()
    total_amount = request.form.get('total_amount', '0')
    paid_amount = request.form.get('paid_amount', '0')
    payment_method = request.form.get('payment_method', '').strip()
    remarks = request.form.get('remarks', '').strip()

    if not all([supplier_name, invoice_no, payment_date, payment_method]):
        flash('Supplier, invoice, date, and payment method are required.', 'error')
        return redirect(url_for('payments'))

    try:
        total_amount_value = float(total_amount)
        paid_amount_value = float(paid_amount)
    except ValueError:
        flash('Please enter valid payment values.', 'error')
        return redirect(url_for('payments'))

    if total_amount_value < 0 or paid_amount_value < 0:
        flash('Payment values cannot be negative.', 'error')
        return redirect(url_for('payments'))

    if paid_amount_value > total_amount_value:
        flash('Paid amount cannot be greater than total amount.', 'error')
        return redirect(url_for('payments'))

    remaining_amount = round(total_amount_value - paid_amount_value, 2)
    status = payment_status_for(total_amount_value, paid_amount_value)

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO payments (user_id, supplier_name, invoice_no, payment_date, total_amount, paid_amount, remaining_amount, payment_method, status, remarks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (user_id, supplier_name, invoice_no, payment_date, total_amount_value, paid_amount_value, remaining_amount, payment_method, status, remarks),
    )
    conn.commit()
    conn.close()

    flash('Supplier payment record added successfully.', 'success')
    return redirect(url_for('payments'))


@app.route('/edit-payment/<int:payment_id>', methods=['GET', 'POST'])
@login_required
def edit_payment(payment_id):
    user_id = session['user_id']
    conn = get_db_connection()
    payment = conn.execute(
        'SELECT * FROM payments WHERE id = ? AND user_id = ?',
        (payment_id, user_id),
    ).fetchone()
    conn.close()

    if payment is None:
        flash('Invalid supplier payment record.', 'error')
        return redirect(url_for('payments'))

    if request.method == 'POST':
        supplier_name = request.form.get('supplier_name', '').strip()
        invoice_no = request.form.get('invoice_no', '').strip()
        payment_date = request.form.get('payment_date', '').strip()
        total_amount = request.form.get('total_amount', '0')
        paid_amount = request.form.get('paid_amount', '0')
        payment_method = request.form.get('payment_method', '').strip()
        remarks = request.form.get('remarks', '').strip()

        if not all([supplier_name, invoice_no, payment_date, payment_method]):
            flash('Supplier, invoice, date, and payment method are required.', 'error')
            return redirect(url_for('payments'))

        try:
            total_amount_value = float(total_amount)
            paid_amount_value = float(paid_amount)
        except ValueError:
            flash('Please enter valid payment values.', 'error')
            return redirect(url_for('payments'))

        if total_amount_value < 0 or paid_amount_value < 0:
            flash('Payment values cannot be negative.', 'error')
            return redirect(url_for('payments'))

        if paid_amount_value > total_amount_value:
            flash('Paid amount cannot be greater than total amount.', 'error')
            return redirect(url_for('payments'))

        remaining_amount = round(total_amount_value - paid_amount_value, 2)
        status = payment_status_for(total_amount_value, paid_amount_value)

        conn = get_db_connection()
        conn.execute(
            'UPDATE payments SET supplier_name = ?, invoice_no = ?, payment_date = ?, total_amount = ?, paid_amount = ?, remaining_amount = ?, payment_method = ?, status = ?, remarks = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
            (supplier_name, invoice_no, payment_date, total_amount_value, paid_amount_value, remaining_amount, payment_method, status, remarks, payment_id, user_id),
        )
        conn.commit()
        conn.close()

        flash('Supplier payment updated successfully.', 'success')
        return redirect(url_for('payments'))

    user = get_user_by_id(user_id)
    payment_rows = get_payments_for_user(user_id)
    return render_template(
        'payments.html',
        user=user,
        payments=payment_rows,
        editing_payment=payment,
        total_supplier_amount=sum(float(row['total_amount']) for row in payment_rows),
        total_paid=sum(float(row['paid_amount']) for row in payment_rows),
        total_pending=sum(float(row['remaining_amount']) for row in payment_rows if row['status'] in ('PENDING', 'PARTIAL')),
        payment_methods=PAYMENT_METHODS,
        print_mode=False,
    )


@app.route('/delete-payment/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    user_id = session['user_id']
    conn = get_db_connection()
    result = conn.execute('DELETE FROM payments WHERE id = ? AND user_id = ?', (payment_id, user_id))
    conn.commit()
    conn.close()
    if result.rowcount > 0:
        flash('Supplier payment deleted successfully.', 'success')
    else:
        flash('Invalid supplier payment record.', 'error')
    return redirect(url_for('payments'))


@app.route('/print-payment-report')
@login_required
def print_payment_report():
    user = get_user_by_id(session['user_id'])
    payment_rows = get_payments_for_user(user['id'])
    total_supplier_amount = sum(float(row['total_amount']) for row in payment_rows)
    total_paid = sum(float(row['paid_amount']) for row in payment_rows)
    total_pending = sum(
        float(row['remaining_amount']) for row in payment_rows if row['status'] in ('PENDING', 'PARTIAL')
    )
    return render_template(
        'payments.html',
        user=user,
        payments=payment_rows,
        total_supplier_amount=total_supplier_amount,
        total_paid=total_paid,
        total_pending=total_pending,
        payment_methods=PAYMENT_METHODS,
        print_mode=True,
    )


@app.route('/search-payments', methods=['POST'])
def search_payments():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    search_value = request.form.get('search', '').strip().lower()
    user = get_user_by_id(session['user_id'])
    rows = get_payments_for_user(user['id'])
    filtered = []
    for row in rows:
        supplier_name = (row['supplier_name'] or '').lower()
        invoice_no = (row['invoice_no'] or '').lower()
        if search_value in supplier_name or search_value in invoice_no:
            filtered.append(row)

    total_supplier_amount = sum(float(row['total_amount']) for row in filtered)
    total_paid = sum(float(row['paid_amount']) for row in filtered)
    total_pending = sum(float(row['remaining_amount']) for row in filtered if row['status'] in ('PENDING', 'PARTIAL'))
    return render_template(
        'payments.html',
        user=user,
        payments=filtered,
        total_supplier_amount=total_supplier_amount,
        total_paid=total_paid,
        total_pending=total_pending,
        payment_methods=PAYMENT_METHODS,
        print_mode=False,
    )


@app.route('/customer-dashboard', methods=['GET'])
@customer_login_required
def customer_dashboard():
    user = get_user_by_id(session.get('customer_id')) if session.get('customer_id') else get_guest_customer_user()
    search_term = request.args.get('q', '').strip()
    products = get_all_products()
    if search_term:
        search_term_lower = search_term.lower()
        products = [
            product for product in products
            if search_term_lower in (product['product_name'] or '').lower()
            or search_term_lower in (product['category'] or '').lower()
            or search_term_lower in (product['shop_name'] or '').lower()
        ]

    product_reviews_map = {}
    for product in products:
        product_reviews_map[product['id']] = get_reviews_for_product(product['id'])

    return render_template(
        'customer_dashboard.html',
        user=user,
        products=products,
        search_term=search_term,
        product_reviews_map=product_reviews_map,
    )


@app.route('/place-order', methods=['POST'])
@customer_login_required
def place_order():
    customer_id = session.get('customer_id') or get_guest_customer_user()['id']
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', type=int)
    delivery_address = request.form.get('delivery_address', '').strip()
    payment_mode = request.form.get('payment_mode', '').strip()
    send_whatsapp = request.form.get('send_whatsapp', '0')

    if not product_id or not quantity or quantity <= 0:
        flash('Please select a valid product and quantity.', 'error')
        return redirect(url_for('customer_dashboard'))

    if not delivery_address:
        flash('Delivery address is required.', 'error')
        return redirect(url_for('customer_dashboard'))

    if payment_mode not in CUSTOMER_PAYMENT_MODES:
        flash('Please select a valid payment mode.', 'error')
        return redirect(url_for('customer_dashboard'))

    product = get_product_by_id(product_id)
    if product is None:
        flash('Invalid product selected.', 'error')
        return redirect(url_for('customer_dashboard'))

    if quantity > product['stock']:
        flash('Selected quantity exceeds available stock.', 'error')
        return redirect(url_for('customer_dashboard'))

    shop_owner = get_user_by_id(product['user_id'])
    total_amount = float(product['price']) * int(quantity)
    conn = get_db_connection()
    conn.execute(
        '''
        INSERT INTO customer_orders (customer_id, shop_id, product_id, product_name, quantity, total_amount, delivery_address, payment_mode, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
        ''',
        (
            customer_id,
            product['user_id'],
            product['id'],
            product['product_name'],
            quantity,
            total_amount,
            delivery_address,
            payment_mode,
        ),
    )
    conn.commit()
    conn.close()

    clean_mobile = re.sub(r'\D', '', str(shop_owner['mobile']))
    order_message = (
        f"New order request from customer: {session['customer_username']}\n"
        f"Product: {product['product_name']}\n"
        f"Quantity: {quantity}\n"
        f"Address: {delivery_address}\n"
        f"Payment mode: {payment_mode}\n"
        f"Total: ₹{total_amount:.2f}"
    )

    whatsapp_url = f"https://wa.me/{clean_mobile}?text={quote(order_message)}"
    flash('Order submitted successfully. The shop owner will receive your order details on WhatsApp.', 'success')
    if str(send_whatsapp) == '1':
        return redirect(whatsapp_url)
    return redirect(url_for('customer_dashboard'))


@app.route('/add-review', methods=['POST'])
@customer_login_required
def add_review():
    customer_id = session.get('customer_id') or get_guest_customer_user()['id']
    product_id = request.form.get('product_id', type=int)
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not product_id or not rating:
        flash('Please select a product and rating.', 'error')
        return redirect(url_for('customer_dashboard'))

    if rating < 1 or rating > 5:
        flash('Rating must be between 1 and 5.', 'error')
        return redirect(url_for('customer_dashboard'))

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO customer_reviews (customer_id, product_id, rating, comment) VALUES (?, ?, ?, ?)',
        (customer_id, product_id, rating, comment),
    )
    conn.commit()
    conn.close()

    flash('Thank you for your review.', 'success')
    return redirect(url_for('customer_dashboard'))


@app.route('/customer-register', methods=['GET', 'POST'])
def customer_register_route():
    return customer_register()


init_db()


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
