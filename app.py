import os
import re
from datetime import datetime, timedelta
import google.generativeai as genai
import markdown2
import numpy as np
import requests
import tensorflow as tf
from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask import (Flask, flash, jsonify, redirect, render_template, request,url_for)
from flask_bcrypt import Bcrypt
from flask_login import (LoginManager, UserMixin, current_user, login_required, login_user, logout_user)
from flask_pymongo import PyMongo
from PIL import Image
from tensorflow.keras.models import load_model
from werkzeug.utils import secure_filename
from functools import wraps

load_dotenv()

app = Flask(__name__)

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# CONFIGURATION
app.config["SECRET_KEY"] = os.urandom(24)
app.config["MONGO_URI"] = os.getenv("MONGO_URI")


# INITIALIZE EXTENSIONS & CUSTOM FILTERS
mongo = PyMongo(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

@app.template_filter('markdown')
def markdown_filter(s):
    return markdown2.markdown(s, extras=["fenced-code-blocks", "tables"])


# DATABASE COLLECTIONS
users_collection = mongo.db.users
diagnoses_collection = mongo.db.diagnoses
tasks_collection = mongo.db.tasks

# MODEL LOADING
MODEL_PATH = 'banana_disease_model.keras'
model = load_model(MODEL_PATH)
CLASS_NAMES = ['Anthracnose', 'Banana Fruit-Scarring Beetle', 'Banana Split Peel', 'Healthy Banana', 'Leaf Banana Black Sigatoka Disease', 'Leaf Banana Bract Mosaic Virus Disease', 'Leaf Banana Healthy Leaf', 'Leaf Banana Insect Pest Disease', 'Leaf Banana Moko Disease', 'Leaf Banana Natural Death', 'Leaf Banana Panama Disease', 'Leaf Banana Yellow Sigatoka Disease']
HEALTHY_CONDITIONS = ['healthy banana', 'leaf banana healthy leaf', 'leaf banana natural death']

# USER AUTHENTICATION
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.email = user_data["email"]
        self.name = user_data["name"]
        self.crop_location = user_data.get("crop_location", "")
        self.role = user_data.get("role", "user")

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({"_id": ObjectId(user_id)})
    return User(user_data) if user_data else None

# ADMIN ROUTES

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        
        user_role = getattr(current_user, 'role', 'user')
        if isinstance(user_role, tuple):
            user_role = user_role[0]
            
        if user_role != 'admin':
            flash('This page is for admins only.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/users', endpoint='admin_users')
@login_required
@admin_required
def admin_users():
    """Renders the User Management page."""
    all_users = list(users_collection.find().sort('name', 1))
    return render_template('admin_dashboard.html', users=all_users)

@app.route('/admin/add_user', methods=['POST'], endpoint='admin_add_user')
@login_required
@admin_required
def admin_add_user():
    """Handles the form submission for adding a new user."""
    try:
        email = request.form.get('email')
        if users_collection.find_one({'email': email}):
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('admin_users'))

        user_data = {
            "name": request.form.get('name'),
            "email": email,
            "password": bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8'),
            "country": request.form.get('country'),
            "crop_location": request.form.get('crop_location'),
            "address": request.form.get('address', ''),
            "role": request.form.get('role', 'user'),
        }
        users_collection.insert_one(user_data)
        flash('User created successfully!', 'success')
    except Exception as e:
        flash(f'An error occurred: {e}', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/update_user/<user_id>', methods=['POST'], endpoint='admin_update_user')
@login_required
@admin_required
def admin_update_user(user_id):
    """Handles the form submission for updating an existing user."""
    try:
        update_data = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'role': request.form.get('role'),
            'country': request.form.get('country'),
            'crop_location': request.form.get('crop_location'),
            'address': request.form.get('address', ''),
        }
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if user['email'] != update_data['email'] and users_collection.find_one({'email': update_data['email']}):
            flash('That email address is already in use by another account.', 'error')
            return redirect(url_for('admin_users'))
        
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
        flash('User updated successfully!', 'success')
    except Exception as e:
        flash(f'An error occurred: {e}', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<user_id>', methods=['POST'], endpoint='admin_delete_user')
@login_required
@admin_required
def admin_delete_user(user_id):
    """Handles the deletion of a user."""
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))

    try:
        users_collection.delete_one({'_id': ObjectId(user_id)})
        diagnoses_collection.delete_many({'user_id': ObjectId(user_id)})
        tasks_collection.delete_many({'user_id': ObjectId(user_id)})
        
        flash('User and all their associated data have been deleted.', 'success')
    except Exception as e:
        flash(f'An error occurred: {e}', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/feedback', endpoint='admin_feedback')
@login_required
@admin_required
def admin_feedback():
    """Renders the User Feedback page (both accurate and inaccurate)."""
    feedback_diagnoses = list(diagnoses_collection.find({
        "$or": [
            {'reported_as_inaccurate': True}, 
            {'confirmed_accurate': True}
        ]
    }).sort('timestamp', -1))
    
    return render_template('admin_feedback.html', diagnoses=feedback_diagnoses)


# AI & Weather API 
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

def predict_disease(image_path):
    img = Image.open(image_path).resize((256, 256))
    img_array = tf.keras.preprocessing.image.img_to_array(img)
    img_array = tf.expand_dims(img_array, 0)
    predictions = model.predict(img_array)
    score = tf.nn.softmax(predictions[0])
    predicted_class = CLASS_NAMES[np.argmax(score)]
    confidence = (100 * np.max(score))
    return predicted_class, confidence

def get_smart_suggestions(disease_name):
    if disease_name.strip().lower() in HEALTHY_CONDITIONS:
        return {
            "description": "This plant appears to be healthy.",
            "treatment": "No treatment is necessary. Continue to monitor its condition and provide proper care.",
            "prevention": "Maintain a regular watering schedule and ensure the plant gets adequate sunlight.",
            "schedule": []
        }

    prompt = f"""
    Act as a plant pathologist for a banana plant diagnosed with '{disease_name}'.
    Provide the following information clearly. Use markdown headings for each section.

    ### Description
    (Provide a brief, easy-to-understand description of this disease.)

    ### Treatment Plan
    (Provide a step-by-step treatment plan. Be specific.)

    ### Prevention
    (Provide a list of preventive measures to avoid this in the future.)

    ### Generated Treatment Schedule
    (Based on your treatment plan, create a detailed, actionable schedule for the next 4-6 weeks in a Markdown table.
    Use these exact column headers: | Date (Relative) | Task | Details |
    For the date, use relative terms like "Today", "Tomorrow", "Day 7 (Week 1)", "Day 14 (Week 2)", "Continuous".
    Each row should represent a single, clear action. Do not use any asterisks or other markdown formatting inside the table cells.)
    """
    try:
        response = gemini_model.generate_content(prompt)
        text = response.text
        
        description = re.search(r"### Description\s*\n(.*?)\n### Treatment Plan", text, re.DOTALL)
        treatment = re.search(r"### Treatment Plan\s*\n(.*?)\n### Prevention", text, re.DOTALL)
        prevention = re.search(r"### Prevention\s*\n(.*?)\n### Generated Treatment Schedule", text, re.DOTALL)
        
        schedule_text = re.search(r"### Generated Treatment Schedule\s*\n(.*?)(?:\n###|$)", text, re.DOTALL)
        schedule = []
        if schedule_text:
            rows = re.findall(r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|", schedule_text.group(1))
            for row in rows:
                date_text = row[0].strip().replace('**', '')
                task_text = row[1].strip().replace('**', '')
                details_text = row[2].strip().replace('**', '')

                if "Date (Relative)" not in date_text and "---" not in date_text:
                    schedule.append({
                        "date": date_text,
                        "task": task_text,
                        "details": details_text
                    })
        
        return {
            "description": description.group(1).strip() if description else "N/A",
            "treatment": treatment.group(1).strip() if treatment else "N/A",
            "prevention": prevention.group(1).strip() if prevention else "N/A",
            "schedule": schedule
        }
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return {"description": "Error fetching details.", "treatment": "", "prevention": "", "schedule": []}

def parse_relative_date(relative_date_str):
    """Converts strings like 'Today', 'Day 7 (Week 1)' to datetime objects."""
    today = datetime.now().date()
    relative_date_str = relative_date_str.lower()
    
    if "today" in relative_date_str:
        return datetime.combine(today, datetime.min.time())
    if "tomorrow" in relative_date_str:
        return datetime.combine(today + timedelta(days=1), datetime.min.time())
    
    match = re.search(r"day (\d+)", relative_date_str)
    if match:
        days_from_now = int(match.group(1)) - 1
        return datetime.combine(today + timedelta(days=days_from_now), datetime.min.time())
        
    match = re.search(r"in (\d+) days", relative_date_str)
    if match:
        days = int(match.group(1))
        return datetime.combine(today + timedelta(days=days), datetime.min.time())
    
    return datetime.combine(today, datetime.min.time())

def get_weather_forecast(location):
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key or not location:
        return None

    try:
        current_url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
        response_current = requests.get(current_url)
        response_current.raise_for_status()
        data_current = response_current.json()

        current_weather = {
            "location": data_current["name"],
            "condition": data_current["weather"][0]["main"],
            "temp": data_current["main"]["temp"],
            "humidity": data_current["main"]["humidity"],
            "icon": data_current["weather"][0]["icon"],
            "feels_like": data_current["main"]["feels_like"],
            "wind_kph": round(data_current["wind"]["speed"] * 3.6) 
        }

        forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={location}&appid={api_key}&units=metric"
        response_forecast = requests.get(forecast_url)
        response_forecast.raise_for_status()
        data_forecast = response_forecast.json()

        tomorrow_forecast_data = None
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        for item in data_forecast["list"]:
            if tomorrow_date in item["dt_txt"] and "12:00:00" in item["dt_txt"]:
                tomorrow_forecast_data = item
                break
        
        if not tomorrow_forecast_data:
            for item in data_forecast["list"]:
                if tomorrow_date in item["dt_txt"]:
                    tomorrow_forecast_data = item
                    break

        tomorrow_forecast = {
            "condition": tomorrow_forecast_data["weather"][0]["main"],
            "icon": tomorrow_forecast_data["weather"][0]["icon"],
            "maxtemp": tomorrow_forecast_data["main"]["temp_max"],
            "mintemp": tomorrow_forecast_data["main"]["temp_min"],
            "chance_of_rain": int(tomorrow_forecast_data.get("pop", 0) * 100) 
        }

        return {
            "current": current_weather,
            "forecast": tomorrow_forecast
        }

    except requests.exceptions.RequestException as e:
        print(f"OpenWeatherMap API Error: {e}")
        return None

def get_agri_innovations():
    prompt = """
    Act as an agricultural journalist. Provide a single, recent innovation or news item about banana cultivation.
    Format your response with these exact markdown headings:

    ### Headline
    (A short, engaging title for the news item.)

    ### Summary
    (A brief, one-paragraph summary of the news.)
    """
    try:
        response = gemini_model.generate_content(prompt)
        text = response.text
        
        headline = re.search(r"### Headline\s*\n(.*?)\n### Summary", text, re.DOTALL)
        summary = re.search(r"### Summary\s*\n(.*)", text, re.DOTALL)
        
        if headline and summary:
            return {
                "headline": headline.group(1).strip().replace("**", ""),
                "summary": summary.group(1).strip()
            }
        else:
            return {"headline": "Latest News", "summary": response.text}

    except Exception as e:
        print(f"Gemini API Error (Innovations): {e}")
        return {"headline": "Insights Unavailable", "summary": "AI-powered insights are currently being updated. Please check back soon."}

def get_weather_advice(weather_data):
    if not weather_data:
        return "Weather data unavailable to generate advice."
        
    prompt = f"""
    Given the current weather for a banana farmer:
    - Condition: {weather_data['condition']}
    - Temperature: {weather_data['temp']}°C
    - Humidity: {weather_data['humidity']}%
    - Wind Speed: {weather_data['wind_kph']} kph

    Provide a very short, one-sentence piece of actionable advice.
    Start directly with the advice. Example: High humidity increases fungal risk, so ensure good air circulation.
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error (Weather Advice): {e}")
        return "Could not generate weather advice at this time."

def get_comparison_advice(old_diagnosis, new_diagnosis):
    """Generates a comparison summary between two diagnoses."""
    prompt = f"""
    Act as a plant pathologist analyzing a follow-up diagnosis.
    - The original diagnosis was: '{old_diagnosis['disease_name']}' with {old_diagnosis['confidence']} confidence.
    - The new diagnosis, after treatment, is: '{new_diagnosis['disease_name']}' with {new_diagnosis['confidence']} confidence.

    Provide a concise, one-paragraph summary of the treatment progress.
    - If the plant is now healthy, state this clearly and congratulate the user.
    - If the disease is the same but confidence is lower, mention the slight improvement.
    - If there is no change or it's worse, state this and suggest reviewing the treatment plan.
    Start directly with the analysis.
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error (Comparison): {e}")
        return "Could not generate a comparison at this time."

# Signup Route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_data = {
            "name": request.form.get('name'),
            "email": request.form.get('email'),
            "password": bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8'),
            "country": request.form.get('country'),
            "address": request.form.get('address'),
            "crop_location": request.form.get('crop_location'),
            "role": "user",
        }
        if users_collection.find_one({'email': user_data['email']}):
            flash('Email already exists.', 'error')
            return redirect(url_for('register'))
        
        users_collection.insert_one(user_data)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_data = users_collection.find_one({'email': email})
        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# CORE APPLICATION ROUTES
@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    recent_diagnoses = list(diagnoses_collection.find(
        {'user_id': ObjectId(current_user.id)}
    ).sort('timestamp', -1).limit(3))

    today = datetime.now().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    todays_tasks = list(tasks_collection.find({
        'user_id': ObjectId(current_user.id),
        'due_date': {'$gte': start_of_day, '$lt': end_of_day}
    }).sort('due_date', 1))

    weather = get_weather_forecast(current_user.crop_location)
    innovations = get_agri_innovations()
    
    weather_advice = get_weather_advice(weather['current'] if weather else None)

    return render_template('dashboard.html', 
                           diagnoses=recent_diagnoses, 
                           tasks=todays_tasks, 
                           weather=weather, 
                           innovations=innovations,
                           weather_advice=weather_advice)

@app.route('/diagnose', methods=['GET', 'POST'])
@login_required
def diagnose():
    if request.method == 'POST':
        plant_identifier = request.form.get('plant_identifier', 'My Plant')
        parent_diagnosis_id = request.form.get('parent_diagnosis_id') 

        if 'file' not in request.files or request.files['file'].filename == '':
            flash('No file selected.', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join('static', 'uploads', filename)
            file.save(filepath)
            
            db_image_path = os.path.join('uploads', filename).replace("\\", "/")
            disease_name, confidence = predict_disease(filepath)
            suggestions = get_smart_suggestions(disease_name)
            
            new_diagnosis = {
                'user_id': ObjectId(current_user.id),
                'plant_identifier': plant_identifier,
                'disease_name': disease_name,
                'confidence': f"{confidence:.2f}%",
                'suggestions': suggestions,
                'image_path': db_image_path,
                'timestamp': datetime.now()
            }
            if parent_diagnosis_id:
                new_diagnosis['parent_diagnosis_id'] = ObjectId(parent_diagnosis_id)

            result = diagnoses_collection.insert_one(new_diagnosis)
            
            if parent_diagnosis_id:
                return redirect(url_for('follow_up_results', new_diagnosis_id=result.inserted_id))
            else:
                return redirect(url_for('results', diagnosis_id=result.inserted_id))
            
    return render_template('diagnose.html')

@app.route('/results/<diagnosis_id>')
@login_required
def results(diagnosis_id):
    diagnosis = diagnoses_collection.find_one_or_404({'_id': ObjectId(diagnosis_id)})
    if diagnosis['user_id'] != ObjectId(current_user.id):
        user_role = getattr(current_user, 'role', 'user')
        if isinstance(user_role, tuple):
            user_role = user_role[0]
        if user_role != 'admin':
            return "Unauthorized", 403
            
    return render_template('results.html', diagnosis=diagnosis)

@app.route('/logbook')
@login_required
def logbook():
    user_diagnoses = list(diagnoses_collection.find(
        {'user_id': ObjectId(current_user.id)}
    ).sort('timestamp', -1))
    return render_template('logbook.html', diagnoses=user_diagnoses)

@app.route('/delete_diagnosis/<diagnosis_id>', methods=['POST'])
@login_required
def delete_diagnosis(diagnosis_id):
    diagnosis = diagnoses_collection.find_one_or_404({
        '_id': ObjectId(diagnosis_id),
        'user_id': ObjectId(current_user.id)
    })

    if diagnosis and 'image_path' in diagnosis:
        try:
            filepath = os.path.join('static', diagnosis['image_path'])
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting image file {filepath}: {e}")
    
    tasks_collection.delete_many({'diagnosis_id': ObjectId(diagnosis_id)})
    diagnoses_collection.delete_one({'_id': ObjectId(diagnosis_id)})
    
    flash('Logbook entry and all associated tasks have been deleted.', 'success')
    return redirect(url_for('logbook'))

@app.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html')

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        update_data = {
            'name': request.form.get('name'),
            'country': request.form.get('country'),
            'address': request.form.get('address'),
            'crop_location': request.form.get('crop_location')
        }
        
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password:
            if new_password == confirm_password:
                update_data['password'] = bcrypt.generate_password_hash(new_password).decode('utf-8')
            else:
                flash('New passwords do not match. Please try again.', 'error')
                user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})
                return render_template('account.html', user=user_data)

        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': update_data}
        )
        
        flash('Your account has been updated successfully!', 'success')
        return redirect(url_for('account'))

    user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})
    return render_template('account.html', user=user_data)


# API ROUTES for JavaScript
@app.route('/api/toggle_task/<task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = tasks_collection.find_one({'_id': ObjectId(task_id), 'user_id': ObjectId(current_user.id)})
    if task:
        new_status = not task.get('is_completed', False)
        tasks_collection.update_one({'_id': ObjectId(task_id)}, {'$set': {'is_completed': new_status}})
        return jsonify({'status': 'success', 'is_completed': new_status})
    return jsonify({'status': 'error', 'message': 'Task not found'}), 404

@app.route('/api/delete_task/<task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    result = tasks_collection.delete_one({
        '_id': ObjectId(task_id),
        'user_id': ObjectId(current_user.id)
    })
    if result.deleted_count == 1:
        return jsonify({'status': 'success', 'message': 'Task deleted successfully.'})
    else:
        return jsonify({'status': 'error', 'message': 'Task not found or permission denied.'}), 404

@app.route('/api/calendar_events')
@login_required
def api_calendar_events():
    user_tasks = tasks_collection.find({'user_id': ObjectId(current_user.id)})
    events = []
    for task in user_tasks:
        events.append({
            'id': str(task['_id']),
            'title': task['description'],
            'start': task['due_date'].isoformat(),
            'allDay': task.get('is_all_day', False)
        })
    return jsonify(events)

@app.route('/api/add_schedule_to_calendar', methods=['POST'])
@login_required
def add_schedule_to_calendar():
    data = request.json
    tasks = data.get('tasks')
    diagnosis_id = data.get('diagnosis_id')

    if not tasks or not diagnosis_id:
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    diagnosis = diagnoses_collection.find_one({'_id': ObjectId(diagnosis_id)})
    plant_identifier = diagnosis.get('plant_identifier', 'Plant')

    tasks_to_insert = []
    all_day_keywords = ['monitor', 'inspect', 'check', 'sanitation', 'assess']
    day_time_tracker = {}

    for task in tasks:
        due_date = parse_relative_date(task['date'])
        task_lower = task['task'].lower()
        
        is_all_day = any(keyword in task_lower for keyword in all_day_keywords)
        
        if not is_all_day:
            date_key = due_date.date()
            if date_key in day_time_tracker:
                last_time = day_time_tracker[date_key]
                new_time = last_time + timedelta(minutes=15)
                due_date = new_time
            else:
                due_date = due_date.replace(hour=9, minute=0, second=0, microsecond=0)
            day_time_tracker[date_key] = due_date

        tasks_to_insert.append({
            'user_id': ObjectId(current_user.id),
            'diagnosis_id': ObjectId(diagnosis_id),
            'description': f"{plant_identifier}: {task['task']}",
            'details': task['details'],
            'due_date': due_date,
            'is_completed': False,
            'is_all_day': is_all_day,
            'created_at': datetime.now()
        })
    
    if tasks_to_insert:
        tasks_collection.insert_many(tasks_to_insert)

    return jsonify({'status': 'success', 'message': 'Treatment schedule has been added to your calendar!'})

@app.route('/api/schedule_follow_up/<diagnosis_id>', methods=['POST'])
@login_required
def schedule_follow_up(diagnosis_id):
    """Creates a follow-up task in the calendar for 7 days from now."""
    diagnosis = diagnoses_collection.find_one_or_404({'_id': ObjectId(diagnosis_id)})
    plant_identifier = diagnosis.get('plant_identifier', 'Plant')
    
    follow_up_date = datetime.now() + timedelta(days=7)
    
    new_task = {
        'user_id': ObjectId(current_user.id),
        'diagnosis_id': ObjectId(diagnosis_id),
        'description': f"Follow-up for: {plant_identifier}",
        'details': "Upload a new photo to check treatment progress.",
        'due_date': follow_up_date,
        'is_completed': False,
        'is_all_day': True,
        'is_follow_up': True, 
        'created_at': datetime.now()
    }
    tasks_collection.insert_one(new_task)
    return jsonify({'status': 'success', 'message': 'Follow-up task has been scheduled for 7 days from now!'})

@app.route('/api/confirm_diagnosis/<diagnosis_id>', methods=['POST'])
@login_required
def confirm_diagnosis(diagnosis_id):
    """API endpoint for a user to confirm an accurate diagnosis."""
    result = diagnoses_collection.update_one(
        {'_id': ObjectId(diagnosis_id), 'user_id': ObjectId(current_user.id)},
        {'$set': {
            'confirmed_accurate': True,
            'reported_as_inaccurate': False, # Ensure it's not marked as inaccurate
            'confirm_timestamp': datetime.now()
        }}
    )
    
    if result.matched_count == 1:
        return jsonify({'status': 'success', 'message': 'Thank you for your feedback!'})
    else:
        return jsonify({'status': 'error', 'message': 'Diagnosis not found or permission denied.'}), 404

@app.route('/api/report_diagnosis/<diagnosis_id>', methods=['POST'])
@login_required
def report_diagnosis(diagnosis_id):
    """API endpoint for a user to report an inaccurate diagnosis."""
    data = request.json
    reason = data.get('reason')
    
    if not reason:
        return jsonify({'status': 'error', 'message': 'A reason is required to submit a report.'}), 400
        
    result = diagnoses_collection.update_one(
        {'_id': ObjectId(diagnosis_id), 'user_id': ObjectId(current_user.id)},
        {'$set': {
            'reported_as_inaccurate': True,
            'confirmed_accurate': False, # Ensure it's not marked as accurate
            'report_reason': reason,
            'report_timestamp': datetime.now()
        }}
    )
    
    if result.matched_count == 1:
        return jsonify({'status': 'success', 'message': 'Report submitted successfully. An admin will review this.'})
    else:
        return jsonify({'status': 'error', 'message': 'Diagnosis not found or permission denied.'}), 404

# ADMIN CHART DATA API
@app.route('/api/admin/chart_data', endpoint='admin_chart_data')
@login_required
@admin_required
def admin_chart_data():
    try:
        # Feedback Pie Chart 
        confirmed_count = diagnoses_collection.count_documents({'confirmed_accurate': True})
        reported_count = diagnoses_collection.count_documents({'reported_as_inaccurate': True})
        
        # Inaccuracy Bar Chart 
        pipeline = [
            {"$match": {"reported_as_inaccurate": True}},
            {"$group": {"_id": "$disease_name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        inaccurate_data = list(diagnoses_collection.aggregate(pipeline))
        
        bar_labels = [d['_id'] for d in inaccurate_data]
        bar_counts = [d['count'] for d in inaccurate_data]

        return jsonify({
            'pieData': {
                'labels': ['Confirmed Accurate', 'Reported Inaccurate'],
                'counts': [confirmed_count, reported_count]
            },
            'barData': {
                'labels': bar_labels,
                'counts': bar_counts
            }
        })
    except Exception as e:
        print(f"Error fetching chart data: {e}")
        return jsonify({"error": str(e)}), 500


# FOLLOW-UP ROUTES
@app.route('/follow_up/<original_diagnosis_id>')
@login_required
def follow_up_diagnose(original_diagnosis_id):
    """Page for uploading a follow-up image for a specific diagnosis."""
    original_diagnosis = diagnoses_collection.find_one_or_404({'_id': ObjectId(original_diagnosis_id)})
    return render_template('follow_up_diagnose.html', diagnosis=original_diagnosis)

@app.route('/follow_up_results/<new_diagnosis_id>')
@login_required
def follow_up_results(new_diagnosis_id):
    """Displays the comparison between the original and new diagnosis."""
    new_diagnosis = diagnoses_collection.find_one_or_404({'_id': ObjectId(new_diagnosis_id)})
    
    if 'parent_diagnosis_id' not in new_diagnosis:
        return "Error: This is not a follow-up diagnosis.", 404
        
    original_diagnosis = diagnoses_collection.find_one_or_404({'_id': new_diagnosis['parent_diagnosis_id']})
    
    comparison_summary = get_comparison_advice(original_diagnosis, new_diagnosis)
    
    return render_template('follow_up_results.html', 
                           original=original_diagnosis, 
                           new=new_diagnosis, 
                           summary=comparison_summary)

if __name__ == '__main__':
    if not os.path.exists('static/uploads'):
        os.makedirs('static/uploads')

    app.run(debug=True)
