"""Untrusted legacy CSV mapping with explicit validation and fixed money precision."""
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from ..rules import fail

ALIASES={
 'products': {
  'sku':('sku','item_code','itemcode','product_code','productcode','stock_code','code'),
  'name':('name','product_name','item_name','item','title','description'),
  'barcode':('barcode','bar_code','ean','upc','gtin'),
  'price':('price','selling_price','sale_price','retail_price','mrp','unit_price'),
  'cost':('cost','purchase_price','buy_price','unit_cost','cost_price'),
  'initial':('initial','stock','opening_stock','qty','quantity','stock_on_hand','on_hand'),
  'reorder':('reorder','reorder_point','minimum_stock','min_stock'),
  'category_code':('category_code','category','group'),
  'unit_code':('unit_code','unit','uom'),
 },
 'customers': {
  'name':('name','customer','customer_name','client_name'),
  'phone':('phone','phone_number','mobile','mobile_number','contact','telephone'),
  'address':('address','customer_address'),
 },
 'suppliers': {
  'name':('name','supplier','supplier_name','vendor','vendor_name'),
  'contact':('contact','phone','email','supplier_contact','mobile'),
  'lead_days':('lead_days','lead_time_days','lead_time','days'),
 }
}


def normalize(header):
    return re.sub(r'[^a-z0-9]+','_',header.casefold().strip()).strip('_')


def parse_csv(text,kind):
    if not text.strip(): return []
    if len(text)>250_000: fail(f'{kind} CSV exceeds the 250 KB upload limit.',413)
    sample=text.lstrip('\ufeff')
    try:
        dialect=csv.Sniffer().sniff(sample[:2048],delimiters=',;\t')
    except csv.Error:
        dialect=csv.excel
    try:
        reader=csv.DictReader(io.StringIO(sample),dialect=dialect,strict=True)
        headers=reader.fieldnames
        if not headers or len(headers)>50: fail(f'{kind}: invalid or excessive headers.')
        keys=[normalize(k) for k in headers]
        if len(set(keys))!=len(keys): fail(f'{kind}: duplicate CSV header.')
        mapping={field:next((headers[keys.index(a)] for a in names if a in keys),None)
                 for field,names in ALIASES[kind].items()}
        required=['sku','name','price'] if kind=='products' else ['name']
        missing=[field for field in required if not mapping[field]]
        if missing: fail(f'{kind}: missing columns: '+', '.join(missing)+'.')
        result=[]
        for line,row in enumerate(reader,start=2):
            if len(result)>=200: fail(f'{kind}: import a maximum of 200 rows per batch.')
            if None in row or any(x is None for x in row.values()): fail(f'{kind} row {line}: invalid column count.')
            if not any(str(value).strip() for value in row.values()): continue
            obj={field:str(row[column] or '').strip() if column else '' for field,column in mapping.items()}
            obj['_row']=line
            if kind=='products':
                obj['sku']=obj['sku'].upper()
                if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,49}',obj['sku']): fail(f'products row {line}: invalid SKU.')
                if not obj['name'] or len(obj['name'])>150: fail(f'products row {line}: name length must be 1–150.')
                if len(obj['barcode'])>60: fail(f'products row {line}: barcode too long.')
                obj['price']=minor(obj['price'],f'products row {line} price')
                obj['cost']=minor(obj['cost'] or '0',f'products row {line} cost')
                for field,default in [('initial','0'),('reorder','5')]:
                    try: d=Decimal(obj[field] or default)
                    except InvalidOperation: fail(f'products row {line}: invalid {field}.')
                    if not d.is_finite() or d<0 or d>1_000_000 or d.as_tuple().exponent < -3:
                        fail(f'products row {line}: {field} must have at most 3 decimal places.')
                    obj[field]=d
                obj['category_code']=normalize(obj['category_code'] or 'general')
                obj['unit_code']=normalize(obj['unit_code'] or 'piece')
                if len(obj['category_code'])>60 or len(obj['unit_code'])>60: fail(f'products row {line}: invalid lookup code.')
            elif kind=='customers':
                if not obj['name'] or len(obj['name'])>150 or len(obj['phone'])>30 or len(obj['address'])>500:
                    fail(f'customers row {line}: invalid name, phone, or address.')
            else:
                if not obj['name'] or len(obj['name'])>150 or len(obj['contact'])>250:
                    fail(f'suppliers row {line}: invalid name or contact.')
                try: lead=int(obj['lead_days'] or '7')
                except ValueError: fail(f'suppliers row {line}: lead days must be an integer.')
                if not 0<=lead<=365: fail(f'suppliers row {line}: lead days out of range.')
                obj['lead_days']=lead
            result.append(obj)
    except (csv.Error,UnicodeError):
        fail(f'{kind}: malformed CSV file.')
    for column in (['sku'] if kind=='products' else ['name'] if kind=='suppliers' else []):
        items=[str(x[column]).casefold() for x in result]
        if len(items)!=len(set(items)): fail(f'{kind}: repeated {column} within the CSV file.')
    return result


def minor(value,label):
    try: amount=Decimal(value)
    except InvalidOperation: fail(f'{label}: invalid money value.')
    scaled=amount*100
    if not amount.is_finite() or amount<0 or scaled!=scaled.to_integral_value() or scaled>100_000_000_000:
        fail(f'{label}: use a positive money amount with at most 2 decimals.')
    return int(scaled)
