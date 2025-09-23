# NittanyBusiness Marketplace

A dynamic online marketplace platform built with **Flask**, **SQLite**, and **Bootstrap**.

---

## 📁 Project Structure

```
NittanyBusiness/
├── NittanyBusinessDataset/             # CSV files to populate database
├── static/
│   ├── css/
│   │   └── styles.css                   # Main stylesheet
│   └── images/
│       └── placeholder.jpg              # Default product image
├── templates/
│   ├── cart.html                        # Shopping cart page
│   ├── checkout.html                    # Checkout and payment confirmation
│   ├── claim_requests.html              # Helpdesk: Staff claim incoming tickets
│   ├── createProductListing.html        # Seller creates a new product listing
│   ├── dashboard.html                   # Role-based user dashboard (Buyer, Seller, HelpDesk)
│   ├── deleteProductListing.html        # Seller deletes a product listing
│   ├── editProductListing.html          # Seller edits an existing product
│   ├── leave_review.html                # Buyers leave reviews for sellers
│   ├── login.html                       # User login page
│   ├── manage_helpdesk_accounts.html    # HelpDesk manages pending helpdesk account requests
│   ├── manage_requests.html             # HelpDesk handles support tickets
│   ├── navbar.html                      # Navbar included across pages
│   ├── orders.html                      # Buyers view their past orders
│   ├── payment_methods.html             # Buyers manage saved payment cards
│   ├── product_info.html                # Detailed product view
│   ├── productListings.html             # Seller's personal listings dashboard
│   ├── products.html                    # Public products grid with filters and search
│   ├── profile.html                     # User profile update page
│   ├── register.html                    # First step registration page (select role)
│   ├── registerBuyer.html               # Buyer-specific registration completion
│   ├── registerHelpDesk.html            # HelpDesk employee registration request
│   ├── registerSeller.html              # Seller-specific registration completion
│   ├── seller_reviews.html              # View reviews about a specific seller
│   ├── submit_request.html              # Buyers submit helpdesk support tickets
│   ├── thank_you.html                   # Order confirmation / thank you page
│   └── update_request.html               # HelpDesk updates ongoing support tickets
├── app.py                               # Main Flask backend (routes and logic)
├── initialize_db.py                     # Database initializer and seeder
├── requirements.txt                     # Python package dependencies
├── .gitignore                           # Git ignore list
└── database.db                          # SQLite database file
```

---

## 💄 Data Structure

**Database:** SQLite3  
**Schema:** Normalized structure based on real-world e-commerce systems.

| Table             | Purpose |
| ----------------- | ------- |
| Users             | Login authentication (buyers, sellers, helpdesk) |
| Helpdesk          | HelpDesk employee directory |
| Requests          | HelpDesk support tickets |
| Buyers            | Buyers' business information |
| Sellers           | Sellers' business information |
| CreditCards       | Buyers' saved payment methods |
| Address           | Address information |
| Zipcodes          | City/State data tied to addresses |
| Categories        | Product category hierarchy |
| ProductListings   | Product details and inventory |
| Orders            | Buyer purchase records |
| Reviews           | Ratings and feedback on sellers |

---

## 🚀 Features

- **Secure Authentication**  
  Login, registration, and session management.

- **Dynamic Product Listings**  
  View, filter by category, search, and filter by price range.

- **Role-Specific Dashboards**  
  - **Buyers**: Manage cart, orders, profile updates, and payment methods.
  - **Sellers**: Create, edit, delete listings and view seller reviews.
  - **HelpDesk**: Approve staff accounts, manage support requests.

- **Shopping Cart System**  
  Add, remove, and checkout products seamlessly.

- **Review System**  
  Buyers leave reviews for sellers after successful orders.

- **Support Ticket System**  
  HelpDesk resolves customer issues submitted via requests.

- **Responsive Frontend**  
  Mobile-ready Bootstrap 5 UI design.

---

## 🛠️ Setup Instructions

1. Install Python packages:
    ```bash
    pip install -r requirements.txt
    ```

2. Initialize the database:
    ```bash
    python initialize_db.py
    ```

3. Start the Flask server:
    ```bash
    python app.py
    ```

4. Access the application in your browser:
    ```
    http://localhost:5000
    ```

---

## 💡 Extra Features Implemented

- [x] Full shopping cart workflow
- [x] Dynamic price range filters
- [x] Leave and display seller reviews
- [x] Role-based dashboards and authorization
- [x] HelpDesk ticket claim and account management
- [x] Payment card management for buyers

---

## 📚 Citations

- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLite Documentation](https://www.sqlitetutorial.net/)
- [Bootstrap Framework](https://getbootstrap.com/)
- [MDN Web Docs (HTML/CSS)](https://developer.mozilla.org/)
- [Penn State CMPSC 431W Lectures — Prof. Wang-Chien Lee and TAs]


