import sqlite3 as sql
import csv
import hashlib
import os

DATABASE = 'database.db'
PARENT_DIR = os.path.dirname(os.path.abspath(__file__))

#------------------------------------------------------------------------------
# Create Tables with Associated Attributes
#------------------------------------------------------------------------------

# Create the Users Table
def create_user_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL
        );
    ''')
    connection.commit()
    connection.close()

# Create the HelpDesk Table
def create_helpdesk_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Helpdesk (
            email TEXT PRIMARY KEY,
            position TEXT NOT NULL,
            FOREIGN KEY (email) REFERENCES Users (email)
        );
    ''')
    connection.commit()
    connection.close()

# Create the Requests Table
def create_requests_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_email TEXT NOT NULL,
            helpdesk_staff_email TEXT NOT NULL,
            request_type TEXT NOT NULL,
            request_desc TEXT NOT NULL,
            request_status INTEGER NOT NULL,
            FOREIGN KEY (sender_email) REFERENCES Users (email),
            FOREIGN KEY (helpdesk_staff_email) REFERENCES Helpdesk (email)
        );
    ''')
    connection.commit()
    connection.close()

# Create the Buyers Table
def create_buyers_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Buyers (
            email TEXT PRIMARY KEY,
            business_name TEXT NOT NULL,
            buyer_address_id TEXT NOT NULL,
            FOREIGN KEY (email) REFERENCES Users (email),
            FOREIGN KEY (buyer_address_id) REFERENCES Address (address_id)
        );
    ''')
    connection.commit()
    connection.close()

# Create the CreditCards Table
def create_creditcards_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS CreditCards (
            credit_card_num TEXT PRIMARY KEY,
            card_type TEXT NOT NULL,
            expire_month INTEGER NOT NULL,
            expire_year INTEGER NOT NULL,
            security_code INTEGER NOT NULL,
            owner_email TEXT NOT NULL,
            FOREIGN KEY (owner_email) REFERENCES Buyers (email)
        );
    ''')
    connection.commit()
    connection.close()

# Create the Address Table
def create_address_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Address (
            address_id TEXT PRIMARY KEY,
            zipcode INTEGER NOT NULL,
            street_num INTEGER NOT NULL,
            street_name TEXT NOT NULL
        );
    ''')
    connection.commit()
    connection.close()

# Create the Zipcode Table
def create_zipcode_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Zipcodes (
            zipcode INTEGER PRIMARY KEY,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            FOREIGN KEY (zipcode) REFERENCES Address (zipcode)
        );
    ''')
    connection.commit()
    connection.close()

# Create the Sellers Table
def create_sellers_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Sellers (
            email TEXT PRIMARY KEY,
            business_name TEXT NOT NULL,
            business_address_id TEXT NOT NULL,
            bank_routing_number INTEGER NOT NULL,
            bank_account_number INTEGER NOT NULL,
            balance INTEGER NOT NULL,
            FOREIGN KEY (email) REFERENCES Users (email),
            FOREIGN KEY (business_address_id) REFERENCES Address (address_id)
        );
    ''')
    connection.commit()
    connection.close()
    
# Create the Categories Table
def create_categories_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Categories (
            category_name TEXT PRIMARY KEY,
            parent_category TEXT,
            FOREIGN KEY (parent_category) REFERENCES Categories (category_name)
        );
    ''')
    connection.commit()
    connection.close()

# Create the ProductLists Table
def create_productlistings_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ProductListings (
            seller_email TEXT,
            listing_id INTEGER,
            category TEXT NOT NULL,
            product_title TEXT NOT NULL,
            product_name TEXT NOT NULL,
            product_description TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            product_price INTEGER NOT NULL,
            status INTEGER NOT NULL,
            PRIMARY KEY (seller_email, listing_id),
            FOREIGN KEY (seller_email) REFERENCES Sellers (email),
            FOREIGN KEY (category) REFERENCES Categories (category_name)
        );
    ''')
    connection.commit()
    connection.close()

# Create the Orders Table
def create_orders_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            buyer_email TEXT NOT NULL,
            listing_id INTEGER NOT NULL,
            date DATE NOT NULL,
            quantity INTEGER NOT NULL,
            payment INTEGER NOT NULL,
            FOREIGN KEY (seller_email) REFERENCES Sellers (email),
            FOREIGN KEY (buyer_email) REFERENCES Buyers (email),
            FOREIGN KEY (listing_id) REFERENCES ProductListings (listing_id)
        );
    ''')
    connection.commit()
    connection.close()

# Create the Reviews Table
def create_reviews_table():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Reviews (
            order_id INTEGER PRIMARY KEY,
            review_desc TEXT,
            rating INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES Orders (order_id)
        );
    ''')
    connection.commit()
    connection.close()

#------------------------------------------------------------------------------
# Populate Tables
# - Parse CSV files and populate the data into the respective tables
#------------------------------------------------------------------------------

def hash_password(password):
    """Hash the password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

# Populate the Users Table
def populate_users():
    """Load users from CSV and insert into the database with hashed passwords."""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Users.csv")

    # Read CSV and populate Users table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            email = row.get('\ufeffemail', '').strip()
            password = row.get('password', '').strip()
            hashed_password = hash_password(password)  # Hash it before storing

            if email and password:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Users (email, password) VALUES (?, ?);', (email, hashed_password))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the HelpDesk Table
def populate_helpdesk():
    """Load HelpDesk entities from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Helpdesk.csv")

    # Read CSV and populate Helpdesk table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            email = row.get('\ufeffemail', '').strip()
            position = row.get('Position', '').strip()

            if email and position:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Helpdesk (email, position) VALUES (?, ?);', (email, position))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the Requests Table
def populate_requests():
    """Load Requests from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Requests.csv")

    # Read CSV and populate Requests table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            request_id = row.get('\ufeffrequest_id', '').strip()
            sender_email = row.get('sender_email', '').strip()
            helpdesk_staff_email = row.get('helpdesk_staff_email', '').strip()
            request_type = row.get('request_type', '').strip()
            request_desc = row.get('request_desc', '').strip()
            request_status = row.get('request_status', '').strip()

            if request_id and sender_email and helpdesk_staff_email and request_type and request_desc and request_status:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Requests (request_id, sender_email, helpdesk_staff_email, request_type, request_desc, request_status) VALUES (?, ?, ?, ?, ?, ?);', (request_id, sender_email, helpdesk_staff_email, request_type, request_desc, request_status))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the Buyers Table
def populate_buyers():
    """Load buyers from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Buyers.csv")

    # Read CSV and populate Buyers table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            email = row.get('\ufeffemail', '').strip()
            business_name = row.get('business_name', '').strip()
            buyer_address_id = row.get('buyer_address_id', '').strip()

            if email and business_name and buyer_address_id:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Buyers (email, business_name, buyer_address_id) VALUES (?, ?, ?);', (email, business_name, buyer_address_id))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the CreditCard Table
def populate_creditcards():
    """Load Credit Cards from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Credit_Cards.csv")

    # Read CSV and populate CreditCards table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            credit_card_num = row.get('\ufeffcredit_card_num', '').strip()
            card_type = row.get('card_type', '').strip()
            expire_month = row.get('expire_month', '').strip()
            expire_year = row.get('expire_year', '').strip()
            security_code = row.get('security_code', '').strip()
            owner_email = row.get('Owner_email', '').strip()

            if credit_card_num and card_type and expire_month and expire_year and security_code and owner_email:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO CreditCards (credit_card_num, card_type, expire_month, expire_year, security_code, owner_email) VALUES (?, ?, ?, ?, ?, ?);', (credit_card_num, card_type, expire_month, expire_year, security_code, owner_email))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()


# Populate the Address Table
def populate_address():
    """Load addresses from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Address.csv")

    # Read CSV and populate Address table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            address_id = row.get('\ufeffaddress_id', '').strip()
            zipcode = row.get('zipcode', '').strip()
            street_num = row.get('street_num', '').strip()
            street_name = row.get('street_name', '').strip()

            if address_id and zipcode and street_num and street_name:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?);', (address_id, zipcode, street_num, street_name))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()


# Populate the Zipcode Table
def populate_zipcode():
    """Load Zipcodes from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Zipcode_Info.csv")

    # Read CSV and populate Zipcodes table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            zipcode = row.get('\ufeffzipcode', '').strip()
            city = row.get('city', '').strip()
            state = row.get('state', '').strip()

            if zipcode and city and state:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Zipcodes (zipcode, city, state) VALUES (?, ?, ?);', (zipcode, city, state))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the Sellers Table
def populate_sellers():
    """Load Sellers from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Sellers.csv")

    # Read CSV and populate Sellers table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            email = row.get('\ufeffemail', '').strip()
            business_name = row.get('business_name', '').strip()
            business_address_id = row.get('Business_Address_ID', '').strip()
            bank_routing_number = row.get('bank_routing_number', '').strip()
            bank_account_number = row.get('bank_account_number', '').strip()
            balance = row.get('balance', '').strip()

            if email and business_name and business_address_id and bank_routing_number and bank_account_number and balance:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Sellers (email, business_name, business_address_id, bank_routing_number, bank_account_number, balance) VALUES (?, ?, ?, ?, ?, ?);', (email, business_name, business_address_id, bank_routing_number, bank_account_number, balance))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()
    
# Populate the Categories Table
def populate_categories():
    """Load Categories from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Categories.csv")

    # Read CSV and populate Categories table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            parent_category = row.get('parent_category', '').strip()
            category_name = row.get('category_name', '').strip()

            if category_name:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Categories (category_name, parent_category) VALUES (?, ?);', (category_name, parent_category))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the ProductLists Table
def populate_productlistings():
    """Load Product Listings from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Product_Listings.csv")

    # Read CSV and populate ProductLists table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            seller_email = row.get('Seller_Email', '').strip()
            listing_id = row.get('Listing_ID', '').strip()
            category = row.get('Category', '').strip()
            product_title = row.get('Product_Title', '').strip()
            product_name = row.get('Product_Name', '').strip()
            product_description = row.get('Product_Description', '').strip()
            quantity = row.get('Quantity', '').strip()
            product_price = row.get('Product_Price', '').strip()
            status = row.get('Status', '').strip()

            if seller_email and listing_id and category and product_title and product_name and product_description and quantity and product_price and status:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO ProductListings (seller_email, listing_id, category, product_title, product_name, product_description, quantity, product_price, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);', (seller_email, listing_id, category, product_title, product_name, product_description, quantity, product_price, status))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the Orders Table
def populate_orders():
    """Load Orders from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Orders.csv")

    # Read CSV and populate Orders table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            order_id = row.get('Order_ID', '').strip()
            seller_email = row.get('Seller_Email', '').strip()
            buyer_email = row.get('Buyer_Email', '').strip()
            listing_id = row.get('Listing_ID', '').strip()
            date = row.get('Date', '').strip()
            quantity = row.get('Quantity', '').strip()
            payment = row.get('Payment', '').strip()

            if order_id and seller_email and buyer_email and listing_id and date and quantity and payment:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO Orders (order_id, seller_email, listing_id, buyer_email, date, quantity, payment) VALUES (?, ?, ?, ?, ?, ?, ?);', (order_id, seller_email, listing_id, buyer_email, date, quantity, payment))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

# Populate the Reviews Table
def populate_reviews():
    """Load Reviews from CSV and insert into the database"""
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    csv_file = os.path.join(PARENT_DIR, "NittanyBusinessDataset", "Reviews.csv")

    # Read CSV and populate Reviews table
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            order_id = row.get('Order_ID', '').strip()
            review_desc = row.get('Review_Desc', '').strip()
            rating = row.get('Rate', '').strip()

            if order_id and review_desc and rating:  # Ensure values exist
                try:
                    cursor.execute('INSERT INTO reviews (order_id, review_desc, rating) VALUES (?, ?, ?);', (order_id, review_desc, rating))
                except sql.IntegrityError:
                    pass  # Skip duplicates
    connection.commit()
    connection.close()

if __name__ == "__main__":
    # Delete old database to ensure proper password hashing
    if os.path.exists(DATABASE):
        os.remove(DATABASE)

    # Call the table creation functions
    create_user_table()
    create_helpdesk_table()
    create_requests_table()
    create_buyers_table()
    create_creditcards_table()
    create_address_table()
    create_zipcode_table()
    create_sellers_table()
    create_categories_table()
    create_productlistings_table()  
    create_orders_table()
    create_reviews_table()
    

    # Call the table population functions - SPECIFIC ORDER TO MAINTAIN DEPENDENCIES
    populate_users()
    populate_address()
    populate_zipcode()            # Populate after Address

    populate_buyers()             # Populate after Users, Address
    populate_sellers()            # Populate after Users, Address
    populate_helpdesk()           # Populate after Users

    populate_requests()           # Populate after Users, HelpDesk
    populate_creditcards()        # Populate after Buyers

    populate_categories()
    populate_productlistings()    # Populate after Sellers, Categories
    populate_orders()             # Populate after Buyers, Sellers, ProductListings
    populate_reviews()            # Populate after Orders