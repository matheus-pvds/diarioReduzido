from selenium import webdriver
from selenium.webdriver.common.by import By
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
    print("Loading page...")
    driver.get(url)
    time.sleep(5)

    # Get cookies
    cookies = driver.get_cookies()
    print(f"Got {len(cookies)} cookies")
    for c in cookies:
        print(f"  {c['name']}={c['value'][:30]}... domain={c.get('domain','')}")

    # Execute the search JavaScript
    print("\n=== Executing AjaxPro search ===")
    # First, let's find the AjaxPro proxy namespace
    result = driver.execute_script("""
        // Check what global AjaxPro namespaces exist
        var namespaces = [];
        for (var key in window) {
            if (key.includes('diel') || key.includes('AjaxPro')) {
                namespaces.push(key);
            }
        }
        return JSON.stringify(namespaces);
    """)
    print(f"AjaxPro namespaces: {result}")

    # Try to get the function definition
    result2 = driver.execute_script("""
        if (typeof diel_diel_lis !== 'undefined') {
            return Object.keys(diel_diel_lis).join(', ');
        }
        return 'NOT FOUND';
    """)
    print(f"diel_diel_lis methods: {result2}")

    # Try executing search via page's built-in function
    print("\n=== Trying to click on first edition date to trigger search ===")
    
    # Find all edition date elements
    date_links = driver.find_elements(By.CSS_SELECTOR, "a[data-date]")
    print(f"Date links with data-date: {len(date_links)}")
    
    # Check for specific date elements
    for el in driver.find_elements(By.CSS_SELECTOR, "span.dia, a.dia, td[data-date]"):
        print(f"Date element: tag={el.tag_name}, class={el.get_attribute('class')}, text={el.text.strip()}")
    
    # Full page HTML for date-related elements
    html = driver.page_source
    
    # Find the calendar/search HTML structure
    print("\n=== Search/Calendar HTML structure ===")
    # Look for input fields related to date
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input.date, input[data-date]"):
        name = inp.get_attribute("name") or "(no name)"
        id = inp.get_attribute("id") or "(no id)"
        placeholder = inp.get_attribute("placeholder") or ""
        print(f"Input: name={name}, id={id}, placeholder={placeholder}")
    
    # Check for jsFunction variable  
    result3 = driver.execute_script("""
        return JSON.stringify({
            jsFunction: typeof jsFunction !== 'undefined' ? jsFunction : 'NOT FOUND',
            PageSize: typeof PageSize !== 'undefined' ? PageSize : 'NOT FOUND',
            hdf_cdEdicaoAtual: typeof hdf_cdEdicaoAtual !== 'undefined' ? document.getElementById('hdf_cdEdicaoAtual')?.value : 'NOT FOUND'
        });
    """)
    print(f"\nJS vars: {result3}")
    
    # Try to understand the search function
    result4 = driver.execute_script("""
        var funcStr = '';
        if (typeof GetDiario === 'function') {
            funcStr = GetDiario.toString().substring(0, 500);
        } else {
            funcStr = 'GetDiario not defined as global function';
        }
        return funcStr;
    """)
    print(f"\nGetDiario function: {result4[:600]}")
    
    # Try returning the search results structure
    result5 = driver.execute_script("""
        var rows = document.querySelectorAll('[id*="rptDiario"]');
        return 'Found ' + rows.length + ' rows via selector';
    """)
    print(f"\nSearch results rows: {result5}")
    
    # Look at the search result container HTML
    containers = driver.find_elements(By.CSS_SELECTOR, "div[class*='resultado'], div[id*='resultado'], div[id*='lista'], div[class*='lista']")
    print(f"\nResult containers: {len(containers)}")

    # Get the page's HTML around the search results section
    body_html = driver.page_source
    # Find the search results
    for marker in ["Registros encontrados", "N\u00ba", "Edi\u00e7\u00f5es Anteriores", "VISUALIZAR ARQUIVO"]:
        idx = body_html.find(marker)
        if idx >= 0:
            snippet = body_html[max(0,idx-50):idx+300]
            print(f"\n--- Found '{marker}' at pos {idx} ---")
            print(snippet)

finally:
    driver.quit()
