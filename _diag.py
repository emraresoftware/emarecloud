"""Tanılama testi — session izolasyonu kontrolü"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['FLASK_ENV'] = 'development'

from app import create_app
from extensions import db

app, _ = create_app(config_overrides={
    'TESTING': True,
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
})

with app.app_context():
    from models import User
    op = User(username='op', email='op@test.com', role='operator')
    op.set_password('TestPass123!')
    db.session.add(op)
    db.session.commit()

    # Test 1: Login as admin
    c1 = app.test_client()
    c1.get('/login')
    with c1.session_transaction() as s:
        csrf = s.get('csrf_token', '')
    r = c1.post('/login', data={'username': 'admin', 'password': 'admin123', 'csrf_token': csrf}, follow_redirects=True)
    print(f'C1 admin login: {r.status_code}')

    # Test 2: Fresh client
    c2 = app.test_client()
    r2 = c2.get('/')
    print(f'C2 fresh GET /: {r2.status_code} (expect 302)')

    # Test 3: Login as operator
    c3 = app.test_client()
    c3.get('/login')
    with c3.session_transaction() as s3:
        csrf3 = s3.get('csrf_token', '')
    r3 = c3.post('/login', data={'username': 'op', 'password': 'TestPass123!', 'csrf_token': csrf3}, follow_redirects=True)
    print(f'C3 op login: {r3.status_code}')
    r3b = c3.get('/admin/users')
    print(f'C3 op admin/users: {r3b.status_code} (expect 403)')

print('--- DONE ---')
