const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');
const compiled = ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname,'../src/requestId.ts'),'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
function load(crypto) { const context={exports:{},crypto,Uint8Array}; vm.runInNewContext(compiled,context); return context.exports.newRequestId; }
test('uses native randomUUID with the correct receiver',()=>{
 const source={randomUUID(){assert.equal(this,source);return 'native-id';}};
 assert.equal(load(source)(),'native-id');
});
test('HTTP fallback uses random bytes and produces valid unique v4 IDs',()=>{
 const source={getRandomValues(bytes){assert.equal(this,source);return webcrypto.getRandomValues(bytes);}};
 const generate=load(source), ids=new Set();
 for(let i=0;i<10000;i++) {const id=generate();assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);ids.add(id);}
 assert.equal(ids.size,10000);
});
test('fallback sets version and variant bits without discarding other bytes',()=>{
 const generate=load({getRandomValues(bytes){bytes.fill(255);return bytes;}});
 assert.equal(generate(),'ffffffff-ffff-4fff-bfff-ffffffffffff');
});
test('unsupported browser reports an explicit error',()=>{
 assert.throws(load(undefined),/cannot generate request IDs/);
});
