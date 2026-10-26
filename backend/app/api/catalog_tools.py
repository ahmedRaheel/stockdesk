"""SKU variant families and atomic, batch-traced pack/BOM production."""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, field_validator
from .contracts import Contract, Identifier, Quantity
from .router import User, authenticated
from .. import db, security, service
from ..rules import fail, business_date

router = APIRouter(prefix="/api/v1/tenants/{tenant}/catalog-tools", dependencies=[Depends(authenticated)], tags=["Catalog and assembly"])


def obj(value):
    return json.loads(value) if isinstance(value, str) else value


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class FamilyCreate(Contract):
    request: Identifier
    name: str = Field(min_length=1, max_length=100)
    axes: list[str] = Field(min_length=1, max_length=6)

    @field_validator("axes")
    @classmethod
    def valid_axes(cls, value):
        result = [x.strip().casefold() for x in value]
        if any(not x or len(x)>40 for x in result) or len(set(result)) != len(result):
            raise ValueError("Use distinct nonempty variant axes of at most 40 characters.")
        return result


class FamilyUpdate(Contract):
    version: int = Field(strict=True, ge=1)
    name: str = Field(min_length=1, max_length=100)
    active: bool = Field(strict=True)


class Variant(Contract):
    version: int = Field(strict=True, ge=0)
    attributes: dict[str, str] = Field(min_length=1, max_length=6)

    @field_validator("attributes")
    @classmethod
    def valid_attributes(cls, value):
        result = {k.strip().casefold(): v.strip() for k,v in value.items()}
        if len(result)!=len(value) or any(not k or len(k)>40 or not v or len(v)>100 for k,v in result.items()):
            raise ValueError("Variant attributes must be nonempty, distinct and within length limits.")
        return result


@router.get("/families")
async def families(tenant: str, user: User, q: str=Query("",max_length=100), offset: int=Query(0,ge=0,le=1000000)):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,"read")
        rows=await c.fetch("SELECT f.*,(SELECT count(*) FROM product_variants v WHERE v.tenant=f.tenant AND v.family=f.id) AS variants FROM product_families f WHERE tenant=$1 AND ($2='' OR strpos(lower(name),lower($2))>0) ORDER BY name,id LIMIT 50 OFFSET $3",tenant,q,offset)
        return {"items":[{**dict(r),"axes":obj(r["axes"])} for r in rows]}


@router.post("/families")
async def create_family(tenant: str, user: User, body: FamilyCreate, request: Request):
    security.csrf(request)
    digest=signature(body.model_dump(exclude={"request"}))
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"product",lock=True)
            prior=await c.fetchrow("SELECT * FROM product_families WHERE tenant=$1 AND request=$2",tenant,body.request)
            if prior:
                if prior["signature"]!=digest: fail("Submission ID already used for different data.",409)
                return {"id":prior["id"]}
            identifier=service.uid()
            await c.execute("INSERT INTO product_families(id,tenant,request,signature,name,axes) VALUES($1,$2,$3,$4,$5,$6)",identifier,tenant,body.request,digest,body.name,json.dumps(body.axes))
            await service.audit(c,tenant,user,"Variant family created",{"id":identifier,"name":body.name,"axes":body.axes})
            return {"id":identifier}


@router.put("/families/{identifier}")
async def update_family(tenant: str, identifier: str, user: User, body: FamilyUpdate, request: Request):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"product",lock=True)
            row=await c.fetchrow("UPDATE product_families SET name=$1,active=$2,version=version+1 WHERE tenant=$3 AND id=$4 AND version=$5 RETURNING version",body.name,body.active,tenant,identifier,body.version)
            if not row: fail("Variant family changed or was not found. Reload.",409)
            await service.audit(c,tenant,user,"Variant family updated",{"id":identifier,**body.model_dump()})
            return dict(row)


@router.get("/families/{identifier}")
async def family_detail(tenant: str, identifier: str, user: User, offset: int=Query(0,ge=0,le=1000000)):
    async with db.pool.acquire() as c:
        async with c.transaction(isolation="repeatable_read",readonly=True):
            await service.authorize(c,user,tenant,"read")
            family=await c.fetchrow("SELECT * FROM product_families WHERE tenant=$1 AND id=$2",tenant,identifier)
            if not family: fail("Variant family not found.",404)
            variants=await c.fetch("SELECT v.*,p.name,p.sku,p.barcode,p.price,p.stock,p.active FROM product_variants v JOIN products p ON p.tenant=v.tenant AND p.id=v.product WHERE v.tenant=$1 AND v.family=$2 ORDER BY p.sku,p.id LIMIT 50 OFFSET $3",tenant,identifier,offset)
            return {"family":{**dict(family),"axes":obj(family["axes"])},"items":[{**dict(v),"attributes":obj(v["attributes"])} for v in variants]}


@router.put("/families/{identifier}/variants/{product}")
async def assign_variant(tenant: str, identifier: str, product: str, user: User, body: Variant, request: Request):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"product",lock=True)
            family=await c.fetchrow("SELECT * FROM product_families WHERE tenant=$1 AND id=$2 AND active=true",tenant,identifier)
            if not family: fail("Active variant family not found.",404)
            if set(body.attributes)!=set(obj(family["axes"])): fail("Supply exactly the family's variant axes.")
            if not await c.fetchval("SELECT 1 FROM products WHERE tenant=$1 AND id=$2 AND active=true",tenant,product): fail("Active product not found.",404)
            old=await c.fetchrow("SELECT * FROM product_variants WHERE tenant=$1 AND product=$2",tenant,product)
            current_version=await c.fetchval("SELECT variant_revision FROM products WHERE tenant=$1 AND id=$2",tenant,product)
            if current_version!=body.version: fail("Variant assignment changed. Reload before saving.",409)
            combination=signature({k:v.casefold() for k,v in body.attributes.items()})
            if await c.fetchval("SELECT 1 FROM product_variants WHERE tenant=$1 AND family=$2 AND combination=$3 AND product<>$4",tenant,identifier,combination,product): fail("This variant combination already belongs to another SKU.",409)
            await c.execute("UPDATE products SET variant_revision=variant_revision+1 WHERE tenant=$1 AND id=$2",tenant,product)
            await c.execute("INSERT INTO product_variants(tenant,product,family,attributes,combination,version) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(tenant,product) DO UPDATE SET family=excluded.family,attributes=excluded.attributes,combination=excluded.combination,version=excluded.version",tenant,product,identifier,json.dumps(body.attributes),combination,body.version+1)
            await service.audit(c,tenant,user,"Product variant assigned",{"product":product,"family":identifier,"attributes":body.attributes,"previous":dict(old) if old else None})
            return {"version":body.version+1}


class Component(Contract):
    product: Identifier
    quantity: Quantity


class RecipeFields(Contract):
    name: str = Field(min_length=1,max_length=100)
    kind: Literal["bom","pack"]
    output: Identifier
    components: list[Component] = Field(min_length=1,max_length=50)
    active: bool = Field(default=True,strict=True)


class RecipeCreate(RecipeFields):
    request: Identifier


class RecipeUpdate(RecipeFields):
    version: int = Field(strict=True,ge=1)


class JobPreview(Contract):
    version: int = Field(strict=True,ge=1)
    direction: Literal["build","unpack"] = "build"
    quantity: Quantity
    lot: str = Field(min_length=1,max_length=80)
    expires: date | None = None
    note: str = Field(min_length=1,max_length=500)


class JobCommit(JobPreview):
    request: Identifier
    quote_token: Identifier


async def product_info(c,tenant,identifier):
    row=await c.fetchrow("SELECT p.*,u.fractional FROM products p JOIN lookups u ON u.tenant=p.tenant AND u.id=p.unit_id WHERE p.tenant=$1 AND p.id=$2 AND p.active=true",tenant,identifier)
    if not row: fail("Active product not found.",404)
    return row


def check_quantity(product, quantity):
    if quantity<=0 or quantity>Decimal('1000000000') or quantity.quantize(Decimal('.001'))!=quantity:
        fail("Assembly quantities must be positive, within one billion and have at most three decimals.")
    if not product["fractional"] and quantity!=quantity.to_integral_value(): fail("This product requires whole quantities.")


async def validate_recipe(c,tenant,body,identifier=None):
    components=body.components
    ids={r.product for r in components}
    if len(ids)!=len(components) or body.output in ids: fail("Recipe components must be distinct and cannot contain the output SKU.")
    if body.kind=="pack" and len(components)!=1: fail("A pack conversion requires exactly one component SKU.")
    await product_info(c,tenant,body.output)
    for component in components: check_quantity(await product_info(c,tenant,component.product),component.quantity)
    # Recipe graph validation is bounded by the tenant's defined recipes; execution
    # consumes stocked SKUs, never recursively manufactures a missing component.
    graph={r['output']:{x['product'] for x in obj(r['components'])} for r in await c.fetch("SELECT output,components FROM assembly_recipes WHERE tenant=$1 AND ($2::text IS NULL OR id<>$2)",tenant,identifier)}
    graph[body.output]=ids
    visited=set(); stack=[(body.output,False)]; active=set()
    while stack:
        node,exit_node=stack.pop()
        if exit_node: active.remove(node);visited.add(node);continue
        if node in active: fail("Recipe dependencies cannot contain a cycle.")
        if node in visited: continue
        active.add(node);stack.append((node,True))
        stack.extend((child,False) for child in graph.get(node,()))


@router.get("/recipes")
async def recipes(tenant: str,user: User,q: str=Query("",max_length=100),offset: int=Query(0,ge=0,le=1000000)):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,"stock")
        rows=await c.fetch("SELECT r.*,p.name AS output_name,p.sku AS output_sku FROM assembly_recipes r JOIN products p ON p.tenant=r.tenant AND p.id=r.output WHERE r.tenant=$1 AND ($2='' OR strpos(lower(r.name||' '||p.sku),lower($2))>0) ORDER BY r.name,r.id LIMIT 50 OFFSET $3",tenant,q,offset)
        return {"items":[{**dict(r),"components":obj(r['components'])} for r in rows]}


@router.get("/recipes/{identifier}")
async def recipe_detail(tenant: str,identifier: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,"stock")
        row=await c.fetchrow("SELECT r.*,p.name AS output_name,p.sku AS output_sku FROM assembly_recipes r JOIN products p ON p.tenant=r.tenant AND p.id=r.output WHERE r.tenant=$1 AND r.id=$2",tenant,identifier)
        if not row: fail("Recipe not found.",404)
        result={**dict(row),"components":obj(row['components'])}
        for component in result['components']:
            product=await c.fetchrow("SELECT name,sku FROM products WHERE tenant=$1 AND id=$2",tenant,component['product'])
            component.update(dict(product))
        return result


@router.post("/recipes")
async def create_recipe(tenant: str,user: User,body: RecipeCreate,request: Request):
    security.csrf(request)
    digest=signature(body.model_dump(mode="json",exclude={"request"}))
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"stock",lock=True)
            prior=await c.fetchrow("SELECT * FROM assembly_recipes WHERE tenant=$1 AND request=$2",tenant,body.request)
            if prior:
                if prior['signature']!=digest: fail("Submission ID already used for different data.",409)
                return {"id":prior['id']}
            await validate_recipe(c,tenant,body)
            identifier=service.uid()
            await c.execute("INSERT INTO assembly_recipes(id,tenant,request,signature,name,kind,output,components,active) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",identifier,tenant,body.request,digest,body.name,body.kind,body.output,json.dumps([x.model_dump(mode='json') for x in body.components]),body.active)
            await service.audit(c,tenant,user,"Assembly recipe created",{"id":identifier,**body.model_dump(mode='json')})
            return {"id":identifier}


@router.put("/recipes/{identifier}")
async def update_recipe(tenant: str,identifier: str,user: User,body: RecipeUpdate,request: Request):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,"stock",lock=True)
            prior=await c.fetchrow("SELECT * FROM assembly_recipes WHERE tenant=$1 AND id=$2",tenant,identifier)
            if not prior: fail("Recipe not found.",404)
            if prior['version']!=body.version: fail("Recipe changed. Reload before saving.",409)
            components=[x.model_dump(mode='json') for x in body.components]
            structural=body.kind!=prior['kind'] or body.output!=prior['output'] or components!=obj(prior['components'])
            if structural and await c.fetchval("SELECT 1 FROM assembly_jobs WHERE tenant=$1 AND recipe=$2",tenant,identifier):
                fail("A used recipe's conversion cannot change. Create a new output SKU and recipe.",409)
            if structural or body.active: await validate_recipe(c,tenant,body,identifier)
            await c.execute("UPDATE assembly_recipes SET name=$1,kind=$2,output=$3,components=$4,active=$5,version=version+1 WHERE tenant=$6 AND id=$7",body.name,body.kind,body.output,json.dumps(components),body.active,tenant,identifier)
            await service.audit(c,tenant,user,"Assembly recipe updated",{"id":identifier,**body.model_dump(mode='json')})
            return {"version":body.version+1}


async def prepare_job(c,tenant,identifier,body):
    recipe=await c.fetchrow("SELECT * FROM assembly_recipes WHERE tenant=$1 AND id=$2 AND active=true",tenant,identifier)
    if not recipe: fail("Active recipe not found.",404)
    if recipe['version']!=body.version: fail("Recipe changed. Reload before saving.",409)
    if body.direction=='unpack' and recipe['kind']!='pack': fail("Only pack recipes can be unpacked.")
    if body.expires and body.expires<business_date(): fail("Output expiry cannot be in the past.")
    components=obj(recipe['components'])
    inputs=components if body.direction=='build' else [{'product':recipe['output'],'quantity':'1'}]
    outputs=[{'product':recipe['output'],'quantity':'1'}] if body.direction=='build' else components
    result={'recipe':identifier,'name':recipe['name'],'kind':recipe['kind'],'version':recipe['version'],'inputs':[],'outputs':[],'input_catalog_cost':0}
    earliest=None
    for line in inputs:
        product=await product_info(c,tenant,line['product'])
        qty=Decimal(line['quantity'])*body.quantity
        check_quantity(product,qty)
        remaining=qty; allocations=[]
        for batch in await c.fetch("SELECT * FROM stock_batches WHERE tenant=$1 AND product=$2 AND stock>0 AND (expires IS NULL OR expires>=(now() AT TIME ZONE 'Asia/Karachi')::date) ORDER BY expires NULLS LAST,created,id",tenant,product['id']):
            take=min(remaining,batch['stock'])
            if take:
                allocations.append({'batch':batch['id'],'lot':batch['lot'],'expires':batch['expires'].isoformat() if batch['expires'] else None,'quantity':str(take)})
                if batch['expires']: earliest=min(earliest,batch['expires']) if earliest else batch['expires']
                remaining-=take
            if not remaining: break
        if remaining: fail("Insufficient non-expired component stock: "+product['sku'],409)
        from ..rules import line_amount
        cost=line_amount(product['cost'],qty)
        result['input_catalog_cost']+=cost
        result['inputs'].append({'product':product['id'],'name':product['name'],'sku':product['sku'],'quantity':str(qty),'catalog_cost':cost,'batches':allocations,'stock_revision':product['stock_revision']})
    if earliest and (not body.expires or body.expires>earliest): fail("Output expiry must not exceed the earliest consumed batch expiry.")
    for line in outputs:
        product=await product_info(c,tenant,line['product'])
        qty=Decimal(line['quantity'])*body.quantity
        check_quantity(product,qty)
        if product['expiry_required'] and not body.expires: fail("Batch number and expiry date are required.")
        result['outputs'].append({'product':product['id'],'name':product['name'],'sku':product['sku'],'quantity':str(qty)})
    result['earliest_input_expiry']=earliest.isoformat() if earliest else None
    result['quote_token']=signature({'tenant':tenant,'body':body.model_dump(mode='json',include=set(JobPreview.model_fields)),'result':result})
    return result,recipe


@router.post("/recipes/{identifier}/preview")
async def preview_job(tenant: str,identifier: str,user: User,body: JobPreview,request: Request):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction(isolation='repeatable_read',readonly=True):
            await service.authorize(c,user,tenant,'stock')
            return (await prepare_job(c,tenant,identifier,body))[0]


@router.post("/recipes/{identifier}/jobs")
async def commit_job(tenant: str,identifier: str,user: User,body: JobCommit,request: Request):
    security.csrf(request)
    digest=signature({'recipe':identifier,**body.model_dump(mode='json',exclude={'request'})})
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'stock',lock=True)
            prior=await c.fetchrow("SELECT * FROM assembly_jobs WHERE tenant=$1 AND request=$2",tenant,body.request)
            if prior:
                if prior['signature']!=digest: fail("Submission ID already used for different data.",409)
                return obj(prior['result'])
            result,recipe=await prepare_job(c,tenant,identifier,body)
            if result['quote_token']!=body.quote_token: fail("Component stock or recipe changed. Review a fresh preview.",409)
            identifier_job=service.uid(); movements=[]
            for line in result['inputs']:
                for batch in line['batches']:
                    mid=service.uid();movements.append(mid)
                    await c.execute("INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,batch_id) VALUES($1,$2,$3,$4,'OUT',$5,$6,$7)",mid,tenant,line['product'],-Decimal(batch['quantity']),'Assembly '+identifier_job,user['email'],batch['batch'])
            for line in result['outputs']:
                mid=service.uid();movements.append(mid)
                await c.execute("INSERT INTO movements(id,tenant,product,quantity,type,notes,actor,lot,expires) VALUES($1,$2,$3,$4,'IN',$5,$6,$7,$8)",mid,tenant,line['product'],Decimal(line['quantity']),'Assembly '+identifier_job,user['email'],body.lot,body.expires)
            result.update(id=identifier_job,direction=body.direction,quantity=str(body.quantity),lot=body.lot,expires=body.expires.isoformat() if body.expires else None,note=body.note,actor=user['email'],movements=movements,created=(await c.fetchval('SELECT now()')).isoformat())
            await c.execute("INSERT INTO assembly_jobs(id,tenant,recipe,request,signature,direction,quantity,snapshot,result,actor) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",identifier_job,tenant,identifier,body.request,digest,body.direction,body.quantity,json.dumps({**dict(recipe),'components':obj(recipe['components'])},default=str),json.dumps(result),user['email'])
            await service.audit(c,tenant,user,'Assembly posted',{'id':identifier_job,'recipe':identifier,'direction':body.direction,'movements':movements})
            return result


@router.get("/jobs")
async def jobs(tenant: str,user: User,offset: int=Query(0,ge=0,le=1000000)):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'stock')
        return {'items':[obj(r['result']) for r in await c.fetch('SELECT result FROM assembly_jobs WHERE tenant=$1 ORDER BY created DESC,id LIMIT 50 OFFSET $2',tenant,offset)]}

@router.get('/variants/{product}')
async def variant_assignment(tenant: str,product: str,user: User):
    async with db.pool.acquire() as c:
        await service.authorize(c,user,tenant,'read')
        row=await c.fetchrow("SELECT p.variant_revision,to_jsonb(v) AS assignment FROM products p LEFT JOIN product_variants v ON v.tenant=p.tenant AND v.product=p.id WHERE p.tenant=$1 AND p.id=$2",tenant,product)
        if not row: fail('Product not found.',404)
        return {'version':row['variant_revision'],'assignment':obj(row['assignment'])}


@router.delete('/families/{identifier}/variants/{product}')
async def remove_variant(tenant: str,identifier: str,product: str,user: User,request: Request,version: int=Query(ge=1)):
    security.csrf(request)
    async with db.pool.acquire() as c:
        async with c.transaction():
            await service.authorize(c,user,tenant,'product',lock=True)
            row=await c.fetchrow('DELETE FROM product_variants WHERE tenant=$1 AND family=$2 AND product=$3 AND version=$4 RETURNING *',tenant,identifier,product,version)
            if not row: fail('Variant assignment changed. Reload before saving.',409)
            await c.execute('UPDATE products SET variant_revision=variant_revision+1 WHERE tenant=$1 AND id=$2',tenant,product)
            await service.audit(c,tenant,user,'Product variant detached',dict(row))
            return {'ok':True}
