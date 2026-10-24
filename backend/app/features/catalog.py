"""Catalog commands. Caller owns authorization and transaction scope."""

import re
from ..rules import clean, number, boolean, fail
from ..service import uid, audit


async def save_product(c, u, b, t=None):
    tenant = b.get("tenant", "")
    action = b.get("action")
    name = clean(b.get("name"), "Product name")
    category = clean(b.get("category"), "Category", 80)
    price = number(b.get("price"), "Price")
    cost = number(b.get("cost"), "Cost")
    reorder = number(b.get("reorder"), "Reorder point", 0, 1000000000)
    barcode = clean(b.get("barcode", ""), "Barcode", 60, optional=True) or None
    if barcode and (not re.fullmatch("[\\x20-\\x7e]+", barcode)):
        fail("Barcode must contain printable ASCII characters.")
    if action == "product":
        sku = clean(b.get("sku"), "SKU", 50).upper()
        if not re.fullmatch("[A-Z0-9][A-Z0-9._-]{0,49}", sku):
            fail("SKU must use letters, digits, dots, underscores or hyphens.")
        initial = number(b.get("initial"), "Opening stock", 0, 1000000000)
        pid = uid()
        if await c.fetchval(
            "SELECT 1 FROM products WHERE tenant=$1 AND (lower(sku)=lower($2) OR lower(barcode)=lower($2) OR ($3::text IS NOT NULL AND (lower(sku)=lower($3) OR lower(barcode)=lower($3))))",
            tenant,
            sku,
            barcode,
        ):
            fail("SKU or barcode already identifies another product.")
        await c.execute(
            "INSERT INTO products(id,tenant,sku,barcode,name,category,price,cost,reorder) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
            pid,
            tenant,
            sku,
            barcode,
            name,
            category,
            price,
            cost,
            reorder,
        )
        await c.execute(
            "INSERT INTO movements(id,tenant,product,quantity,type,notes,actor) VALUES($1,$2,$3,$4,'OPENING','Opening balance',$5)",
            uid(),
            tenant,
            pid,
            initial,
            u["email"],
        )
        await audit(c, tenant, u, "Product created", {"sku": sku, "initial": initial})
    else:
        pid = clean(b.get("id"), "Product ID", 100)
        if not await c.fetchval(
            "SELECT 1 FROM products WHERE tenant=$1 AND id=$2", tenant, pid
        ):
            fail("Product not found.", 404)
        if barcode and await c.fetchval(
            "SELECT 1 FROM products WHERE tenant=$1 AND id<>$2 AND (lower(sku)=lower($3) OR lower(barcode)=lower($3))",
            tenant,
            pid,
            barcode,
        ):
            fail("Barcode already identifies another product.")
        await c.execute(
            "UPDATE products SET name=$1,category=$2,barcode=$3,price=$4,cost=$5,reorder=$6,active=$7 WHERE tenant=$8 AND id=$9",
            name,
            category,
            barcode,
            price,
            cost,
            reorder,
            boolean(b.get("active")),
            tenant,
            pid,
        )
        await audit(c, tenant, u, "Product updated", {"id": pid})
    return {"id": pid, "ok": True}
