import os
from flask import Flask, redirect, render_template, request, url_for, flash, session
from PIL import Image
from torchvision import transforms
import CNN
import numpy as np
import torch
import torch.nn.functional as F
import pandas as pd
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


disease_info = pd.read_csv('disease_info.csv' , encoding='cp1252')
supplement_info = pd.read_csv('supplement_info.csv',encoding='cp1252')

# Database Initialization
def init_db():
    conn = sqlite3.connect('scans.db')
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT UNIQUE, 
                  password TEXT)''')
    # Scans table with user_id
    c.execute('''CREATE TABLE IF NOT EXISTS scans
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER,
                  plant_name TEXT, 
                  disease_name TEXT, 
                  image_path TEXT, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Check if user_id column exists in scans table (for existing databases)
    c.execute("PRAGMA table_info(scans)")
    columns = [column[1] for column in c.fetchall()]
    if 'user_id' not in columns:
        c.execute("ALTER TABLE scans ADD COLUMN user_id INTEGER")
        
    conn.commit()
    conn.close()

init_db()

idx_to_classes = CNN.get_classes()
num_classes = len(idx_to_classes)

model = CNN.CNN(num_classes)    
model.load_state_dict(torch.load("plant_disease_model_1_latest.pt", map_location=torch.device('cpu')))
model.eval()

def prediction(image_path):
    try:
        image = Image.open(image_path).convert('RGB')
        transform = transforms.Compose([
            transforms.Resize(255),
            transforms.CenterCrop(224),
            transforms.ToTensor()
        ])
        input_data = transform(image)
        # Duplicate into a batch of 2 so BatchNorm can compute live statistics
        input_batch = torch.stack([input_data, input_data])
        model.train()  # use batch stats, not empty running stats
        with torch.no_grad():
            output = model(input_batch)
            probabilities = F.softmax(output, dim=1)
            confidence, index = torch.max(probabilities, dim=1)
        return index[0].item(), round(confidence[0].item() * 100, 2)
    except Exception as e:
        print(f"Prediction error: {e}")
        return None, None


app = Flask(__name__)
app.secret_key = "plantlens_secret_key_secure" # Secure secret key for sessions

@app.route('/')
def home_page():
    return render_template('home.html')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/hybridaction/zybTrackerStatisticsAction')
def zybTrackerStatisticsAction():
    return '', 204

@app.route('/contact')
def contact():
    return render_template('contact-us.html')

@app.route('/index')
def ai_engine_page():
    return render_template('index.html')

@app.route('/mobile-device')
def mobile_device_detected_page():
    return render_template('mobile-device.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = generate_password_hash(password)
        
        try:
            conn = sqlite3.connect('scans.db')
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            conn.close()
            flash("Registration successful! Please login.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists.")
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = sqlite3.connect('scans.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            flash(f"Welcome back, {username}!")
            return redirect(url_for('home_page'))
        else:
            flash("Invalid username or password.")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash("You have been logged out.")
    return redirect(url_for('home_page'))

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        if 'image' not in request.files:
            flash("No image part in the request.")
            return redirect(url_for('ai_engine_page'))
            
        image = request.files['image']
        
        if image.filename == '':
            flash("No image selected for uploading.")
            return redirect(url_for('ai_engine_page'))

        filename = image.filename
        file_path = os.path.join('static/uploads', filename)
        image.save(file_path)
        
        # Check if file is empty
        if os.path.getsize(file_path) == 0:
            flash("The uploaded image is empty. Please try another one.")
            return redirect(url_for('ai_engine_page'))

        print(file_path)
        pred, confidence = prediction(file_path)
        
        if pred is None:
            flash("Could not identify the image. It might be corrupted or in an unsupported format.")
            return redirect(url_for('ai_engine_page'))
            
        title = disease_info['disease_name'][pred]
        description =disease_info['description'][pred]
        prevent = disease_info['Possible Steps'][pred]
        image_url = disease_info['image_url'][pred]
        supplement_name = supplement_info['supplement name'][pred]
        supplement_image_url = supplement_info['supplement image'][pred]
        supplement_buy_link = supplement_info['buy link'][pred]

        # Save to database
        try:
            conn = sqlite3.connect('scans.db')
            c = conn.cursor()
            user_id = session.get('user_id') # Can be None if guest
            c.execute("INSERT INTO scans (user_id, plant_name, disease_name, image_path) VALUES (?, ?, ?, ?)", 
                      (user_id, title.split('___')[0].replace('_', ' '), title, file_path))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")

        return render_template('submit.html' , title = title , desc = description , prevent = prevent , 
                               image_url = image_url , pred = pred ,sname = supplement_name , simage = supplement_image_url , 
                               buy_link = supplement_buy_link, confidence = confidence, user_image = file_path)

@app.route('/market', methods=['GET', 'POST'])
def market():
    return render_template('market.html', supplement_image = list(supplement_info['supplement image']),
                           supplement_name = list(supplement_info['supplement name']), disease = list(disease_info['disease_name']), buy = list(supplement_info['buy link']))


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get("message", "").lower()
    
    # Simple logic for now. In a production app, you'd connect to Gemini/OpenAI
    response = "I'm your PlantLens assistant. I can help you identify plant diseases and give you care tips. Just upload a photo to get started!"
    
    if "hello" in user_msg or "hi" in user_msg:
        response = "Hello! ?? How can I help you with your plants today?"
    elif "how" in user_msg and "work" in user_msg:
        response = "It's easy! Go to the 'AI Engine' page, upload a photo of a plant leaf, and our Deep Learning model will diagnose any diseases instantly."
    elif "tomato" in user_msg:
        response = "Tomatoes are prone to diseases like Early Blight and Bacterial Spot. Make sure they have good airflow and avoid watering the leaves directly."
    elif "water" in user_msg:
        response = "Most plants prefer to be watered when the top inch of soil feels dry. Overwatering is a common cause of root rot!"
    elif "thank" in user_msg:
        response = "You're welcome! Happy gardening! ??"

    return {"response": response}

@app.route('/garden')
def garden():
    if 'user_id' not in session:
        flash("Please login to view your Digital Garden.")
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('scans.db')
    c = conn.cursor()
    c.execute("SELECT plant_name, disease_name, image_path, timestamp FROM scans WHERE user_id = ? ORDER BY timestamp DESC", (session['user_id'],))
    scans = c.fetchall()
    conn.close()
    return render_template('garden.html', scans=scans)

if __name__ == '__main__':
    app.run(debug=True)
