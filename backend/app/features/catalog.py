"""Catalog commands. Caller owns authorization and transaction scope."""

import re
from ..rules import clean, number, boolean, fail, quantity
from ..service import uid, audit


async def save_product(c, u, b, t=None):
    tenant = b.get("tenant", "")
    action = b.get("action")
    name = clean(b.get("name"), "Product name")
    from .reference import lookup

    category_id = b.get("category_id")
    if category_id:
        selected = await lookup(c, tenant, category_id, "category")
        category = selected["name"]
    else:
        # Compatibility with old clients: resolve an existing label, never create one implicitly.
        category = clean(b.get("category"), "Category", 80)
        category_id = await c.fetchval(
            "SELECT id FROM lookups WHERE tenant=$1 AND kind='category' AND name=$2 AND active=true ORDER BY id LIMIT 1",
            tenant,
            category,
        )
        if not category_id:
            fail("Choose a category from Lookup Management.")
    unit_id = b.get("unit_id") or await c.fetchval(
        "SELECT id FROM lookups WHERE tenant=$1 AND kind='unit' AND code='piece' AND active=true",
        tenant,
    )
    unit = await lookup(c, tenant, unit_id, "unit")
    aliases = clean(b.get("search_aliases", ""), "Search aliases", 500, optional=True)
    price = number(b.get("price"), "Price")
    cost = number(b.get("cost"), "Cost")
    reorder = quantity(b.get("reorder"), "Reorder point")
    barcode = clean(b.get("barcode", ""), "Barcode", 60, optional=True) or None
    if barcode and (not re.fullmatch("[\\x20-\\x7e]+", barcode)):
        fail("Barcode must contain printable ASCII characters.")
    expiry_required = boolean(b.get("expiry_required", False))
    prescription_required = boolean(b.get("prescription_required", False))
    if action == "product":
        sku = clean(b.get("sku"), "SKU", 50).upper()
        if not re.fullmatch("[A-Z0-9][A-Z0-9._-]{0,49}", sku):
            fail("SKU must use letters, digits, dots, underscores or hyphens.")
        initial = quantity(b.get("initial"), "Opening stock")
        if not unit["fractional"] and initial != initial.to_integral_value():
            fail("This unit requires whole quantities.")
        if expiry_required and initial > 0:
            fail(
                "Create expiry-tracked products with zero opening stock, then receive a dated batch."
            )
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
        current_unit = await c.fetchval(
            "SELECT unit_id FROM products WHERE tenant=$1 AND id=$2", tenant, pid
        )
        if current_unit != unit_id:
            fail("Unit cannot be changed after product creation; create a new SKU.")
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
    if action == "editProduct":
        old = await c.fetchrow(
            "SELECT expiry_required,stock FROM products WHERE tenant=$1 AND id=$2",
            tenant,
            pid,
        )
        if old["expiry_required"] != expiry_required and old["stock"] > 0:
            fail("Expiry tracking can only change when stock is zero.")
    await c.execute(
        "UPDATE products SET expiry_required=$1,generic_name=$2,strength=$3,prescription_required=$4 WHERE tenant=$5 AND id=$6",
        expiry_required,
        clean(b.get("generic_name", ""), "Generic name", 150, True),
        clean(b.get("strength", ""), "Strength", 80, True),
        prescription_required,
        tenant,
        pid,
    )
    await c.execute(
        "UPDATE products SET category_id=$1,unit_id=$2,search_aliases=$3 WHERE tenant=$4 AND id=$5",
        category_id,
        unit_id,
        aliases,
        tenant,
        pid,
    )
    return {"id": pid, "ok": True}
