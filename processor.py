import io
import json
import time
from datetime import datetime
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY deve estar configurada no arquivo .env")
        self.client = genai.Client(api_key=self.api_key)

    def process_pdf(self, pdf_data, prompt="Resuma de forma detalhada e objetiva as principais decisões, nomeações e editais deste diário oficial. Importante: quantifique e conte todos os atos repetitivos (por exemplo, se houver rescisões de contrato ou nomeações, conte e informe o número total exato de servidores afetados em vez de usar termos vagos como 'muitos' ou 'vários'). VOCÊ DEVE RESPONDER APENAS EM PORTUGUÊS DO BRASIL. NÃO USE INGLÊS EM NENHUMA HIPÓTESE."):
        """
        Processes PDF bytes using Gemini with dynamic failover and in-memory streaming.
        """
        # Evita latência de rede consultando a API de modelos em ambiente serverless.
        gemini_models = [
            "gemini-3.1-pro-preview",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            
        ]

        # 1. Upload the file
        print("Enviando PDF para processamento em memória...")
        pdf_io = io.BytesIO(pdf_data)
        # We provide a config to help the API identify the file type since there is no filename
        uploaded_file = self.client.files.upload(
            file=pdf_io, 
            config={'mime_type': 'application/pdf', 'display_name': 'diary.pdf'}
        )
        
        # 2. Wait for processing
        while uploaded_file.state.name == "PROCESSING":
            print("Processando arquivo, aguardando...")
            time.sleep(1) # Reduced sleep for faster response
            uploaded_file = self.client.files.get(name=uploaded_file.name)

        last_error = None
        for model_name in gemini_models:
            try:
                clean_name = model_name.split('/')[-1]
                print(f"Tentando com o modelo: {clean_name}")
                
                response = self.client.models.generate_content(
                    model=clean_name,
                    contents=[uploaded_file, prompt]
                )
                
                # Clean up response from any accidental technical markers
                cleaned_text = response.text
                markers_to_remove = [
                    "[SYSTEM ERROR]", 
                    "(AI: fallback-logic)", 
                    "Summary fallback:",
                    "[API RATE LIMIT REACHED]"
                ]
                for marker in markers_to_remove:
                    cleaned_text = cleaned_text.replace(marker, "")
                
                # Check if response is empty or suspiciously short
                if not cleaned_text.strip():
                    continue

                # Clean up uploaded file
                self.client.files.delete(name=uploaded_file.name)
                return cleaned_text.strip(), clean_name
            except Exception as e:
                print(f"Erro no modelo {model_name}: {e}")
                last_error = e
                continue

        # Clean up
        try:
            self.client.files.delete(name=uploaded_file.name)
        except:
            pass
            
        return "Desculpe, não foi possível gerar o resumo automático no momento devido a limites de quota. Por favor, tente novamente mais tarde.", "indisponível"
