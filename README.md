# 🏭 SmartFactory – Manufacturing KPI & Efficiency Monitoring System

SmartFactory is a web-based Industry 4.0 dashboard designed to help **MSMEs** monitor production performance, identify bottlenecks, and make **data-driven operational decisions**.  
The system focuses on **manufacturing KPIs**, efficiency tracking, and real-time alerts using a lightweight, explainable backend.

🌍 **Aligned with UN SDG 9: Industry, Innovation & Infrastructure**

---

## 📌 Problem Statement

Many Micro, Small, and Medium Enterprises (MSMEs) still rely on manual tracking and fragmented tools to monitor production performance.  
This results in:
- Poor visibility into machine efficiency  
- Delayed identification of bottlenecks  
- Inefficient utilization of industrial resources  
- Reactive decision-making instead of proactive planning  

There is a strong need for a **simple, affordable, and deployable digital infrastructure** that enables MSMEs to adopt Industry 4.0 practices.

---

## 💡 Proposed Solution

SmartFactory provides a **centralized manufacturing performance monitoring system** that:
- Collects production and machine data
- Computes key manufacturing KPIs
- Detects bottlenecks and inefficiencies
- Generates alerts and actionable insights
- Presents all information through a clean industrial dashboard

The system is designed to be **lightweight, explainable, and deployable**, making it suitable for MSMEs.

---

## ⚙️ Key Features

### 🔐 Authentication & Roles
- Secure login system
- Role-based access:
  - **Admin / Factory Manager** – Full access
  - **Operator** – View-only access

### 📊 Manufacturing KPIs
- Production Efficiency (%)
- Machine Utilization (%)
- Idle Time
- Delay Percentage
- Bottleneck Machine Identification

### 🏭 Machine & Production Management
- Add and manage machines
- Define machine type and capacity
- Log planned vs actual production
- Track runtime hours per shift

### 🚨 Alerts & Insights
- Automatic alert generation when KPIs drop below thresholds
- Severity levels: Critical / Warning / Normal
- Clear, actionable recommendations

### 📈 Analytics & Reports
- Efficiency trends
- Machine-wise utilization charts
- Bottleneck rankings
- CSV report download for production data

### ⚙️ Configurable System
- Adjustable performance thresholds
- Shift duration configuration
- Factory profile settings

---

## 🧠 System Workflow (High-Level)

1. User logs into the system  
2. Production and machine data is stored in the database  
3. Backend engine calculates KPIs using rule-based logic  
4. Thresholds are applied to detect inefficiencies  
5. Alerts and insights are generated  
6. Data is visualized on the dashboard  
7. Reports can be exported for analysis  

---

## 🛠️ Tech Stack

### Frontend
- HTML
- CSS
- Vanilla JavaScript
- Chart.js

### Backend
- Python Flask
- Firebase database
- Session-based authentication

### Deployment
- Vercel

