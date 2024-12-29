from flask import Flask, request, jsonify, session, render_template, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from flask_session import Session
import os
import random
import psycopg2
from psycopg2 import sql
import datetime
import jwt
from functools import wraps

app = Flask(__name__)
CORS(app)

SECRET_KEY='this is jwt'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

DB_HOST = 'localhost'
DB_NAME = 'postgres'
DB_USER = 'postgres'
DB_PASSWORD = '122333'

def get_db_connection():
    connection = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return connection

def create_users_table_if_not_exist():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

create_users_table_if_not_exist()

def create_tables_if_not_exist():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            discount_price REAL NOT NULL,
            sizes TEXT NOT NULL,
            description TEXT NOT NULL,
            image_paths TEXT NOT NULL  
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_reviews_table():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
      CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            Product_name TEXT NOT NULL,
            Rating Integer NOT NULL,
            Description TEXT NOT NULL,
            Category TEXT NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

create_tables_if_not_exist()
create_reviews_table()

@app.route('/signup', methods=['POST'])
def register():
    username = request.json.get('username')
    email = request.json.get('email')
    password = request.json.get('password')

    if not username or not email or not password:
        return jsonify({"error": "Check the entered details properly"}), 400

    hashed_password = generate_password_hash(password)
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO users(username, email, password) VALUES(%s, %s, %s);
        """, (username, email, hashed_password))
        connection.commit()
        cursor.close()
        connection.close()
        return jsonify({"message": "User registered successfully"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/login', methods=['POST'])
def signin():
    username = request.json.get('username')
    password = request.json.get('password')

    if not username or not password:
        return jsonify({"error": "Both username and password are required"}), 400

    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT password FROM users WHERE username=%s;
            """, (username,))
            user = cursor.fetchone()

        if not user or not check_password_hash(user[0], password):
            return jsonify({"error": "Invalid username or password"}), 401

        expiration_time = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        token = jwt.encode({
            'username': username,
            'exp': expiration_time,
            'iat': datetime.datetime.utcnow()
        }, SECRET_KEY, algorithm='HS256')

        return jsonify({"message": "User signed in successfully", "token": token}), 200

    except psycopg2.Error as db_err:  # Replace psycopg2 with your database library
        return jsonify({"error": "Database error occurred.", "details": str(db_err)}), 500
    except jwt.PyJWTError as jwt_err:
        return jsonify({"error": "Token generation error.", "details": str(jwt_err)}), 500
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred."}), 500
    finally:
        connection.close()
    
@app.route('/products', methods=['GET'])
def get_products():
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()

        # Check if products are found
        if not products:
            return jsonify({"error": "No products exist"}), 404
        
        # Format the result to match frontend expectations
        products_list = []
        for product in products:
            product_dict = {
                "id": product[0],  # Assuming 'id' is the first column
                "name": product[1],  # Assuming 'name' is the second column
                "price": product[2],  # Assuming 'price' is the third column
                "image" :product[6] if isinstance(product[6], list) else product[6].split(',')# Assuming 'image' is the sixth column (or adjust accordingly)
            }
            products_list.append(product_dict)

        return jsonify(products_list), 200
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500
    
@app.route('/create/review', methods=['POST'])
def create_review():
    try:
        data = request.get_json()  # Get JSON data from the request

        # Extract values from the JSON data
        username = data.get('username')
        product_name = data.get('product_name')
        rating = data.get('rating')
        description = data.get('description')
        category = data.get('category')

        # Check if all fields are provided
        if not all([username, product_name, rating, description, category]):
            return jsonify({"error": "All fields are required"}), 400
        connection = get_db_connection()
        cursor=connection.cursor()
        cursor.execute("SELECT username from users where username=%s",(username,))
        user=cursor.fetchall()
        if not user:
            return jsonify({"error":"You should be an existing user"}),400
        
        # Insert the review into the database
        
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO reviews (username, Product_name, Rating, Description, Category)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, product_name, rating, description, category))

        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({"message": "Review added successfully!"}), 201

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500


@app.route('/edit/review', methods=['PUT'])
def edit_review():
    try:
        data = request.get_json()
        username = data['username']
        product_name = data['product_name']
        rating = data['rating']
        description = data['description']
        category = data.get('category', '')
        token = request.headers.get('Authorization')
        if token:
            token = token.replace('Bearer ', '')  # Remove the 'Bearer ' prefix if it exists
        if not token:
            return jsonify({'error': 'Token is missing!'}), 401

            # Decode the token to get the user information (e.g., username)
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"],options={"verify_signature": False})
        user = data['username']
        
        # Check if the logged-in user is the same as the review author
        if username != user:
            return jsonify({"error": f'You can only delete your own reviews.'}), 403
        # Proceed with review update logic (Make sure you have the logic for updating the review in DB)
        # Update review in the database
        # For example: db.update_review(username, product_name, data)
        connection = get_db_connection()
        cursor = connection.cursor()

        # Update the review in the database
        cursor.execute("""
            UPDATE reviews
            SET rating = %s, description = %s, category = %s
            WHERE username = %s AND product_name = %s
        """, (rating, description, category, username, product_name))

        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({"message": "Review updated successfully!"}), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
@app.route('/delete/review', methods=['DELETE'])
def delete_review():
    try:
        data = request.get_json()
        username = data.get('username')
        product_name = data.get('id')
        token = request.headers.get('Authorization')
        if token:
            token = token.replace('Bearer ', '')  # Remove the 'Bearer ' prefix if it exists
        if not token:
            return jsonify({'error': 'Token is missing!'}), 401

            # Decode the token to get the user information (e.g., username)
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"],options={"verify_signature": False})
        user = data['username']
        
        # Check if the logged-in user is the same as the review author
        if username != user:
            return jsonify({"error": f'You can only delete your own reviews.'}), 403

        # Proceed with review delete logic (Make sure you have the logic for deleting the review in DB)
        # For example: db.delete_review(username, product_name)
        connection = get_db_connection()
        cursor = connection.cursor()

        # Delete the review from the database
        cursor.execute("""
            DELETE FROM reviews WHERE username = %s AND id = %s
        """, (username, product_name))

        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({"message": "Review deleted successfully!"}), 200

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    
@app.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # Fetch product details
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({"error": "Product not found"}), 404

        # Fetch reviews
        cursor.execute("SELECT id, username, product_name, rating, description, category FROM reviews WHERE product_name = %s", (product[1],))
        reviews = cursor.fetchall()
        connection.close()

        # Generate HTML content for images and reviews
        image_html = ''.join([f'<div><img src="/uploads/{image}" alt="{product[1]}" class="product-image" /></div>' for image in product[6].split(',')])
        reviews_html = """<div class='reviews-section'>
            <h2>Reviews</h2>
        """
        sum,count = 0,0
        if reviews:
            for review in reviews:
                sum += review[3]
                count+=1
                reviews_html += f"""<div class='review' id="review-{review[0]}">
                    <p><b>{review[1]}</b></p>
                    <p>Rating: {review[3]} / 5</p>
                    <p><small>{review[4]}</small></p>
                    <button onclick="showEditForm('{review[1]}', '{review[5]}', '{review[3]}', '{review[4]}')" style="background-color: #4CAF50; color: white; cursor: pointer; border-radius:15px; padding:5px; border:2px #4CAF50;">Edit</button>
                    <button onclick="deleteReview('{review[0]}','{review[1]}')" style="background-color: #4CAF50; color: white; cursor: pointer; border-radius:15px; padding:5px; border:2px #4CAF50;">Delete</button>
                </div>"""
        else:
            reviews_html += "<p>No reviews yet. Be the first to review this product!</p>"
        if sum==0 or count==0:
                reviews_html += f"""<br><button onclick="showReviewForm()" style="background-color: #4CAF50; color: white; cursor: pointer; border-radius:15px; padding:5px; border:2px #4CAF50;">Add Review</button></div>"""
        else:
            reviews_html += f"""Average Rating:{sum//count}<br><br><button onclick="showReviewForm()" style="background-color: #4CAF50; color: white; cursor: pointer; border-radius:15px; padding:5px; border:2px #4CAF50;">Add Review</button></div>"""

        # HTML template
        product_html = f"""
            <html>
            <head>
                <title>{product[1]}</title>
                <style>
                    body {{
                font-family: Arial, sans-serif;
                background-color: #f9f9f9;
                margin: 0;
                padding: 20px;
            }}
            h1 {{ text-align: center; color: #333; }}
            .product-container {{
                max-width: 1200px;
                margin: 0 auto;
                background-color: #fff;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
            .product-info {{
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                align-items: center;
            }}
            .prod-images {{
                max-width: 600px;
                width: 100%;
                margin-right: 30px;
            }}
            .product-image {{
                width: 100%;
                height: auto;
                max-height: 600px;
                border-radius: 8px;
            }}
            .carousel-dots {{
                text-align: center;
                padding-top: 10px;
            }}
            .dot {{
                height: 15px;
                width: 15px;
                margin: 0 4px;
                background-color: #bbb;
                border-radius: 50%;
                display: inline-block;
                transition: background-color 0.3s ease;
                cursor: pointer;
            }}
            .active-dot {{
                background-color: #717171;
            }}
            .product-details {{
                max-width: 500px;
                width: 100%;
                padding: 20px;
            }}
            .reviews-section {{
                margin-top: 30px;
            }}
            .review {{
                border-bottom: 1px solid #ddd;
                margin-bottom: 10px;
                padding-bottom: 10px;
            }}
            .review-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .review-content {{
                padding-top: 10px;
                color: #555;
                
            }}
            .review-form-container {{
                background-color: #fff;
                padding: 20px;
                width:50%;
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                margin-top: 20px;
            }}
            .review-form-container input,
            .review-form-container textarea,
            .review-form-container button {{
                width: 40%;
                padding: 10px;
                margin-bottom: 15px;
                border: 1px solid #ccc;
                border-radius: 8px;
            }}
            .review-form-container button {{
                background-color: #4CAF50;
                color: white;
                cursor: pointer;
            }}
            .review-form-container button:hover {{
                background-color: #45a049;
            }}
                </style>
            </head>
            <body>
                <div class="product-container">
            <div class="product-info">
                <div class="prod-images">
                    {image_html}
                    <div class="carousel-dots">
                        <!-- Dots for image carousel -->
                        <span class="dot" onclick="currentSlide(1)"></span>
                        <span class="dot" onclick="currentSlide(2)"></span>
                        <span class="dot" onclick="currentSlide(3)"></span>
                    </div>
                </div>
                <div class="product-details">
                    <h1>{product[1]}</h1>
                    <p class="price">Price: <strike style="color:red;">₹{product[2]}</strike> ₹{product[3]}</p>
                    <p><b>Sizes:</b><br> {product[4]}</p>
                    <p><b>Description:</b><br> {product[5]}</p>
                </div>
            </div>

            <div class="reviews-section">
                {reviews_html}
            </div>
        </div>

        <div id="review-form" class="review-form-container" style="display:none;">
            <form id="reviewForm" onsubmit="uploadReview(event)">
                <label for="username">Username:</label>
                <input type="text" name="username" required><br>
                <input type="hidden" name="product_name" value="{product[1]}">
                <label for="rating">Rating (1-5):</label>
                <input type="number" name="rating" min="1" max="5" required><br>
                <label for="description">Review:</label>
                <textarea name="description" required></textarea><br><br>
                <label for="category">Category</label>
                <input type="text" name="category"><br>
                <button type="submit">Submit Review</button>
            </form>
        </div>
                <script>
                    function showReviewForm() {{
                        document.getElementById('review-form').style.display = 'block';
                    }}

                    async function uploadReview(event) {{
                        event.preventDefault();
                        const reviewForm = document.getElementById('reviewForm');
                        const formData = new FormData(reviewForm);
                        const formObject = {{}}; 
                        formData.forEach((value, key) => {{
                            formObject[key] = value;
                        }});

                        try {{
                            const response = await fetch('/create/review', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json',
                                }},
                                body: JSON.stringify(formObject),
                            }});

                            const data = await response.json();
                            if (response.ok) {{
                                alert('Review submitted successfully!');
                                window.location.reload();
                            }} else {{
                                alert('Error: ' + data.error);
                            }}
                        }} catch (error) {{
                            console.error('Error submitting review:', error);
                        }}
                    }}
 let slideIndex = 1;
            showSlides(slideIndex);

            function currentSlide(n) {{
                showSlides(slideIndex = n);
            }}

            function showSlides(n) {{
                let i;
                let slides = document.getElementsByClassName("product-image");
                let dots = document.getElementsByClassName("dot");
                if (n > slides.length) {{
                    slideIndex = 1;
                }}
                if (n < 1) {{
                    slideIndex = slides.length;
                }}
                for (i = 0; i < slides.length; i++) {{
                    slides[i].style.display = "none";
                }}
                for (i = 0; i < dots.length; i++) {{
                    dots[i].className = dots[i].className.replace(" active-dot", "");
                }}
                slides[slideIndex - 1].style.display = "block";
                dots[slideIndex - 1].className += " active-dot";
            }}

                   async function showEditForm(username, productName, rating, description) {{
    const reviewForm = document.getElementById('reviewForm');
    document.getElementById('review-form').style.display = 'block';
    reviewForm.username.value = username;
    reviewForm.product_name.value = productName;
    reviewForm.rating.value = rating;
    reviewForm.description.value = description;

    reviewForm.onsubmit = async (event) => {{
        event.preventDefault();

        const formData = new FormData(reviewForm);
        const formObject = {{}};  
        formData.forEach((value, key) => {{
            formObject[key] = value;  
        }});

        // Assuming token is stored in localStorage or sessionStorage
        const token = localStorage.getItem('token');  // or sessionStorage.getItem('token')

        try {{
            const response = await fetch('/edit/review', {{
                method: 'PUT',
                headers: {{
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${{token}}`,  // Send the token in the Authorization header
            }},
                body: JSON.stringify(formObject),
            }});

            if (response.ok) {{
                alert('Review updated successfully!');
                window.location.reload();
            }} else {{
                const data = await response.json();
                alert('Error: ' + data.error);
            }}
        }} catch (error) {{
            console.error('Error updating review:', error);
        }}
    }};
}}

async function deleteReview(reviewId,user) {{
    if (!confirm('Are you sure you want to delete this review?')) return;

    // Assuming token is stored in localStorage or sessionStorage
    const token = localStorage.getItem('token');  // or sessionStorage.getItem('token')

    try {{
        const response = await fetch('/delete/review', {{
            method: 'DELETE',
            headers: {{
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${{token}}`,  // Send the token in the Authorization header
            }},
            body: JSON.stringify({{
                id: reviewId,
                username:user
            }}),
        }});

        if (response.ok) {{
            alert('Review deleted successfully!');
            document.querySelector(`#review-${{reviewId}}`).remove();
        }} else {{
            const data = await response.json();
            alert('Error: ' + data.error);
        }}
    }} catch (error) {{
        console.error('Error deleting review:', error);
        alert('A network error occurred. Please try again later.');
    }}
}}

                </script>
            </body>
            </html>
        """
        return product_html, 200

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500
    
@app.route('/add-product', methods=['POST'])
def add_product():
    try:
        data = request.form
        images = request.files.getlist('images')
        image_paths = []

        for image in images:
            filename = f"{random.randint(100000, 999999)}_{image.filename}"
            filepath = os.path.join('uploads', filename)
            image.save(filepath)
            image_paths.append(filename)

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO products (name, price, discount_price, sizes, description, image_paths) VALUES (%s, %s, %s, %s, %s, %s);",
            (data['name'], data['price'], data['discountPrice'], data['sizes'], data['description'], ','.join(image_paths))
        )
        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({'message': 'Product added successfully!'}), 201
    except Exception as e:
        return jsonify({'error':f"{e}"})
@app.route('/upload')
def upload():
    return render_template('upload.html')
@app.route('/login')
def login():
    return render_template('login.html')  
@app.route('/index')
def index1():
    return render_template('index.html')  

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(app.root_path, 'uploads'), filename)
    
@app.route('/')
def index():
    return render_template('home.html')

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)