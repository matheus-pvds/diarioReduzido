import requests
import bs4

url = 'https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1'
try:
    print(f"Buscando URL: {url}")
    response = requests.get(url, timeout=30)
    print(f"Status: {response.status_code}")
    soup = bs4.BeautifulSoup(response.text, "html.parser")
    
    # Try different selectors if the original one fails
    botao_pdf = soup.find('a', class_='btn-primary arquivo-pdf')
    print(f"Botão (class_='btn-primary arquivo-pdf'): {botao_pdf}")
    
    if not botao_pdf:
        # Fallback search - find any link that looks like a PDF diary
        pdf_links = [a for a in soup.find_all('a', href=True) if '.pdf' in a['href'].lower()]
        print(f"Outros links PDF encontrados: {len(pdf_links)}")
        for l in pdf_links[:3]:
            print(f"  - {l['href']}")
            
    link = botao_pdf['href'] if botao_pdf else None
    print(f"Link final: {link}")

except Exception as e:
    print(f"Erro: {e}")
