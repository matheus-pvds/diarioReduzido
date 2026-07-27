import unittest
import os
import threading
import time
import re

os.environ['RECAPTCHA_SITE_KEY'] = ''
os.environ['RECAPTCHA_SECRET_KEY'] = ''
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

BASE = 'http://localhost:5777'
USER = 'tester'
PASS = '1234'
EMAIL = 't@t.com'


def solve_captcha(page_source):
        m = re.search(r'Quanto é (\d+)\s*([+-])\s*(\d+)\?', page_source)
        if not m:
                return '0'
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        return str(a + b if op == '+' else a - b)


class TestAllRoutes(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
                app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
                app.config['TESTING'] = True
                cls.ctx = app.app_context()
                cls.ctx.push()
                db.create_all()
                cls._seed_post()
                cls._start_server()
                cls._init_driver()
                cls._register_user()

        @classmethod
        def _seed_post(cls):
                cls.post = Post(
                        title='Teste Render',
                        content='# Header\n\n**bold** and *italic*\n\n- item1\n- item2',
                        model='gemini-2.5-flash',
                        pdf_link='https://example.com/test.pdf'
                )
                db.session.add(cls.post)
                db.session.commit()

        @classmethod
        def _start_server(cls):
                t = threading.Thread(
                        target=app.run, daemon=True,
                        kwargs={'port': 5777, 'debug': False, 'use_reloader': False}
                )
                t.start()
                time.sleep(2)

        @classmethod
        def _init_driver(cls):
                opts = Options()
                for a in ['--headless=new', '--no-sandbox',
                          '--disable-dev-shm-usage', '--window-size=1280,720']:
                        opts.add_argument(a)
                cls.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()), options=opts
                )
                cls.wait = WebDriverWait(cls.driver, 10)

        @classmethod
        def _register_user(cls):
                cls.driver.get(BASE + '/register')
                time.sleep(0.3)
                src = cls.driver.page_source
                cls.driver.find_element(By.NAME, 'username').send_keys(USER)
                cls.driver.find_element(By.NAME, 'email').send_keys(EMAIL)
                cls.driver.find_element(By.NAME, 'password').send_keys(PASS)
                cls.driver.find_element(By.NAME, 'confirm_password').send_keys(PASS)
                cls.driver.find_element(By.NAME, 'captcha').send_keys(solve_captcha(src))
                cls.driver.find_element(By.XPATH, "//button[@type='submit']").click()
                WebDriverWait(cls.driver, 10).until(
                        lambda d: '/dashboard' in d.current_url
                )
                cls.driver.get(BASE + '/logout')

        @classmethod
        def tearDownClass(cls):
                cls.driver.quit()
                db.drop_all()
                cls.ctx.pop()

        def setUp(self):
                db.session.rollback()
                p = Post.query.get(1)
                if not p:
                        db.session.add(Post(
                                title='Teste Render',
                                content='# Header\n\n**bold** and *italic*\n\n- item1\n- item2',
                                model='gemini-2.5-flash',
                                pdf_link='https://example.com/test.pdf'
                        ))
                        db.session.commit()
                self.driver.get(BASE + '/logout')

        # ————— helpers —————

        uid = 0

        def unique(self):
                type(self).uid += 1
                return str(type(self).uid)

        def go(self, path):
                self.driver.get(BASE + path)

        def find(self, by, value):
                return self.driver.find_element(by, value)

        def assert_text(self, text):
                self.assertIn(text, self.driver.page_source)

        def login(self):
                self.go('/login')
                time.sleep(0.3)
                src = self.driver.page_source
                self.find(By.NAME, 'username').send_keys(USER)
                self.find(By.NAME, 'password').send_keys(PASS)
                self.find(By.NAME, 'captcha').send_keys(solve_captcha(src))
                self.driver.execute_script("document.querySelector('form').submit()")
                self.wait.until(lambda d: '/dashboard' in d.current_url)

        def register_user(self):
                u = self.unique()
                self.go('/register')
                time.sleep(0.3)
                src = self.driver.page_source
                self.find(By.NAME, 'username').send_keys(f'u{u}')
                self.find(By.NAME, 'email').send_keys(f'{u}@t.com')
                self.find(By.NAME, 'password').send_keys(PASS)
                self.find(By.NAME, 'confirm_password').send_keys(PASS)
                self.find(By.NAME, 'captcha').send_keys(solve_captcha(src))
                self.find(By.XPATH, "//button[@type='submit']").click()
                self.wait.until(lambda d: '/dashboard' in d.current_url)
                return f'u{u}'

        def register_new_user(self, user, email, pw):
                self.go('/register')
                time.sleep(0.3)
                src = self.driver.page_source
                self.find(By.NAME, 'username').send_keys(user)
                self.find(By.NAME, 'email').send_keys(email)
                self.find(By.NAME, 'password').send_keys(pw)
                self.find(By.NAME, 'confirm_password').send_keys(pw)
                self.find(By.NAME, 'captcha').send_keys(solve_captcha(src))
                self.find(By.XPATH, "//button[@type='submit']").click()

        # ================================================================
        # PUBLIC ROUTES
        # ================================================================

        def test_index_title(self):
                self.go('/')
                self.assertIn('Diário de Valadares', self.driver.title)
                self.assert_text('O Diário Reduzido')
                self.assert_text('A síntese matinal do Diário Oficial')

        def test_index_article_metadata(self):
                self.go('/')
                for text in ['Teste Render', 'Inteligência Artificial',
                             'Portal da Transparência', 'example.com/test.pdf',
                             'gemini-2.5-flash', 'Todos os direitos reservados']:
                        self.assert_text(text)

        def test_index_markdown_renders_html(self):
                self.go('/')
                el = self.wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'article-content'))
                )
                self.assertTrue(el.is_displayed())
                html = el.get_attribute('innerHTML')
                for tag in ['<h1>', '<strong>', '<em>', '<ul>', '<li>']:
                        self.assertIn(tag, html)
                for word in ['Header', 'bold', 'italic', 'item1', 'item2']:
                        self.assertIn(word, html)

        def test_index_guest_links(self):
                self.go('/')
                self.assert_text('Entrar')
                self.assert_text('Criar conta')

        def test_index_pix_area(self):
                self.go('/')
                self.assert_text('Contribua com um PIX')
                btn = self.find(By.XPATH, "//button[contains(text(),'Copiar chave')]")
                self.assertTrue(btn.is_displayed())

        def test_index_no_post(self):
                Post.query.delete()
                db.session.commit()
                self.go('/')
                self.assert_text('Extraordinário')
                self.assert_text('O Diário de hoje ainda está sendo redigido')

        def test_index_check_interval_shown(self):
                self.go('/')
                raw = self.driver.page_source.lower()
                self.assertTrue('verificação' in raw or 'fim de semana' in raw)

        def test_login_form_fields(self):
                self.go('/login')
                for text in ['Usuário', 'Senha', 'Esqueci a senha',
                             'Novo por aqui?', 'Crie uma conta', 'Voltar ao início']:
                        self.assert_text(text)
                for name in ['username', 'password', 'captcha']:
                        self.assertTrue(self.find(By.NAME, name).is_displayed())

        def test_login_submit_btn(self):
                self.go('/login')
                btn = self.find(By.XPATH, "//button[@type='submit']")
                self.assertEqual(btn.text.strip().upper(), 'ENTRAR')

        def test_login_page_links(self):
                self.go('/login')
                cases = [('Crie uma conta', '/register'),
                         ('Esqueci a senha', '/forgot'),
                         ('Voltar ao início', '/')]
                for txt, href in cases:
                        with self.subTest(link=txt):
                                el = self.find(By.XPATH, f"//a[contains(text(),'{txt}')]")
                                self.assertIn(href, el.get_attribute('href'))

        def test_register_form_fields(self):
                self.go('/register')
                self.assertIn('Registrar', self.driver.title)
                for text in ['Usuário', 'E-mail', 'Senha', 'Confirmar senha',
                             'Já tem conta?', 'Entre aqui', 'Voltar ao início']:
                        self.assert_text(text)
                for name in ['username', 'email', 'password',
                             'confirm_password', 'captcha']:
                        self.assertTrue(self.find(By.NAME, name).is_displayed())

        def test_register_has_login_link(self):
                self.go('/register')
                el = self.find(By.XPATH, "//a[contains(text(),'Entre aqui')]")
                self.assertIn('/login', el.get_attribute('href'))

        def test_plans_cards_and_prices(self):
                self.go('/planos')
                self.assertIn('Planos', self.driver.title)
                self.assert_text('Escolha seu plano')
                for name, price in [('1 Dia', 'R$10'), ('1 Mês', 'R$30'),
                                    ('3 Meses', 'R$60'), ('6 Meses', 'R$60'),
                                    ('Anual', 'R$108')]:
                        with self.subTest(plan=name):
                                self.assert_text(name)
                                self.assert_text(price)
                btns = self.driver.find_elements(
                        By.XPATH, "//button[contains(text(),'Escolher')]"
                )
                self.assertEqual(len(btns), 5)

        def test_plans_perks(self):
                self.go('/planos')
                self.assert_text('Todos os planos incluem:')
                for perk in ['Favoritos ilimitados', 'Pedidos de datas ilimitados',
                             'Acesso completo ao arquivo', 'Sem anúncios']:
                        self.assert_text(perk)

        def test_plans_back_link(self):
                self.go('/planos')
                el = self.find(By.XPATH, "//a[contains(text(),'Página inicial')]")
                self.assertIn('/', el.get_attribute('href'))

        def test_forgot_has_form(self):
                self.go('/forgot')
                self.assertTrue(self.find(By.NAME, 'email').is_displayed())
                btn = self.find(By.XPATH, "//button[@type='submit']")
                self.assertTrue(btn.is_displayed())

        def test_coffee_to_planos(self):
                self.go('/coffee')
                self.wait.until(lambda d: '/planos' in d.current_url)
                self.assert_text('Escolha seu plano')

        def test_view_post_loads(self):
                self.go('/post/1')
                self.wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'article-content'))
                )
                for text in ['Teste Render', 'Inteligência Artificial',
                             'https://example.com/test.pdf']:
                        self.assert_text(text)

        def test_view_post_markdown(self):
                self.go('/post/1')
                el = self.wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'article-content'))
                )
                for tag in ['<h1>', '<strong>', '<ul>']:
                        self.assertIn(tag, el.get_attribute('innerHTML'))

        def test_pagamento_sucesso(self):
                self.go('/pagamento/sucesso')
                self.assert_text('Pagamento Confirmado!')

        def test_pagamento_falha(self):
                self.go('/pagamento/falha')
                self.assert_text('Falha no Pagamento')

        # ================================================================
        # PROTECTED ROUTES — anonymous
        # ================================================================

        def test_dashboard_requires_login(self):
                self.go('/dashboard')
                self.assertIn('/login', self.driver.current_url)

        def test_archive_requires_login(self):
                self.go('/archive')
                self.assertIn('/login', self.driver.current_url)

        def test_favorites_requires_login(self):
                self.go('/favorites')
                self.assertIn('/login', self.driver.current_url)

        # ================================================================
        # AUTH FLOW
        # ================================================================

        def test_register_then_login(self):
                u = self.unique()
                self.register_new_user(f'u{u}', f'{u}@t.com', PASS)
                self.wait.until(lambda d: '/dashboard' in d.current_url)
                self.go('/logout')
                self.go('/login')
                src = self.driver.page_source
                self.find(By.NAME, 'username').send_keys(f'u{u}')
                self.find(By.NAME, 'password').send_keys(PASS)
                self.find(By.NAME, 'captcha').send_keys(solve_captcha(src))
                self.find(By.XPATH, "//button[@type='submit']").click()
                self.wait.until(lambda d: '/dashboard' in d.current_url)
                self.assert_text('Painel')
                self.assert_text('Gratuito')

        def test_login_wrong_password(self):
                self.go('/login')
                time.sleep(0.3)
                src = self.driver.page_source
                self.find(By.NAME, 'username').send_keys(USER)
                self.find(By.NAME, 'password').send_keys('wrongpass')
                self.find(By.NAME, 'captcha').send_keys(solve_captcha(src))
                self.driver.execute_script("document.querySelector('form').submit()")
                time.sleep(0.5)
                self.assert_text('Credenciais inválidas')

        # ================================================================
        # PROTECTED ROUTES — authenticated
        # ================================================================

        def test_dashboard_content(self):
                self.login()
                for text in ['Painel', 'Diário mais recente',
                             'Buscar por data', 'Minha conta', 'Gratuito',
                             'Pontos de fidelidade', 'Seus pontos',
                             'Meta para 1 mês grátis']:
                        self.assert_text(text)

        def test_dashboard_latest_link(self):
                self.login()
                link = self.find(By.XPATH, "//a[contains(text(),'Ver edição')]")
                self.assertTrue(link.is_displayed())
                link.click()
                self.wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'article-content'))
                )

        def test_dashboard_search_form(self):
                self.login()
                self.assertTrue(self.find(By.NAME, 'date').is_displayed())
                btn = self.find(By.XPATH, "//button[contains(text(),'Buscar')]")
                self.assertTrue(btn.is_displayed())

        def test_dashboard_nav_links(self):
                self.login()
                cases = [('Página inicial', '/'), ('Arquivo', '/archive'),
                         ('Planos', '/planos'), ('Sair', '/logout')]
                for txt, href in cases:
                        with self.subTest(link=txt):
                                el = self.find(By.XPATH, f"//a[contains(text(),'{txt}')]")
                                self.assertIn(href, el.get_attribute('href'))

        def test_dashboard_has_planos_link(self):
                self.login()
                el = self.find(By.XPATH, "//a[contains(text(),'Ver planos')]")
                self.assertIn('/planos', el.get_attribute('href'))

        def test_archive_shows_posts(self):
                self.login()
                self.go('/archive')
                self.assert_text('Arquivo')
                self.assert_text('Teste Render')

        def test_favorites_page(self):
                self.login()
                self.go('/favorites')
                self.assert_text('Favoritos')

        def test_logout(self):
                self.login()
                self.go('/logout')
                self.assertIn('/', self.driver.current_url)

        def test_index_auth_links(self):
                self.login()
                self.go('/')
                self.assert_text('Arquivo')
                self.assert_text('Sair')

        def test_index_auth_search(self):
                self.login()
                self.go('/')
                self.assertTrue(self.find(By.NAME, 'date').is_displayed())
                btn = self.find(By.XPATH, "//button[contains(text(),'Buscar')]")
                self.assertTrue(btn.is_displayed())


if __name__ == '__main__':
        unittest.main()
