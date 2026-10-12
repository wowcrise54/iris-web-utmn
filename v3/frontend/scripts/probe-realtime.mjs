import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { io } from 'socket.io-client';
import * as Y from 'yjs';

const root = path.resolve('../..');
const env = Object.fromEntries(fs.readFileSync(path.join(root, '.env.v3.validation'), 'utf8').split(/\r?\n/)
  .filter((line) => line.includes('=')).map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));
const base = 'http://127.0.0.1:18084';
const login = await fetch(base + '/api/v2/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'administrator', password: env.IRIS_ADM_PASSWORD }) });
assert.equal(login.status, 200);
const data = await login.json();
const token = (data.data ?? data).tokens.access_token;
const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token };
const notesResponse = await fetch(base + '/api/v2/cases/2/notes', { headers });
const notesPayload = await notesResponse.json();
const existingNotes = notesPayload.data ?? notesPayload;
const directoryId = existingNotes[0].directory_id;
assert.ok(directoryId, 'A case-owned note directory is required');
const created = await fetch(base + '/api/v2/cases/2/notes', { method: 'POST', headers,
  body: JSON.stringify({ note_title: 'V3 transport acceptance', note_content: 'Initial probe note', directory_id: directoryId }) });
assert.equal(created.status, 201, await created.clone().text());
const note = await created.json();
const noteId = (note.data ?? note).note_id;
assert.ok(noteId);
const doc = `note:${noteId}`;
const wait = (socket, event, predicate = () => true) => new Promise((resolve, reject) => {
  const timer = setTimeout(() => { socket.off(event, onEvent); reject(new Error('Timed out waiting for ' + event)); }, 20000);
  function onEvent(value) { if (!predicate(value)) return; clearTimeout(timer); socket.off(event, onEvent); resolve(value); }
  socket.on(event, onEvent);
});
const connect = async () => {
  const socket = io(base + '/collab', { auth: { token }, transports: ['websocket'],
    extraHeaders: { Origin: 'https://localhost:18545' }, autoConnect: false, reconnection: false });
  const connected = wait(socket, 'connect');
  socket.connect();
  await connected;
  return socket;
};
const first = await connect();
const second = await connect();
try {
  let initial = wait(first, 'sync-init'); first.emit('join', { doc }); const snapshot = await initial;
  initial = wait(second, 'sync-init'); second.emit('join', { doc }); await initial;
  const ydoc = new Y.Doc();
  Y.applyUpdate(ydoc, Buffer.from(snapshot.y_state, 'base64'));
  const before = Y.encodeStateVector(ydoc);
  const paragraph = new Y.XmlElement('paragraph');
  ydoc.getXmlFragment('prosemirror').push([paragraph]);
  const text = new Y.XmlText(); paragraph.push([text]); text.insert(0, 'Native ASGI shared edit accepted');
  const delivered = wait(second, 'sync', (value) => value.doc === doc);
  first.emit('sync', { doc, update: Buffer.from(Y.encodeStateAsUpdate(ydoc, before)).toString('base64') });
  await delivered;
  const queueDelivered = wait(second, 'validation-cross-process');
  execFileSync('docker', ['exec', 'iris-v3-validation-20261010-worker-1', 'python', '-c',
    `from app import app, socket_io; socket_io.emit('validation-cross-process', {'ok': True}, namespace='/collab', room='${doc}')`],
    { stdio: 'pipe' });
  assert.deepEqual(await queueDelivered, { ok: true });
  first.emit('leave', { doc }); second.emit('leave', { doc });
  await new Promise((resolve) => setTimeout(resolve, 1500));
  const response = await fetch(base + `/api/v2/cases/2/notes/${noteId}`, { headers });
  assert.equal(response.status, 200);
  assert.match(JSON.stringify(await response.json()), /Native ASGI shared edit accepted/);
  console.log('Two-client Yjs edit, persistence and worker queue delivery passed');
} finally {
  first.disconnect(); second.disconnect();
  await fetch(base + `/api/v2/cases/2/notes/${noteId}`, { method: 'DELETE', headers });
}
