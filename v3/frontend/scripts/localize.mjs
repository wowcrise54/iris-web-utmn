import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'svelte/compiler';

const root = path.resolve('src');
const inventory = new Set();
const attributes = new Set(['title', 'placeholder', 'aria-label', 'alt', 'label', 'description', 'tooltip', 'emptyMessage']);
const fields = new Set(['label', 'title', 'placeholder', 'description', 'tooltip', 'emptyMessage', 'header']);
const isText = (text) => /[A-Za-z]{2}/.test(text) && !/^\s*(?:https?:|\/|#[0-9a-f]{3,8}$)/i.test(text);
const skip = new Set(['script', 'style', 'code', 'pre', 'svelte:head']);

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? files(file) : file.endsWith('.svelte') ? [file] : [];
  });
}

let changed = 0;
for (const file of files(root)) {
  if (file.endsWith(path.join('routes', '+layout.svelte')) || file.includes('LanguageSwitch.svelte')) continue;
  const source = fs.readFileSync(file, 'utf8');
  if (source.includes('const irisLocale = useLocale()')) continue;
  const ast = parse(source);
  const edits = [];
  const call = (text) => {
    inventory.add(text);
    return `irisT(${JSON.stringify(text)}, $irisLocale)`;
  };
  const walk = (node, parent, blocked = false) => {
    if (!node || typeof node !== 'object') return;
    blocked ||= skip.has(node.name);
    if (!blocked && node.type === 'Text' && parent?.type !== 'Attribute') {
      const value = node.data.trim();
      if (isText(value)) {
        const leading = node.data.match(/^\s*/)[0];
        const trailing = node.data.match(/\s*$/)[0];
        edits.push([node.start, node.end, `${leading}{${call(value)}}${trailing}`]);
      }
      return;
    }
    if (!blocked && node.type === 'Attribute' && attributes.has(node.name) && Array.isArray(node.value)
        && node.value.length === 1 && node.value[0].type === 'Text' && isText(node.value[0].data)) {
      const eq = source.indexOf('=', node.start);
      if (eq >= 0 && eq < node.end) edits.push([eq + 1, node.end, `{${call(node.value[0].data)}}`]);
      return;
    }
    for (const [key, value] of Object.entries(node)) {
      if (['parent', 'loc', 'start', 'end'].includes(key)) continue;
      if (Array.isArray(value)) value.forEach((child) => walk(child, node, blocked));
      else if (value && typeof value === 'object') walk(value, node, blocked);
    }
  };
  walk(ast.html, null);
  const walkScript = (node, parent) => {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'Literal' && typeof node.value === 'string' && isText(node.value)
        && parent?.type === 'Property' && parent.value === node && !parent.computed
        && fields.has(parent.key.name ?? parent.key.value)) {
      edits.push([node.start, node.end, call(node.value)]);
      return;
    }
    for (const [key, value] of Object.entries(node)) {
      if (['parent', 'loc', 'start', 'end'].includes(key)) continue;
      if (Array.isArray(value)) value.forEach((child) => walkScript(child, node));
      else if (value && typeof value === 'object') walkScript(value, node);
    }
  };
  walkScript(ast.instance?.content, null);
  if (!edits.length) continue;
  const inject = "\n\timport { translate as irisT, useLocale } from '$lib/i18n/context';\n\tconst irisLocale = useLocale();\n";
  if (ast.instance) {
    const start = source.indexOf('>', ast.instance.start) + 1;
    edits.push([start, start, inject]);
  } else edits.push([0, 0, `<script lang="ts">${inject}</script>\n`]);
  let output = source;
  edits.sort((a, b) => b[0] - a[0]).forEach(([start, end, value]) => {
    output = output.slice(0, start) + value + output.slice(end);
  });
  parse(output);
  fs.writeFileSync(file, output);
  changed++;
}
fs.mkdirSync('src/lib/i18n', { recursive: true });
fs.writeFileSync('src/lib/i18n/inventory.json', JSON.stringify([...inventory].sort(), null, 2) + '\n');
console.log(`Localized ${changed} components; ${inventory.size} source strings`);
