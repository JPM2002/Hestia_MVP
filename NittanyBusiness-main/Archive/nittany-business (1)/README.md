# NittanyBusiness Marketplace

A marketplace platform built with Flask and HTML5/CSS, connected to CSV datasets.

## Project Structure

\`\`\`
nittanybusiness/
├── app.py                  # Main Flask application
├── templates/              # HTML templates
│   ├── login.html          # Login page
│   ├── register.html       # Registration page
│   ├── products.html       # Products listing page
│   ├── dashboard.html      # User dashboard
│   ├── orders.html         # Orders page
│   ├── manage_listings.html # Seller's product listings
│   ├── manage_tickets.html # Helpdesk support tickets
│   ├── payment_methods.html # Buyer's payment methods
│   ├── sales_analytics.html # Seller's sales analytics
│   └── profile.html        # User profile page
├── static/                 # Static assets
│   ├── css/
│   │   └── styles.css      # Global CSS styles
│   └── images/
│       └── placeholder.jpg # Placeholder image
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
\`\`\`

## Setup Instructions

1. Install required packages:
   \`\`\`
   pip install -r requirements.txt
   \`\`\`

2. Update the `DATASET_PATH` in app.py to point to your CSV files location.

3. Run the application:
   \`\`\`
   python app.py
   \`\`\`

4. Access the application at http://localhost:5000

## CSV Dataset Integration

The application reads data from the following CSV files:
- Users.csv - User account information
- Buyers.csv - Buyer-specific information
- Sellers.csv - Seller-specific information
- Helpdesk.csv - Helpdesk user information
- Product_Listings.csv - Product information
- Categories.csv - Product categories
- Orders.csv - Order information
- Reviews.csv - Product reviews
- Address.csv - Address information
- Zipcode_Info.csv - Zipcode information
- Credit_Cards.csv - Payment methods
- Requests.csv - Support requests

## Features

- User authentication (login/register)
- Product browsing with filtering, sorting, and pagination
- Role-based dashboard (Buyer, Seller, HelpDesk)
- Order management
- Product listing management for sellers
- Support ticket management for helpdesk staff
- Payment method management for buyers
- Sales analytics for sellers
- User profile management
- Responsive design using Bootstrap

## Integration with Flask

The templates use Jinja2 syntax for integration with Flask:
- Variables: `{{ variable_name }}`
- Control structures: `{% if condition %}...{% endif %}`
- URL generation: `{{ url_for('route_name') }}`

## Notes

This application uses pandas to read data from CSV files. In a production environment, you would typically use a database instead.
