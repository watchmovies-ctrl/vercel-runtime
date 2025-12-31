from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
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
