from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time, json

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

driver = webdriver.Chrome(options=options)

try:
    url = "https://www.valadares.mg.gov.br/diario-eletronico/caderno/governador-valadares-mg/1"
    print(f"Navigating to {url}...")
    driver.get(url)
    time.sleep(5)
    
    page_source = driver.page_source
    print(f"Page title: {driver.title}")
    
    # Find PDF link for current edition
    print("\n=== Looking for current edition PDF link ===")
    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        href = link.get_attribute("href") or ""
        text = link.text.strip()
        if "abrir_arquivo" in href or href.endswith(".pdf"):
            print(f"PDF LINK: href={href}, text='{text}'")
        if "arquivo" in href.lower() or "pdf" in href.lower():
            print(f"CANDIDATE: href={href}, text='{text}', class='{link.get_attribute('class')}'")
    
    # Try all CSS selectors
    print("\n=== Trying CSS selectors ===")
    for sel in ["a.btn-primary.arquivo-pdf", "a.arquivo-pdf", "a.btn-primary", "a[href*='abrir_arquivo']", "a[href*='.pdf']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        print(f"  '{sel}': found {len(els)}")
        for el in els:
            print(f"    -> href={el.get_attribute('href')}, text='{el.text.strip()}', class='{el.get_attribute('class')}'")
    
    # Look for the search form
    print("\n=== Looking for search/previous editions section ===")
    sections = driver.find_elements(By.CSS_SELECTOR, "div[id*='diel'], div[class*='diel'], section[id*='pesquisa'], section[class*='pesquisa']")
    print(f"  diel/pesquisa sections: {len(sections)}")
    
    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
        print(f"  IFRAME: src={iframe.get_attribute('src')}")
    
    # Check for AjaxPro usage
    print("\n=== Checking for AjaxPro scripts ===")
    scripts = driver.find_elements(By.TAG_NAME, "script")
    for s in scripts:
        src = s.get_attribute("src") or ""
        if "ajaxpro" in src.lower():
            print(f"  AjaxPro script: {src}")
    
    # Try to find the search form in the page
    print("\n=== Page HTML snippets ===")
    html = driver.page_source
    # Look for common form patterns
    for marker in ["diel_diel_lis", "GetDiario", "pesquisar", "btnPesquisar", "dtSolicitada", "NUEDICAO"]:
        idx = html.find(marker)
        if idx >= 0:
            print(f"  Found '{marker}' at pos {idx}: ...{html[max(0,idx-100):idx+200]}...")
    
    # Find all form elements  
    print("\n=== Forms on page ===")
    forms = driver.find_elements(By.TAG_NAME, "form")
    print(f"  Total forms: {len(forms)}")
    for i, f in enumerate(forms):
        action = f.get_attribute("action") or "(none)"
        method = f.get_attribute("method") or "get"
        print(f"  Form #{i}: action='{action}', method='{method}'")
        inputs = f.find_elements(By.CSS_SELECTOR, "input, select, textarea, button")
        for inp in inputs[:10]:
            tag = inp.tag_name
            name = inp.get_attribute("name") or "(no name)"
            itype = inp.get_attribute("type") or ""
            val = inp.get_attribute("value") or ""
            print(f"    <{tag}> name='{name}' type='{itype}' value='{val[:50]}'")
    
    # Get the page's HTML around the current edition area
    print("\n=== Current Edition area ===")
    body_text = driver.find_element(By.TAG_NAME, "body").text[:2000]
    print(body_text)

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
finally:
    driver.quit()
