# Zayrah Life Backend
Complete backend for Zayrah Life's web application with management system.

---

## Prerequisite
- Python 3
- PostgreSQL 16

---

## 📦 Installation

### Clone the repository
```bash
git clone git@github.com:KrystalSoftwareBangladesh/ZayrahLife-Backend.git
cd ZayrahLife-Backend
```

### Install dependency
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### Environment Setup
```bash
cp .env.example ZayrahLifeBackend/env.py
```
And then update values based on your environment.

### Migration
```bash
python manage.py migrate
```

### Create Super User
```bash
python manage.py createsuperuser
```