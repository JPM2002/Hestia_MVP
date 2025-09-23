from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import math
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nittany-business-secret-key'

# Define the path to your dataset
DATASET_PATH = r"C:\Users\Javie\Documents\GitHub\NittanyBusiness\V2\nittany-business\NittanyBusinessDataset"

# Data access functions
def load_csv(filename):
    """Load a CSV file from the dataset directory"""
    file_path = os.path.join(DATASET_PATH, filename)
    return pd.read_csv(file_path)

def get_user_by_email(email):
    """Get a user by email"""
    users_df = load_csv("Users.csv")
    user = users_df[users_df['email'] == email]
    if not user.empty:
        user_data = user.iloc[0].to_dict()
        
        # Determine user type
        buyers_df = load_csv("Buyers.csv")
        sellers_df = load_csv("Sellers.csv")
        helpdesk_df = load_csv("Helpdesk.csv")
        
        if email in buyers_df['email'].values:
            user_data['user_type'] = 'buyer'
            buyer_data = buyers_df[buyers_df['email'] == email].iloc[0].to_dict()
            user_data['business_name'] = buyer_data['business_name']
            user_data['address_id'] = buyer_data['buyer_address_id']
        elif email in sellers_df['email'].values:
            user_data['user_type'] = 'seller'
            seller_data = sellers_df[sellers_df['email'] == email].iloc[0].to_dict()
            user_data['business_name'] = seller_data['business_name']
            user_data['address_id'] = seller_data['Business_Address_ID']
            user_data['balance'] = seller_data['balance']
        elif email in helpdesk_df['email'].values:
            user_data['user_type'] = 'helpdesk'
            helpdesk_data = helpdesk_df[helpdesk_df['email'] == email].iloc[0].to_dict()
            user_data['position'] = helpdesk_data['Position']
        
        # Extract first and last name from email (since we don't have actual names in Users.csv)
        # This is just a placeholder - in a real app, you'd have actual names
        username = email.split('@')[0]
        user_data['first_name'] = username[:4].capitalize()
        user_data['last_name'] = username[4:].capitalize()
        
        return user_data
    return None

def get_user_address(address_id):
    """Get address details by address_id"""
    addresses_df = load_csv("Address.csv")
    address = addresses_df[addresses_df['address_id'] == address_id]
    if not address.empty:
        address_data = address.iloc[0].to_dict()
        
        # Get city and state from zipcode
        zipcode_info_df = load_csv("Zipcode_Info.csv")
        zipcode_info = zipcode_info_df[zipcode_info_df['zipcode'] == address_data['zipcode']]
        if not zipcode_info.empty:
            zipcode_data = zipcode_info.iloc[0].to_dict()
            address_data['city'] = zipcode_data['city']
            address_data['state'] = zipcode_data['state']
        
        return address_data
    return {}

def get_products(page=1, per_page=9, category=None, sort_by=None, search=None):
    """Get products with pagination, filtering, and sorting"""
    products_df = load_csv("Product_Listings.csv")
    
    # Clean up column names and data
    products_df.columns = [col.strip() for col in products_df.columns]
    
    # Convert price strings to numeric values
    products_df['Product_Price'] = products_df['Product_Price'].apply(
        lambda x: float(re.sub(r'[^\d.]', '', str(x))) if pd.notna(x) else 0
    )
    
    # Filter by active status
    products_df = products_df[products_df['Status'] == 1]
    
    # Apply category filter if provided
    if category and category != "":
        products_df = products_df[products_df['Category'] == category]
    
    # Apply search filter if provided
    if search and search != "":
        search_lower = search.lower()
        products_df = products_df[
            products_df['Product_Title'].str.lower().str.contains(search_lower) | 
            products_df['Product_Description'].str.lower().str.contains(search_lower)
        ]
    
    # Apply sorting
    if sort_by == 'price_low':
        products_df = products_df.sort_values('Product_Price')
    elif sort_by == 'price_high':
        products_df = products_df.sort_values('Product_Price', ascending=False)
    else:  # Default to newest (we don't have a date field, so we'll use Listing_ID as a proxy)
        products_df = products_df.sort_values('Listing_ID', ascending=False)
    
    # Calculate pagination
    total_products = len(products_df)
    total_pages = math.ceil(total_products / per_page)
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_products)
    
    # Get the products for the current page
    paginated_products = products_df.iloc[start_idx:end_idx]
    
    # Convert to list of dictionaries
    products = []
    for _, row in paginated_products.iterrows():
        product = row.to_dict()
        # Rename fields to match our template
        product['product_id'] = product['Listing_ID']
        product['product_name'] = product['Product_Name']
        product['description'] = product['Product_Description']
        product['price'] = product['Product_Price']
        product['stock_quantity'] = product['Quantity']
        products.append(product)
    
    # Create pagination info
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_products,
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None,
        'iter_pages': lambda: range(1, total_pages + 1) if total_pages > 0 else range(1, 2)
    }
    
    return products, pagination

def get_categories():
    """Get all product categories"""
    categories_df = load_csv("Categories.csv")
    
    # Clean up column names
    categories_df.columns = [col.strip() for col in categories_df.columns]
    
    # Create a list of unique categories
    unique_categories = categories_df['category_name'].unique()
    
    # Convert to list of dictionaries
    categories = []
    for category in unique_categories:
        categories.append({
            'category_id': category,
            'category_name': category
        })
    
    return categories

def get_user_orders(email, user_type):
    """Get orders for a user based on their type"""
    orders_df = load_csv("Orders.csv")
    
    # Clean up column names
    orders_df.columns = [col.strip() for col in orders_df.columns]
    
    if user_type == 'buyer':
        user_orders = orders_df[orders_df['Buyer_Email'] == email]
    elif user_type == 'seller':
        user_orders = orders_df[orders_df['Seller_Email'] == email]
    else:
        return []
    
    # Get product details for each order
    products_df = load_csv("Product_Listings.csv")
    products_df.columns = [col.strip() for col in products_df.columns]
    
    orders = []
    for _, row in user_orders.iterrows():
        order = row.to_dict()
        
        # Get product details
        product = products_df[products_df['Listing_ID'] == order['Listing_ID']]
        if not product.empty:
            product_data = product.iloc[0].to_dict()
            order['product_name'] = product_data['Product_Name']
            order['product_description'] = product_data['Product_Description']
        
        # Get review if available
        reviews_df = load_csv("Reviews.csv")
        reviews_df.columns = [col.strip() for col in reviews_df.columns]
        review = reviews_df[reviews_df['Order_ID'] == order['Order_ID']]
        if not review.empty:
            review_data = review.iloc[0].to_dict()
            order['rating'] = review_data['Rate']
            order['review'] = review_data['Review_Desc']
        
        orders.append(order)
    
    return orders

def get_helpdesk_requests(email):
    """Get requests assigned to a helpdesk staff member"""
    requests_df = load_csv("Requests.csv")
    
    # Clean up column names
    requests_df.columns = [col.strip() for col in requests_df.columns]
    
    # Get requests assigned to this helpdesk staff
    staff_requests = requests_df[requests_df['helpdesk_staff_email'] == email]
    
    return staff_requests.to_dict('records')

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    message = None
    success = False
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = get_user_by_email(email)
        
        if user and user.get('password') == password:  # In a real app, use proper password hashing
            session['user'] = {
                'id': user.get('user_id', email),
                'name': f"{user.get('first_name', '')} {user.get('last_name', '')}",
                'email': user['email'],
                'type': user['user_type'],
                'business_name': user.get('business_name', '')
            }
            return redirect(url_for('dashboard'))
        else:
            message = 'Invalid email or password'
    
    return render_template('login.html', message=message, success=success)

@app.route('/register', methods=['GET', 'POST'])
def register():
    message = None
    success = False
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        user_type = request.form.get('user_type')
        
        # Check if user already exists
        existing_user = get_user_by_email(email)
        if existing_user:
            message = 'Email already registered'
        else:
            # In a real application, you would add the user to the database
            # For now, just show a success message
            message = f'Account created for {name} as {user_type}'
            success = True
    
    return render_template('register.html', message=message, success=success)

@app.route('/products')
def products():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'newest')
    search = request.args.get('search', '')
    
    products_list, pagination = get_products(
        page=page, 
        per_page=9, 
        category=category, 
        sort_by=sort,
        search=search
    )
    
    categories = get_categories()
    
    return render_template(
        'products.html', 
        products=products_list, 
        categories=categories, 
        pagination=pagination,
        selected_category=category,
        sort=sort,
        search=search
    )

@app.route('/dashboard')
def dashboard():
    # Check if user is logged in
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = session['user']
    
    # Get additional user details
    user_details = get_user_by_email(user['email'])
    if user_details:
        # Update user session with additional details
        user.update({
            'business_name': user_details.get('business_name', ''),
            'balance': user_details.get('balance', 0),
            'position': user_details.get('position', '')
        })
        
        # Get address if available
        if 'address_id' in user_details:
            address = get_user_address(user_details['address_id'])
            if address:
                user['address'] = f"{address.get('street_num', '')} {address.get('street_name', '')}, {address.get('city', '')}, {address.get('state', '')} {address.get('zipcode', '')}"
    
    # Add last login time
    user['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Get user-specific data
    if user['type'] == 'buyer' or user['type'] == 'seller':
        user['orders'] = get_user_orders(user['email'], user['type'])
    elif user['type'] == 'helpdesk':
        user['requests'] = get_helpdesk_requests(user['email'])
    
    # Update session
    session['user'] = user
    
    return render_template('dashboard.html', user=user)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# Placeholder routes for dashboard links
@app.route('/orders')
def orders():
    # Check if user is logged in
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = session['user']
    user_orders = get_user_orders(user['email'], user['type'])
    
    return render_template('orders.html', orders=user_orders, user=user)

@app.route('/wishlist')
def wishlist():
    return "Wishlist Page"

@app.route('/manage_listings')
def manage_listings():
    # Check if user is logged in and is a seller
    if 'user' not in session or session['user']['type'] != 'seller':
        return redirect(url_for('login'))
    
    user = session['user']
    
    # Get seller's product listings
    products_df = load_csv("Product_Listings.csv")
    products_df.columns = [col.strip() for col in products_df.columns]
    
    seller_products = products_df[products_df['Seller_Email'] == user['email']]
    
    # Convert price strings to numeric values
    seller_products['Product_Price'] = seller_products['Product_Price'].apply(
        lambda x: float(re.sub(r'[^\d.]', '', str(x))) if pd.notna(x) else 0
    )
    
    # Convert to list of dictionaries
    listings = []
    for _, row in seller_products.iterrows():
        product = row.to_dict()
        # Rename fields to match our template
        product['product_id'] = product['Listing_ID']
        product['product_name'] = product['Product_Name']
        product['description'] = product['Product_Description']
        product['price'] = product['Product_Price']
        product['stock_quantity'] = product['Quantity']
        product['status'] = 'Active' if product['Status'] == 1 else 'Inactive'
        listings.append(product)
    
    return render_template('manage_listings.html', listings=listings, user=user)

@app.route('/manage_tickets')
def manage_tickets():
    # Check if user is logged in and is a helpdesk staff
    if 'user' not in session or session['user']['type'] != 'helpdesk':
        return redirect(url_for('login'))
    
    user = session['user']
    requests = get_helpdesk_requests(user['email'])
    
    return render_template('manage_tickets.html', requests=requests, user=user)

@app.route('/payment_methods')
def payment_methods():
    # Check if user is logged in and is a buyer
    if 'user' not in session or session['user']['type'] != 'buyer':
        return redirect(url_for('login'))
    
    user = session['user']
    
    # Get buyer's credit cards
    credit_cards_df = load_csv("Credit_Cards.csv")
    credit_cards_df.columns = [col.strip() for col in credit_cards_df.columns]
    
    buyer_cards = credit_cards_df[credit_cards_df['Owner_email'] == user['email']]
    
    # Convert to list of dictionaries
    cards = []
    for _, row in buyer_cards.iterrows():
        card = row.to_dict()
        # Mask card number for security
        card_num = card['credit_card_num']
        card['masked_number'] = f"**** **** **** {card_num[-4:]}"
        cards.append(card)
    
    return render_template('payment_methods.html', cards=cards, user=user)

@app.route('/sales_analytics')
def sales_analytics():
    # Check if user is logged in and is a seller
    if 'user' not in session or session['user']['type'] != 'seller':
        return redirect(url_for('login'))
    
    user = session['user']
    
    # Get seller's orders
    orders = get_user_orders(user['email'], 'seller')
    
    # Calculate total sales
    total_sales = sum(order['Payment'] for order in orders)
    
    # Calculate average order value
    avg_order_value = total_sales / len(orders) if orders else 0
    
    # Count total orders
    total_orders = len(orders)
    
    return render_template(
        'sales_analytics.html', 
        user=user, 
        orders=orders, 
        total_sales=total_sales, 
        avg_order_value=avg_order_value, 
        total_orders=total_orders
    )

@app.route('/knowledge_base')
def knowledge_base():
    return "Knowledge Base Page"

@app.route('/profile')
def profile():
    # Check if user is logged in
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = session['user']
    
    # Get full user details
    user_details = get_user_by_email(user['email'])
    
    # Get address if available
    address = {}
    if 'address_id' in user_details:
        address = get_user_address(user_details['address_id'])
    
    return render_template('profile.html', user=user, user_details=user_details, address=address)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    # Add to cart logic here
    # For now, just redirect back to products
    return redirect(url_for('products'))

@app.route('/buy_now/<int:product_id>')
def buy_now(product_id):
    # Buy now logic here
    return "Buy Now Page"

if __name__ == '__main__':
    app.run(debug=True)
