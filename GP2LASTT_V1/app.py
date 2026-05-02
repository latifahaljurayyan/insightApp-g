import mysql.connector
import os
import json
from datetime import datetime, date
import re
import joblib
import nltk
import numpy as np
import pandas as pd
from nltk.corpus import stopwords, wordnet
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from nltk import pos_tag
from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)
from collections import Counter
from werkzeug.utils import secure_filename
import smtplib
import random
from email.mime.text import MIMEText

GMAIL_USER = 'nora.aljarboua@gmail.com'
GMAIL_PASS = 'fpnl lvjf kfqr equo'
reset_codes = {}



nltk.download('punkt',     quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('wordnet',   quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)
nltk.download('omw-1.4', quiet=True)


stop_words = set(stopwords.words('english'))
negation_words = {"not", "no", "nor", "never"}
stop_words = stop_words - negation_words
lemmatizer = WordNetLemmatizer()

def remove_stopwords(tokens):
    return [word for word in tokens if word not in stop_words]

def get_wordnet_pos(tag):
    if tag.startswith('J'):
        return wordnet.ADJ
    elif tag.startswith('V'):
        return wordnet.VERB
    elif tag.startswith('N'):
        return wordnet.NOUN
    elif tag.startswith('R'):
        return wordnet.ADV
    else:
        return wordnet.NOUN

def lemmatize_tokens(tokens):
    pos_tags = pos_tag(tokens)
    return [
        lemmatizer.lemmatize(word, get_wordnet_pos(tag))
        for word, tag in pos_tags
    ]


def preprocess(text: str) -> str:
    text = re.sub(r"http\S+", "", str(text))
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = text.lower()
    tokens = word_tokenize(text)
    tokens = remove_stopwords(tokens)
    tokens = lemmatize_tokens(tokens)
    return " ".join(tokens)


LABEL_MAP = {
    'positive': 'Positive', 'pos': 'Positive', '2': 'Positive',
    'negative': 'Negative', 'neg': 'Negative', '0': 'Negative',
    'neutral':  'Neutral',  'neu': 'Neutral',  '1': 'Neutral',
}

def normalize_label(label) -> str:
    s = str(label).strip()
    if s in ('Positive', 'Negative', 'Neutral'):
        return s
    return LABEL_MAP.get(s.lower(), s.capitalize())


def generate_recommendations(neg_insights: dict, neg_pct: float) -> list:
    recs = []

    sorted_topics = sorted(
        neg_insights.items(),
        key=lambda x: x[1]['pct'],
        reverse=True
    )

    for topic, info in sorted_topics[:4]:
        pct = info['pct']

        if pct < 5:
            continue

        priority = (
            'high' if pct >= 30 else
            'medium' if pct >= 15 else
            'low'
        )

        recs.append({
            'topic': topic,
            'pct': pct,
            'text': RECOMMENDATION_TEMPLATES.get(topic, f'Address {topic} issues'),
            'priority': priority,
        })

    if neg_pct >= 30:
        recs.append({
            'topic': 'General',
            'pct': neg_pct,
            'text': 'Overall negative sentiment is high — conduct a comprehensive app review and user-feedback session.',
            'priority': 'high',
        })

    return recs


app = Flask(__name__)
app.secret_key = 'appinsight-secret-key-2026'

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

model      = joblib.load(os.path.join(BASE_DIR, 'sentiment_model.pkl'))
vectorizer = joblib.load(os.path.join(BASE_DIR, 'tfidf_vectorizer.pkl'))

MODEL_VERSION = 'v2.1'



#  DB CONNECTION

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="appinsight"
    )

#  Keyword Extraction 
def extract_keywords(reviews):
    all_words = []
    for text in reviews:
        cleaned = preprocess(text)
        words = cleaned.split()
        all_words.extend(words)
    word_counts = Counter(all_words)
    return [word for word, count in word_counts.most_common(20) if len(word) > 2]


#  Sentiment Analysis and Topic Insights  

def predict_texts(texts):
    cleaned = [preprocess(t) for t in texts]
    X       = vectorizer.transform(cleaned)
    labels  = [normalize_label(l) for l in model.predict(X).tolist()]
    print("Predictions types:", set(labels))
    try:
        scores = model.decision_function(X)
        if scores.ndim == 1:
            scores = scores.reshape(-1, 1)
        exp_s  = np.exp(scores - scores.max(axis=1, keepdims=True))
        proba  = exp_s / exp_s.sum(axis=1, keepdims=True)
        confs  = proba.max(axis=1).tolist()
    except Exception:
        confs = [None] * len(labels)
    return labels, confs


def expected_sentiment(rating):
    try:
        r = float(rating)
    except (ValueError, TypeError):
        return None
    if r <= 2:  return 'Negative'
    if r == 3:  return 'Neutral'
    return 'Positive'


TOPIC_KEYWORDS = {
    'Shipping & Delivery':    ['ship', 'deliver', 'package', 'courier', 'track', 'arriv', 'dispatch', 'transit', 'late'],
    'Login & Authentication': ['login', 'signin', 'sign in', 'password', 'auth', 'account', 'access', 'lock', 'credential'],
    'Payment & Billing':      ['pay', 'payment', 'charge', 'bill', 'refund', 'transaction', 'credit', 'card', 'invoice'],
    'Performance & Speed':    ['slow', 'lag', 'crash', 'freeze', 'hang', 'load', 'speed', 'unresponsive', 'stuck', 'performance'],
    'Customer Support':       ['support', 'customer service', 'help', 'response', 'staff', 'team', 'contact', 'ticket'],
    'UI & Design':            ['design', 'interface', 'confus', 'difficult', 'navigat', 'button', 'layout', 'screen'],
    'Features':               ['feature', 'function', 'option', 'update', 'useful', 'tool', 'capabilit', 'miss'],
    'Ease of Use':            ['easy', 'simple', 'intuitive', 'friend', 'convenient', 'smooth', 'straightforward'],
}

RECOMMENDATION_TEMPLATES = {
    'Shipping & Delivery':    'Improve shipping speed and delivery tracking to reduce negative reviews',
    'Login & Authentication': 'Enhance login stability and fix authentication issues for better user access',
    'Payment & Billing':      'Resolve payment processing issues and improve billing transparency',
    'Performance & Speed':    'Optimize app performance to reduce crashes and improve loading speed',
    'Customer Support':       'Strengthen customer support responsiveness and issue-resolution time',
    'UI & Design':            'Improve UI/UX design for better navigation and usability',
    'Features':               'Prioritise missing features requested by users to increase satisfaction',
    'Ease of Use':            'Simplify user flows and onboarding to make the app more intuitive',
}


def analyze_topics(reviews: list) -> dict:
    total = len(reviews)
    if not total:
        return {}
    counts = {t: 0 for t in TOPIC_KEYWORDS}
    others_count = 0
    for text in reviews:
        lower = text.lower()
        matched = False
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                counts[topic] += 1
                matched = True
                break
        if not matched:
            others_count += 1
    result = {
        t: {'count': c, 'pct': round(c / total * 100, 1)}
        for t, c in counts.items() if c > 0
    }
    result = dict(sorted(result.items(), key=lambda x: x[1]['count'], reverse=True))
    if others_count > 0:
        result['Others'] = {'count': others_count, 'pct': round(others_count / total * 100, 1)}
    return result


def analyze_dataframe(df):
    texts = df['review'].fillna('').astype(str).tolist()
    labels, confs = predict_texts(texts)

    results = []
    for idx, (row_idx, row) in enumerate(df.iterrows()):
        rating    = str(row.get('rating', ''))
        predicted = labels[idx]
        expected  = expected_sentiment(rating)
        try:
            r = float(rating)
        except (ValueError, TypeError):
            r = None
        mismatch = (
            r is not None and (
                (1 <= r <= 2 and predicted == 'Positive') or
                (4 <= r <= 5 and predicted == 'Negative')
            )
        )
        results.append({
            'review_text': str(row.get('review', '')),
            'rating':      rating,
            'app_name':    str(row.get('app_name', '')),
            'sentiment':   predicted,
            'confidence':  round(confs[idx] * 100, 1) if confs[idx] is not None else None,
            'expected':    expected or '—',
            'mismatch':    mismatch,
        })

    total = len(results)
    counts = {}
    for r in results:
        counts[r['sentiment']] = counts.get(r['sentiment'], 0) + 1

    summary = {}
    for label, count in counts.items():
        summary[label] = {'count': count, 'pct': round(count / total * 100, 1) if total else 0}
    for label in ('Positive', 'Negative', 'Neutral'):
        summary.setdefault(label, {'count': 0, 'pct': 0.0})

    mismatch_count = sum(1 for r in results if r['mismatch'])
    mismatch_pct   = round(mismatch_count / total * 100, 1) if total else 0

    neg_texts = [r['review_text'] for r in results if r['sentiment'] == 'Negative']
    pos_texts = [r['review_text'] for r in results if r['sentiment'] == 'Positive']
    neg_insights     = analyze_topics(neg_texts)
    pos_insights     = analyze_topics(pos_texts)
    neg_pct_val      = summary.get('Negative', {}).get('pct', 0)
    recommendations  = generate_recommendations(neg_insights, neg_pct_val)
    keywords         = extract_keywords(texts)

    return {
        'total':           total,
        'summary':         summary,
        'results':         results,
        'mismatch_count':  mismatch_count,
        'mismatch_pct':    mismatch_pct,
        'neg_insights':    neg_insights,
        'pos_insights':    pos_insights,
        'recommendations': recommendations,
        'keywords':        keywords,
    }


# PAGE ROUTES

@app.route('/')
@app.route('/HomePage.html')
def home():
    return render_template('HomePage.html')


@app.route('/login.html')
@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/login-admin.html')
@app.route('/admin-login')
def admin_login_page():
    return render_template('login-admin.html')


@app.route('/signup.html')
@app.route('/signup')
def signup_page():
    return render_template('signup.html')


@app.route('/forget_password.html')
def forget_password():
    return render_template('forget_password.html')

@app.route('/api/send-reset-code', methods=['POST'])
def api_send_reset_code():
    data = request.get_json()
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'success': False, 'error': 'Email required'}), 400
    code = str(random.randint(1000, 9999))
    reset_codes[email] = code
    try:
        msg = MIMEText(f'Your AppInsight reset code is : {code}')
        msg['Subject'] = 'AppInsight - Password Reset Code'
        msg['From'] = GMAIL_USER
        msg['To'] = email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    data =  request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data received'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE user SET password = %s WHERE email = %s',
            (password, email)
        )
        conn.commit()
        affected = cursor.rowcount
        cursor.close()
        if affected == 0:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    

@app.route('/api/verify-reset-code', methods=['POST'])
def api_verify_reset_code():
    data = request.get_json()
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    if reset_codes.get(email) == code:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid code'}), 400



@app.route('/FAQ.html')
@app.route('/faq')
def faq():
    return render_template('FAQ.html')


@app.route('/logout.html')
@app.route('/logout')
def logout():
    return render_template('logout.html')


@app.route('/profile.html')
def profile():
    return render_template('profile.html')


@app.route('/user-dashboard.html')
@app.route('/dashboard')
def user_dashboard():
    return render_template('user-dashboard.html')


@app.route('/uploadFile.html')
@app.route('/upload')
def upload_page():
    return render_template('uploadFile.html')


@app.route('/uploadedfile.html')
@app.route('/files')
def file_library():
    return render_template('uploadedfile.html')


@app.route('/Compare_apps.html')
@app.route('/compare')
def compare_page():
    return render_template('Compare_apps.html')


@app.route('/admin-dashboard.html')
@app.route('/admin')
def admin_dashboard():
    return render_template('admin-dashboard.html')


@app.route('/AdminManageUsers.html')
@app.route('/admin/users')
def admin_manage_users():
    return render_template('AdminManageUsers.html')


@app.route('/admin-model.html')
@app.route('/admin/model')
def admin_model_page():
    return render_template('admin-model.html')


@app.route('/admin-faq.html')
@app.route('/admin/faq')
def admin_faq():
    return render_template('admin-faq.html')


@app.route('/admin-logout.html')
@app.route('/admin-logout')
def admin_logout():
    return render_template('admin-logout.html')



# Authentication API

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data      = request.get_json()
    full_name = data.get('name', '').strip()
    email     = data.get('email', '').strip().lower()
    password  = data.get('password', '')

    if not full_name or not email or not password:
        return jsonify({'success': False, 'error': 'All fields are required.'}), 400

    parts      = full_name.split(' ', 1)
    first_name = parts[0]
    last_name  = parts[1] if len(parts) > 1 else None

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT user_id FROM user WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Email already registered.'}), 409

        cursor.execute(
            "INSERT INTO user (first_name, last_name, email, password) VALUES (%s, %s, %s, %s)",
            (first_name, last_name, email, password)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/login', methods=['POST'])
def api_login():
    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, first_name, last_name, email, status FROM user "
            "WHERE email = %s AND password = %s",
            (email, password)
        )
        user = cursor.fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'Invalid email or password.'}), 401
        if user['status'] != 'active':
            return jsonify({'success': False, 'error': 'Your account has been deactivated.'}), 403

        full_name = f"{user['first_name']} {user['last_name'] or ''}".strip()
        session['user_id']    = user['user_id']
        session['user_email'] = user['email']
        session['user_name']  = full_name
        return jsonify({'success': True, 'user': {'name': full_name, 'email': user['email']}})
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT admin_id FROM admin WHERE email = %s AND password = %s",
            (email, password)
        )
        admin = cursor.fetchone()
        if not admin:
            return jsonify({'success': False, 'error': 'Invalid admin credentials.'}), 401
        session['admin']    = True
        session['admin_id'] = admin['admin_id']
        return jsonify({'success': True})
    finally:
        cursor.close()
        db.close()


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})



# PROFILE API

@app.route('/api/profile', methods=['GET'])
def api_get_profile():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, first_name, last_name, email, gender, dob, phone, status, created_at "
            "FROM user WHERE user_id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        if not user:
            return jsonify({'success': False, 'error': 'User not found.'}), 404
        if isinstance(user.get('dob'), date):
            user['dob'] = user['dob'].isoformat()
        if isinstance(user.get('created_at'), datetime):
            user['created_at'] = user['created_at'].isoformat()
        return jsonify({'success': True, 'user': user})
    finally:
        cursor.close()
        db.close()


@app.route('/api/profile', methods=['PUT'])
def api_update_profile():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    data       = request.get_json()
    first_name = data.get('first_name', '').strip()
    last_name  = data.get('last_name', '').strip() or None
    gender     = data.get('gender', '').strip() or None
    dob        = data.get('dob', '').strip() or None
    phone      = data.get('phone', '').strip() or None

    if not first_name:
        return jsonify({'success': False, 'error': 'First name is required.'}), 400

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE user SET first_name=%s, last_name=%s, gender=%s, dob=%s, phone=%s "
            "WHERE user_id=%s",
            (first_name, last_name, gender, dob, phone, user_id)
        )
        db.commit()
        session['user_name'] = f"{first_name} {last_name or ''}".strip()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/profile/password', methods=['PUT'])
def api_change_password():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    data         = request.get_json()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({'success': False, 'error': 'Both old and new passwords are required.'}), 400

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT password FROM user WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if not row or row['password'] != old_password:
            return jsonify({'success': False, 'error': 'Current password is incorrect.'}), 401

        cursor.execute("UPDATE user SET password=%s WHERE user_id=%s", (new_password, user_id))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()



# FAQ API

@app.route('/api/faqs', methods=['GET'])
def api_get_faqs():
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT faq_id, question, answer, updated_at FROM faq ORDER BY faq_id")
        rows = cursor.fetchall()
        for row in rows:
            if isinstance(row.get('updated_at'), date):
                row['updated_at'] = row['updated_at'].isoformat()
        return jsonify(rows)
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/faqs', methods=['POST'])
def api_create_faq():
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    data     = request.get_json()
    question = data.get('question', '').strip()
    answer   = data.get('answer', '').strip()

    if not question or not answer:
        return jsonify({'success': False, 'error': 'Question and answer are required.'}), 400

    db     = get_db()
    cursor = db.cursor()
    try:
        today = date.today().isoformat()
        cursor.execute(
            "INSERT INTO faq (question, answer, updated_at) VALUES (%s, %s, %s)",
            (question, answer, today)
        )
        db.commit()
        return jsonify({'success': True, 'faq_id': cursor.lastrowid})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/faqs/<int:faq_id>', methods=['PUT'])
def api_update_faq(faq_id):
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    data     = request.get_json()
    question = data.get('question', '').strip()
    answer   = data.get('answer', '').strip()

    if not question or not answer:
        return jsonify({'success': False, 'error': 'Question and answer are required.'}), 400

    db     = get_db()
    cursor = db.cursor()
    try:
        today = date.today().isoformat()
        cursor.execute(
            "UPDATE faq SET question=%s, answer=%s, updated_at=%s WHERE faq_id=%s",
            (question, answer, today, faq_id)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/faqs/<int:faq_id>', methods=['DELETE'])
def api_delete_faq(faq_id):
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM faq WHERE faq_id=%s", (faq_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()



# FILE UPLOAD & ANALYSIS API 

@app.route('/api/upload', methods=['POST'])
def api_upload():

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    uploaded = request.files['file']
    if not uploaded.filename.lower().endswith('.csv'):
        return jsonify({'success': False, 'error': 'Only CSV files are supported.'}), 400

    app_name = request.form.get('app_name', '').strip() or uploaded.filename

    filename   = secure_filename(f"{user_id}_{int(datetime.now().timestamp())}_{uploaded.filename}")
    file_path  = os.path.join(UPLOAD_FOLDER, filename)
    uploaded.save(file_path)

    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip().str.lower()
        if 'review' not in df.columns:
            os.remove(file_path)
            return jsonify({'success': False, 'error': 'CSV must contain a "review" column.'}), 422

        result = analyze_dataframe(df)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'success': False, 'error': str(e)}), 500

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO file (user_id, app_name, file_path, model_version) VALUES (%s, %s, %s, %s)",
            (user_id, app_name, file_path, MODEL_VERSION)
        )
        file_id = cursor.lastrowid

        for r in result['results']:
            try:
                rating_val = float(r['rating']) if r['rating'] else None
            except (ValueError, TypeError):
                rating_val = None
            cursor.execute(
                "INSERT INTO review (file_id, review_text, rating, sentiment_label) VALUES (%s, %s, %s, %s)",
                (file_id, r['review_text'], rating_val, r['sentiment'])
            )

        summary        = result['summary']
        pos_pct        = summary.get('Positive', {}).get('pct', 0.0)
        neg_pct        = summary.get('Negative', {}).get('pct', 0.0)
        neu_pct        = summary.get('Neutral',  {}).get('pct', 0.0)
        ratings        = [float(r['rating']) for r in result['results']
                          if r['rating'] not in ('', None, '—')]
        avg_rating     = round(sum(ratings) / len(ratings), 2) if ratings else None
        top_pos        = json.dumps(list(result['pos_insights'].keys())[:5])
        top_neg        = json.dumps(list(result['neg_insights'].keys())[:5])
        cached_result  = json.dumps({
            'keywords':        result['keywords'],
            'neg_insights':    result['neg_insights'],
            'pos_insights':    result['pos_insights'],
            'recommendations': result['recommendations'],
            'mismatch_count':  result['mismatch_count'],
            'mismatch_pct':    result['mismatch_pct'],
        })

        cursor.execute(
            "INSERT INTO single_analysis "
            "(file_id, positive_percent, negative_percent, neutral_percent, "
            " average_rating, top_positive_features, top_negative_features, cached_result) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (file_id, pos_pct, neg_pct, neu_pct, avg_rating, top_pos, top_neg, cached_result)
        )
        db.commit()
        result['file_id'] = file_id
        result['success'] = True
        return jsonify(result)
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/files', methods=['GET'])
def api_get_files():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT f.file_id, f.app_name, f.model_version, f.uploaded_at, "
            "       s.positive_percent, s.negative_percent, s.neutral_percent, "
            "       s.average_rating, s.top_positive_features, s.top_negative_features "
            "FROM file f "
            "LEFT JOIN single_analysis s ON s.file_id = f.file_id "
            "WHERE f.user_id = %s "
            "ORDER BY f.uploaded_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        for row in rows:
            if isinstance(row.get('uploaded_at'), datetime):
                row['uploaded_at'] = row['uploaded_at'].isoformat()
            for key in ('top_positive_features', 'top_negative_features'):
                if row.get(key):
                    try:
                        row[key] = json.loads(row[key])
                    except (ValueError, TypeError):
                        pass
        return jsonify({'success': True, 'files': rows})
    finally:
        cursor.close()
        db.close()


@app.route('/api/files/<int:file_id>', methods=['DELETE'])
def api_delete_file(file_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT file_path FROM file WHERE file_id=%s AND user_id=%s", (file_id, user_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'File not found.'}), 404

        cursor.execute("DELETE FROM single_analysis     WHERE file_id=%s",            (file_id,))
        cursor.execute("DELETE FROM comparison_analysis WHERE file1_id=%s OR file2_id=%s", (file_id, file_id))
        cursor.execute("DELETE FROM review              WHERE file_id=%s",            (file_id,))
        cursor.execute("DELETE FROM file                WHERE file_id=%s",            (file_id,))
        db.commit()

        if row['file_path'] and os.path.exists(row['file_path']):
            os.remove(row['file_path'])

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/files/<int:file_id>/result', methods=['GET'])
def api_get_file_result(file_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT f.file_id, f.app_name, f.file_path FROM file f "
            "WHERE f.file_id=%s AND f.user_id=%s",
            (file_id, user_id)
        )
        file_row = cursor.fetchone()
        if not file_row:
            return jsonify({'success': False, 'error': 'File not found.'}), 404

        cursor.execute(
            "SELECT review_text, rating, sentiment_label FROM review WHERE file_id=%s",
            (file_id,)
        )
        reviews = cursor.fetchall()

        cursor.execute(
            "SELECT positive_percent, negative_percent, neutral_percent, "
            "average_rating, top_positive_features, top_negative_features, cached_result "
            "FROM single_analysis WHERE file_id=%s LIMIT 1",
            (file_id,)
        )
        sr = cursor.fetchone()

        
        results = [
            {
                'review_text': r['review_text'],
                'rating': str(r['rating']) if r['rating'] is not None else '',
                'sentiment': r['sentiment_label'],
            }
            for r in reviews
        ]

        total = len(results)

        
        counts = {}
        for r in results:
            counts[r['sentiment']] = counts.get(r['sentiment'], 0) + 1

        summary = {}
        for label, count in counts.items():
            summary[label] = {
                'count': count,
                'pct': round(count / total * 100, 1) if total else 0
            }

        for label in ('Positive', 'Negative', 'Neutral'):
            summary.setdefault(label, {'count': 0, 'pct': 0.0})

      
        top_pos = []
        top_neg = []

        if sr:
            try:
                top_pos = json.loads(sr['top_positive_features'] or '[]')
            except:
                pass
            try:
                top_neg = json.loads(sr['top_negative_features'] or '[]')
            except:
                pass

        cached = {}
        if sr and sr.get('cached_result'):
            try:
                cached = json.loads(sr['cached_result'])
            except Exception:
                pass

        if 'mismatch_count' in cached:
            mismatch_count = cached['mismatch_count']
            mismatch_pct   = cached['mismatch_pct']
        else:
            mismatch_count = 0
            for r in results:
                try:
                    rating = float(r['rating'])
                except Exception:
                    continue
                if (1 <= rating <= 2 and r['sentiment'] == 'Positive') or \
                   (4 <= rating <= 5 and r['sentiment'] == 'Negative'):
                    mismatch_count += 1
            mismatch_pct = round(mismatch_count / total * 100, 1) if total else 0

        keywords = cached.get('keywords') or extract_keywords([r['review_text'] for r in results])

        neg_texts = [r['review_text'] for r in results if r['sentiment'] == 'Negative']
        pos_texts = [r['review_text'] for r in results if r['sentiment'] == 'Positive']
        neg_insights    = cached.get('neg_insights')    or analyze_topics(neg_texts)
        pos_insights    = cached.get('pos_insights')    or analyze_topics(pos_texts)
        neg_pct_val     = summary.get('Negative', {}).get('pct', 0)
        recommendations = cached.get('recommendations') or generate_recommendations(neg_insights, neg_pct_val)

        return jsonify({
            'success': True,
            'file_id': file_id,
            'app_name': file_row['app_name'],
            'total': total,
            'summary': summary,
            'results': results,
            'top_positive_features': top_pos,
            'top_negative_features': top_neg,
            'average_rating': sr['average_rating'] if sr else None,
            'keywords': keywords,
            'neg_insights': neg_insights,
            'pos_insights': pos_insights,
            'recommendations': recommendations,
            'mismatch_count': mismatch_count,
            'mismatch_pct': mismatch_pct
        })

    finally:
        cursor.close()
        db.close()



# SENTIMENT MODEL API 


@app.route('/api/predict', methods=['POST'])
def api_predict():
    """POST JSON {"text": "..."}. Returns sentiment and confidence."""
    data = request.get_json()
    text = data.get('text', '').strip() if data else ''
    if not text:
        return jsonify({'error': 'No text provided.'}), 400
    try:
        labels, confs = predict_texts([text])
        return jsonify({
            'sentiment':  labels[0],
            'confidence': round(confs[0] * 100, 1) if confs[0] is not None else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/mismatch', methods=['POST'])
def api_mismatch():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded.'}), 400
    file = request.files['file']
    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files are supported.'}), 400
    try:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip().str.lower()
        if 'review' not in df.columns:
            return jsonify({'error': 'CSV must contain a "review" column.'}), 422

        texts          = df['review'].fillna('').astype(str).tolist()
        labels, _      = predict_texts(texts)
        total          = len(labels)
        mismatch_count = 0
        chart_data     = {str(s): {'Positive': 0, 'Neutral': 0, 'Negative': 0} for s in range(1, 6)}

        for idx, (_, row) in enumerate(df.iterrows()):
            predicted = labels[idx]
            try:
                star = min(max(round(float(row.get('rating', 0))), 1), 5)
            except (ValueError, TypeError):
                star = 0
            if star > 0:
                chart_data[str(star)][predicted] = chart_data[str(star)].get(predicted, 0) + 1
            if (1 <= star <= 2 and predicted == 'Positive') or \
               (4 <= star <= 5 and predicted == 'Negative'):
                mismatch_count += 1

        mismatch_pct = round(mismatch_count / total * 100, 1) if total else 0
        return jsonify({
            'total':          total,
            'mismatch_count': mismatch_count,
            'mismatch_pct':   mismatch_pct,
            'chart_data':     chart_data,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/compare/latest', methods=['GET'])
def api_compare_latest():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Not logged in.'}), 401

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT ca.file1_id, ca.file2_id,
                   ca.file1_positive_percent, ca.file1_negative_percent, ca.file1_neutral_percent,
                   ca.file1_average_rating,
                   ca.file2_positive_percent, ca.file2_negative_percent, ca.file2_neutral_percent,
                   ca.file2_average_rating,
                   f1.app_name AS name1, f2.app_name AS name2
            FROM comparison_analysis ca
            JOIN file f1 ON f1.file_id = ca.file1_id
            JOIN file f2 ON f2.file_id = ca.file2_id
            WHERE f1.user_id = %s AND f2.user_id = %s
            ORDER BY ca.created_at DESC
            LIMIT 1
            """,
            (user_id, user_id)
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'No comparison found.'})

        cursor.execute("SELECT COUNT(*) AS cnt FROM review WHERE file_id = %s", (row['file1_id'],))
        total1 = cursor.fetchone()['cnt']

        cursor.execute("SELECT COUNT(*) AS cnt FROM review WHERE file_id = %s", (row['file2_id'],))
        total2 = cursor.fetchone()['cnt']

        def build_result(total, pos_pct, neg_pct, neu_pct, avg_rating):
            return {
                'total': total,
                'summary': {
                    'Positive': {'count': round(total * pos_pct / 100), 'pct': float(pos_pct or 0)},
                    'Negative': {'count': round(total * neg_pct / 100), 'pct': float(neg_pct or 0)},
                    'Neutral':  {'count': round(total * neu_pct / 100), 'pct': float(neu_pct or 0)},
                },
                'avg_rating': float(avg_rating) if avg_rating is not None else None,
                'results': [],
            }

        return jsonify({
            'success': True,
            'name1': row['name1'],
            'name2': row['name2'],
            'app1': build_result(total1, row['file1_positive_percent'], row['file1_negative_percent'],
                                 row['file1_neutral_percent'], row['file1_average_rating']),
            'app2': build_result(total2, row['file2_positive_percent'], row['file2_negative_percent'],
                                 row['file2_neutral_percent'], row['file2_average_rating']),
        })
    finally:
        cursor.close()
        db.close()


@app.route('/api/compare', methods=['POST'])
def api_compare():

    f1 = request.files.get('file1')
    f2 = request.files.get('file2')

    if not f1 or not f2:
        return jsonify({'error': 'Two CSV files are required (file1 and file2).'}), 400

    app_name1 = request.form.get('app_name1', '').strip() or f1.filename
    app_name2 = request.form.get('app_name2', '').strip() or f2.filename
    user_id   = session.get('user_id')

    fp1 = fp2 = None
    db = None
    cursor = None

    try:
        # Read CSV
        df1 = pd.read_csv(f1)
        df2 = pd.read_csv(f2)

        df1.columns = df1.columns.str.strip().str.lower()
        df2.columns = df2.columns.str.strip().str.lower()

        if 'review' not in df1.columns or 'review' not in df2.columns:
            return jsonify({'error': 'Both CSVs must contain a "review" column.'}), 422

        res1 = analyze_dataframe(df1)
        res2 = analyze_dataframe(df2)

        def _summary(res):
            s = res['summary']

            ratings = [
                float(r['rating']) for r in res['results']
                if r['rating'] not in ('', None, '—')
            ]

            avg = round(sum(ratings) / len(ratings), 2) if ratings else None

            return (
                s.get('Positive', {}).get('pct', 0.0),
                s.get('Negative', {}).get('pct', 0.0),
                s.get('Neutral',  {}).get('pct', 0.0),
                avg,
                json.dumps(list(res['pos_insights'].keys())[:5]),
                json.dumps(list(res['neg_insights'].keys())[:5]),
            )

        pp1, np1, nu1, ar1, tp1, tn1 = _summary(res1)
        pp2, np2, nu2, ar2, tp2, tn2 = _summary(res2)

        if user_id:
            f1.seek(0)
            f2.seek(0)

            fn1 = secure_filename(f"{user_id}_{int(datetime.now().timestamp())}_1_{f1.filename}")
            fn2 = secure_filename(f"{user_id}_{int(datetime.now().timestamp())}_2_{f2.filename}")

            fp1 = os.path.join(UPLOAD_FOLDER, fn1)
            fp2 = os.path.join(UPLOAD_FOLDER, fn2)

            f1.save(fp1)
            f2.save(fp2)

            db = get_db()
            cursor = db.cursor()

            # Insert files
            cursor.execute(
                "INSERT INTO file (user_id, app_name, file_path, model_version) VALUES (%s,%s,%s,%s)",
                (user_id, app_name1, fp1, MODEL_VERSION)
            )
            file1_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO file (user_id, app_name, file_path, model_version) VALUES (%s,%s,%s,%s)",
                (user_id, app_name2, fp2, MODEL_VERSION)
            )
            file2_id = cursor.lastrowid

            # Save reviews
            def _save_reviews(fid, results):
                for r in results:
                    try:
                        rv = float(r['rating']) if r['rating'] else None
                    except:
                        rv = None

                    cursor.execute(
                        "INSERT INTO review (file_id, review_text, rating, sentiment_label) VALUES (%s,%s,%s,%s)",
                        (fid, r['review_text'], rv, r['sentiment'])
                    )

            _save_reviews(file1_id, res1['results'])
            _save_reviews(file2_id, res2['results'])

            cursor.execute(
                """
                INSERT INTO comparison_analysis (
                    file1_id, file2_id,
                    file1_positive_percent, file1_negative_percent, file1_neutral_percent,
                    file1_average_rating, file1_top_positive_features, file1_top_negative_features,
                    file2_positive_percent, file2_negative_percent, file2_neutral_percent,
                    file2_average_rating, file2_top_positive_features, file2_top_negative_features,
                    created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
                """,
                (
                    file1_id, file2_id,
                    pp1, np1, nu1, ar1, tp1, tn1,
                    pp2, np2, nu2, ar2, tp2, tn2
                )
            )

            db.commit()

        return jsonify({
            'app1': res1,
            'app2': res2
        })

    except Exception as e:
        if db:
            db.rollback()

        if fp1 and os.path.exists(fp1):
            os.remove(fp1)
        if fp2 and os.path.exists(fp2):
            os.remove(fp2)

        return jsonify({'error': str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


# ADMIN API

@app.route('/api/admin/users', methods=['GET'])
def api_admin_users():
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id AS id, first_name, last_name, email, status, created_at FROM user ORDER BY user_id"
        )
        rows = cursor.fetchall()
        for row in rows:
            row['name'] = f"{row.pop('first_name')} {row.pop('last_name') or ''}".strip()
            if isinstance(row.get('created_at'), datetime):
                row['created_at'] = row['created_at'].isoformat()
        return jsonify(rows)
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
def api_admin_update_user(user_id):
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    data   = request.get_json()
    name   = data.get('name', '').strip()
    email  = data.get('email', '').strip().lower()
    status = data.get('status', '').strip()

    if not name or not email or not status:
        return jsonify({'success': False, 'error': 'All fields are required.'}), 400

    parts      = name.split(' ', 1)
    first_name = parts[0]
    last_name  = parts[1] if len(parts) > 1 else None

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE user SET first_name=%s, last_name=%s, email=%s, status=%s WHERE user_id=%s",
            (first_name, last_name, email, status, user_id)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def api_admin_delete_user(user_id):
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            "DELETE FROM single_analysis WHERE file_id IN (SELECT file_id FROM file WHERE user_id=%s)",
            (user_id,)
        )
        cursor.execute(
            "DELETE FROM comparison_analysis WHERE file1_id IN (SELECT file_id FROM file WHERE user_id=%s)"
            "                                  OR file2_id IN (SELECT file_id FROM file WHERE user_id=%s)",
            (user_id, user_id)
        )
        cursor.execute(
            "DELETE FROM review WHERE file_id IN (SELECT file_id FROM file WHERE user_id=%s)",
            (user_id,)
        )
        cursor.execute("DELETE FROM file WHERE user_id=%s", (user_id,))
        cursor.execute("DELETE FROM user WHERE user_id=%s", (user_id,))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/users/<int:user_id>/status', methods=['PATCH'])
def api_admin_update_status(user_id):
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    data   = request.get_json()
    status = data.get('status', '').strip()
    if status not in ('active', 'inactive'):
        return jsonify({'success': False, 'error': 'Status must be "active" or "inactive".'}), 400

    db     = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("UPDATE user SET status=%s WHERE user_id=%s", (status, user_id))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/stats', methods=['GET'])
def api_admin_stats():
    """Dashboard summary stats for the admin."""
    if not session.get('admin'):
        return jsonify({'success': False, 'error': 'Unauthorized.'}), 403

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total_users FROM user")
        total_users = cursor.fetchone()['total_users']

        cursor.execute("SELECT COUNT(*) AS active_users FROM user WHERE status='active'")
        active_users = cursor.fetchone()['active_users']

        cursor.execute("SELECT COUNT(*) AS total_files FROM file")
        total_files = cursor.fetchone()['total_files']

        cursor.execute("SELECT COUNT(*) AS total_reviews FROM review")
        total_reviews = cursor.fetchone()['total_reviews']

        return jsonify({
            'success':       True,
            'total_users':   total_users,
            'active_users':  active_users,
            'total_files':   total_files,
            'total_reviews': total_reviews,
        })
    finally:
        cursor.close()
        db.close()


@app.route('/api/admin/model/stats', methods=['GET'])
def api_admin_model_stats():
    dataset_total   = 34352
    test_samples    = 6871
    train_per_class = 13020
    train_total     = train_per_class * 3

    classes = {
        'Negative': {'count': train_per_class, 'pct': round(train_per_class / train_total * 100, 1)},
        'Positive': {'count': train_per_class, 'pct': round(train_per_class / train_total * 100, 1)},
        'Neutral':  {'count': train_per_class, 'pct': round(train_per_class / train_total * 100, 1)},
    }
    return jsonify({
        'accuracy':         0.632222,
        'f1_score':         0.586804,
        'precision':        0.589999,
        'recall':           0.586025,
        'version':          MODEL_VERSION,
        'algorithm':        'TF-IDF + SVM',
        'dataset_total':    dataset_total,
        'training_samples': train_total,
        'test_samples':     test_samples,
        'last_trained':     'Jan 15, 2026',
        'classes':          classes,
    })


@app.route('/api/admin/model/stats_json', methods=['GET'])
def api_admin_model_stats_json():
    with open("dashboard_data.json") as f:
        data = json.load(f)
    return jsonify(data)


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True)
