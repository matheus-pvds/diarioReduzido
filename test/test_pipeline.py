import unittest
import os
from datetime import date, datetime
os.environ["GEMINI_API_KEY"] = "dummy-api-key-for-testing"
os.environ["POSTGRES_URL"] = "sqlite:///:memory:"
from unittest.mock import patch, MagicMock
from app import app, db, Post, fetch_daily_diary, perform_update_logic
from processor import GeminiClient

class TestDiaryPipeline(unittest.TestCase):
    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        self.ctx = app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    @patch('requests.Session.get')
    def test_stage1_scraper(self, mock_get):
        """Test if the scraper correctly identifies the PDF link from HTML."""
        mock_html = '<html><body><a class="btn-primary arquivo-pdf" href="/test.pdf">Download</a></body></html>'
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = mock_html
        
        link, _ = fetch_daily_diary()
        self.assertEqual(link, 'https://www.valadares.mg.gov.br/test.pdf')

    @patch('google.genai.Client')
    def test_stage2_gemini_processing(self, mock_genai):
        """Test the Gemini client logic and model fallback."""
        # Mock the Gemini API response
        mock_client = MagicMock()
        mock_genai.return_value = mock_client
        
        mock_file = MagicMock()
        mock_file.state.name = "SUCCEEDED"
        mock_client.files.upload.return_value = mock_file
        
        mock_response = MagicMock()
        mock_response.text = "Resumo de teste"
        mock_client.models.generate_content.return_value = mock_response
        
        client = GeminiClient()
        summary, model = client.process_pdf(b"dummy pdf data content")
        
        self.assertEqual(summary, "Resumo de teste")
        self.assertIn("gemini", model)

    @patch('app.fetch_daily_diary')
    @patch('app.latest_diario_from_api')
    @patch('requests.get')
    @patch('processor.GeminiClient.process_pdf')
    def test_stage3_full_pipeline_logic(self, mock_process, mock_get, mock_latest, mock_fetch):
        """Test the integration: Detect change -> Process -> Save to DB."""
        # Setup mocks
        mock_latest.return_value = (3076, datetime(2026, 7, 24))
        mock_fetch.return_value = ("https://example.com/new_diary.pdf", None)
        mock_get.return_value.content = b"pdf content"
        mock_process.return_value = ("Sumário Final", "gemini-test-model")
        
        # 1. First run: Should create a post
        result = perform_update_logic()
        self.assertEqual(result['status'], 'success')
        
        post = Post.query.first()
        self.assertIsNotNone(post)
        self.assertEqual(post.pdf_link, "https://example.com/new_diary.pdf")
        self.assertEqual(post.content, "Sumário Final")

        # 2. Second run with same link: Should NOT process again
        result_no_change = perform_update_logic()
        self.assertEqual(result_no_change['status'], 'no_change')
        self.assertEqual(Post.query.count(), 1) # Still only 1 post

    def test_stage4_db_persistence(self):
        """Verify database model integrity."""
        post = Post(title="Test", content="Content", model="Model", pdf_link="link")
        db.session.add(post)
        db.session.commit()
        
        saved_post = Post.query.filter_by(title="Test").first()
        self.assertEqual(saved_post.content, "Content")

    def test_unique_pdf_link_constraint(self):
        """Same pdf_link must not be insertable twice."""
        from sqlalchemy.exc import IntegrityError
        db.session.add(Post(title="A", content="C1", model="m", pdf_link="same.pdf"))
        db.session.commit()
        db.session.add(Post(title="B", content="C2", model="m", pdf_link="same.pdf"))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        self.assertEqual(Post.query.count(), 1)

    def test_dedupe_posts_by_link(self):
        """Dedupe keeps one post per pdf_link (legacy schema without unique)."""
        from app import dedupe_posts_by_link
        from sqlalchemy import text
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE post RENAME TO post_legacy'))
            conn.execute(text('''CREATE TABLE post (
                id INTEGER NOT NULL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                summary TEXT,
                commentary TEXT,
                date DATETIME,
                publication_date DATE,
                model VARCHAR(100),
                pdf_link VARCHAR(500)
            )'''))
            conn.execute(text('DROP TABLE post_legacy'))
        db.session.add(Post(title="A", content="C1", model="m", pdf_link="dup.pdf"))
        db.session.add(Post(title="B", content="C2", model="m", pdf_link="dup.pdf"))
        db.session.commit()
        deleted = dedupe_posts_by_link()
        self.assertEqual(deleted, 1)
        self.assertEqual(Post.query.count(), 1)

if __name__ == '__main__':
    unittest.main()