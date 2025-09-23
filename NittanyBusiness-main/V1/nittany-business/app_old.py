from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3 as sql
import os
import hashlib
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nittanybusiness.db'
app.config['SQLALCHEMY_TRACK_CHANGES'] = False

db = SQLAlchemy(app)

Data = os.path.join(os.path.dirname(__file__), 'database.db')

DATABASE = 'database.db'

def hash_password(password):
    """Hash the password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

# Sample routes to demonstrate template rendering
@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    message, success = None, False

    flashed = get_flashed_messages()
    if flashed:
        try:
            message, success = flashed[0]
        except ValueError:
            message = flashed[0]
            success = None
    
    if request.method == 'POST':
        # Handle login logic here
        email = request.form.get('email')
        password = request.form.get('password')
        
        hashed_password = hash_password(password)

        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ? AND password = ?;', (email, hashed_password))
            user = cursor.fetchone()
            connection.commit()
            
            if user:
                email = user[0]
                userName = ""
                
                # checks buyer table to see if user is a buyer
                cursor.execute('SELECT business_name FROM Buyers WHERE email = ?;', (email,))
                buyerResult = cursor.fetchone()
                isBuyer = buyerResult is not None
                connection.commit()
                
                # checks sellers table to see if user is a seller
                cursor.execute('SELECT business_name FROM Sellers WHERE email = ?;', (email,))
                sellerResult = cursor.fetchone()
                isSeller = sellerResult is not None
                connection.commit()
                
                # checks helpdesk table to see if user is help desk and approved
                cursor.execute('SELECT position, approved FROM Helpdesk WHERE email = ?;', (email,))
                helpdeskResult = cursor.fetchone()
                isHelpDesk = helpdeskResult is not None and helpdeskResult[1] == 1  # approved == 1
                connection.commit()
                
                if isBuyer:
                    userName = buyerResult[0]
                    userType = 'Buyer'
                elif isSeller:
                    userName = sellerResult[0]
                    userType = 'Seller'
                elif isHelpDesk:
                    userName = email  # or helpdeskResult[0] for position if you want
                    userType = 'Help Desk'
                else:
                    user = None  # prevent logging in if not any of the 3
                
                if user:
                    session['user'] = {'id': email, 'name': userName, 'type': userType}

        except Exception as e:
            print(e)
        finally:
            if connection:
                connection.close() 

        if user:
            return redirect(url_for('dashboard'))
        else:
            message = 'Invalid email or password.'
    
    return render_template('login.html', message=message, success=success)



# Manage pending HelpDesk accounts
@app.route('/manage_helpdesk_accounts')
def manage_helpdesk_accounts():
    if 'user' not in session:
        flash('You must be logged in to access this page.', 'error')
        return redirect(url_for('login'))

    if session['user']['type'] != 'Help Desk':
        flash('Only HelpDesk staff can access this page.', 'error')
        return redirect(url_for('dashboard'))

    user = session['user']

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute('SELECT email, position FROM Helpdesk WHERE approved = 0')
    pending_helpdesks = cursor.fetchall()
    connection.close()

    pending_helpdesks = [{'email': row[0], 'position': row[1]} for row in pending_helpdesks]

    return render_template('manage_helpdesk_accounts.html', 
                           pending_helpdesks=pending_helpdesks,
                           user=user)


# Approve a HelpDesk user
@app.route('/approve_helpdesk/<email>', methods=['POST'])
def approve_helpdesk(email):
    if 'user' not in session or session['user']['type'] != 'Help Desk':
        flash('You are not authorized.', 'error')
        return redirect(url_for('login'))

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('UPDATE Helpdesk SET approved = 1 WHERE email = ?', (email,))
    connection.commit()
    connection.close()

    flash('HelpDesk account approved successfully!', 'success')
    return redirect(url_for('manage_helpdesk_accounts'))


# Reject (delete) a HelpDesk request
@app.route('/reject_helpdesk/<email>', methods=['POST'])
def reject_helpdesk(email):
    if 'user' not in session or session['user']['type'] != 'Help Desk':
        flash('You are not authorized.', 'error')
        return redirect(url_for('login'))

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('DELETE FROM Helpdesk WHERE email = ?', (email,))
    cursor.execute('DELETE FROM Users WHERE email = ?', (email,))
    connection.commit()
    connection.close()

    flash('HelpDesk account rejected and removed.', 'success')
    return redirect(url_for('manage_helpdesk_accounts'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    message = None
    success = None

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        user_type = request.form.get('user_type')
        name = request.form.get('name')

        # NEW: Check if passwords match
        if password != confirm_password:
            message = "Passwords do not match. Please try again."
            success = False
            return render_template('register.html', message=message, success=success)

        session['userRegistration'] = {
            'email': email,
            'password': password,
            'name': name,
        }

        # Redirect based on user type
        if user_type == 'buyer':
            return redirect(url_for('registerBuyer'))
        elif user_type == 'seller':
            return redirect(url_for('registerSeller'))
        elif user_type == 'helpdesk':
            return redirect(url_for('registerHelpDesk'))

    return render_template('register.html', message=message, success=success)


@app.route('/registerBuyer', methods=['GET', 'POST'])
def registerBuyer():
    message, success = "", False
    
    if request.method == 'POST':
        userRegistration = session.get('userRegistration', {})
        # goes into User table
        email = userRegistration.get('email')
        password = userRegistration.get('password')
        password = hash_password(password)
        
        # goes into Buyers table
        business_name = request.form.get('name')
        
        # goes into Address Table
        zipcode = request.form.get('zipcode')
        street_num = request.form.get('street_num')
        street_name = request.form.get('street_name')
        
        # connects Buyers and Address
        address_id = uuid.uuid4().hex
        
        # Add validation and database operations
        try:
            # Add the buyer to database
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute('''
                INSERT INTO Users(email,password)
                VALUES(?,?)
            ''', (email, password))
            connection.commit()
            cursor.execute('''
                INSERT INTO Buyers(email,business_name,buyer_address_id)
                VALUES(?,?,?)
            ''', (email, business_name,address_id))
            connection.commit()
            cursor.execute('''
                INSERT INTO Address(address_ID,zipcode,street_num,street_name)
                VALUES(?,?,?,?)
            ''', (address_id, zipcode, street_num, street_name))
            connection.commit()
            
            message = f'Buyer account created for {business_name}'
            success = True
            flash((message, success))
            
            return redirect(url_for('login'))
        except Exception as e:
            message = f'Failed to create account: {e}'
            success = False
        finally:
            if connection:
                connection.close()

    return render_template('registerBuyer.html', message=message, success=success)


@app.route('/registerHelpDesk', methods=['GET', 'POST'])
def registerHelpDesk():
    message, success = "", False

    if request.method == 'POST':
        userRegistration = session.get('userRegistration', {})
        email = userRegistration.get('email')
        password = userRegistration.get('password')
        password = hash_password(password)
        position = request.form.get('position')

        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()

            # Insert into Users
            cursor.execute('''
                INSERT INTO Users(email, password)
                VALUES (?, ?)
            ''', (email, password))
            connection.commit()

            # Insert into Helpdesk with approved = 0
            cursor.execute('''
                INSERT INTO Helpdesk (email, position, approved)
                VALUES (?, ?, 0)
            ''', (email, position))
            connection.commit()

            message = f'HelpDesk account created successfully! Please wait for approval.'
            success = True
            flash((message, success))

            return redirect(url_for('login'))

        except Exception as e:
            message = f'Failed to create account: {e}'
            success = False

        finally:
            if connection:
                connection.close()

    return render_template('registerHelpDesk.html', message=message, success=success)



@app.route('/registerSeller', methods=['GET', 'POST'])
def registerSeller():
    message = None
    success = True
    
    if request.method == 'POST':
        userRegistration = session.get('userRegistration', {})
        
        # for Users table
        email = userRegistration.get('email')
        password = userRegistration.get('password')
        password = hash_password(password)
        
        # for Sellers table
        Business_Name = request.form.get('Business_Name')
        address_id = uuid.uuid4().hex
        bank_routing_number = request.form.get('bank_routing_number')
        bank_account_number = request.form.get('bank_account_number')
        balance = 0 #default
        
        # goes into Address Table
        zipcode = request.form.get('zipcode')
        street_num = request.form.get('street_num')
        street_name = request.form.get('street_name')
        
        # Add validation and database operations
        try:
            # Add the seller to database
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute('''
                INSERT INTO Users(email,password)
                VALUES(?,?)
            ''', (email, password))
            connection.commit()
            cursor.execute('''
                INSERT INTO Sellers(email, Business_Name, Business_Address_Id, bank_routing_number,bank_account_number, balance)
                VALUES(?,?,?,?,?,?)
            ''', (email, Business_Name, address_id, bank_routing_number,bank_account_number, balance))
            connection.commit()
            cursor.execute('''
                INSERT INTO Address(address_ID,zipcode,street_num,street_name)
                VALUES(?,?,?,?)
            ''', (address_id, zipcode, street_num, street_name))
            connection.commit()
            connection.close()
            
            message = f'Seller account created successfully!'
            success = True
            flash((message, success))
            
            return redirect(url_for('login'))
        except Exception as e:
            message = f'Failed to create account: {e}'
            success = False
        finally:
            if connection:
                connection.close()

    return render_template('registerSeller.html', message=message, success=success)


@app.route('/products')
def products():
    user = session.get('user', {})  # Always get user first

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    selected_category = request.args.get('category')
    search_query = request.args.get('search')
    price_range = request.args.get('price_range')  # <-- NEW

    # Start building SQL query
    base_query = '''
        SELECT * FROM ProductListings
    '''
    where_clauses = []
    params = []

    # Category filter
    if selected_category:
        where_clauses.append('category IN (SELECT category_name FROM Categories WHERE category_name = ? OR parent_category = ?)')
        params.extend([selected_category, selected_category])

    # Build full query
    if where_clauses:
        base_query += ' WHERE ' + ' AND '.join(where_clauses)

    cursor.execute(base_query, params)

    attributes = ['seller_email', 'listing_id', 'category', 'product_title', 'product_name', 'product_description', 'quantity', 'product_price', 'status']
    products = [dict(zip(attributes, row)) for row in cursor.fetchall()]

    # Search filter (in memory after fetching)
    if search_query:
        products = [
            product for product in products
            if (search_query.lower() in product['product_name'].lower() or 
                search_query.lower() in product['product_description'].lower() or
                search_query.lower() in product['product_title'].lower() or
                search_query.lower() in product['seller_email'].lower())
        ]

    # Price range filter (also in memory after fetching)
    if price_range:
        if '-' in price_range:
            min_price, max_price = price_range.split('-')
            min_price = float(min_price)
            max_price = float(max_price)
            products = [
                p for p in products
                if min_price <= float(str(p['product_price']).replace('$', '').replace(',', '').strip()) <= max_price
            ]
        elif price_range == '1000+':
            products = [
                p for p in products
                if float(str(p['product_price']).replace('$', '').replace(',', '').strip()) >= 1000
            ]

    # Fetch Seller Names
    for product in products:
        cursor.execute('SELECT business_name FROM Sellers WHERE email = ?', (product['seller_email'],))
        seller = cursor.fetchone()
        product['seller_name'] = seller[0] if seller else 'Unknown Seller'

    # Fetch Categories
    if selected_category:
        cursor.execute('''
            SELECT category_name FROM Categories
            WHERE parent_category = ? OR category_name = ?
        ''', (selected_category, selected_category))
    else:
        cursor.execute('SELECT category_name FROM Categories WHERE parent_category = ?', ('Root',))
    categories = [row[0] for row in cursor.fetchall()]

    # Dummy Pagination
    class Pagination:
        def __init__(self):
            self.page = 1
            self.per_page = 10
            self.total = 3
            self.has_prev = False
            self.has_next = False
            self.prev_num = None
            self.next_num = None
        
        def iter_pages(self):
            return [1]
    
    pagination = Pagination()

    connection.close()

    return render_template('products.html',
        user=user,
        products=products,
        categories=categories,
        pagination=pagination,
        selected_category=selected_category,
        selected_price_range=price_range,  # <-- Pass this
        search_query=search_query           # <-- Pass this
    )

#Cart section
@app.route('/cart')
def cart():
    # Make sure user is logged in
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']

    # Only buyers can access the cart
    if user['type'] != 'Buyer':
        return redirect(url_for('dashboard'))

    # Get cart from session
    cart = session.get('cart', [])
    
    # Creates a subtotal for each type of item
    for item in cart:
        item['subtotal'] = float(item['price'].replace('$', '')) * float(item['quantity'])

    # final price of all items
    total_price = sum(float(item['price'].replace('$', '')) * int(item['quantity']) for item in cart)

    return render_template('cart.html', user=user, cart=cart, total_price=total_price)

#route to remove the selected item
@app.route('/remove_from_cart/<int:listing_id>', methods=['POST'])
def remove_from_cart(listing_id):
    if 'cart' not in session:
        return redirect(url_for('cart'))

    cart = session['cart']

    # Keep only the items that are NOT the one we are removing
    cart = [item for item in cart if item['listing_id'] != listing_id]

    session['cart'] = cart  # Save updated cart back into session

    flash('Item removed from cart.', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout/<int:total_price>', methods=['POST'])
def checkout(total_price):
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    if user['type'] != 'Buyer':
        return redirect(url_for('dashboard'))  # Only Buyers manage payments

    user = session['user']

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    if request.method == 'POST':
        # Add new credit card
        credit_card_num = request.form.get('credit_card_num')
        card_type = request.form.get('card_type')
        expire_month = request.form.get('expire_month')
        expire_year = request.form.get('expire_year')
        security_code = request.form.get('security_code')

        if credit_card_num and card_type and expire_month and expire_year and security_code:
            try:
                cursor.execute('''
                    INSERT INTO CreditCards (credit_card_num, card_type, expire_month, expire_year, security_code, owner_email)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (credit_card_num, card_type, expire_month, expire_year, security_code, user['id']))
                connection.commit()
                flash('Credit card added successfully!', 'success')
            except Exception as e:
                flash(f'Failed to add credit card: {e}', 'danger')

    # Fetch buyer's saved cards
    cursor.execute('SELECT credit_card_num, card_type, expire_month, expire_year FROM CreditCards WHERE owner_email = ?', (user['id'],))
    cards = cursor.fetchall()
    connection.close()

    return render_template('checkout.html', 
                           cards=cards,
                           total_price=total_price,
                           user=user)


@app.route('/finalize_sale', methods=['POST'])
def finalize_sale():
    if 'user' not in session:
        flash('You must be logged in to checkout.', 'error')
        return redirect(url_for('login'))

    user = session['user']

    if user['type'] != 'Buyer':
        flash('Only buyers can checkout.', 'error')
        return redirect(url_for('dashboard'))

    cart = session.get('cart', [])

    if not cart:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('cart'))

    try:
        connection = sql.connect(DATABASE)
        cursor = connection.cursor()

        for item in cart:
            listing_id = item['listing_id']
            quantity = item['quantity']
            price = float(item['price'].replace('$', '')) if isinstance(item['price'], str) else float(item['price'])
            payment = price * int(quantity)
            date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Get seller email safely
            cursor.execute('SELECT seller_email FROM ProductListings WHERE listing_id = ?', (listing_id,))
            result = cursor.fetchone()
            if not result:
                continue  # skip if somehow product not found
            seller_email = result[0]

            # Insert the order
            cursor.execute('''
                INSERT INTO Orders (seller_email, buyer_email, listing_id, date, quantity, payment)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (seller_email, user['id'], listing_id, date_now, quantity, payment))

            # Add to seller balance
            cursor.execute('''
                UPDATE Sellers 
                SET balance = balance + ?
                WHERE email = ?
            ''', (payment, seller_email))

            # Decrease product quantity #https://www.interviewquery.com/p/sql-count-case-when
            cursor.execute('''
                UPDATE ProductListings
                SET quantity = quantity - ?,
                    Status = CASE
                                WHEN quantity - ? <= 0 THEN 2
                                ELSE Status
                            END
                WHERE listing_id = ?
            ''', (quantity, quantity, listing_id))

        connection.commit()

        # Clear cart after successful checkout
        session['cart'] = []
        flash('Checkout successful! Your orders have been placed.', 'success')
        return redirect(url_for('thank_you'))

    except Exception as e:
        print(f"Checkout Error: {e}")
        flash('An error occurred during checkout. Please try again.', 'error')
        return redirect(url_for('cart'))

    finally:
        if connection:
            connection.close()

# displays sellers listings for editing, creating, deleting
@app.route('/productListings', methods=['GET', 'POST'])
def productListings():
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    user = session['user']

    selected_category = request.args.get('category')
    sellerEmail = session['user']['id']
    
    message, success = None, False
    flashed = get_flashed_messages(with_categories=True)
    if flashed:
        success, message = flashed[0]

    # Recursively find all products under the selected category
    if selected_category:
        cursor.execute(f'''
        WITH RECURSIVE subcategories(category_name) AS (
            SELECT category_name
            FROM Categories
            WHERE category_name = ?

            UNION ALL

            SELECT c.category_name
            FROM Categories c
            INNER JOIN subcategories s ON c.parent_category = s.category_name
        )
        SELECT * FROM ProductListings
        WHERE category IN (SELECT category_name FROM subcategories)
        AND Seller_Email = ?
        AND Status !=2
        ''', (selected_category, sellerEmail))
    else: # select every listing
        cursor.execute('''
        SELECT * FROM ProductListings
        WHERE Seller_Email = ?
        AND Status != 2
        ''', (sellerEmail,))

    # Preprocess the products into a better format for HTML
    attributes = ['seller_email', 'id', 'category', 'title', 'name', 'description', 'quantity', 'price', 'status']
    products = [dict(zip(attributes, row)) for row in cursor.fetchall()]

    # seller names to display
    for product in products:
        cursor.execute('''
            SELECT (business_name)
            FROM Sellers S
            WHERE S.email = ?
        ''', (product['seller_email'],))
        product['seller_name'] = cursor.fetchone()[0]

    # find children and current category
    if (selected_category):
        cursor.execute('''
            SELECT (category_name)
            FROM Categories
            WHERE parent_category=?
            UNION   
            SELECT (category_name)
            FROM Categories
            WHERE category_name=?    
            ''', (selected_category,selected_category))
    else: # pick all categories
        cursor.execute('''SELECT (category_name) 
            FROM Categories 
            WHERE parent_category = ?''', ("Root",))
    
    categories = [row[0] for row in cursor.fetchall()]

    return render_template('productListings.html', 
                          products=products,
                          categories=categories,
                          selected_category = selected_category,
                          message=message,
                          success=success,
                          user=user
                          )

# seller creates new product listing
@app.route('/createProductListing', methods=['GET', 'POST'])
def createProductListing():
    categories = []
    message = ""
    success = None
    user = session.get('user', {})

    # got to the wrong link and was not logged in
    if 'user' not in session:
        flash('You must be logged in to create a product listing.', 'error')
        return redirect(url_for('login'))

    if user['type'] != 'Seller':
        flash('Only sellers can create product listings.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == "GET":
        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute('''SELECT category_name FROM Categories;''') # select all categories for the dropdown
            categories = [row[0] for row in cursor.fetchall()]
            connection.close()
        except Exception as e:
            print(e)

    if request.method == "POST":
        try:
            sellerEmail = user['id']
            productTitle = request.form.get('productTitle')
            productName = request.form.get('productName')
            description = request.form.get('description')
            category = request.form.get('category')
            price_input = request.form.get('price')
            quantity_input = request.form.get('quantity')
            status_input = request.form.get('active')

            # clean price
            cleaned_price = price_input.replace('$', '').replace(',', '').strip()
            price = float(cleaned_price)

            # set quantity and check
            quantity = int(quantity_input)
            if quantity <= 0:
                raise ValueError("Quantity must be greater than 0.")

            # set status
            status = 1 if status_input == 'active' else 0

            connection = sql.connect(DATABASE)
            cursor = connection.cursor()

            # Find last Listing_ID and increment
            cursor.execute('SELECT MAX(Listing_ID) FROM ProductListings WHERE Seller_Email = ?', (sellerEmail,))
            lastID = cursor.fetchone()[0]
            if lastID:
                listingID = lastID + 1
            else:
                listingID = 1

            # Insert new product
            cursor.execute('''
                INSERT INTO ProductListings(
                    Seller_Email, Listing_ID, Category, Product_Title, 
                    Product_Name, Product_Description, Quantity, Product_Price, Status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sellerEmail, listingID, category, productTitle,
                  productName, description, quantity, price, status))

            connection.commit()
            message = f'{productTitle} listed successfully!'
            success = 'success'
            flash(message, success)
            return redirect(url_for('productListings'))

        except ValueError as ve:
            message = f'Invalid input: {ve}'
            success = 'error'
            flash(message, success)
        except Exception as e:
            message = f'Failed to list product: {e}'
            success = 'error'
            flash(message, success)
        finally:
            if 'connection' in locals():
                connection.close()

    return render_template('createProductListing.html', message=message, success=success, categories=categories,user=user)

# edit product listing after it has been created
@app.route('/editProductListing', methods=['GET', 'POST'])
def editProductListing():
    categories = []
    message = ""
    success = None
    
    user = session['user']
    sellerEmail = user['id']
    
    productData = {}
    
    # reupdate the productID since it is a new product
    listingID = session.get('productID')
    if not listingID:
        listingID = request.args.get('productID')
        if listingID:
            session['productID'] = listingID

    if request.method == "GET":
        try:
            listingID = request.args.get('productID')
            session['productID'] = listingID
            
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute('''SELECT * FROM ProductListings WHERE Listing_ID = ? AND Seller_Email = ?''', (listingID, sellerEmail))
            product = cursor.fetchone()
            
            # to display the current editable product in the html
            if product:
                productData = {
                                'productTitle': product[3],
                                'productName': product[4],
                                'description': product[5],
                                'productCategory': product[2],
                                'price': product[7],
                                'quantity': product[6],
                                'status': product[8]
                            }
    
            cursor.execute('''SELECT category_name FROM Categories;''')
            categories = [row[0] for row in cursor.fetchall()]
            connection.close()
            
        except Exception as e:
            print(e)
        finally:
            if connection:
                connection.close()
        
    if request.method == "POST":
        productTitle = request.form.get('productTitle')
        productName = request.form.get('productName')
        description = request.form.get('description')
        category = request.form.get('category')
        price = request.form.get('price')
        quantity = request.form.get('quantity')
        status = request.form.get('active')
        status = 1 if status == 'active' else 0
        
        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            
            # change this listing based on the updated fields of the form
            cursor.execute('''
                UPDATE ProductListings
                SET Category=?, Product_Title=?, Product_Name=?, Product_Description=?, Quantity=?, Product_Price=?, Status=?
                WHERE Seller_Email=? AND Listing_ID=?
            ''', (category, productTitle, productName, description, quantity, price, status, sellerEmail, listingID))
            connection.commit()
            
            message = f'{productTitle} Updated!'
            success = 'success'
            flash(message, success)
            
            return redirect(url_for('productListings'))
        except Exception as e:
            print(e)
            message = f'Failed to update product: {e}'
            success = False
        finally:
            if connection:
                connection.close()
    
    return render_template('editProductListing.html', message=message, success=success, categories=categories, productData=productData, user=user)

# seller removes a product listing from the market
@app.route('/deleteProductListing', methods=['GET', 'POST'])
def deleteProductListing():
    if request.method == "GET":
        listingID = request.args.get('productID')
        session['productID'] = listingID
        
    if request.method == "POST":
        user = session['user']
        sellerEmail = user['id']

        listingID = session.get('productID')
                
        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            
            # essentially delete the listing by making its status "sold"
            cursor.execute('''
                UPDATE ProductListings
                SET Status=2
                WHERE Seller_Email=? AND Listing_ID=?
            ''', (sellerEmail, listingID))
            connection.commit()
            
            message = f'Deleted!'
            success = 'success'
            flash(message, success)
            
            return redirect(url_for('productListings'))
        except Exception as e:
            print(e)
            message = f'Failed to delete product: {e}'
            success = 'error'
            flash(message, success)
        finally:
            if connection:
                connection.close()
    
    return render_template('deleteProductListing.html')
    
# homepage for all users
@app.route('/dashboard')
def dashboard():
    message, success = None, False

    flashed = get_flashed_messages(with_categories=True)
    if flashed:
        success, message = flashed[0]
            
    # Check if user is logged in
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Sample user data
    user = session['user']
    if not isinstance(user, dict):
        user = {'name': 'Demo User', 'type': 'buyer', 'last_login': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    else:
        user['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if (user['type'] == 'Seller'):
        connection = sql.connect(DATABASE)
        cursor = connection.cursor()
        cursor.execute('''
            SELECT (balance)
            FROM Sellers S
            WHERE S.email = ?
            ''', (user['id'],))
        balance = cursor.fetchone()[0]
    else:
        balance = 0


    return render_template('dashboard.html', user=user, message=message, success=success, balance=balance)

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('cart', None)  # optional: also clear cart if needed
    session.clear()  # ✅ clear all session data including flashed messages
    return redirect(url_for('login'))


# Placeholder routes for dashboard links
@app.route('/orders')
def orders():
    user = session.get('user', {})

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    
    cursor.execute('''
        SELECT *
        FROM Orders O
        WHERE buyer_email = ?
        ORDER BY date DESC
    ''', (user['id'],))

    attributes = ['order_id', 'seller_email', 'buyer_email', 'listing_id', 'date', 'quantity', 'payment']
    orders = [dict(zip(attributes, row)) for row in cursor.fetchall()]
    
    for order in orders:
        # Find Seller names for display
        cursor.execute('''
            SELECT business_name
            FROM Sellers
            WHERE email = ?
        ''', (order['seller_email'],))
        seller = cursor.fetchone()
        order['seller_name'] = seller[0] if seller else 'Unknown Seller'

        # Find Buyer names for display
        cursor.execute('''
            SELECT business_name
            FROM Buyers
            WHERE email = ?
        ''', (order['buyer_email'],))
        buyer = cursor.fetchone()
        order['buyer_name'] = buyer[0] if buyer else 'Unknown Buyer'

        # Find Product Info
        cursor.execute('''
            SELECT product_title, product_name
            FROM ProductListings
            WHERE listing_id = ?
        ''', (order['listing_id'],))
        product = cursor.fetchone()
        if product:
            order['product_title'] = product[0]
            order['product_name'] = product[1]
        else:
            order['product_title'] = 'Unknown Title'
            order['product_name'] = 'Unknown Product'

        # Check if this order has a Review
        cursor.execute('''
            SELECT review_desc, rating
            FROM Reviews
            WHERE order_id = ?
        ''', (order['order_id'],))
        review = cursor.fetchone()
        if review:
            order['has_review'] = True
            order['review_desc'] = review[0]
            order['rating'] = review[1]
        else:
            order['has_review'] = False

    connection.close()

    return render_template('orders.html', 
                           user=user,
                           orders=orders
                           )

@app.route('/leave_review/<int:order_id>', methods=['GET', 'POST'])
def leave_review(order_id):
    if 'user' not in session:
        flash('You must be logged in to leave a review.', 'error')
        return redirect(url_for('login'))

    user = session['user']

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    # First, check if the order actually exists and belongs to this user
    cursor.execute('''
        SELECT buyer_email
        FROM Orders
        WHERE order_id = ?
    ''', (order_id,))
    order = cursor.fetchone()
    
    if not order:
        flash('Order not found.', 'error')
        connection.close()
        return redirect(url_for('orders'))

    if order[0] != user['id']:
        flash('You can only review your own orders.', 'error')
        connection.close()
        return redirect(url_for('orders'))

    if request.method == 'POST':
        review_desc = request.form.get('review_desc', '')
        rating = request.form.get('rating')

        if not rating:
            flash('Rating is required.', 'error')
            connection.close()
            return redirect(url_for('leave_review', order_id=order_id))

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except ValueError:
            flash('Rating must be an integer between 1 and 5.', 'error')
            connection.close()
            return redirect(url_for('leave_review', order_id=order_id, user=user))

        # Insert into Reviews table
        try:
            cursor.execute('''
                INSERT INTO Reviews (order_id, review_desc, rating)
                VALUES (?, ?, ?)
            ''', (order_id, review_desc, rating))
            connection.commit()
            flash('Review submitted successfully!', 'success')
        except Exception as e:
            flash(f'Failed to submit review: {e}', 'error')
        finally:
            connection.close()

        return redirect(url_for('orders'))

    connection.close()
    return render_template('leave_review.html', order_id=order_id, user=user)


@app.route('/thank_you')
def thank_you():
    user = session['user']
    return render_template('thank_you.html',
                           user=user)

@app.route('/update_request/<int:request_id>', methods=['GET', 'POST'])
def update_request(request_id):
    if 'user' not in session:
        flash('You must be logged in to access your profile.', 'error')
        return redirect(url_for('login'))
    
    if session['user']['type'] != 'Help Desk':
        flash('You must be Help Desk to access this page.', 'error')
        return redirect(url_for('dashboard'))
    
    user = session['user']

    if request.method == 'POST':
        new_category = request.form.get('new_category')
        parent_category = request.form.get('parent_category')
        new_sender_email = request.form.get('new_sender_email')
        new_request_status = request.form.get('new_request_status')

        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()

            # Handle category creation if provided
            if new_category and parent_category:
                cursor.execute('''
                    INSERT INTO Categories (category_name, parent_category)
                    VALUES (?, ?)
                ''', (new_category, parent_category))
                connection.commit()

            # Handle email change if provided
            if new_sender_email:
                # Get old email from the request
                cursor.execute('SELECT sender_email FROM Requests WHERE request_id = ?', (request_id,))
                old_email = cursor.fetchone()
                
                if old_email:
                    old_email = old_email[0]
                    
                    # First update Users table
                    cursor.execute('''
                        UPDATE Users
                        SET email = ?
                        WHERE email = ?
                    ''', (new_sender_email, old_email))
                    cursor.execute('''
                        UPDATE Requests
                        SET sender_email = ?
                        WHERE sender_email = ?
                    ''', (new_sender_email, old_email))
                    
                    # Second figure out what type the old email was
                    cursor.execute('SELECT * FROM Buyers WHERE email = ?', (old_email,))
                    buyer = cursor.fetchone()
                    
                    cursor.execute('SELECT * FROM Sellers WHERE email = ?', (old_email,))
                    seller = cursor.fetchone()
                    
                    cursor.execute('SELECT * FROM Helpdesk WHERE email = ?', (old_email,))
                    helpdesk = cursor.fetchone()

                    # Third update the table
                    if buyer:
                        cursor.execute('''
                            UPDATE Buyers
                            SET email = ?
                            WHERE email = ?
                        ''', (new_sender_email, old_email))
                        connection.commit()
                        cursor.execute('''
                            UPDATE CreditCards
                            SET owner_email = ?
                            WHERE owner_email = ?
                        ''', (new_sender_email, old_email))
                        connection.commit()
                        cursor.execute('''
                            UPDATE Orders
                            SET buyer_email = ?
                            WHERE buyer_email = ?
                        ''', (new_sender_email, old_email))
                        connection.commit()
                        
                    elif seller:
                        cursor.execute('''
                            UPDATE Sellers
                            SET email = ?
                            WHERE email = ?
                        ''', (new_sender_email, old_email))
                        connection.commit()
                        cursor.execute('''
                            UPDATE Orders
                            SET seller_email = ?
                            WHERE seller_email = ?
                        ''', (new_sender_email, old_email))
                        cursor.execute('''
                            UPDATE ProductListings
                            SET seller_email = ?
                            WHERE seller_email = ?
                        ''', (new_sender_email, old_email))
                        connection.commit()
                        
                    elif helpdesk:
                        cursor.execute('''
                            UPDATE Helpdesk
                            SET email = ?
                            WHERE email = ?
                        ''', (new_sender_email, old_email))
                        connection.commit()

            # Handle request status update (approve/deny)
            if new_request_status is not None:
                cursor.execute('''
                    UPDATE Requests
                    SET request_status = ?
                    WHERE request_id = ?
                ''', (int(new_request_status), request_id))
                connection.commit()
            
        except Exception as e:
            print("Error in update_request:", e)
        finally:
            if connection:
                connection.close()
        flash('Request updated successfully!', 'success')
        return redirect(url_for('manage_requests'))

    return render_template('update_request.html', 
                           request_id=request_id,
                           user=user)

@app.route('/manage_requests')
def manage_requests():
    if 'user' not in session:
        flash('You must be logged in to access your profile.', 'error')
        return redirect(url_for('login'))
    
    elif session['user']['type'] != 'Help Desk':
        flash('You must be Help Desk to access this page.', 'error')
        return redirect(url_for('dashboard'))
    
    user = session['user']

    try:
        connection = sql.connect(DATABASE)
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Requests WHERE request_status = 0 AND helpdesk_staff_email = ?", (session['user']['id'],))
        requests_list = cursor.fetchall()
        requests = []
        for i,x in enumerate(requests_list):
            requests.append({})
            requests[i]['request_id'] = x[0]
            requests[i]['sender_email'] = x[1]
            requests[i]['helpdesk_email'] = x[2]
            requests[i]['request_type'] = x[3]
            requests[i]['request_desc'] = x[4]
            requests[i]['request_status'] = x[5]
        connection.commit()
            
    except Exception as e:
        print(e)
    finally:
        if connection:
            connection.close() 

    return render_template('manage_requests.html', 
                           requests=requests,
                           user=user)

@app.route('/claim_requests', methods=['GET', 'POST'])
def claim_requests():
    if 'user' not in session:
        flash('You must be logged in to access your profile.', 'error')
        return redirect(url_for('login'))
    
    elif session['user']['type'] != 'Help Desk':
        flash('You must be Help Desk to access this page.', 'error')
        return redirect(url_for('dashboard'))
    
    user = session['user']

    if request.method == 'POST':
        request_id = request.form.get('request_id')
        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE Requests
                SET helpdesk_staff_email = ?
                WHERE request_id = ?
            """, (session['user']['id'], request_id))
            connection.commit()
                
        except Exception as e:
            print(e)
        finally:
            if connection:
                connection.close()

    requests = []
    try:
        connection = sql.connect(DATABASE)
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Requests WHERE request_status = 0 AND helpdesk_staff_email = ?", ('helpdeskteam@nittybiz.com',))
        requests_list = cursor.fetchall()
        for i,x in enumerate(requests_list):
            requests.append({})
            requests[i]['request_id'] = x[0]
            requests[i]['sender_email'] = x[1]
            requests[i]['helpdesk_email'] = x[2]
            requests[i]['request_type'] = x[3]
            requests[i]['request_desc'] = x[4]
            requests[i]['request_status'] = x[5]
        connection.commit()
            
    except Exception as e:
        print(e)
    finally:
        if connection:
            connection.close()

    return render_template('claim_requests.html', requests=requests, user=user)

@app.route('/payment_methods', methods=['GET', 'POST'])
def payment_methods():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    if user['type'] != 'Buyer':
        return redirect(url_for('dashboard'))  # Only Buyers manage payments

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    if request.method == 'POST':
        # Add new credit card
        credit_card_num = request.form.get('credit_card_num')
        card_type = request.form.get('card_type')
        expire_month = request.form.get('expire_month')
        expire_year = request.form.get('expire_year')
        security_code = request.form.get('security_code')

        if credit_card_num and card_type and expire_month and expire_year and security_code:
            try:
                cursor.execute('''
                    INSERT INTO CreditCards (credit_card_num, card_type, expire_month, expire_year, security_code, owner_email)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (credit_card_num, card_type, expire_month, expire_year, security_code, user['id']))
                connection.commit()
                flash('Credit card added successfully!', 'success')
            except Exception as e:
                flash(f'Failed to add credit card: {e}', 'danger')

        # ✅ Always redirect after POST (even if success or error)
        connection.close()
        return redirect(url_for('payment_methods'))

    # Fetch buyer's saved cards
    cursor.execute('SELECT credit_card_num, card_type, expire_month, expire_year FROM CreditCards WHERE owner_email = ?', (user['id'],))
    cards = cursor.fetchall()
    connection.close()

    return render_template('payment_methods.html', 
                           cards=cards,
                           user=user)


@app.route('/delete_card/<card_num>', methods=['POST'])
def delete_card(card_num):
    if 'user' not in session:
        return redirect(url_for('login'))

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('DELETE FROM CreditCards WHERE credit_card_num = ? AND owner_email = ?', (card_num, session['user']['id']))
    connection.commit()
    connection.close()

    flash('Credit card removed.', 'success')
    return redirect(url_for('payment_methods'))

@app.route('/product_info/<int:product_id>')
def product_info(product_id):
    user = session['user']

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()
    cursor.execute('''
        SELECT *
        FROM ProductListings
        WHERE listing_id = ?
        ''', (product_id,))
    product_row = cursor.fetchone()

    if not product_row:
        flash('Product not found.', 'danger')
        return redirect(url_for('products'))

    product_attributes = ['seller_email', 'listing_id', 'category', 'product_title', 'product_name', 'product_description', 'quantity', 'product_price', 'status']
    product = dict(zip(product_attributes, product_row))

    cursor.execute('''
            SELECT (business_name)
            FROM Sellers S
            WHERE S.email = ?
        ''', (product['seller_email'],))
    product['seller_name'] = cursor.fetchone()[0]

    cursor.execute('''
            SELECT review_desc, rating
            FROM Reviews R
            JOIN Orders O ON R.order_id = O.order_id
            WHERE O.listing_id = ?
        ''', (product['listing_id'],))
    review_attributes = ['review_desc', 'rating']
    reviews = [dict(zip(review_attributes, row)) for row in cursor.fetchall()]
    connection.close()

    return render_template('product_info.html',
                           product=product,
                           reviews=reviews,
                           user=user)

@app.route('/seller_reviews')
def seller_reviews():
    if 'user' not in session:
        flash('You must be logged in.', 'error')
        return redirect(url_for('login'))

    user = session['user']
    if user['type'] != 'Seller':
        flash('Only sellers can view their reviews.', 'error')
        return redirect(url_for('dashboard'))

    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    # Get all orders that belong to this seller
    cursor.execute('''
        SELECT O.order_id, O.listing_id, O.date, O.quantity, O.payment, R.review_desc, R.rating
        FROM Orders O
        LEFT JOIN Reviews R ON O.order_id = R.order_id
        WHERE O.seller_email = ?
        ORDER BY O.date DESC
    ''', (user['id'],))

    attributes = ['order_id', 'listing_id', 'date', 'quantity', 'payment', 'review_desc', 'rating']
    reviews = [dict(zip(attributes, row)) for row in cursor.fetchall()]

    connection.close()

    return render_template('seller_reviews.html', user=user, reviews=reviews)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        flash('You must be logged in to access your profile.', 'error')
        return redirect(url_for('login'))
    user = session['user']
    
    flashed = get_flashed_messages(with_categories=True)
    if flashed:
        category, message = flashed[0]
        success = (category == 'success')
    else:
        message, success = None, False

    if request.method == 'POST':
        
        passcode = request.form.get('passcode')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        hashed_password = hash_password(passcode)

        user = session['user']
        email = user['id']
        if new_password != confirm_password:
            
            flash('Passwords do not match.', 'error')
            return redirect(url_for('profile'))
        
        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ? AND password = ?;', (email, hashed_password))
            user = cursor.fetchone()
            connection.commit()
            if user:
                new_hashed_password = hash_password(new_password)
                cursor.execute("""
                    UPDATE users
                    SET password = ?
                    WHERE email = ?
                """, (new_hashed_password, email))
                connection.commit()
                flash('Password updated successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid passcode.', 'error')
                success = False
                return redirect(url_for('profile'))
            
        except Exception as e:
            print(e)
        finally:
            if connection:
                connection.close() 
        
    return render_template('profile.html', user=user, message=message, success=success)

@app.route('/submit_request', methods=['GET', 'POST'])
def submit_request():
    if 'user' not in session:
        flash('You must be logged in to access your profile.', 'error')
        return redirect(url_for('login'))
    user = session['user']
    if request.method == 'POST':
        request_type = request.form.get('request_type')
        description = request.form.get('description')

        helpdesk_email = 'helpdeskteam@nittybiz.com'
        request_status = 0
        email = user['id']
        if not request_type or not description:
            flash('All fields are required.', 'error')
            return redirect(url_for('submit_request'))
        try:
            connection = sql.connect(DATABASE)
            cursor = connection.cursor()
            cursor.execute("""INSERT INTO Requests (sender_email, helpdesk_staff_email, request_type, request_desc, request_status)
            VALUES (?, ?, ?, ?, ?)""", (email, helpdesk_email, request_type, description, request_status))
            connection.commit()
            flash('Helpdesk request submitted successfully!', 'success')
            
        except Exception as e:
            print(e)
        finally:
            if connection:
                connection.close()

    return render_template('submit_request.html', user=user)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    connection = sql.connect(DATABASE)
    cursor = connection.cursor()

    # ✅ Using correct column names from your ProductListings table
    cursor.execute('''
        SELECT seller_email, listing_id, category, product_title, product_name, product_description, quantity, product_price, status
        FROM ProductListings
        WHERE listing_id = ?
    ''', (product_id,))
    product_row = cursor.fetchone()
    connection.close()

    if not product_row:
        flash('Product not found.', 'danger')
        return redirect(url_for('products'))

    attributes = ['seller_email', 'listing_id', 'category', 'product_title', 'product_name', 'product_description', 'quantity', 'product_price', 'status']
    product = dict(zip(attributes, product_row))

    # Initialize cart if not present
    if 'cart' not in session:
        session['cart'] = []

    cart = session['cart']

    # Read quantity from form
    form_quantity = int(request.form.get('quantity', 1))  # Default to 1 if missing
    print(form_quantity)

    for item in cart:
        if item['listing_id'] == product['listing_id']:
            # If already exists, increase quantity
            item['quantity'] += form_quantity
            break

    else:
        # Otherwise add new product
        cart.append({
            'listing_id': product['listing_id'],
            'name': product['product_name'],
            'price': product['product_price'],
            'quantity': form_quantity
        })

    session['cart'] = cart  # Save cart back into session
    flash('Product added to cart!', 'success')

    return redirect(url_for('products'))

if __name__ == '__main__':
    app.run(debug=True)