import os
from google import genai
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

def list_available_models():
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("ERRO: GEMINI_API_KEY não encontrada. Verifique seu arquivo .env ou variáveis de ambiente.")
        return

    print(f"Iniciando verificação com a chave: ...{api_key[-4:]}")
    
    try:
        client = genai.Client(api_key=api_key)
        print("Buscando modelos disponíveis...\n")
        
        models = client.models.list()
        
        count = 0
        for m in models:
            # Filtra apenas modelos que suportam geração de conteúdo
            if 'generateContent' in m.supported_actions:
                count += 1
                print(f"Modelo: {m.name}")
                print(f"  Nome de Exibição: {m.display_name}")
                print(f"  Versão: {m.version}")
                print("-" * 40)
        
        print(f"\nTotal de modelos de geração encontrados: {count}")
            
    except Exception as e:
        print(f"Ocorreu um erro ao acessar a API: {e}")

if __name__ == "__main__":
    list_available_models()