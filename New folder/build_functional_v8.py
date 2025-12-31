import os
import zipfile
import io

# ==========================================
# 1. PYTHON BACKEND (Restored Logic + New Features)
# ==========================================

APP_PY = """from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from config import Config
from database.db_manager import init_db, get_db_connection
from services.analytics_service import calculate_kpis, get_analytics_data
from werkzeug.security import check_password_hash
import random
import csv
import io

app = Flask(__name__)
app.config.from_object(Config)

with app.app_context():
    init_db()

# Middleware
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Auth Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (request.form['username'],)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], request.form['password']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Core Pages
@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/machines')
@login_required
def machines():
    conn = get_db_connection()
    machines_list = conn.execute('SELECT * FROM machines').fetchall()
    conn.close()
    return render_template('machines.html', active_page='machines', machines=machines_list)

@app.route('/machines/add', methods=['POST'])
@login_required
def add_machine():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO machines (name, type, capacity_per_hour, status) VALUES (?, ?, ?, ?)', 
             (request.form['name'], request.form['type'], request.form['capacity'], 'Active'))
    
    # Init log for today
    mid = c.lastrowid
    c.execute("INSERT INTO production_logs (machine_id, date, planned_qty, actual_qty, runtime_hours) VALUES (?, DATE('now'), ?, 0, 0)", 
             (mid, int(request.form['capacity']) * 8)) # Default 8 hr shift plan
    
    conn.commit()
    conn.close()
    flash(f"Machine {request.form['name']} added successfully!")
    return redirect(url_for('machines'))

@app.route('/machines/delete/<int:id>', methods=['POST'])
@login_required
def delete_machine(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM machines WHERE id = ?', (id,))
    conn.execute('DELETE FROM production_logs WHERE machine_id = ?', (id,))
    conn.commit()
    conn.close()
    flash("Machine removed.")
    return redirect(url_for('machines'))

@app.route('/machines/toggle/<int:id>', methods=['POST'])
@login_required
def toggle_machine(id):
    conn = get_db_connection()
    curr = conn.execute("SELECT status FROM machines WHERE id=?", (id,)).fetchone()['status']
    new_status = 'Maintenance' if curr == 'Active' else 'Active'
    conn.execute("UPDATE machines SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    conn.close()
    return redirect(url_for('machines'))

@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    logs = conn.execute('SELECT p.*, m.name as machine_name FROM production_logs p JOIN machines m ON p.machine_id = m.id ORDER BY p.date DESC').fetchall()
    return render_template('reports.html', active_page='reports', logs=logs)

@app.route('/alerts')
@login_required
def alerts():
    conn = get_db_connection()
    alerts = conn.execute('SELECT a.*, m.name as machine_name FROM alerts a JOIN machines m ON a.machine_id = m.id ORDER BY a.created_at DESC').fetchall()
    return render_template('alerts.html', active_page='alerts', alerts=alerts, c=sum(1 for a in alerts if a['severity']=='Critical'), w=sum(1 for a in alerts if a['severity']=='Warning'), i=sum(1 for a in alerts if a['severity']=='Info'))

@app.route('/analytics')
@login_required
def analytics():
    data = get_analytics_data()
    return render_template('analytics.html', active_page='analytics', rankings=data['rankings'], trend_labels=data['trend']['labels'], trend_data=data['trend']['data'])

@app.route('/help')
@login_required
def help_page():
    return render_template('help.html', active_page='help')

@app.route('/settings')
@login_required
def settings():
    conn = get_db_connection()
    s = {row['key']: row['value'] for row in conn.execute("SELECT * FROM settings").fetchall()}
    conn.close()
    return render_template('settings.html', active_page='settings', s=s)

@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('plant_name', request.form['plant_name']))
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('threshold_eff', request.form['threshold_eff']))
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('shift_hours', request.form['shift_hours']))
    conn.commit()
    conn.close()
    flash("System configuration updated.")
    return redirect(url_for('settings'))

@app.route('/settings/reset_data', methods=['POST'])
@login_required
def reset_data():
    conn = get_db_connection()
    conn.execute('DELETE FROM production_logs')
    conn.execute('DELETE FROM alerts')
    # Re-seed logs for today only to prevent empty dash
    machines = conn.execute('SELECT id, capacity_per_hour FROM machines').fetchall()
    for m in machines:
        conn.execute("INSERT INTO production_logs (machine_id, date, planned_qty, actual_qty, runtime_hours) VALUES (?, DATE('now'), ?, 0, 0)", 
                    (m['id'], m['capacity_per_hour']*8))
    conn.commit()
    conn.close()
    flash("All historical data has been wiped.")
    return redirect(url_for('settings'))

@app.route('/download_csv')
@login_required
def download_csv():
    conn = get_db_connection()
    logs = conn.execute('SELECT p.date, m.name, p.planned_qty, p.actual_qty FROM production_logs p JOIN machines m ON p.machine_id = m.id').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Machine', 'Planned', 'Actual'])
    for r in logs: writer.writerow([r['date'], r['name'], r['planned_qty'], r['actual_qty']])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=report.csv"})

@app.route('/api/dashboard')
@login_required
def api_data(): return jsonify(calculate_kpis())

@app.route('/api/simulate')
@login_required
def simulate():
    conn = get_db_connection()
    logs = conn.execute("SELECT id, machine_id, actual_qty, planned_qty FROM production_logs WHERE date = DATE('now')").fetchall()
    for log in logs:
        # Don't update if machine is in maintenance (check machine status)
        m_status = conn.execute("SELECT status FROM machines WHERE id=?", (log['machine_id'],)).fetchone()['status']
        if m_status == 'Active' and log['actual_qty'] < log['planned_qty']:
            new_qty = min(log['planned_qty'], log['actual_qty'] + random.randint(20, 100))
            new_run = min(8.0, 0.5 + (new_qty/100))
            conn.execute("UPDATE production_logs SET actual_qty = ?, runtime_hours = ? WHERE id = ?", (new_qty, round(new_run, 1), log['id']))
    conn.commit()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
"""

# ==========================================
# 2. UPDATED TEMPLATES (Machines & Settings)
# ==========================================

# MACHINES PAGE (Now with ADD Form and Maintenance Toggle)
MACHINES_HTML = """{% extends "base.html" %}
{% block title %}Machine Configuration{% endblock %}
{% block content %}

<!-- Flash Messages -->
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <div class="glass-card" style="padding: 10px; background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; margin-bottom: 20px;">
      {% for message in messages %}
        <p style="margin: 0; color: #fff;">✓ {{ message }}</p>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}

<div class="grid-2">
    <!-- ADD FORM -->
    <div class="glass-card">
        <h3 style="margin-top:0;">Add New Machine</h3>
        <form action="{{ url_for('add_machine') }}" method="POST">
            <label>Machine ID / Name</label>
            <input type="text" name="name" placeholder="e.g. LATHE-05" required>
            
            <label>Machine Type</label>
            <select name="type">
                <option>CNC Milling</option>
                <option>Hydraulic Press</option>
                <option>Packaging Line</option>
                <option>Laser Cutter</option>
                <option>3D Printer</option>
            </select>
            
            <label>Capacity (Units/Hr)</label>
            <input type="number" name="capacity" value="100" required>
            
            <button type="submit" class="btn btn-glow" style="width:100%; justify-content:center;">
                + Deploy Machine
            </button>
        </form>
    </div>

    <!-- LIST -->
    <div class="glass-card">
        <h3 style="margin-top:0;">Fleet Management</h3>
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {% for m in machines %}
                <tr>
                    <td><strong>{{ m.name }}</strong></td>
                    <td style="color:var(--text-muted);">{{ m.type }}</td>
                    <td>
                        <form action="{{ url_for('toggle_machine', id=m.id) }}" method="POST" style="display:inline;">
                            <button class="status-badge {% if m.status == 'Active' %}status-Good{% else %}status-Warning{% endif %}" style="border:none; cursor:pointer;">
                                {{ m.status }}
                            </button>
                        </form>
                    </td>
                    <td>
                        <form action="{{ url_for('delete_machine', id=m.id) }}" method="POST">
                            <button class="btn btn-danger" style="padding: 4px 10px; font-size:11px;">Remove</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
"""

# SETTINGS PAGE (Now with Danger Zone & Shift Hours)
SETTINGS_HTML = """{% extends "base.html" %}
{% block title %}System Configuration{% endblock %}
{% block content %}

{% with messages = get_flashed_messages() %}
  {% if messages %}
    <div class="glass-card" style="padding: 10px; background: rgba(99, 102, 241, 0.2); border: 1px solid #6366f1; margin-bottom: 20px;">
      {% for message in messages %}
        <p style="margin: 0; color: #fff;">ℹ️ {{ message }}</p>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}

<div class="grid-2">
    <div class="glass-card">
        <h3>Performance Thresholds</h3>
        <form action="{{ url_for('update_settings') }}" method="POST">
            <label>Plant / Unit Name</label>
            <input type="text" name="plant_name" value="{{ s.plant_name }}" required>
            
            <label>Low Efficiency Alert Threshold (%)</label>
            <input type="number" name="threshold_eff" value="{{ s.threshold_eff }}" step="0.1" required>
            
            <label>Standard Shift Duration (Hours)</label>
            <input type="number" name="shift_hours" value="{{ s.shift_hours }}" step="0.5" required>
            
            <button type="submit" class="btn btn-glow" style="width:100%; justify-content:center; margin-top:20px;">
                Save Configuration
            </button>
        </form>
    </div>

    <div class="glass-card">
        <h3 style="color:#ef4444;">Danger Zone</h3>
        <p style="font-size:13px; color:#94a3b8; margin-bottom:20px;">
            Resetting the system will delete all historical production logs and alerts. 
            This action cannot be undone. Use this before a new Hackathon demo.
        </p>
        
        <form action="{{ url_for('reset_data') }}" method="POST" onsubmit="return confirm('Are you sure you want to wipe all data?');">
            <button type="submit" class="btn btn-danger" style="width:100%; justify-content:center;">
                ⚠️ Factory Reset
            </button>
        </form>
        
        <div style="margin-top:30px; padding:15px; background:rgba(255,255,255,0.05); border-radius:8px;">
            <h4 style="margin:0 0 10px 0;">System Info</h4>
            <p style="font-size:13px; color:#94a3b8; margin:5px 0;">Version: <strong>v8.0.0 (Functional)</strong></p>
        </div>
    </div>
</div>
{% endblock %}
"""

# ==========================================
# 3. SUPPORTING FILES (Preserved)
# ==========================================

# CONFIG
CONFIG_PY = """import os
class Config:
    SECRET_KEY = 'v8_functional_secret'
    DB_NAME = "smartfactory_v8.db"
    SHIFT_HOURS = 8.0
"""

# DB MANAGER
DB_MANAGER_PY = """import sqlite3
from config import Config
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

def get_db_connection():
    conn = sqlite3.connect(Config.DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, role TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS machines (id INTEGER PRIMARY KEY, name TEXT, type TEXT, capacity_per_hour INTEGER, status TEXT DEFAULT "Active")')
    c.execute('CREATE TABLE IF NOT EXISTS production_logs (id INTEGER PRIMARY KEY, machine_id INTEGER, date TEXT, planned_qty INTEGER, actual_qty INTEGER, runtime_hours REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, machine_id INTEGER, message TEXT, severity TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')

    if c.execute('SELECT count(*) FROM users').fetchone()[0] == 0:
        c.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', ('admin', generate_password_hash('admin123'), 'admin'))
        c.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', ('operator', generate_password_hash('operator123'), 'operator'))

    if c.execute('SELECT count(*) FROM machines').fetchone()[0] == 0:
        machines = [('CNC-01', 'Milling', 100), ('CNC-02', 'Milling', 100), ('PRESS-A', 'Press', 500), ('PACK-01', 'Packing', 1000)]
        c.executemany('INSERT INTO machines (name, type, capacity_per_hour) VALUES (?, ?, ?)', machines)
        
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('plant_name', 'Nagpur MIDC Zone-A')")
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('threshold_eff', '75.0')")
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('shift_hours', '8.0')")
        
        # Seed history
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            c.execute("INSERT INTO production_logs (machine_id, date, planned_qty, actual_qty, runtime_hours) VALUES (1, ?, 800, ?, ?)", (date, random.randint(700, 800), 7.5))
    
    conn.commit()
    conn.close()
"""

# ANALYTICS SERVICE
ANALYTICS_SERVICE_PY = """from database.db_manager import get_db_connection
from config import Config

def calculate_kpis():
    conn = get_db_connection()
    rows = conn.execute("SELECT m.name, m.status, p.* FROM machines m LEFT JOIN production_logs p ON m.id = p.machine_id WHERE p.date = DATE('now')").fetchall()
    
    # Get Dynamic Settings
    s_rows = conn.execute("SELECT * FROM settings").fetchall()
    settings = {row['key']: row['value'] for row in s_rows}
    thresh = float(settings.get('threshold_eff', 75.0))
    shift_h = float(settings.get('shift_hours', 8.0))
    
    data = []
    total_eff, delays = 0, 0
    active_machines = 0
    
    for r in rows:
        if not r['planned_qty']: continue
        
        # Skip maintenance machines in Avg calculation if no production
        if r['status'] == 'Maintenance' and r['actual_qty'] == 0:
            data.append({"name": r['name'], "efficiency": 0, "utilization": 0, "idle_time": 0, "actual_qty": 0, "planned_qty": 0, "status": "Maintenance"})
            continue
            
        active_machines += 1
        eff = round((r['actual_qty'] / r['planned_qty'] * 100), 1)
        util = round((r['runtime_hours'] / shift_h * 100), 1)
        idle = round(shift_h - r['runtime_hours'], 1)
        
        status = "Good"
        if r['status'] == 'Maintenance': status = "Maintenance"
        elif eff < thresh: status = "Critical"
        elif eff < (thresh + 15): status = "Warning"
        
        if r['actual_qty'] < r['planned_qty'] and r['status'] == 'Active': delays += 1
        
        data.append({"name": r['name'], "efficiency": eff, "utilization": util, "idle_time": idle, "actual_qty": r['actual_qty'], "planned_qty": r['planned_qty'], "status": status})
        total_eff += eff
    
    avg = round(total_eff / active_machines, 1) if active_machines > 0 else 0
    
    # Bottleneck is active machine with lowest efficiency
    active_data = [d for d in data if d['status'] != 'Maintenance']
    bottle = min(active_data, key=lambda x: x['efficiency'])['name'] if active_data else "None"
    
    conn.close()
    return {"kpi_summary": {"avg_efficiency": avg, "total_machines": len(data), "delayed_orders": delays, "bottleneck": bottle}, "machines": data}

def get_analytics_data():
    conn = get_db_connection()
    rankings = conn.execute("SELECT m.name, AVG((p.actual_qty * 1.0 / p.planned_qty) * 100) as avg_eff FROM machines m JOIN production_logs p ON m.id = p.machine_id GROUP BY m.id ORDER BY avg_eff DESC").fetchall()
    trend = conn.execute("SELECT date, AVG((actual_qty * 1.0 / planned_qty) * 100) as daily_eff FROM production_logs GROUP BY date ORDER BY date DESC LIMIT 7").fetchall()
    conn.close()
    
    t_labels = [r['date'] for r in trend][::-1]
    t_data = [round(r['daily_eff'], 1) for r in trend][::-1]
    
    return {"rankings": [{"name": r['name'], "avg_eff": round(r['avg_eff'], 1)} for r in rankings], "trend": {"labels": t_labels, "data": t_data}}
"""

# HTML Files (Reused Standard ones)
LOGIN_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login</title><link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}"></head><body class="login-body"><div class="glow-orb orb-1"></div><div class="glow-orb orb-2"></div><div class="login-container"><div class="glass-login-card"><div class="login-header"><div class="brand-icon-large">⚡</div><h2>SmartFactory</h2><p>Industrial Intelligence Platform</p></div>{% if error %}<div class="error-banner"><span>⚠️</span> {{ error }}</div>{% endif %}<form method="POST"><div class="input-group"><label>Username</label><input type="text" name="username" placeholder="admin" required autofocus></div><div class="input-group"><label>Password</label><input type="password" name="password" placeholder="••••••••" required></div><button type="submit" class="btn btn-glow full-width">Login</button></form><div style="margin-top:30px; font-size:12px; opacity:0.6;">Restricted Access • MIDC Zone-A</div></div></div></body></html>"""
BASE_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>SmartFactory V8</title><link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}"><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head><body><div class="app-container"><aside class="sidebar"><div class="brand"><span class="brand-icon">⚡</span><h2>SmartFactory</h2></div><nav class="nav-menu"><a href="{{ url_for('dashboard') }}" class="nav-item {% if active_page == 'dashboard' %}active{% endif %}"><span>📊</span> Dashboard</a><a href="{{ url_for('machines') }}" class="nav-item {% if active_page == 'machines' %}active{% endif %}"><span>⚙️</span> Machines</a><a href="{{ url_for('reports') }}" class="nav-item {% if active_page == 'reports' %}active{% endif %}"><span>📑</span> Reports</a><a href="{{ url_for('alerts') }}" class="nav-item {% if active_page == 'alerts' %}active{% endif %}"><span>🔔</span> Alerts</a><a href="{{ url_for('analytics') }}" class="nav-item {% if active_page == 'analytics' %}active{% endif %}"><span>📈</span> Analytics</a><a href="{{ url_for('settings') }}" class="nav-item {% if active_page == 'settings' %}active{% endif %}"><span>⚙️</span> Settings</a><a href="{{ url_for('help_page') }}" class="nav-item {% if active_page == 'help' %}active{% endif %}"><span>❓</span> Help Guide</a></nav><div class="sidebar-footer"><a href="{{ url_for('logout') }}" class="logout-link"><span>🚪</span> Sign Out</a></div></aside><main class="main-content"><header class="top-bar"><div class="page-title"><h1>{% block title %}{% endblock %}</h1><p>Production Unit: Nagpur MIDC Zone-A</p></div><div class="action-area">{% block actions %}{% endblock %}</div></header><div class="content-scroll">{% block content %}{% endblock %}</div></main></div><script src="{{ url_for('static', filename='js/main.js') }}"></script>{% block scripts %}{% endblock %}</body></html>"""
DASHBOARD_HTML = """{% extends "base.html" %}{% block title %}Dashboard{% endblock %}{% block actions %}<div class="status-badge status-Good">● Live System</div><button onclick="simulateShift()" class="btn btn-glow"><span>⚡</span> Simulate Shift</button>{% endblock %}{% block content %}<div class="grid-4"><div class="glass-card"><span class="kpi-label">Plant Efficiency</span><h2 class="kpi-value text-grad" id="kpi-eff">--%</h2></div><div class="glass-card"><span class="kpi-label">Active Machines</span><h2 class="kpi-value" id="kpi-active">--</h2></div><div class="glass-card" style="border-color: rgba(245, 158, 11, 0.3);"><span class="kpi-label" style="color: #fbbf24;">Delayed Orders</span><h2 class="kpi-value" id="kpi-delay" style="color: #fbbf24;">--</h2></div><div class="glass-card" style="border-color: rgba(239, 68, 68, 0.3);"><span class="kpi-label" style="color: #f87171;">Bottleneck</span><h2 class="kpi-value" id="kpi-bottleneck" style="color: #f87171; font-size: 24px;">--</h2></div></div><div class="grid-2"><div class="glass-card" style="height: 380px;"><span class="kpi-label">Efficiency by Machine</span><div style="height: 300px; margin-top: 15px;"><canvas id="efficiencyChart"></canvas></div></div><div class="glass-card" style="height: 380px;"><span class="kpi-label">Utilization Breakdown</span><div style="height: 300px; margin-top: 15px;"><canvas id="utilizationChart"></canvas></div></div></div><div class="table-container"><div style="display:flex; justify-content:space-between; margin-bottom: 20px;"><span class="kpi-label">Live Production Status</span><span class="kpi-label">Updates every 5s</span></div><table><thead><tr><th>Machine Name</th><th>Status</th><th>Progress (Act/Plan)</th><th>Efficiency</th><th>Idle Time</th></tr></thead><tbody id="dashboard-table"></tbody></table></div>{% endblock %}{% block scripts %}<script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>{% endblock %}"""
REPORTS_HTML = """{% extends "base.html" %}{% block title %}Production Reports{% endblock %}{% block content %}<div class="glass-card"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;"><span class="kpi-label">Production Logs</span><a href="{{ url_for('download_csv') }}" class="btn btn-glow" style="padding: 8px 16px; font-size:12px; text-decoration:none;">Download CSV Report</a></div><table><thead><tr><th>Date</th><th>Machine</th><th>Planned</th><th>Actual</th><th>Runtime</th><th>Performance</th></tr></thead><tbody>{% for log in logs %}<tr><td style="color:var(--text-muted);">{{ log.date }}</td><td><strong>{{ log.machine_name }}</strong></td><td>{{ log.planned_qty }}</td><td>{{ log.actual_qty }}</td><td>{{ log.runtime_hours }} hrs</td><td>{% set eff = (log.actual_qty / log.planned_qty * 100)|round(1) if log.planned_qty > 0 else 0 %}<span class="status-badge {% if eff < 75 %}status-Critical{% else %}status-Good{% endif %}">{{ eff }}%</span></td></tr>{% endfor %}</tbody></table></div>{% endblock %}"""
ALERTS_HTML = """{% extends "base.html" %}{% block title %}System Alerts{% endblock %}{% block actions %}<button class="btn btn-glow" onclick="window.location.reload()">Refresh Stream</button>{% endblock %}{% block content %}<div class="grid-3"><div class="alert-card alert-critical"><div class="alert-icon">🚨</div><div><h4>Critical</h4><p class="alert-count">{{ c }}</p></div></div><div class="alert-card alert-warning"><div class="alert-icon">⚠️</div><div><h4>Warnings</h4><p class="alert-count">{{ w }}</p></div></div><div class="alert-card alert-info"><div class="alert-icon">ℹ️</div><div><h4>Info</h4><p class="alert-count">{{ i }}</p></div></div></div><div class="glass-card" style="margin-top: 24px;"><h3>Alert History</h3><div class="alert-list">{% for alert in alerts %}<div class="alert-item alert-{{ alert.severity }}" style="background: rgba(255,255,255,0.02); border-left: 4px solid; padding: 16px; border-radius: 8px; margin-bottom: 10px; border-color: {% if alert.severity == 'Critical' %}#ef4444{% elif alert.severity == 'Warning' %}#f59e0b{% else %}#6366f1{% endif %};"><div style="font-size:11px; color:#94a3b8; margin-bottom:5px;">{{ alert.created_at }}</div><div style="font-size:14px; margin-bottom:5px;">{{ alert.message }}</div><div style="font-size:12px; color:#94a3b8;">Source: {{ alert.machine_name }}</div></div>{% endfor %}</div></div>{% endblock %}"""
ANALYTICS_HTML = """{% extends "base.html" %}{% block title %}Performance Analytics{% endblock %}{% block content %}<div class="glass-card" style="height: 400px; margin-bottom: 24px;"><span class="kpi-label">7-Day Plant Efficiency Trend</span><div style="height: 320px; margin-top: 15px;"><canvas id="trendChart"></canvas></div></div><div class="grid-2"><div class="glass-card"><h3>Machine Rankings (All Time)</h3><table><thead><tr><th>Rank</th><th>Machine</th><th>Avg Efficiency</th><th>Performance Bar</th></tr></thead><tbody>{% for m in rankings %}<tr><td><strong>#{{ loop.index }}</strong></td><td>{{ m.name }}</td><td>{{ m.avg_eff }}%</td><td style="width:40%;"><div class="progress-bar"><div class="progress-fill" style="width: {{ m.avg_eff }}%; background: {% if m.avg_eff >= 90 %}#10b981{% elif m.avg_eff >= 75 %}#fbbf24{% else %}#ef4444{% endif %};"></div></div></td></tr>{% endfor %}</tbody></table></div><div class="glass-card"><h3>Downtime Distribution</h3><div style="height: 250px;"><canvas id="downtimeChart"></canvas></div></div></div><script>document.addEventListener('DOMContentLoaded', () => { new Chart(document.getElementById('trendChart'), { type: 'line', data: { labels: {{ trend_labels | tojson }}, datasets: [{ label: 'Avg Efficiency (%)', data: {{ trend_data | tojson }}, borderColor: '#6366f1', backgroundColor: 'rgba(99, 102, 241, 0.1)', fill: true, tension: 0.4 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, max: 100 } } } }); new Chart(document.getElementById('downtimeChart'), { type: 'pie', data: { labels: ['Maintenance', 'Material Shortage', 'Operator Unavailable', 'Setup Time'], datasets: [{ data: [30, 25, 15, 30], backgroundColor: ['#ef4444', '#f59e0b', '#6366f1', '#10b981'], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } } }); });</script>{% endblock %}"""
HELP_HTML = """{% extends "base.html" %}{% block title %}User Guide{% endblock %}{% block content %}<div class="grid-2"><div class="glass-card"><h3>🚀 Getting Started</h3><p style="color:#94a3b8; font-size:14px; line-height:1.6;">Welcome to SmartFactory. This system is designed to help MSMEs track production efficiency in real-time.<br><br><strong>Default Logins:</strong><br>• Admin: <code>admin</code> / <code>admin123</code><br>• Operator: <code>operator</code> / <code>operator123</code></p></div><div class="glass-card"><h3>📊 Understanding KPIs</h3><ul style="color:#94a3b8; font-size:14px; line-height:1.8; padding-left:20px;"><li><strong>Efficiency:</strong> (Actual Output / Planned Output) × 100</li><li><strong>Utilization:</strong> (Runtime Hours / 8 Hour Shift) × 100</li><li><strong>Bottleneck:</strong> The machine with the lowest efficiency.</li><li><strong>Status Colors:</strong> <span style="color:#10b981">Green (>75%)</span>, <span style="color:#ef4444">Red (<75%)</span>.</li></ul></div></div>{% endblock %}"""

STYLE_CSS = """@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap'); :root { --primary: #6366f1; --primary-dark: #4f46e5; --secondary: #8b5cf6; --bg-dark: #0f172a; --bg-panel: #1e293b; --text-main: #f8fafc; --text-muted: #94a3b8; --success: #10b981; --warning: #f59e0b; --danger: #ef4444; --border: rgba(255, 255, 255, 0.08); } * { box-sizing: border-box; transition: all 0.2s ease-in-out; } body { margin: 0; font-family: 'Outfit', sans-serif; background-color: var(--bg-dark); color: var(--text-main); height: 100vh; overflow: hidden; } .app-container { display: flex; height: 100%; } .sidebar { width: 280px; background: var(--bg-panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 24px; } .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 40px; padding-left: 10px; } .brand-icon { font-size: 24px; background: linear-gradient(135deg, var(--primary), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; } .brand h2 { margin: 0; font-size: 20px; } .nav-menu { flex: 1; display: flex; flex-direction: column; gap: 8px; } .nav-item { display: flex; align-items: center; gap: 14px; padding: 14px 18px; border-radius: 12px; color: var(--text-muted); text-decoration: none; font-weight: 500; } .nav-item:hover { background: rgba(255,255,255,0.03); color: var(--text-main); transform: translateX(5px); } .nav-item.active { background: linear-gradient(90deg, rgba(99, 102, 241, 0.15), transparent); color: var(--primary); border-left: 3px solid var(--primary); } .sidebar-footer { margin-top: auto; padding-top: 20px; border-top: 1px solid var(--border); } .logout-link { display: flex; align-items: center; gap: 10px; color: var(--danger); text-decoration: none; font-size: 14px; font-weight: 500; padding: 10px; border-radius: 8px; } .logout-link:hover { background: rgba(239, 68, 68, 0.1); } .main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; } .top-bar { padding: 24px 32px; display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(10px); border-bottom: 1px solid var(--border); z-index: 10; } .page-title h1 { margin: 0; font-size: 24px; font-weight: 600; } .page-title p { margin: 4px 0 0 0; color: var(--text-muted); font-size: 13px; } .action-area { display: flex; align-items: center; gap: 16px; } .btn { padding: 10px 20px; border-radius: 10px; border: none; font-weight: 600; cursor: pointer; font-family: 'Outfit', sans-serif; display: flex; align-items: center; gap: 8px; } .btn-glow { background: linear-gradient(135deg, var(--primary), var(--secondary)); color: white; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3); } .btn-glow:hover { box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5); transform: translateY(-1px); } .btn-danger { background: rgba(239, 68, 68, 0.1); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.2); } .content-scroll { padding: 32px; overflow-y: auto; flex: 1; } .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; margin-bottom: 32px; } .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-bottom: 32px; } .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; } .glass-card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 16px; padding: 24px; position: relative; overflow: hidden; } .glass-card::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: linear-gradient(90deg, var(--primary), transparent); opacity: 0.5; } .kpi-label { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); margin-bottom: 8px; display: block; } .kpi-value { font-size: 32px; font-weight: 700; margin: 0; color: white; } .text-grad { background: linear-gradient(to right, #fff, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; } .table-container { background: var(--bg-panel); border-radius: 16px; padding: 20px; border: 1px solid var(--border); } table { width: 100%; border-collapse: separate; border-spacing: 0 8px; } th { text-align: left; padding: 12px 16px; color: var(--text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; } td { background: rgba(255,255,255,0.02); padding: 16px; font-size: 14px; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); } td:first-child { border-left: 1px solid var(--border); border-top-left-radius: 8px; border-bottom-left-radius: 8px; } td:last-child { border-right: 1px solid var(--border); border-top-right-radius: 8px; border-bottom-right-radius: 8px; } .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; } .status-Good { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); } .status-Warning { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.2); } .status-Critical { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.2); } .login-body { display: flex; justify-content: center; align-items: center; background: radial-gradient(circle at top right, #1e1b4b, #0f172a); position: relative; } .login-container { width: 100%; max-width: 400px; padding: 20px; z-index: 10; } .glass-login-card { background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); padding: 40px; border-radius: 24px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); text-align: center; } .login-header { margin-bottom: 30px; } .brand-icon-large { font-size: 48px; margin-bottom: 10px; display: inline-block; background: linear-gradient(135deg, var(--primary), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; } .input-group { text-align: left; margin-bottom: 20px; } .input-group label { margin-bottom: 8px; display: block; font-size: 12px; text-transform: uppercase; color: var(--text-muted); } .input-group input, select { width:100%; padding:12px; background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); font-size: 16px; transition: 0.3s; color: white; border-radius:8px; } .input-group input:focus { border-color: var(--primary); box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1); background: rgba(15, 23, 42, 0.8); outline:none; } .full-width { width: 100%; justify-content: center; padding: 14px; font-size: 16px; margin-top: 10px; } .error-banner { background: rgba(239, 68, 68, 0.1); color: #fca5a5; padding: 12px; border-radius: 8px; font-size: 13px; margin-bottom: 20px; border: 1px solid rgba(239, 68, 68, 0.2); } .glow-orb { position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.4; z-index: 1; } .orb-1 { width: 300px; height: 300px; background: var(--primary); top: -50px; left: -50px; } .orb-2 { width: 400px; height: 400px; background: var(--secondary); bottom: -100px; right: -100px; } .alert-card { background: var(--bg-panel); border-radius: 12px; padding: 20px; display: flex; align-items: center; gap: 16px; border: 1px solid var(--border); } .alert-card.alert-critical { border-color: rgba(239, 68, 68, 0.3); } .alert-card.alert-warning { border-color: rgba(245, 158, 11, 0.3); } .alert-card.alert-info { border-color: rgba(99, 102, 241, 0.3); } .alert-icon { font-size: 32px; } .alert-count { font-size: 32px; font-weight: 700; margin: 5px 0 0 0; } .progress-bar { width: 100%; height: 8px; background: rgba(255,255,255,0.05); border-radius: 4px; overflow: hidden; } .progress-fill { height: 100%; border-radius: 4px; transition: width 0.3s; } @media (max-width: 1024px) { .grid-4, .grid-3 { grid-template-columns: 1fr 1fr; } .grid-2 { grid-template-columns: 1fr; } }"""
DASHBOARD_JS = """document.addEventListener('DOMContentLoaded', () => { fetchData(); setInterval(fetchData, 5000); Chart.defaults.color = '#94a3b8'; Chart.defaults.borderColor = 'rgba(255,255,255,0.05)'; }); let charts = {}; function fetchData() { fetch('/api/dashboard').then(r => r.json()).then(updateUI); } function simulateShift() { const btn = document.querySelector('.btn-glow'); btn.innerHTML = '<span>⚙️</span> Processing...'; fetch('/api/simulate').then(() => { fetchData(); setTimeout(() => btn.innerHTML = '<span>⚡</span> Simulate Shift', 500); }); } function updateUI(data) { const s = data.kpi_summary; document.getElementById('kpi-eff').textContent = s.avg_efficiency + '%'; document.getElementById('kpi-active').textContent = s.total_machines; document.getElementById('kpi-delay').textContent = s.delayed_orders; document.getElementById('kpi-bottleneck').textContent = s.bottleneck; const tbody = document.getElementById('dashboard-table'); tbody.innerHTML = ''; data.machines.forEach(m => { tbody.innerHTML += `<tr><td><strong>${m.name}</strong></td><td><span class="status-badge status-${m.status}">${m.status}</span></td><td><div style="display:flex; align-items:center; gap:8px;"><span style="font-size:12px; width:60px;">${m.actual_qty} / ${m.planned_qty}</span><div style="flex:1; height:4px; background:rgba(255,255,255,0.1); border-radius:2px;"><div style="width:${Math.min((m.actual_qty/m.planned_qty)*100, 100)}%; height:100%; background:${m.status === 'Critical' ? '#ef4444' : '#10b981'}; border-radius:2px;"></div></div></div></td><td><strong style="color:${m.status === 'Critical' ? '#ef4444' : '#10b981'}">${m.efficiency}%</strong></td><td>${m.idle_time}h</td></tr>`; }); updateCharts(data.machines); } function updateCharts(machines) { const labels = machines.map(m => m.name); if (charts.eff) charts.eff.destroy(); charts.eff = new Chart(document.getElementById('efficiencyChart'), { type: 'bar', data: { labels: labels, datasets: [{ label: 'Efficiency %', data: machines.map(m => m.efficiency), backgroundColor: machines.map(m => m.efficiency < 75 ? '#ef4444' : '#6366f1'), borderRadius: 4, barThickness: 30 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: { display: true, color: 'rgba(255,255,255,0.05)' } } } } }); if (charts.util) charts.util.destroy(); charts.util = new Chart(document.getElementById('utilizationChart'), { type: 'doughnut', data: { labels: labels, datasets: [{ data: machines.map(m => m.utilization), backgroundColor: ['#6366f1', '#8b5cf6', '#ec4899', '#10b981'], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, padding: 20 } } }, cutout: '75%' } }); }"""
MAIN_JS = "console.log('SmartFactory V8 Loaded');"

# ==========================================
# 4. ZIP BUILDER
# ==========================================

structure = {
    'smartfactory_v8/requirements.txt': "Flask==3.0.0\nWerkzeug==3.0.0",
    'smartfactory_v8/config.py': CONFIG_PY,
    'smartfactory_v8/app.py': APP_PY,
    'smartfactory_v8/database/__init__.py': "",
    'smartfactory_v8/database/db_manager.py': DB_MANAGER_PY,
    'smartfactory_v8/services/__init__.py': "",
    'smartfactory_v8/services/analytics_service.py': ANALYTICS_SERVICE_PY,
    'smartfactory_v8/templates/login.html': LOGIN_HTML,
    'smartfactory_v8/templates/base.html': BASE_HTML,
    'smartfactory_v8/templates/dashboard.html': DASHBOARD_HTML,
    'smartfactory_v8/templates/machines.html': MACHINES_HTML,
    'smartfactory_v8/templates/reports.html': REPORTS_HTML,
    'smartfactory_v8/templates/alerts.html': ALERTS_HTML,
    'smartfactory_v8/templates/analytics.html': ANALYTICS_HTML,
    'smartfactory_v8/templates/help.html': HELP_HTML,
    'smartfactory_v8/templates/settings.html': SETTINGS_HTML,
    'smartfactory_v8/static/css/style.css': STYLE_CSS,
    'smartfactory_v8/static/js/main.js': MAIN_JS,
    'smartfactory_v8/static/js/dashboard.js': DASHBOARD_JS,
}

zip_buffer = io.BytesIO()
with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
    for file_path, content in structure.items():
        zip_file.writestr(file_path, content)

with open("SmartFactory_Functional_V8.zip", "wb") as f:
    f.write(zip_buffer.getvalue())

print("✅ SUCCESS: 'SmartFactory_Functional_V8.zip' created!")
