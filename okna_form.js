// Windows & doors calculator (same price lookup as okna.py; the server recomputes everything on submit).
// Needs OKNA_CENIK (okna_cenik_2026.json) defined before this script.
const OKNA_TYPES = [
  {value: 'jednokridla', label: 'Okno', sub: '1-křídlé', door: false, svg: '<rect x="10" y="6" width="28" height="36" rx="2"/><rect x="14" y="10" width="20" height="28"/>'},
  {value: 'dvoukridla', label: 'Okno', sub: '2-křídlé', door: false, svg: '<rect x="7" y="6" width="34" height="36" rx="2"/><line x1="24" y1="8" x2="24" y2="40"/>'},
  {value: 'trojkridla', label: 'Okno', sub: '3-křídlé', door: false, svg: '<rect x="6" y="8" width="36" height="32" rx="2"/><line x1="18" y1="10" x2="18" y2="38"/><line x1="30" y1="10" x2="30" y2="38"/>'},
  {value: 'bd_jedno', label: 'Balk. dveře', sub: '1-křídlé', door: true, svg: '<rect x="14" y="4" width="20" height="40" rx="1"/><rect x="18" y="8" width="12" height="34"/>'},
  {value: 'bd_dvou', label: 'Balk. dveře', sub: '2-křídlé', door: true, svg: '<rect x="9" y="4" width="30" height="40" rx="1"/><line x1="24" y1="6" x2="24" y2="42"/>'},
  {value: 'vd_jedno', label: 'Vchod. dveře', sub: '1-křídlé', door: true, svg: '<rect x="14" y="4" width="20" height="40" rx="1"/><line x1="18" y1="20" x2="30" y2="20"/>'},
  {value: 'vd_dvou', label: 'Vchod. dveře', sub: '2-křídlé', door: true, svg: '<rect x="9" y="4" width="30" height="40" rx="1"/><line x1="24" y1="6" x2="24" y2="42"/><line x1="13" y1="20" x2="20" y2="20"/><line x1="28" y1="20" x2="35" y2="20"/>'},
];
const OKNA_SURFACES = [
  {value: 'Bila', label: 'Bílá', sub: '', swatch: '#ffffff'},
  {value: 'Dekor1str', label: 'Dekor', sub: '1-stranný', swatch: 'linear-gradient(90deg,#b5793b 50%,#fff 50%)'},
  {value: 'Dekor2str', label: 'Dekor', sub: '2-stranný', swatch: '#b5793b'},
];
const OKNA_BASIC = ['Montáž plastových výplní včetně systému parozábran', 'Demontáž oken - PVC',
                    'Likvidace oken a drobné suti', 'Zednické zapravení po montáži parozábran'];
const OKNA_SURFACE_LABEL = {Bila: 'bílá', Dekor1str: 'dekor 1-stranný', Dekor2str: 'dekor 2-stranný'};

let oknaItems = [];
let oknaEditIndex = null;
let oknaTyp = 'dvoukridla';
let oknaPovrch = 'Bila';
let oknaBasic = Object.fromEntries(OKNA_BASIC.map(n => [n, {on: true, manual: null}]));
let oknaDalsi = {};

function oknaEsc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function oknaKc(n) { return new Intl.NumberFormat('cs-CZ').format(Math.round(n)) + ' Kč'; }
function oknaPoint(v, pts) { for (let i = 0; i < pts.length; i++) if (pts[i] >= v) return i; return -1; }

function oknaVypln(povrch, typ, w, h) {
  const t = (OKNA_CENIK.windows[povrch] || {})[typ];
  if (!t) throw new Error('Neznámý typ výplně.');
  const i = oknaPoint(w, t.widths), j = oknaPoint(h, t.heights);
  if (i < 0 || j < 0) throw new Error('Rozměr ' + w + '×' + h + ' mm je mimo rozsah ceníku (max ' + t.widths[t.widths.length - 1] + '×' + t.heights[t.heights.length - 1] + ' mm).');
  return {cena: t.grid[j][i], bod: t.widths[i] + '×' + t.heights[j]};
}
function oknaParapetZaMetr(skupina, hloubka) {
  const t = OKNA_CENIK.accessories.parapet_pvc_interier, i = oknaPoint(hloubka, t.depths);
  if (i < 0) throw new Error('Hloubka parapetu je nad rozsahem ceníku.');
  return (skupina === 2 ? t.g2 : t.g1)[i];
}
function oknaStineni(druh, w, h) {
  const t = OKNA_CENIK.accessories[druh], i = oknaPoint(w, t.widths), j = oknaPoint(h, t.heights);
  if (i < 0 || j < 0) throw new Error('Rozměr ' + w + '×' + h + ' mm je mimo rozsah ceníku (' + (druh === 'zaluzie' ? 'žaluzie' : 'síť') + ').');
  return t.grid[j][i];
}
function oknaWork(name) { return OKNA_CENIK.work.find(w => w.nazev === name); }
function oknaObvod() { return Math.round(10 * oknaItems.reduce((s, it) => s + 2 * (it.sirka + it.vyska) / 1000 * it.ks, 0)) / 10; }
function oknaBasicQty(name) {
  const st = oknaBasic[name];
  if (!st || !st.on) return 0;
  return st.manual !== null && st.manual !== '' ? (Number(st.manual) || 0) : oknaObvod();
}
function oknaItemAccessories(it) {
  let s = 0;
  if (it.parapet) s += Math.round(oknaParapetZaMetr(it.parapet.skupina, it.parapet.hloubka) * it.parapet.delkaM);
  if (it.zaluzie) s += oknaStineni('zaluzie', it.zaluzie.sirka, it.zaluzie.vyska);
  if (it.sit) s += oknaStineni('site', it.sit.sirka, it.sit.vyska);
  return s;
}
function oknaItemTotal(it) { return (oknaVypln(it.povrch, it.typ, it.sirka, it.vyska).cena + oknaItemAccessories(it)) * it.ks; }

// Same lines as okna.lines() on the server: [{price (per unit, without VAT), qty}]
function oknaLines() {
  const rows = [];
  oknaItems.forEach(it => {
    rows.push({price: oknaVypln(it.povrch, it.typ, it.sirka, it.vyska).cena, qty: it.ks});
    if (it.parapet) rows.push({price: oknaParapetZaMetr(it.parapet.skupina, it.parapet.hloubka), qty: oknaR2(it.parapet.delkaM * it.ks)});
    if (it.zaluzie) rows.push({price: oknaStineni('zaluzie', it.zaluzie.sirka, it.zaluzie.vyska), qty: it.ks});
    if (it.sit) rows.push({price: oknaStineni('site', it.sit.sirka, it.sit.vyska), qty: it.ks});
  });
  OKNA_BASIC.forEach(n => { const q = oknaBasicQty(n); if (q > 0) rows.push({price: oknaWork(n).cena, qty: q}); });
  Object.entries(oknaDalsi).forEach(([n, q]) => { const w = oknaWork(n); if (w && q > 0) rows.push({price: w.cena, qty: q}); });
  return rows;
}
function oknaR2(x) { return Math.round((x + (x >= 0 ? 1e-9 : -1e-9)) * 100) / 100; }

// Totals without VAT (exactly as Odoo will compute the lines: unit price / 0.97, 3 % off, rounded per line),
// area (m²) for the grant, and whether there are windows / doors.
function oknaTotals() {
  let area = 0, hasDoors = false, hasWindows = false;
  oknaItems.forEach(it => {
    area += it.sirka * it.vyska / 1e6 * it.ks;
    if (OKNA_TYPES.find(t => t.value === it.typ).door) hasDoors = true; else hasWindows = true;
  });
  const excl = oknaR2(oknaLines().reduce((s, r) => s + oknaR2(oknaR2(r.price / 0.97) * 0.97 * r.qty), 0));
  return {excl: excl, area: area, count: oknaItems.length, hasDoors: hasDoors, hasWindows: hasWindows};
}

function oknaEditorItem() {
  const val = id => document.getElementById(id).value;
  const it = {typ: oknaTyp, povrch: oknaPovrch, sklo: (document.querySelector('input[name=okna_sklo]:checked') || {}).value || 'trojsklo',
              sirka: Number(val('okna_sirka')), vyska: Number(val('okna_vyska')), ks: Math.max(1, Number(val('okna_ks')) || 1),
              parapet: null, zaluzie: null, sit: null};
  if (document.getElementById('okna_parapet_on').checked && Number(val('okna_parapet_delka')) > 0)
    it.parapet = {hloubka: Number(val('okna_parapet_hloubka')), skupina: Number(val('okna_parapet_skupina')), delkaM: Number(val('okna_parapet_delka'))};
  if (document.getElementById('okna_zaluzie_on').checked && Number(val('okna_zaluzie_sirka')) && Number(val('okna_zaluzie_vyska')))
    it.zaluzie = {sirka: Number(val('okna_zaluzie_sirka')), vyska: Number(val('okna_zaluzie_vyska'))};
  if (document.getElementById('okna_sit_on').checked && Number(val('okna_sit_sirka')) && Number(val('okna_sit_vyska')))
    it.sit = {sirka: Number(val('okna_sit_sirka')), vyska: Number(val('okna_sit_vyska'))};
  return it;
}

function oknaRenderTiles() {
  document.getElementById('okna-types').innerHTML = OKNA_TYPES.map(t =>
    '<button type="button" class="okna-tile' + (t.value === oknaTyp ? ' on' : '') + '" onclick="oknaTyp=\'' + t.value + '\';oknaRenderTiles();oknaEditorChanged()">' +
    '<svg viewBox="0 0 48 48" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">' + t.svg + '</svg>' +
    '<b>' + t.label + '</b><small>' + t.sub + '</small></button>').join('');
  document.getElementById('okna-surfaces').innerHTML = OKNA_SURFACES.map(s =>
    '<button type="button" class="okna-tile' + (s.value === oknaPovrch ? ' on' : '') + '" onclick="oknaPovrch=\'' + s.value + '\';oknaRenderTiles();oknaEditorChanged()">' +
    '<span class="okna-swatch" style="background:' + s.swatch + '"></span><b>' + s.label + '</b><small>' + s.sub + '</small></button>').join('');
}

function oknaEditorChanged() {
  const it = oknaEditorItem();
  const priceEl = document.getElementById('okna-price');
  if (!it.sirka || !it.vyska) { priceEl.className = 'okna-price'; priceEl.textContent = 'Zadejte rozměr'; }
  else {
    try {
      const v = oknaVypln(it.povrch, it.typ, it.sirka, it.vyska);
      priceEl.className = 'okna-price';
      priceEl.innerHTML = 'Cena výplně <b>' + oknaKc(v.cena) + '</b> <small>/ ks bez DPH · rozměr → ' + v.bod + '</small>';
    } catch (e) { priceEl.className = 'okna-price warn'; priceEl.textContent = '⚠ ' + e.message; }
  }
  [['parapet', () => it.parapet && Math.round(oknaParapetZaMetr(it.parapet.skupina, it.parapet.hloubka) * it.parapet.delkaM)],
   ['zaluzie', () => it.zaluzie && oknaStineni('zaluzie', it.zaluzie.sirka, it.zaluzie.vyska)],
   ['sit', () => it.sit && oknaStineni('site', it.sit.sirka, it.sit.vyska)]].forEach(([k, f]) => {
    const on = document.getElementById('okna_' + k + '_on').checked;
    document.getElementById('okna-acc-' + k).classList.toggle('on', on);
    let txt = '';
    if (on) { try { const p = f(); txt = p ? oknaKc(p) : ''; } catch (e) { txt = '⚠ mimo ceník'; } }
    document.getElementById('okna-' + k + '-price').textContent = txt;
  });
  if (typeof calc === 'function') calc();
}

function oknaAddItem() {
  const it = oknaEditorItem(), err = document.getElementById('okna-error');
  const fail = msg => { err.textContent = msg; err.classList.remove('hidden'); };
  err.classList.add('hidden');
  if (!it.sirka || !it.vyska) return fail('Zadejte šířku a výšku položky.');
  if (it.parapet && it.parapet.delkaM > 50) return fail('Délka parapetu je v METRECH (max 50 m) — nezadáváte omylem milimetry?');
  try { oknaItemTotal(it); } catch (e) { return fail(e.message); }
  if (oknaEditIndex === null) oknaItems.push(it); else oknaItems[oknaEditIndex] = it;
  oknaResetEditor();
}

function oknaResetEditor() {
  oknaEditIndex = null;
  oknaTyp = 'dvoukridla'; oknaPovrch = 'Bila';
  const set = (id, v) => { document.getElementById(id).value = v; };
  set('okna_sirka', '1200'); set('okna_vyska', '1500'); set('okna_ks', '1');
  document.querySelector('input[name=okna_sklo][value=trojsklo]').checked = true;
  ['parapet', 'zaluzie', 'sit'].forEach(k => { document.getElementById('okna_' + k + '_on').checked = false; });
  set('okna_parapet_hloubka', '200'); set('okna_parapet_skupina', '1'); set('okna_parapet_delka', '');
  ['zaluzie', 'sit'].forEach(k => { set('okna_' + k + '_sirka', ''); set('okna_' + k + '_vyska', ''); });
  document.getElementById('okna-add-btn').textContent = '+ Přidat položku';
  document.getElementById('okna-cancel-btn').classList.add('hidden');
  document.getElementById('okna-error').classList.add('hidden');
  oknaRenderTiles(); oknaRenderItems(); oknaRenderBasic(); oknaEditorChanged();
}

function oknaEditItem(i) {
  const it = oknaItems[i];
  oknaEditIndex = i; oknaTyp = it.typ; oknaPovrch = it.povrch;
  const set = (id, v) => { document.getElementById(id).value = v; };
  set('okna_sirka', it.sirka); set('okna_vyska', it.vyska); set('okna_ks', it.ks);
  document.querySelector('input[name=okna_sklo][value=' + (it.sklo === 'dvojsklo' ? 'dvojsklo' : 'trojsklo') + ']').checked = true;
  document.getElementById('okna_parapet_on').checked = !!it.parapet;
  set('okna_parapet_hloubka', it.parapet ? it.parapet.hloubka : 200);
  set('okna_parapet_skupina', it.parapet ? it.parapet.skupina : 1);
  set('okna_parapet_delka', it.parapet ? it.parapet.delkaM : '');
  ['zaluzie', 'sit'].forEach(k => {
    document.getElementById('okna_' + k + '_on').checked = !!it[k];
    set('okna_' + k + '_sirka', it[k] ? it[k].sirka : ''); set('okna_' + k + '_vyska', it[k] ? it[k].vyska : '');
  });
  document.getElementById('okna-add-btn').textContent = '✓ Uložit změny položky';
  document.getElementById('okna-cancel-btn').classList.remove('hidden');
  oknaRenderTiles(); oknaRenderItems(); oknaEditorChanged();
}

function oknaRemoveItem(i) {
  oknaItems.splice(i, 1);
  if (oknaEditIndex === i) oknaResetEditor(); else { if (oknaEditIndex !== null && oknaEditIndex > i) oknaEditIndex--; oknaRenderItems(); oknaRenderBasic(); if (typeof calc === 'function') calc(); }
}

function oknaRenderItems() {
  const el = document.getElementById('okna-items');
  if (!oknaItems.length) { el.innerHTML = '<div class="okna-note">Zatím žádná položka — vyplňte výplň výše a klikněte na „Přidat položku".</div>'; return; }
  el.innerHTML = oknaItems.map((it, i) => {
    const t = OKNA_TYPES.find(x => x.value === it.typ), acc = [];
    if (it.parapet) acc.push('parapet ' + it.parapet.hloubka + ' mm, ' + String(it.parapet.delkaM).replace('.', ',') + ' m');
    if (it.zaluzie) acc.push('žaluzie'); if (it.sit) acc.push('síť');
    let total = '';
    try { total = oknaKc(oknaItemTotal(it)); } catch (e) { total = '⚠'; }
    return '<div class="okna-item' + (oknaEditIndex === i ? ' editing' : '') + '">' +
      '<button type="button" class="okna-item-main" onclick="oknaEditItem(' + i + ')">' +
      '<b>' + it.ks + '× ' + t.label + ' ' + t.sub + '</b><small>' + OKNA_SURFACE_LABEL[it.povrch] + ' · ' + it.sirka + '×' + it.vyska + ' mm · ' + it.sklo +
      (acc.length ? ' · ' + acc.join(', ') : '') + '</small></button>' +
      '<span class="okna-item-price">' + total + '</span>' +
      '<button type="button" class="okna-item-del" title="Odebrat" onclick="oknaRemoveItem(' + i + ')">×</button></div>';
  }).join('');
}

function oknaRenderBasic() {
  document.getElementById('okna-obvod').textContent = String(oknaObvod()).replace('.', ',');
  document.getElementById('okna-basic').innerHTML = OKNA_BASIC.map((n, i) => {
    const st = oknaBasic[n], q = oknaBasicQty(n), w = oknaWork(n);
    return '<div class="okna-work' + (st.on ? ' on' : '') + '">' +
      '<label><input type="checkbox" ' + (st.on ? 'checked' : '') + ' onchange="oknaBasic[OKNA_BASIC[' + i + ']].on=this.checked;oknaRenderBasic();calc()"> ' + oknaEsc(n) + '</label>' +
      (st.on ? '<span class="okna-work-qty"><input type="number" min="0" step="0.1" value="' + (st.manual !== null ? oknaEsc(st.manual) : q) + '"' +
        ' onchange="oknaBasic[OKNA_BASIC[' + i + ']].manual=this.value;oknaRenderBasic();calc()"> bm' +
        (st.manual !== null ? ' <button type="button" onclick="oknaBasic[OKNA_BASIC[' + i + ']].manual=null;oknaRenderBasic();calc()">auto</button>' : '') +
        ' <b>' + (q > 0 ? oknaKc(Math.round(w.cena * q)) : '—') + '</b></span>' : '') + '</div>';
  }).join('');
}

function oknaToggleDalsi() {
  const el = document.getElementById('okna-dalsi'), open = el.classList.toggle('hidden') === false;
  document.getElementById('okna-dalsi-sign').textContent = open ? '−' : '+';
  if (open) oknaRenderDalsi();
}

function oknaRenderDalsi() {
  const q = (document.getElementById('okna-dalsi-search').value || '').toLowerCase();
  document.getElementById('okna-dalsi-list').innerHTML = OKNA_CENIK.work
    .filter(w => !OKNA_BASIC.includes(w.nazev) && (!q || w.nazev.toLowerCase().includes(q)))
    .map(w => {
      const idx = OKNA_CENIK.work.indexOf(w);
      return '<div class="okna-dalsi-row"><span>' + oknaEsc(w.nazev) + ' <small>' + w.cena + ' Kč/' + oknaEsc(w.jednotka) + '</small></span>' +
        '<input type="number" min="0" step="0.1" value="' + (oknaDalsi[w.nazev] || 0) + '"' +
        ' onchange="oknaSetDalsi(' + idx + ',this.value)"><small>' + oknaEsc(w.jednotka) + '</small></div>';
    }).join('');
}
function oknaSetDalsi(idx, v) {
  const n = OKNA_CENIK.work[idx].nazev, q = Number(v) || 0;
  if (q > 0) oknaDalsi[n] = q; else delete oknaDalsi[n];
  calc();
}

// Form state ↔ hidden inputs / saved drafts
function oknaSerialize() {
  document.getElementById('inp_okna_items').value = JSON.stringify(oknaItems);
  document.getElementById('inp_okna_prace').value = JSON.stringify({basic: oknaBasic, dalsi: oknaDalsi});
}
function oknaLoad(itemsJson, praceJson) {
  try { oknaItems = JSON.parse(itemsJson || '[]') || []; } catch (e) { oknaItems = []; }
  try {
    const p = JSON.parse(praceJson || '{}') || {};
    OKNA_BASIC.forEach(n => { const s = (p.basic || {})[n]; oknaBasic[n] = s ? {on: !!s.on, manual: s.manual === undefined ? null : s.manual} : {on: true, manual: null}; });
    oknaDalsi = p.dalsi || {};
  } catch (e) {}
  oknaResetEditor();
}

function oknaInit() {
  const d = OKNA_CENIK.accessories.parapet_pvc_interier.depths;
  document.getElementById('okna_parapet_hloubka').innerHTML = d.map(x => '<option value="' + x + '">' + x + ' mm</option>').join('');
  oknaResetEditor();
}
