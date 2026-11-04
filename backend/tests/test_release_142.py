"""Unit-level acceptance checks for bounded CSV mapping and auditable insights.

Full database and HTTP acceptance still require PostgreSQL + dependencies.
"""
from decimal import Decimal
from datetime import date
import pytest
from fastapi import HTTPException
from app.features.migration_parser import parse_csv, minor
from app.features.growth_insights import discount_flags, margin_flags, stock_actions, response_to_question


def test_legacy_product_columns_and_minor_currency():
    rows=parse_csv('Item Code,Item Name,Selling Price,Purchase Price,Stock on Hand\nP-100,Basmati Rice,123.45,95.10,12\n','products')
    assert rows[0]['sku']=='P-100'
    assert rows[0]['price']==12345
    assert rows[0]['cost']==9510
    assert rows[0]['initial']==Decimal(12)
    assert rows[0]['category_code']=='general'
    assert rows[0]['unit_code']=='piece'


def test_legacy_supplier_and_customer_columns():
    assert parse_csv('Vendor Name,Mobile,Lead Time\nVendor A,03001234567,4\n','suppliers')[0]['lead_days']==4
    customer=parse_csv('Customer Name,Mobile,Address\nAda,03001234567,Main Street\n','customers')[0]
    assert customer['name']=='Ada' and customer['address']=='Main Street'


def test_explicit_reject_of_invalid_money_and_duplicate_sku():
    with pytest.raises(HTTPException): minor('7.123','price')
    with pytest.raises(HTTPException): parse_csv('sku,name,price\nP001,A,10\nP001,B,20\n','products')


def test_reject_unbounded_quantity_and_invalid_phone_length():
    with pytest.raises(HTTPException): parse_csv('sku,name,price,quantity\nP-2,A,10,1000001\n','products')
    with pytest.raises(HTTPException): parse_csv('customer_name,phone\nJane,'+'1'*31+'\n','customers')


def test_discount_threshold_includes_exact_boundary():
    flagged=discount_flags([
      {'id':'1','invoice_number':'INV-1','actor':'owner','subtotal':10000,'discount':2000},
      {'id':'2','invoice_number':'INV-2','actor':'owner','subtotal':10000,'discount':1999},
      {'id':'3','invoice_number':'INV-3','actor':'owner','subtotal':0,'discount':0},
    ])
    assert [x['sale'] for x in flagged]==['1']


def test_margin_and_restock_flags_are_evidence_based():
    products=[{'id':'1','sku':'A','name':'A','price':200,'cost':250,'stock':Decimal('3.0'),'reorder':Decimal('4.0'),'active':True},
              {'id':'2','sku':'B','name':'B','price':300,'cost':250,'stock':Decimal('6.0'),'reorder':Decimal('4.0'),'active':True}]
    assert [x['product'] for x in margin_flags(products)]==['1']
    assert stock_actions(products)[0]['suggested_minimum']=='5.0'


def test_copilot_answer_does_not_claim_fraud():
    report={'period_days':30,'sales_count':12,'sales_total_minor':150000,'reorder':[],
      'leakage':{'discounts':[], 'below_cost':[]}}
    answer=response_to_question('Show profit leakage and discount fraud',report)
    assert answer['automated_actions_taken'] is False
    assert 'not proof of fraud' in answer['answer'].lower()


def test_empty_import_is_allowed_for_unused_dataset():
    assert parse_csv('','products')==[]
