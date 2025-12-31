import sqlite3
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
