import unittest, os, threading, time
os.environ['GEMINI_API_KEY'] = 'dummy'
os.environ['POSTGRES_URL'] = 'sqlite:///:memory:'

from app import app, db, Post
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

class TestContentRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        cls.ctx = app.app_context()
        cls.ctx.push()
        db.create_all()

        post = Post(
            title='Teste Render',
            content='# Header\n\n**bold** and *italic*\n\n- item1\n- item2',
            model='test',
            pdf_link='https://example.com/test.pdf'
        )
        db.session.add(post)
        db.session.commit()

        cls.server_thread = threading.Thread(
            target=app.run, kwargs={'port': 5777, 'debug': False, 'use_reloader': False}, daemon=True
        )
        cls.server_thread.start()
        time.sleep(2)

        chrome_opts = Options()
        chrome_opts.add_argument('--headless=new')
        chrome_opts.add_argument('--no-sandbox')
        chrome_opts.add_argument('--disable-dev-shm-usage')
        chrome_opts.add_argument('--window-size=1280,720')
        service = Service(ChromeDriverManager().install())
        cls.driver = webdriver.Chrome(service=service, options=chrome_opts)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        db.drop_all()
        cls.ctx.pop()

    def test_body_text_is_rendered(self):
        self.driver.get('http://localhost:5777/')
        wait = WebDriverWait(self.driver, 15)
        content = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'article-content')))

        html = content.get_attribute('innerHTML')

        self.assertIn('<h1>', html, 'Markdown H1 should be rendered as <h1>')
        self.assertIn('Header', html, 'Header text should appear')
        self.assertIn('<strong>', html, 'Bold markdown should render <strong>')
        self.assertIn('<em>', html, 'Italic markdown should render <em>')
        self.assertIn('<ul>', html, 'List should render')
        self.assertIn('<li>', html, 'List items should render')
        self.assertTrue(content.is_displayed(), 'Content div should be visible')

if __name__ == '__main__':
    unittest.main()
