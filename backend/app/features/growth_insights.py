"""Explainable, deterministic retail insights; never claim estimated loss as proven fraud."""
from decimal import Decimal


def discount_flags(sales, threshold=Decimal("0.20")):
    flagged=[]
    for row in sales:
        subtotal,discount=int(row['subtotal']),int(row['discount'])
        if subtotal>0 and Decimal(discount)/Decimal(subtotal)>=threshold:
            flagged.append({"type":"high_discount","sale":row['id'],
                "invoice":row['invoice_number'],"actor":row['actor'],
                "discount":discount,"subtotal":subtotal,
                "discount_pct":round(discount/subtotal*100,1),
                "severity":"review", "reason":"Discount is at least 20% of invoice subtotal."})
    return sorted(flagged,key=lambda r:(-r['discount_pct'],r['invoice']))[:25]


def margin_flags(products):
    return [{"type":"below_cost_price","product":p['id'],"sku":p['sku'],"name":p['name'],
       "price":int(p['price']),"cost":int(p['cost']),"difference":int(p['cost'])-int(p['price']),
       "severity":"review","reason":"Current list price is below recorded unit cost."}
       for p in products if p['active'] and p['cost']>p['price']][:25]


def stock_actions(products):
    return [{"type":"reorder","product":p['id'],"sku":p['sku'],"name":p['name'],
      "stock":str(p['stock']),"reorder":str(p['reorder']),
      "suggested_minimum":str(max(Decimal(0),Decimal(str(p['reorder']))*2-Decimal(str(p['stock'])))),
      "reason":"Current stock is at or below its configured reorder threshold."}
      for p in products if p['active'] and Decimal(str(p['stock']))<=Decimal(str(p['reorder']))][:25]


def response_to_question(question, report):
    """Bounded intent routing using only source-backed statistics, not fabricated LLM answers."""
    q=question.lower().strip()
    if any(w in q for w in ("reorder","stock","inventory","purchase")):
        items=report['reorder'][:5]
        answer=f"{len(report['reorder'])} products are at or below their reorder level."
        evidence=items
        intent='stock'
    elif any(w in q for w in ("discount","fraud","leak","loss","margin","refund","return")):
        evidence=(report['leakage']['discounts']+report['leakage']['below_cost'])[:5]
        answer=f"Review {len(report['leakage']['discounts'])} unusually discounted invoices and {len(report['leakage']['below_cost'])} products priced below cost. These are signals, not proof of fraud."
        intent='leakage'
    else:
        evidence=[]
        answer=f"For the last {report['period_days']} days: {report['sales_count']} completed invoices and {report['sales_total_minor']} in recorded sales (minor currency units). {len(report['reorder'])} products need reorder review."
        intent='summary'
    return {"intent":intent,"answer":answer,"evidence":evidence,
            "method":"auditable_rules","automated_actions_taken":False}
