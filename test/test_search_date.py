import os
import unittest
from datetime import date
from unittest.mock import patch

os.environ['RECAPTCHA_SITE_KEY'] = ''
os.environ['RECAPTCHA_SECRET_KEY'] = ''
os.environ['GEMINI_API_KEY'] = 'dummy'
os.environ['POSTGRES_URL'] = 'sqlite:///test_search_date.db'
os.environ['FLASK_DEBUG'] = 'true'

from app import app, db, Post, User
from werkzeug.security import generate_password_hash


class TestSearchDateRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_search_date.db'
        app.config['TESTING'] = True
        cls.ctx = app.app_context()
        cls.ctx.push()
        db.drop_all()
        db.create_all()
        db.session.add(User(username='s', email='s@t.com',
                            password=generate_password_hash('pw'),
                            email_verified=True, is_paid=True))
        db.session.commit()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.drop_all()
        cls.ctx.pop()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['csrf_token'] = 'tok'
        return self.client.post('/login', data={
            'username': 's', 'password': 'pw', 'csrf_token': 'tok'
        }, follow_redirects=True)

    def test_search_date_creates_post(self):
        self._login()
        fake_pdf = 'https://example.com/diario-24-07-2026.pdf'
        with patch('app.search_diary_by_date',
                   return_value=(fake_pdf, date(2026, 7, 24))), \
             patch('app.requests.get') as get:
            get.return_value.content = b'pdf'
            with patch('processor.GeminiClient.process_pdf',
                       return_value=('raw text', 'gemini-x')), \
                 patch('app.parse_content',
                       return_value=('Title', 'Body', None, None)):
                r = self.client.post('/search-date', data={
                    'date': '2026-07-24', 'csrf_token': 'tok'
                }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        post = Post.query.filter_by(pdf_link=fake_pdf).first()
        self.assertIsNotNone(post)
        self.assertEqual(post.publication_date, date(2026, 7, 24))

    def test_search_date_not_found(self):
        self._login()
        with patch('app.search_diary_by_date', return_value=(None, None)):
            r = self.client.post('/search-date', data={
                'date': '2026-01-01', 'csrf_token': 'tok'
            }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Nenhum diário encontrado', r.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
