// Puerta de WhatsApp de Asistencia: un número propio (QR) que envía los avisos que le pide la app.
// Solo escucha en la red interna de compose y exige el token compartido (WA_GATEWAY_TOKEN).
const http = require('http');
const QRCode = require('qrcode');
const pino = require('pino');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');

const TOKEN = process.env.WA_GATEWAY_TOKEN || '';
const AUTH_DIR = process.env.WA_AUTH_DIR || '/data/auth';
let sock = null, qr = null, estado = 'desconectado';

// Contactos agregados en el teléfono (WhatsApp los entrega al vincular y cuando cambian). Se guardan junto a la sesión: al cerrarla se borran con ella.
const contactos = new Map(); // «569…@s.whatsapp.net» -> nombre
const ARCHIVO_CONTACTOS = () => AUTH_DIR + '/contactos.json';
let guardando = null;
function cargarContactos() { try { for (const [j, n] of JSON.parse(require('fs').readFileSync(ARCHIVO_CONTACTOS(), 'utf8'))) contactos.set(j, n); } catch { /* aún no hay */ } }
function anotarContactos(lista) {
  let cambio = false;
  for (const c of lista || []) {
    // Preferimos el número; si WhatsApp solo entrega el identificador interno (@lid) también sirve para enviar.
    const jid = [c.phoneNumber, c.id].find(x => typeof x === 'string' && x.endsWith('@s.whatsapp.net')) || [c.id, c.lid].find(x => typeof x === 'string' && x.endsWith('@lid'));
    const nombre = c.name || c.notify || c.verifiedName;
    if (jid && nombre && contactos.get(jid) !== nombre) { contactos.set(jid, nombre); cambio = true; }
  }
  if (cambio && !guardando) guardando = setTimeout(() => { guardando = null; try { require('fs').writeFileSync(ARCHIVO_CONTACTOS(), JSON.stringify([...contactos])); } catch (e) { console.error('[wa] no se guardaron los contactos', e.message); } }, 3000);
}

// /data/auth es un volumen montado: no se puede borrar la carpeta (EBUSY), solo su contenido.
function limpiarAuth() { const fs = require('fs'); for (const f of fs.readdirSync(AUTH_DIR)) fs.rmSync(AUTH_DIR + '/' + f, { recursive: true, force: true }); }

async function conectar() {
  estado = 'conectando';
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  sock = makeWASocket({ auth: state, logger: pino({ level: 'silent' }), printQRInTerminal: false });
  sock.ev.on('creds.update', saveCreds);
  cargarContactos();
  sock.ev.on('contacts.upsert', anotarContactos);
  sock.ev.on('contacts.update', anotarContactos);
  sock.ev.on('messaging-history.set', (h) => anotarContactos(h.contacts));
  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr: nuevo }) => {
    if (nuevo) qr = nuevo;
    if (connection === 'open') {
      estado = 'conectado'; qr = null; console.log('[wa] conectado');
      // La libreta de contactos solo llega al vincular; si falta (sesión anterior a esta función) se vuelve a pedir su estado de sincronización.
      if (contactos.size === 0) setTimeout(async () => {
        try { await sock?.resyncAppState(['critical_unblock_low'], true); } catch (e) { console.log('[wa] no se pudo pedir la libreta:', e.message || e); }
        console.log('[wa] contactos recibidos:', contactos.size);
      }, 8000);
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      sock = null; qr = null; estado = 'desconectado';
      console.log('[wa] cerrado, código', code);
      // Sesión cerrada desde el teléfono: se borra para pedir un QR nuevo; cualquier otro cierre reintenta.
      if (code === DisconnectReason.loggedOut) { limpiarAuth(); contactos.clear(); }
      setTimeout(() => conectar().catch(e => console.error('[wa]', e)), 5000);
    }
  });
}

// Un número (solo dígitos) va a su chat; un grupo llega ya como «…@g.us».
const jidDe = (t) => { const s = String(t || '').trim(); if (/^[0-9-]+@g\.us$/.test(s) || /^[0-9]{8,20}@(s\.whatsapp\.net|lid)$/.test(s)) return s; const d = s.replace(/\D/g, ''); return d.length >= 8 ? `${d}@s.whatsapp.net` : ''; };
const leer = (req) => new Promise((ok, no) => { let b = ''; req.on('data', c => { b += c; if (b.length > 20000) { no(new Error('grande')); req.destroy(); } }); req.on('end', () => ok(b)); });
const responder = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };

http.createServer(async (req, res) => {
  if (!TOKEN || req.headers.authorization !== `Bearer ${TOKEN}`) return responder(res, 401, { error: 'no autorizado' });
  try {
    if (req.method === 'GET' && req.url === '/estado') return responder(res, 200, { estado, hayQr: !!qr });
    if (req.method === 'GET' && req.url === '/qr') return responder(res, 200, { estado, qr: qr ? await QRCode.toDataURL(qr, { margin: 1, width: 320 }) : null });
    // Contactos agregados en el teléfono (para asignarles avisos). Llegan al vincular: si faltan, hay que volver a vincular.
    if (req.method === 'GET' && req.url === '/contactos') return responder(res, 200, { contactos: [...contactos].map(([id, nombre]) => ({ id, nombre })).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')) });
    // Los grupos en los que está el número (para asignarles avisos).
    if (req.method === 'GET' && req.url === '/chats') {
      if (estado !== 'conectado' || !sock) return responder(res, 503, { error: 'WhatsApp no está conectado' });
      const g = await sock.groupFetchAllParticipating();
      return responder(res, 200, { grupos: Object.values(g).map(x => ({ id: x.id, nombre: x.subject })).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')) });
    }
    // Corta la conexión: cierra la sesión en WhatsApp (el cierre borra las credenciales y deja listo un QR nuevo).
    if (req.method === 'POST' && req.url === '/desconectar') {
      const habia = !!sock;
      try { await sock?.logout(); } catch (e) { console.log('[wa] logout falló, se limpia igual:', e.message || e); }
      // Con socket, el cierre por logout ya limpia y reconecta (ver connection.update); sin socket se hace acá.
      if (!habia) { limpiarAuth(); contactos.clear(); qr = null; estado = 'desconectado'; conectar().catch(e => console.error('[wa]', e)); }
      return responder(res, 200, { ok: true });
    }
    if (req.method === 'POST' && req.url === '/enviar') {
      const { to, text } = JSON.parse(await leer(req));
      const jid = jidDe(to);
      if (!jid || !text) return responder(res, 400, { error: 'faltan to o text' });
      if (estado !== 'conectado' || !sock) return responder(res, 503, { error: 'WhatsApp no está conectado' });
      const m = await sock.sendMessage(jid, { text: String(text).slice(0, 4000) });
      return responder(res, 200, { ok: true, id: m?.key?.id ?? null });
    }
    responder(res, 404, { error: 'no existe' });
  } catch (e) { responder(res, 500, { error: String(e.message || e) }); }
}).listen(3000, () => console.log('[wa] puerta lista en :3000'));

// Un fallo suelto (p. ej. no poder guardar credenciales) se registra y no tumba la puerta.
process.on('unhandledRejection', (e) => console.error('[wa] error no controlado', e));
conectar().catch(e => console.error('[wa] no pudo iniciar', e));
