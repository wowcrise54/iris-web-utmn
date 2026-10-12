import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'svelte/compiler';
const inventory = new Set(JSON.parse(fs.readFileSync('src/lib/i18n/inventory.json', 'utf8')));
const attrs = new Set(['title', 'placeholder', 'aria-label', 'alt', 'label', 'description', 'tooltip']);
const human = (value) => typeof value === 'string' && /[A-Za-z]/.test(value)
  && (/^[A-Z]/.test(value) || /\s[A-Za-z]/.test(value)) && !/^https?:|^\//.test(value);
function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? files(file) : file.endsWith('.svelte') ? [file] : [];
  });
}
let count = 0;
for (const file of files('src')) {
  const source = fs.readFileSync(file, 'utf8');
  if (!source.includes('const irisLocale = useLocale()')) continue;
  const ast = parse(source);
  const edits = new Map();
  function literal(node) {
    if (node?.type !== 'Literal' || !human(node.value)) return;
    inventory.add(node.value);
    edits.set(node.start, [node.start, node.end, `irisT(${JSON.stringify(node.value)}, $irisLocale)`]);
  }
  function expression(node) {
    if (!node) return;
    if (node.type === 'Literal') literal(node);
    if (node.type === 'ConditionalExpression') {
      expression(node.consequent);
      expression(node.alternate);
    }
  }
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'MustacheTag') expression(node.expression);
    if (node.type === 'Attribute' && attrs.has(node.name) && Array.isArray(node.value)) {
      node.value.filter((value) => value.type === 'MustacheTag').forEach((value) => expression(value.expression));
    }
    // Static toast text is UI, whereas error messages returned by the API remain data.
    if (node.type === 'CallExpression' && node.callee?.type === 'MemberExpression'
      && node.callee.object?.name === 'toast' && ['success', 'error', 'info', 'warning'].includes(node.callee.property?.name)) {
      literal(node.arguments[0]);
    }
    if (node.type === 'CallExpression' && node.callee?.name === 'irisT') return;
    for (const [key, value] of Object.entries(node)) {
      if (['loc', 'parent', 'start', 'end'].includes(key)) continue;
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value === 'object') walk(value);
    }
  }
  walk(ast.html);
  walk(ast.instance?.content);
  if (!edits.size) continue;
  let output = source;
  [...edits.values()].sort((a, b) => b[0] - a[0]).forEach(([start, end, value]) => {
    output = output.slice(0, start) + value + output.slice(end);
  });
  parse(output);
  fs.writeFileSync(file, output);
  count += edits.size;
}
fs.writeFileSync('src/lib/i18n/inventory.json', JSON.stringify([...inventory].sort(), null, 2) + '\n');
console.log(`Localized ${count} dynamic UI labels; ${inventory.size} source strings`);
