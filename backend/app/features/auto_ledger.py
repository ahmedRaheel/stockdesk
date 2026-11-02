"""Atomic double-entry postings for new retail sales and full invoice reversals.

Integer minor units only. The caller owns the tenant lock and DB transaction.
This is a starter chart of accounts; an accountant must map it to the local ledger.
"""
from ..service import uid
from ..rules import fail

ACCOUNTS = {
    '1000': ('Cash and settlement clearing','asset'),
    '1100': ('Customer receivables','asset'),
    '1200': ('Merchandise inventory','asset'),
    '2000': ('Sales tax payable','liability'),
    '2100': ('Supplier payables clearing','liability'),
    '2200': ('Customer refund payable','liability'),
    '4000': ('Retail sales revenue','income'),
    '5000': ('Cost of goods sold','expense'),
}


def sale_entries(total, paid, tax, cost):
    """Returns (account code, debit, credit) using non-negative minor units."""
    if any(not isinstance(v,int) or v<0 for v in (total,paid,tax,cost)) or paid>total or tax>total:
        fail('Invalid accounting posting amounts',409)
    lines = [('1000',paid,0),('1100',total-paid,0),
             ('4000',0,total-tax),('2000',0,tax),
             ('5000',cost,0),('1200',0,cost)]
    return [line for line in lines if line[1] or line[2]]


async def _accounts(c, tenant, codes):
    result={}
    for code in sorted(codes):
        name,kind=ACCOUNTS[code]
        row=await c.fetchrow('''INSERT INTO gl_accounts(id,tenant,code,name,kind)
            VALUES($1,$2,$3,$4,$5) ON CONFLICT(tenant,code)
            DO UPDATE SET code=excluded.code RETURNING id,kind,active''',uid(),tenant,code,name,kind)
        if not row['active'] or row['kind']!=kind:
            fail('GL account configuration incompatible with automated posting: '+code,409)
        result[code]=row['id']
    return result


async def _post(c,tenant,request,memo,reference,actor,lines):
    if sum(x[1] for x in lines)!=sum(x[2] for x in lines):
        fail('Automatic journal does not balance',409)
    if await c.fetchval('SELECT 1 FROM gl_journals WHERE tenant=$1 AND request=$2',tenant,request):
        return False
    accounts=await _accounts(c,tenant,{x[0] for x in lines})
    journal=uid()
    await c.execute('''INSERT INTO gl_journals(id,tenant,request,memo,reference,actor)
        VALUES($1,$2,$3,$4,$5,$6)''',journal,tenant,request,memo,reference,actor)
    for code,debit,credit in lines:
        await c.execute('''INSERT INTO gl_entries(journal,tenant,account,debit,credit)
            VALUES($1,$2,$3,$4,$5)''',journal,tenant,accounts[code],debit,credit)
    return True


async def post_sale(c,tenant,sale,invoice,actor,total,paid,tax,cost):
    return await _post(c,tenant,'sale:'+sale,'POS sale '+invoice,invoice,actor,
                       sale_entries(total,paid,tax,cost))


async def post_receipt(c,tenant,receipt,order,actor,cost):
    if not isinstance(cost,int) or cost<0:
        fail('Invalid receiving cost',409)
    if not cost:
        return False
    return await _post(c,tenant,'receipt:'+receipt,'Purchase receipt '+receipt,order,actor,
                       [('1200',cost,0),('2100',0,cost)])


async def reverse_sale(c,tenant,sale,invoice,actor):
    """Reverse revenue/COGS; paid funds become refund payable, not fictitious cash."""
    original=await c.fetchrow('SELECT id FROM gl_journals WHERE tenant=$1 AND request=$2',tenant,'sale:'+sale)
    if not original:
        return False  # Historical invoices require reviewed backfill.
    entries=await c.fetch('''SELECT a.code,e.debit,e.credit FROM gl_entries e
        JOIN gl_accounts a ON a.tenant=e.tenant AND a.id=e.account
        WHERE e.tenant=$1 AND e.journal=$2''',tenant,original['id'])
    if not entries:
        fail('Source journal has no entries',409)
    reversal=[]
    for e in entries:
        if e['code']=='1000':
            reversal.append(('2200',0,e['debit']))
        else:
            reversal.append((e['code'],e['credit'],e['debit']))
    return await _post(c,tenant,'sale-return:'+sale,
                       'Return and refund obligation '+invoice,invoice,actor,reversal)
