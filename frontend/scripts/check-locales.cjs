/** Detect missing translations for literal labels routed through tr()/field(). */
const ts=require('typescript'),fs=require('fs'),path=require('path');
const source=path.join(__dirname,'../src'),dictionary=JSON.parse(fs.readFileSync(path.join(source,'locales/ur.json'),'utf8'));
const literals=new Set(['StockDesk','PDF','HQ','IN','OUT','English']);let missing=[];
for(const file of fs.readdirSync(source).filter(f=>f.endsWith('.tsx'))){const text=fs.readFileSync(path.join(source,file),'utf8'),ast=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);function visit(n){if(ts.isCallExpression(n)&&['tr','field'].includes(n.expression.getText(ast))&&n.arguments[0]&&ts.isStringLiteral(n.arguments[0])){const s=n.arguments[0].text;if(!dictionary[s]&&!literals.has(s))missing.push(file+': '+s);}ts.forEachChild(n,visit);}visit(ast);}
if(missing.length){console.error(missing.join('\n'));process.exit(1);}console.log('Literal Urdu labels covered. Dynamic data and external errors are outside this check.');
