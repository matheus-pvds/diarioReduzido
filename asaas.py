import os
import re
import requests
from datetime import datetime, timedelta

API_KEY = os.getenv('ASAAS_API_KEY', '')
BASE_URL = os.getenv('ASAAS_BASE_URL', 'https://sandbox.asaas.com/api/v3')

HEADERS = {
    'access_token': API_KEY,
    'Content-Type': 'application/json',
}

def create_customer(name, email, cpf_cnpj):
    payload = {
        'name': name,
        'email': email,
        'cpfCnpj': re.sub(r'\D', '', cpf_cnpj),
    }
    resp = requests.post(f'{BASE_URL}/customers', json=payload, headers=HEADERS, timeout=15)
    data = resp.json()
    if resp.status_code in (200, 201):
        return data['id']
    if resp.status_code == 422 and 'already' in str(data).lower():
        existing = find_customer_by_email(email)
        if existing:
            return existing
    raise Exception(f'Erro Asaas ao criar cliente: {data}')

def find_customer_by_email(email):
    resp = requests.get(f'{BASE_URL}/customers', params={'email': email}, headers=HEADERS, timeout=15)
    data = resp.json()
    if data.get('data') and len(data['data']) > 0:
        return data['data'][0]['id']
    return None

BILLING_TYPES = {'card': 'CREDIT_CARD', 'pix': 'PIX', 'boleto': 'BOLETO'}

def create_payment(customer_id, value, description, external_ref, billing_type='card', due_days=3, installments=1, callback_url=''):
    due_date = (datetime.now() + timedelta(days=due_days)).strftime('%Y-%m-%d')
    asaas_type = BILLING_TYPES.get(billing_type, 'CREDIT_CARD')
    payload = {
        'customer': customer_id,
        'billingType': asaas_type,
        'value': value,
        'dueDate': due_date,
        'description': description,
        'externalReference': str(external_ref),
    }
    if callback_url:
        payload['callbackUrl'] = callback_url
    if installments > 1 and asaas_type == 'CREDIT_CARD':
        payload['installmentCount'] = installments
        payload['installmentValue'] = round(value / installments, 2)
    resp = requests.post(f'{BASE_URL}/payments', json=payload, headers=HEADERS, timeout=15)
    data = resp.json()
    if resp.status_code in (200, 201):
        return data
    raise Exception(f'Erro Asaas ao criar pagamento: {data}')

def get_payment(payment_id):
    resp = requests.get(f'{BASE_URL}/payments/{payment_id}', headers=HEADERS, timeout=15)
    data = resp.json()
    if resp.status_code == 200:
        return data
    raise Exception(f'Erro Asaas ao buscar pagamento: {data}')

def process_webhook(payload):
    event = payload.get('event', '')
    payment = payload.get('payment', {}) or {}
    if event == 'PAYMENT_CONFIRMED':
        external_ref = payment.get('externalReference', '')
        if external_ref:
            parts = external_ref.split('_')
            if len(parts) >= 2:
                user_id = int(parts[0])
                return user_id
    return None
