from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3 as sql
import csv
import hashlib
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Secure session key

DATABASE = 'database.db'
PARENT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Users.csv")


def create_user_table():
    """Create the users table with hashed passwords."""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    ''')
    connection.commit()
    connection.close()


def hash_password(password):
    """Hash the password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def populate_users():
    """Load users from CSV and insert into the database with hashed passwords."""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    # Read CSV and populate users table
    with open(CSV_FILE, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            email = row.get('\ufeffemail', '').strip()
            password = row.get('password', '').strip()
            hashed_password = hash_password(password)  # Hash it before storing

            if email and password:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO users (email, password) VALUES (?, ?);', (email, hashed_password))
                except sql.IntegrityError:
                    pass  # Skip duplicate emails

    connection.commit()
    connection.close()


@app.route('/')
def index():
    """Redirect to the login page."""
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticate users using email and password."""
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hash_password(password)  # Hash input password

        connection = sql.connect(DATABASE)
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ? AND password = ?;', (email, hashed_password))
        user = cursor.fetchone()
        connection.close()

        if user:
            session['user'] = email  # Store user session
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid email or password.'

    return render_template('login.html', error=error)


@app.route('/dashboard')
def dashboard():
    """Protected route that requires login."""
    if 'user' in session:
        return f"Welcome {session['user']}! You are logged in."
    else:
        return redirect(url_for('login'))


@app.route('/logout')
def logout():
    """Logout user and clear session."""
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == "__main__":
    # Delete old database to ensure proper password hashing
    if os.path.exists(DATABASE):
        os.remove(DATABASE)

    create_user_table()
    populate_users()
    app.run(debug=True)
