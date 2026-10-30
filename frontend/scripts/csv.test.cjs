const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const compiled=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/csv.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(compiled,context);
test('CSV protects formula strings including whitespace and keeps numeric losses',()=>{
 const csv=context.exports.csvText([['=SUM(1,2)',' \t+cmd','@name','-2',-2,'Urdu اردو','a"b',null]]);
 assert.equal(csv,'\uFEFF"\'=SUM(1,2)","\' \t+cmd","\'@name","\'-2","-2","Urdu اردو","a""b",""');
});
