from database.db_manager import get_db_connection
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
