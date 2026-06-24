import unittest
import os
os.environ["GEMINI_API_KEY"] = "dummy-api-key-for-testing"
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

    @patch('requests.get')
    def test_stage1_scraper(self, mock_get):
        """Test if the scraper correctly identifies the PDF link from HTML."""
        mock_html = '<html><body><a class="btn-primary arquivo-pdf" href="/test.pdf">Download</a></body></html>'
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = mock_html
        
        link = fetch_daily_diary()
        self.assertEqual(link, 'https://www.valadares.mg.gov.br/test.pdf')

    @patch('processor.genai.Client')
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
    @patch('requests.get')
    @patch('processor.GeminiClient.process_pdf')
    def test_stage3_full_pipeline_logic(self, mock_process, mock_get, mock_fetch):
        """Test the integration: Detect change -> Process -> Save to DB."""
        # Setup mocks
        mock_fetch.return_value = "https://example.com/new_diary.pdf"
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

if __name__ == '__main__':
    unittest.main()