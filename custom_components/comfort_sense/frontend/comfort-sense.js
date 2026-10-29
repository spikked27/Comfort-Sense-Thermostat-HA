/* Comfort Sense console. Local assets; all writes use HA's authenticated admin API. */
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const clone = (value) => JSON.parse(JSON.stringify(value));
const newId = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
const tabs = [
  ["overview", "Overview"],
  ["rooms", "Rooms"],
  ["schedules", "Schedules"],
  ["equipment", "Heating"],
  ["advanced", "Preferences"],
];
const css = `
:host{display:block;height:100%;overflow:auto;color:var(--primary-text-color,#20292e);background:var(--primary-background-color,#f5f7f8);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif);--cs-accent:var(--primary-color,#147d80);--cs-line:var(--divider-color,#dce3e6);--cs-muted:var(--secondary-text-color,#647278);--cs-surface:var(--card-background-color,#fff);--cs-soft:var(--secondary-background-color,#eef3f4);--cs-error:var(--error-color,#bd4545);--cs-warn:var(--warning-color,#a66512);font-size:14px;line-height:1.5}
*{box-sizing:border-box}button,input,select{font:inherit}button,a,input,select{touch-action:manipulation}button,a{ -webkit-tap-highlight-color:transparent }button{cursor:pointer}button:disabled{cursor:default;opacity:.5}a{color:var(--cs-accent)}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid var(--cs-accent);outline-offset:3px}header{position:sticky;top:0;z-index:12;background:var(--cs-surface);border-bottom:1px solid var(--cs-line)}.top{max-width:1240px;margin:auto;padding:16px 30px;display:flex;gap:14px;align-items:center}.logo{width:43px;height:43px;object-fit:contain;background:#fff;border-radius:9px;padding:4px}.brand{font-size:19px;font-weight:750;letter-spacing:-.6px}.sub,.muted{color:var(--cs-muted)}.sub{font-size:12px}.grow{flex:1}.top select{max-width:260px}.version{font-size:12px;letter-spacing:.04em}nav{display:flex;gap:22px;max-width:1240px;padding:0 30px;margin:auto;overflow-x:auto}nav button{white-space:nowrap;border:0;border-bottom:3px solid transparent;border-radius:0;background:transparent;color:var(--cs-muted);padding:14px 0;font-weight:650}nav button[aria-selected=true]{color:var(--cs-accent);border-color:var(--cs-accent)}main{max-width:1240px;margin:auto;padding:32px 30px 130px}.heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:24px}h1{font-size:28px;font-weight:730;letter-spacing:-1px;margin:0 0 4px}h2{font-size:18px;margin:0;font-weight:700;letter-spacing:-.3px}h3{font-size:15px;margin:0 0 6px}.intro{margin:0;color:var(--cs-muted)}.grid{display:grid;gap:20px;grid-template-columns:repeat(2,minmax(0,1fr))}.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.card{background:var(--cs-surface);border:1px solid var(--cs-line);border-radius:18px;padding:23px;min-width:0}.cardhead{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.cardhead h2{margin:0}.card p{margin:8px 0}.space{margin-top:24px}.pill{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:30px;font-size:12px;font-weight:650;background:var(--cs-soft);color:var(--cs-muted);white-space:nowrap}.pill.good{color:var(--cs-accent);background:color-mix(in srgb,var(--cs-accent) 12%,var(--cs-surface))}.pill.error{color:var(--cs-error);background:color-mix(in srgb,var(--cs-error) 10%,var(--cs-surface))}.pill.warning{color:var(--cs-warn);background:color-mix(in srgb,var(--cs-warn) 10%,var(--cs-surface))}.button{display:inline-flex;justify-content:center;align-items:center;gap:8px;border:1px solid var(--cs-line);background:var(--cs-surface);color:inherit;border-radius:10px;padding:10px 15px;min-height:43px;text-decoration:none;font-weight:650}.button.primary{background:var(--cs-accent);border-color:var(--cs-accent);color:var(--text-primary-color,#fff)}.button.quiet{background:transparent;border-color:transparent}.button.danger{color:var(--cs-error)}.row{display:flex;align-items:center;gap:12px}.wrap{flex-wrap:wrap}.between{justify-content:space-between}.metric{font-size:55px;line-height:1.15;font-weight:730;letter-spacing:-2.5px}.metric small{font-size:23px;letter-spacing:-.5px;color:var(--cs-muted);font-weight:500}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:22px 0}.label{font-size:12px;color:var(--cs-muted);font-weight:650;letter-spacing:.02em}.divider{height:1px;background:var(--cs-line);margin:20px 0}.issue{display:flex;gap:13px;align-items:flex-start;padding:15px 0;border-bottom:1px solid var(--cs-line)}.issue:last-child{border:0;padding-bottom:0}.issue:first-child{padding-top:0}.issue .symbol{flex-shrink:0;display:grid;place-items:center;border-radius:9px;width:30px;height:30px;color:var(--cs-accent);background:var(--cs-soft);font-weight:800}.issue.error .symbol{color:var(--cs-error);background:color-mix(in srgb,var(--cs-error) 10%,var(--cs-surface))}.issue.warning .symbol{color:var(--cs-warn)}.issue strong{display:block}.issue p{color:var(--cs-muted);font-size:13px;margin:3px 0}.issue button{margin-left:auto}.roomstat{display:flex;gap:18px;align-items:center;margin-top:20px}.roomtemp{font-size:30px;font-weight:700;letter-spacing:-1px}.track{height:5px;border-radius:10px;background:var(--cs-soft);overflow:hidden;margin-top:7px}.track span{height:100%;display:block;background:var(--cs-accent)}.full{grid-column:1/-1}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.field{display:block;min-width:0}.field>span:first-child,.field>label:first-child{display:block;font-weight:650;margin-bottom:7px}.hint{display:block;font-size:12px;color:var(--cs-muted);margin-top:6px}.input,select{width:100%;padding:11px 12px;border:1px solid var(--cs-line);border-radius:10px;background:var(--cs-surface);color:inherit;min-height:44px}.input:invalid{border-color:var(--cs-error)}.toggle{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:12px 0}.toggle strong{display:block}.toggle input{appearance:none;width:42px;height:24px;flex:0 0 42px;border:0;border-radius:24px;background:var(--cs-muted);position:relative;cursor:pointer}.toggle input:before{content:"";position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:var(--cs-surface);transition:transform .15s}.toggle input:checked{background:var(--cs-accent)}.toggle input:checked:before{transform:translateX(18px)}.segments{display:flex;gap:8px}.segments button{flex:1;padding:13px 8px;border-radius:11px;border:1px solid var(--cs-line);background:var(--cs-surface);color:inherit}.segments button[aria-pressed=true]{border-color:var(--cs-accent);background:color-mix(in srgb,var(--cs-accent) 9%,var(--cs-surface));color:var(--cs-accent)}.segments strong,.segments small{display:block}.segments small{font-size:12px;margin-top:2px;color:var(--cs-muted)}details{margin-top:18px;border-top:1px solid var(--cs-line);padding-top:16px}summary{cursor:pointer;font-weight:650;color:var(--cs-muted)}details[open]>summary{margin-bottom:16px}.empty{text-align:center;padding:38px 16px;color:var(--cs-muted)}.empty h2{color:var(--primary-text-color)}.footer{position:fixed;bottom:0;left:0;right:0;z-index:15;border-top:1px solid var(--cs-line);background:var(--cs-surface);padding:14px 28px;display:flex;align-items:center;justify-content:flex-end;gap:12px}.footer .savehint{margin-right:auto}.errorbox{border-radius:10px;background:color-mix(in srgb,var(--cs-error) 10%,var(--cs-surface));color:var(--cs-error);padding:13px 16px;margin-bottom:20px}.toast{position:fixed;bottom:92px;right:25px;z-index:25;padding:13px 19px;background:var(--cs-accent);color:var(--text-primary-color,#fff);border-radius:12px}.review{position:fixed;inset:0;z-index:22;background:color-mix(in srgb,var(--primary-text-color) 32%,transparent);display:grid;place-items:center;padding:20px}.dialog{max-width:600px;width:100%;max-height:85vh;overflow:auto;background:var(--cs-surface);border-radius:20px;padding:26px;box-shadow:0 20px 80px #0003}.dialog ul{padding-left:22px}.dialog li{padding:5px}.mobilemenu{display:none}.plan{padding:12px 0;border-bottom:1px solid var(--cs-line)}.plan:last-child{border:0}.plan strong{display:block}.inlinewarn{font-size:13px;color:var(--cs-warn)}.legend{display:flex;gap:15px;font-size:12px;color:var(--cs-muted);margin-top:12px}.miniicon{width:38px;height:38px;border-radius:12px;background:var(--cs-soft);display:grid;place-items:center;color:var(--cs-accent);font-size:18px}.targetline{font-size:16px;color:var(--cs-muted)}.roomhead{display:flex;justify-content:space-between;gap:12px}.roomhead input{font-size:19px;font-weight:700;min-width:0}.schedulehead{display:flex;gap:10px;align-items:center;margin-bottom:20px}.schedulehead input{flex:1;min-width:0}.stepnumber{font-size:12px;color:var(--cs-accent);font-weight:700;letter-spacing:.06em;text-transform:uppercase;margin-bottom:7px}.state-note{font-size:12px;color:var(--cs-muted)}.preview{padding:14px;background:var(--cs-soft);border-radius:12px;margin-top:16px}.preview b{font-weight:700}.help-link{font-size:13px}.tabnotice{margin-bottom:20px;padding:12px 16px;border-radius:12px;background:var(--cs-soft)}.learned{color:var(--cs-accent)}.right{text-align:right}
@media(max-width:850px){.grid.three{grid-template-columns:1fr 1fr}.top{padding:12px 18px}nav{padding:0 18px;gap:20px}main{padding:24px 18px 130px}.version{display:none}.top select{max-width:200px}.mobilemenu{display:block}.brand{font-size:17px}}
@media(max-width:580px){.grid,.grid.three,.fields{grid-template-columns:1fr}.heading{align-items:flex-start}.card{padding:19px;border-radius:15px}.top{gap:9px}.top .sub{display:none}.top .logo{width:34px;height:34px}.top select{max-width:155px;font-size:13px;padding:8px}.brand{font-size:16px}.metric{font-size:46px}.footer{padding:12px 16px}.footer .savehint{font-size:12px;max-width:110px}.button{padding:9px 12px}.issue{gap:9px}.issue .button{font-size:12px;padding:7px}.heading h1{font-size:25px}.metrics{gap:10px}.dialog{padding:21px}.top .button{padding:7px}.legend{flex-wrap:wrap}}
@media(max-width:580px){.cardhead{flex-wrap:wrap}.cardhead h2{flex:1 1 210px}.cardhead .pill{white-space:normal}.brand{white-space:nowrap;font-size:15px}.top select{max-width:130px}.top .button{padding:4px;min-height:32px;min-width:32px}.top .logo{width:28px;height:28px}.footer>a{display:none}.footer .button{white-space:nowrap}.heading{flex-wrap:wrap}.heading>div{flex:1 1 230px}}
.pill.error{color:var(--primary-text-color,#20292e)}.inlinewarn{color:var(--primary-text-color,#20292e);border-inline-start:3px solid var(--cs-warn);padding-inline-start:10px}
:host{display:flex;flex-direction:column;overflow:hidden;height:100dvh}header{flex-shrink:0}main{flex:1;min-height:0;width:100%;overflow:auto;padding-bottom:35px}.footer{position:relative;flex-shrink:0;left:auto;right:auto;bottom:auto}
/* Task-first layout: status, required inputs, optional features, detailed tuning. */
main{max-width:1160px;padding:24px 24px 35px}.heading{margin-bottom:18px}h1{font-size:27px}.intro{font-size:13px}.card{padding:20px;border-radius:15px}.cardhead{margin-bottom:16px}.cardhead h2{font-size:17px}.status-banner{display:flex;align-items:center;gap:14px;padding:18px 20px;border:1px solid var(--cs-line);border-radius:15px;background:var(--cs-surface);margin-bottom:14px}.status-banner.error{border-inline-start:4px solid var(--cs-error)}.status-banner.good{border-inline-start:4px solid var(--cs-accent)}.status-banner.warning{border-inline-start:4px solid var(--cs-warn)}.status-banner h2{font-size:21px}.status-banner p{margin:4px 0 0;font-size:13px;color:var(--cs-muted)}.status-mark{width:32px;height:32px;display:grid;place-items:center;border-radius:10px;background:var(--cs-soft);font-weight:800;flex-shrink:0}.status-banner.error .status-mark{color:var(--cs-error)}.comfort-strip{display:grid;grid-template-columns:1fr 1fr 2fr;align-items:center;gap:18px;padding:18px 20px;background:var(--cs-surface);border:1px solid var(--cs-line);border-radius:15px;margin-bottom:14px}.comfort-strip .label{display:block;font-size:11px;letter-spacing:.06em}.comfort-strip strong{display:block;font-size:33px;line-height:1.2;letter-spacing:-1px;margin-top:4px}.comfort-strip strong small{font-size:17px;font-weight:500;color:var(--cs-muted);letter-spacing:0}.comfort-source b{font-size:18px;display:block;margin:3px 0}.comfort-source>span:last-child{font-size:12px}.readiness{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}.readiness-item{background:var(--cs-surface);border:1px solid var(--cs-line);border-radius:12px;padding:12px 14px;text-align:left;color:inherit;min-width:0}.readiness-name{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;color:var(--cs-muted);margin-bottom:5px}.readiness-item>strong{display:block;font-size:16px}.readiness-item>small{display:block;font-size:11px;color:var(--cs-muted);margin-top:4px}.readiness-dot{font-weight:800;color:var(--cs-muted)}.readiness-dot.good{color:var(--cs-accent)}.readiness-dot.error{color:var(--cs-error)}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:24px 0 12px}.section-heading h2{font-size:18px}.room-overview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.compact-room{border:1px solid var(--cs-line);border-radius:13px;background:var(--cs-surface);padding:15px 17px}.compact-room.selected-room{border-color:var(--cs-accent)}.compact-room h3{margin:0;font-size:16px}.compact-room .row{flex-wrap:wrap;gap:8px}.compact-room .room-reading{font-size:28px;letter-spacing:-1px}.room-reading small{font-size:15px;color:var(--cs-muted);font-weight:500;margin-left:3px}.compact-room .muted{font-size:12px}.next-card{margin-top:16px}.next-card .cardhead{margin-bottom:10px}.next-card p{margin-bottom:0}.disclosure{margin-top:16px}.disclosure>summary{display:flex;align-items:center;gap:12px;color:inherit;list-style:none;min-height:30px}.disclosure>summary::-webkit-details-marker{display:none}.disclosure>summary::after{content:"⌄";margin-inline-start:auto;font-size:18px;color:var(--cs-muted)}.disclosure[open]>summary::after{content:"⌃"}.summary-value{font-size:12px;color:var(--cs-muted);font-weight:400}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.detail-grid strong{display:block;font-size:14px}.attention-list{background:var(--cs-surface);border:1px solid var(--cs-line);border-radius:12px;margin-bottom:16px;padding:0 16px}.attention-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--cs-line)}.attention-item:last-child{border:0}.attention-item strong,.attention-item span{display:block}.attention-item strong{font-size:13px}.attention-item span{font-size:12px;color:var(--cs-muted);margin-top:3px}.attention-item .button{flex-shrink:0;font-size:12px}.page-summary{display:flex;align-items:center;gap:12px;margin-bottom:18px;color:var(--cs-muted);font-size:12px;flex-wrap:wrap}.room-editors{align-items:start}.room-snapshot{display:flex;align-items:center;justify-content:space-between;margin:-4px 0 16px;padding-bottom:12px;border-bottom:1px solid var(--cs-line);color:var(--cs-muted);font-size:12px}.room-snapshot>span:first-child{font-size:22px;color:var(--primary-text-color);font-weight:650}.field-head{display:flex;gap:10px;justify-content:space-between;align-items:center;margin-bottom:7px}.field-head>label{font-weight:650}.requirement{font-size:10px;font-weight:600;background:var(--cs-soft);color:var(--cs-muted);border-radius:5px;padding:3px 6px;white-space:nowrap}.input-status{display:block;font-size:12px;margin-top:7px;color:var(--cs-muted)}.input-status.good{color:var(--cs-accent)}.input-status.warning{color:var(--primary-text-color);font-weight:600}.room-options{padding-top:12px;margin-top:12px}.room-options summary{font-size:12px;font-weight:500}.room-editor details>summary{font-size:13px}.notice{background:var(--cs-soft);border-radius:10px;padding:12px 14px;margin:14px 0;font-size:13px}.notice>strong,.notice>span{display:block}.notice>span{font-size:12px;color:var(--cs-muted);margin-top:4px}.notice.warning{border-inline-start:3px solid var(--cs-warn)}.compact-copy,.routine-copy{font-size:14px;margin:0;color:var(--cs-muted)}.external-card{margin-top:16px}.external-card .plan span{display:block}.routine-summary .cardhead{margin-bottom:8px}.compact-empty{text-align:left;padding:16px;border:1px dashed var(--cs-line);border-radius:12px;background:var(--cs-surface);font-size:13px}.schedule-editors{align-items:start}.schedule-editor{margin-top:0}.alarm-card{margin-top:20px}.eyebrow{font-size:11px;display:block;color:var(--cs-muted);margin-bottom:4px}.mode-caption{font-size:12px;color:var(--cs-muted)}.preset-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.preset-tile{padding:14px;border-radius:11px;background:var(--cs-soft)}.preset-tile input{font-size:24px;font-weight:650}.preset-tile .field>span:first-child{font-size:12px;color:var(--cs-muted)}.footer{gap:12px}.footer .savehint{font-size:12px}details>summary{line-height:1.5}nav button{min-height:44px}
@media(max-width:850px){.readiness{grid-template-columns:repeat(2,minmax(0,1fr))}.status-banner{align-items:flex-start;flex-wrap:wrap}.status-banner>.button{margin-left:46px}.preset-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:580px){main{padding:18px 16px 25px}.heading h1{font-size:24px}.heading{gap:8px}.heading>div{flex-basis:210px}.card{padding:17px}.status-banner{padding:14px;gap:10px}.status-banner h2{font-size:19px}.status-banner>.grow{flex:1 1 calc(100% - 44px)}.status-banner>.button{margin-left:42px;font-size:12px;min-height:38px;padding:8px 12px}.comfort-strip{grid-template-columns:1fr 1fr;gap:10px;padding:14px 16px}.comfort-source{grid-column:1/-1;display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-top:10px;border-top:1px solid var(--cs-line)}.comfort-source b{font-size:14px;margin:0}.comfort-source .label{font-size:10px}.comfort-source>span:last-child{margin-left:auto;font-size:11px}.comfort-strip strong{font-size:29px}.readiness{gap:8px}.readiness-item{padding:10px 12px}.readiness-item strong{font-size:14px}.readiness-item small{font-size:10px}.section-heading{margin-top:20px}.section-heading>.muted{font-size:11px}.room-overview{grid-template-columns:1fr}.compact-room{padding:12px 14px}.attention-item{align-items:flex-start;flex-wrap:wrap;gap:5px}.attention-item .button{padding:3px 0;min-height:28px}.cardhead{gap:8px;flex-wrap:wrap}.cardhead h2{flex:initial}.summary-value{font-size:11px}.disclosure>summary{align-items:flex-start;flex-wrap:wrap;gap:5px}.disclosure>summary>span:first-child{flex:1 1 180px}.disclosure>summary>span.summary-value{flex:1 1 auto}.disclosure>summary::after{flex:0 0 15px}.disclosure>summary{min-height:35px}.detail-grid{grid-template-columns:1fr}.preset-grid{gap:10px}.preset-tile{padding:10px}.preset-tile input{font-size:22px}.top{padding:10px 16px}.top select{max-width:130px}nav{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0;padding:0 8px;overflow:visible}nav button{font-size:11px;padding:12px 2px;letter-spacing:-.1px}.sub{display:none}}

`;

class SenseEntityPicker extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.selected = [];
    this.entities = [];
    this.highlight = 0;
  }
  configure({ entities, selected, kind, multiple, label, timeZone }) {
    this.entities = entities;
    this.selected = Array.isArray(selected) ? selected : selected ? [selected] : [];
    this.kind = kind;
    this.timeZone = timeZone;
    this.multiple = multiple;
    this.label = label;
    this.render();
  }
  stateText(e) {
    if (e.device_class === "timestamp" && Number.isFinite(Date.parse(e.state))) {
      try {
        return new Intl.DateTimeFormat(undefined, {
          timeZone: this.timeZone,
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(e.state));
      } catch {
        return e.state;
      }
    }
    return `${e.state} ${e.unit || ""}`.trim();
  }
  allowed(e) {
    const domain = e.entity_id.split(".")[0];
    return this.kind === "temperature"
      ? domain === "sensor" && (e.device_class === "temperature" || ["°C", "°F", "K"].includes(e.unit))
      : this.kind === "timestamp"
        ? domain === "sensor" && e.device_class === "timestamp"
        : this.kind === "presence"
          ? ["person", "binary_sensor", "zone", "device_tracker"].includes(domain)
          : domain === this.kind;
  }
  render() {
    this.shadowRoot.innerHTML = `<style>${css}:host{height:auto;overflow:visible;font-size:13px}.picker{position:relative}.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:8px}.chip{display:flex;align-items:center;gap:8px;max-width:100%;padding:7px 9px;background:var(--cs-soft);border-radius:9px}.chip span{overflow-wrap:anywhere}.chip small{display:block;color:var(--cs-muted)}.chip button{border:0;background:transparent;color:var(--cs-muted);font-size:20px;min-width:28px;min-height:28px}.options{position:absolute;z-index:20;top:100%;left:0;right:0;max-height:260px;overflow:auto;border:1px solid var(--cs-line);border-radius:10px;background:var(--cs-surface);box-shadow:0 12px 28px #0002;padding:5px;margin-top:5px}.option{display:block;width:100%;text-align:left;border:0;border-radius:7px;background:transparent;color:inherit;padding:10px}.option:hover,.option.active{background:var(--cs-soft)}.option small{display:block;color:var(--cs-muted);overflow-wrap:anywhere}.value{float:right;color:var(--cs-accent);font-size:12px}.offline{color:var(--cs-error)}input{font-size:14px}</style><div class="picker"><div class="chips">${this.selected
      .map((id) => {
        let e = this.entities.find((e) => e.entity_id === id);
        return `<div class="chip"><span>${escapeHTML(e?.name || id)}<small>${escapeHTML(e ? this.stateText(e) : "Not available")}</small></span><button type="button" data-remove="${escapeHTML(id)}" aria-label="Remove ${escapeHTML(e?.name || id)}">×</button></div>`;
      })
      .join(
        "",
      )}</div><input class="input" type="search" aria-label="${escapeHTML(this.label)}" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="options" placeholder="${this.selected.length && !this.multiple ? "Replace entity…" : "Search by name or entity…"}" autocomplete="off"><div id="options" class="options" role="listbox" hidden></div></div>`;
    const input = this.shadowRoot.querySelector("input");
    input.addEventListener("input", () => this.options());
    input.addEventListener("focus", () => this.options());
    input.addEventListener("keydown", (e) => {
      let options = [...this.shadowRoot.querySelectorAll(".option")];
      if (e.key === "Escape") {
        this.close();
        return;
      }
      if (["ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        this.highlight = Math.max(
          0,
          Math.min(options.length - 1, this.highlight + (e.key === "ArrowDown" ? 1 : -1)),
        );
        options.forEach((o, i) => o.classList.toggle("active", i === this.highlight));
        options[this.highlight]?.scrollIntoView({ block: "nearest" });
        input.setAttribute("aria-activedescendant", `option-${this.highlight}`);
      }
      if (e.key === "Enter" && options[this.highlight]) {
        e.preventDefault();
        options[this.highlight].click();
      }
    });
    this.shadowRoot.querySelectorAll("[data-remove]").forEach(
      (b) =>
        (b.onclick = () => {
          this.selected = this.selected.filter((id) => id !== b.dataset.remove);
          this.changed();
        }),
    );
    this.onfocusout = () =>
      setTimeout(() => {
        if (!this.matches(":focus-within")) this.close();
      }, 120);
  }
  close() {
    this.shadowRoot.querySelector(".options").hidden = true;
    this.shadowRoot.querySelector("input").setAttribute("aria-expanded", "false");
  }
  options() {
    const input = this.shadowRoot.querySelector("input"),
      term = input.value.toLowerCase();
    this.highlight = 0;
    let results = this.entities
      .filter(
        (e) =>
          this.allowed(e) &&
          !this.selected.includes(e.entity_id) &&
          (e.name + " " + e.entity_id).toLowerCase().includes(term),
      )
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, 40);
    const list = this.shadowRoot.querySelector(".options");
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    list.innerHTML = results.length
      ? results
          .map(
            (e, i) =>
              `<button type="button" role="option" aria-selected="false" id="option-${i}" class="option ${i === 0 ? "active" : ""}" data-id="${escapeHTML(e.entity_id)}"><span class="value ${["unavailable", "unknown"].includes(e.state) ? "offline" : ""}">${escapeHTML(this.stateText(e))}</span><strong>${escapeHTML(e.name)}</strong><small>${escapeHTML(e.entity_id)}</small></button>`,
          )
          .join("")
      : `<div class="empty">No matching ${escapeHTML(this.kind)} entities</div>`;
    list.querySelectorAll("button").forEach(
      (b) =>
        (b.onclick = () => {
          this.selected = this.multiple ? [...this.selected, b.dataset.id] : [b.dataset.id];
          this.changed();
        }),
    );
  }
  changed() {
    this.dispatchEvent(
      new CustomEvent("selection-changed", {
        detail: this.multiple ? this.selected : this.selected[0] || "",
        bubbles: true,
        composed: true,
      }),
    );
    this.render();
  }
}
customElements.define("sense-entity-picker", SenseEntityPicker);

class ComfortSensePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.tab = "overview";
    this.dirty = false;
    this.loading = false;
    this.pick = 0;
    this.error = "";
  }
  set hass(value) {
    this._hass = value;
    if (!this.data && !this.loading && this.isConnected) this.load();
    else if (this.tab === "overview" && !this.dirty && this.data) {
      const climate = value.states?.[this.entry?.climate_entity];
      if (climate !== this.lastClimate) {
        this.lastClimate = climate;
        this.updateOverview();
      }
    }
  }
  get entry() {
    return this.data?.entries.find((e) => e.entry_id === this.entryId) || this.data?.entries[0];
  }
  connectedCallback() {
    this.render();
    if (this._hass) this.load();
    this.timer = setInterval(() => this.load(true), 15000);
  }
  disconnectedCallback() {
    clearInterval(this.timer);
  }
  async load(quiet = false) {
    if (!this._hass || this.loading) return;
    this.loading = true;
    try {
      let data = await this._hass.callWS({ type: "comfort_sense/console" });
      this.data = data;
      if (!this.entryId && data.entries[0]) this.entryId = data.entries[0].entry_id;
      if (!this.dirty) {
        this.draft = clone(this.entry?.config || {});
        this.base = clone(this.draft);
        this.baseRevision = this.entry?.revision;
      }
      this.error = "";
      if (!quiet || this.tab === "overview") this.render();
      else this.updateTop();
    } catch (e) {
      this.error = e.message || "Unable to load Comfort Sense. Check the integration is loaded.";
      if (!quiet) this.render();
    } finally {
      this.loading = false;
    }
  }
  header() {
    return `<header><div class="top"><button class="button quiet mobilemenu" data-menu aria-label="Open Home Assistant sidebar">☰</button><img class="logo" src="/comfort_sense_static/icon.png" alt="Comfort Sense"><div><div class="brand">Comfort Sense</div><div class="sub">Comfort, room by room.</div></div><div class="grow"></div>${this.data?.entries.length ? `<select aria-label="Choose thermostat" data-thermostat>${this.data.entries.map((e) => `<option value="${escapeHTML(e.entry_id)}" ${e.entry_id === this.entry?.entry_id ? "selected" : ""}>${escapeHTML(this.displayName(e.name))}</option>`).join("")}</select>` : ""}<span class="pill version" id="top-mode">${this.entry?.config.shadow ? "Observation only" : "Active control"}</span></div><nav role="tablist" aria-label="Comfort Sense sections">${tabs.map(([id, label]) => `<button role="tab" aria-selected="${this.tab === id}" data-tab="${id}">${label}</button>`).join("")}</nav></header>`;
  }
  render() {
    const focused = this.shadowRoot.activeElement?.dataset?.focus;
    this.pickers = [];
    this.pick = 0;
    this.shadowRoot.innerHTML = `<style>${css}</style>${this.header()}<main>${this.error ? `<div class="errorbox" role="alert">${escapeHTML(this.error)} <button class="button quiet" data-reload>Reload settings</button></div>` : ""}${!this.data ? `<div class="empty">${this.error ? "" : "Loading your thermostats…"}</div>` : !this.entry ? `<div class="empty"><h1>Welcome to Comfort Sense</h1><p>Add a thermostat and its first room to begin.</p><a class="button primary" href="/config/integrations/dashboard/add?domain=comfort_sense">Add thermostat</a></div>` : `<div id="content">${this[this.tab]()}</div>`}</main>${this.entry ? `<div class="footer"><div class="savehint" id="save-state">${this.dirty ? "Unsaved changes" : "All changes saved"}</div><a class="button quiet" href="/config/integrations/dashboard/add?domain=comfort_sense">Add thermostat</a><button class="button" data-discard ${this.dirty ? "" : "disabled"}>Discard</button><button class="button primary" data-review ${this.dirty ? "" : "disabled"}>Review & save</button></div>` : ""}`;
    this.bind();
    if (focused) this.shadowRoot.querySelector(`[data-focus="${focused}"]`)?.focus();
  }
  heading(title, sub, action = "") {
    return `<div class="heading"><div><h1>${title}</h1><p class="intro">${sub}</p></div>${action}</div>`;
  }
  pill(text, type = "") {
    return `<span class="pill ${type}">${escapeHTML(text)}</span>`;
  }
  temp(value) {
    return value === null || value === undefined ? "—" : Number(value).toFixed(1).replace(/\.0$/, "");
  }
  live() {
    const e = this.entry,
      s = this._hass?.states?.[e.climate_entity],
      a = s?.attributes;
    if (!a) return e.live;
    return {
      ...e.live,
      mode: s.state,
      preset: a.preset_mode,
      source: a.active_room,
      reason: a.control_reason,
      temperature: a.current_temperature,
      target: a.temperature,
      demand: a.requested_duty_percent,
      observed: a.observed_relay_on,
      target_origin: a.target_origin || e.live.target_origin,
    };
  }
  inputHealth(ids, kind = "temperature") {
    ids = (Array.isArray(ids) ? ids : [ids]).filter(Boolean);
    const ready = ids.filter((id) => {
      const live = this._hass?.states?.[id];
      const row = this.data.entities.find((e) => e.entity_id === id);
      const value = live?.state ?? row?.state;
      if (value == null || ["", "unknown", "unavailable"].includes(value) || live?.attributes?.restored)
        return false;
      if (kind === "temperature")
        return (
          Number.isFinite(Number(value)) &&
          ["°C", "°F", "K"].includes(live?.attributes?.unit_of_measurement ?? row?.unit)
        );
      if (["switch", "binary_sensor"].includes(kind)) return ["on", "off"].includes(value);
      if (kind === "timestamp") return Number.isFinite(Date.parse(value));
      return true;
    }).length;
    return { total: ids.length, ready, ok: !!ids.length && ready === ids.length };
  }
  roomHealth(room) {
    const health = this.inputHealth(room.temperature_sensors);
    const current = this.entry.rooms.find((r) => r.id === room.id);
    const saved = this.entry.config.rooms.find((r) => r.id === room.id);
    if (
      current &&
      saved &&
      JSON.stringify(saved.temperature_sensors) === JSON.stringify(room.temperature_sensors) &&
      current.temperature == null
    )
      return { ...health, ready: 0, ok: false };
    return health;
  }
  displayName(name = this.entry.name) {
    return name.replace(/^Comfort\s?Sense[-\s]*/i, "").trim() || name;
  }
  setupTiles() {
    const c = this.entry.config,
      heater = this.inputHealth(c.heater, "switch"),
      rooms = c.rooms.filter((r) => this.roomHealth(r).ready > 0).length;
    const occupancy = c.rooms.filter((r) => this.inputHealth(r.occupancy_sensors, "binary_sensor").ok).length;
    const outdoor = this.inputHealth(c.outdoor_sensor);
    outdoor.ok = outdoor.ok && this.entry.live.outdoor != null;
    return [
      {
        name: "Heater",
        value: heater.ok ? "Connected" : "Offline",
        note: "Required for heat",
        ok: heater.ok,
        tab: "equipment",
      },
      {
        name: "Room temperatures",
        value: `${rooms} of ${c.rooms.length} ready`,
        note: "Required per room",
        ok: rooms === c.rooms.length,
        tab: "rooms",
      },
      {
        name: "Occupancy",
        value: occupancy ? `${occupancy} ${occupancy === 1 ? "room" : "rooms"} connected` : "Not connected",
        note: "For automatic room selection",
        ok: occupancy > 0,
        optional: true,
        tab: "rooms",
      },
      {
        name: "Outdoor",
        value: outdoor.ok
          ? `${this.temp(this.entry.live.outdoor)}${this.data.unit}`
          : c.outdoor_sensor
            ? "Unavailable"
            : "Not connected",
        note: "For thermal learning",
        ok: outdoor.ok,
        optional: true,
        tab: "equipment",
      },
    ];
  }
  operatingStatus() {
    const c = this.entry.config,
      l = this.live();
    if (!this.inputHealth(c.heater, "switch").ok)
      return {
        title: "Heating unavailable",
        detail: "The heater is offline. Control and thermal learning are paused.",
        label: "Check heater connection",
        tab: "equipment",
        tone: "error",
      };
    const ready = c.rooms.filter((r) => this.roomHealth(r).ready > 0).length;
    if (!ready)
      return {
        title: "Room temperature needed",
        detail: "Connect a working room temperature sensor before heating can run.",
        label: "Check room sensors",
        tab: "rooms",
        tone: "error",
      };
    if (c.shadow)
      return {
        title: "Observation only",
        detail: "Room selection is running. Comfort Sense is not switching the heater.",
        label: "Review operating mode",
        tab: "equipment",
        tone: "info",
      };
    if (l.mode !== "heat")
      return {
        title: "Thermostat is off",
        detail: "Your settings are saved. Select Heat when you want heating control.",
        label: "Open thermostat controls",
        controls: true,
        tone: "info",
      };
    if (/Startup/i.test(l.reason || ""))
      return {
        title: "Waiting for heater confirmation",
        detail: l.reason,
        label: "Check heater status",
        tab: "equipment",
        tone: "info",
      };
    if (/protection|limit|unavailable|failed/i.test(l.reason || ""))
      return {
        title: "Heating paused",
        detail: l.reason,
        label: "Check heating settings",
        tab: "equipment",
        tone: "warning",
      };
    return {
      title: l.observed ? "Heating" : "Maintaining comfort",
      detail: l.observed
        ? `Warming ${l.source} toward ${this.temp(l.target)}${this.data.unit}.`
        : `Following ${l.source}. Heating will run when needed.`,
      label: "Thermostat controls",
      controls: true,
      tone: "good",
    };
  }
  overview() {
    const e = this.entry,
      l = this.live(),
      status = this.operatingStatus(),
      unit = this.data.unit;
    const attention = e.issues.filter((i) => i.level !== "info" && i.title !== "Heater disconnected");
    return (
      this.heading(
        this.displayName(),
        "Home comfort",
        this.pill(e.config.shadow ? "Observation mode" : "Heating control"),
      ) +
      `<section class="status-banner ${status.tone}" aria-label="Operating status"><div class="status-mark" aria-hidden="true">${status.tone === "error" ? "!" : status.tone === "good" ? "✓" : "i"}</div><div class="grow"><h2>${escapeHTML(status.title)}</h2><p>${escapeHTML(status.detail)}</p></div><button class="button primary" ${status.controls ? "data-controls" : `data-tab="${status.tab}"`}>${status.label} →</button></section>
      <section class="comfort-strip" aria-label="Current comfort"><div><span class="label">CURRENT</span><strong>${this.temp(l.temperature)}<small>${unit}</small></strong></div><div><span class="label">TARGET</span><strong>${this.temp(l.target)}<small>${unit}</small></strong></div><div class="comfort-source"><span class="label">FOLLOWING</span><b>${escapeHTML(l.source || "Unavailable")}</b><span class="muted">${escapeHTML(l.target_origin || l.preset + " preset")}</span></div></section>
      <div class="readiness" aria-label="Input readiness">${this.setupTiles()
        .map(
          (t) =>
            `<button class="readiness-item" data-tab="${t.tab}"><span class="readiness-name">${t.name}<span class="readiness-dot ${t.ok ? "good" : t.optional ? "optional" : "error"}" aria-label="${t.ok ? "Ready" : t.optional ? "Optional input missing" : "Needs attention"}">${t.ok ? "✓" : t.optional ? "—" : "!"}</span></span><strong>${escapeHTML(t.value)}</strong><small>${t.note}</small></button>`,
        )
        .join("")}</div>
      ${attention.length ? `<section class="attention-list">${attention.map((i) => `<div class="attention-item"><div><strong>${escapeHTML(i.title)}</strong><span>${escapeHTML(i.detail)}</span></div><button class="button quiet" data-tab="${i.tab}">${i.tab === "rooms" ? "Check sensors" : i.tab === "schedules" ? "Review schedules" : "Check input"} →</button></div>`).join("")}</section>` : ""}
      <div class="section-heading"><h2>Your rooms</h2><button class="button quiet" data-tab="rooms">Edit rooms →</button></div><div class="room-overview">${e.config.rooms
        .map((r) => {
          const live = e.rooms.find((x) => x.id === r.id) || {};
          return `<section class="compact-room ${live.active ? "selected-room" : ""}"><div class="row between"><h3>${escapeHTML(r.name)}</h3>${this.pill(live.active ? "Following" : "Monitoring", live.active ? "good" : "")}</div><div class="row between"><strong class="room-reading">${this.temp(live.temperature)}<small>${unit}</small></strong><span class="muted">${live.occupancy || 0}% occupancy</span></div></section>`;
        })
        .join("")}</div>
      <section class="card next-card"><div class="cardhead"><h2>Next comfort</h2><button class="button quiet" data-tab="schedules">Edit routine →</button></div>${this.planPreview()}<p class="state-note">${escapeHTML(l.morning)}</p></section>
      <details class="card disclosure diagnostics"><summary><span>Heating & learning details</span><span class="summary-value">${l.demand ?? 0}% demand</span></summary><div class="detail-grid"><div><span class="label">Heat demand</span><strong>${l.demand ?? 0}%</strong></div><div><span class="label">Observed heater</span><strong>${l.observed == null ? "Unavailable" : l.observed ? "On" : "Off"}</strong></div><div><span class="label">Outdoor compensation</span><strong>${escapeHTML(e.live.outdoor_compensation?.status || "Waiting for model")}</strong></div><div><span class="label">Control reason</span><strong>${escapeHTML(l.reason)}</strong></div></div><p class="hint">Demand is a requested share of each heating cycle, not a measurement of furnace runtime.</p>${e.rooms.map((r) => `<p class="state-note"><strong>${escapeHTML(e.config.rooms.find((x) => x.id === r.id)?.name || "Room")}</strong> · ${escapeHTML(r.learning)}</p>`).join("")}</details>`
    );
  }
  selectionNote(ids, kind = "temperature") {
    const h = this.inputHealth(ids, kind);
    if (!h.total) return "";
    return `<span class="input-status ${h.ok ? "good" : "warning"}">${h.ok ? "✓ Connected" : h.ready ? `${h.ready} of ${h.total} reporting` : "! Waiting for a valid reading"}</span>`;
  }
  minutes(label, path, hint = "", min = 0.5, max = 60) {
    return `<label class="field"><span>${label}</span><input class="input" data-field="${path}" data-scale="60" type="number" value="${Number(this.value(path)) / 60}" min="${min}" max="${max}" step="0.5">${hint ? `<span class="hint">${hint}</span>` : ""}</label>`;
  }
  rooms() {
    const ready = this.draft.rooms.filter((r) => this.roomHealth(r).ready > 0).length;
    return (
      this.heading(
        "Rooms",
        "Give each room a temperature sensor. Add occupancy to let Auto follow you.",
        `<button class="button primary" data-add-room>+ Add room</button>`,
      ) +
      `<div class="page-summary">${this.pill(`${ready} of ${this.draft.rooms.length} rooms ready`, ready === this.draft.rooms.length ? "good" : "warning")}<span>Temperature is required · occupancy is optional</span></div>
      <div class="grid room-editors">${this.draft.rooms
        .map((r, i) => {
          const live = this.entry.rooms.find((x) => x.id === r.id) || {},
            health = this.roomHealth(r);
          return `<section class="card room-editor"><div class="cardhead"><h2>${escapeHTML(r.name || "New room")}</h2>${this.pill(health.ready ? "Temperature ready" : r.temperature_sensors.length ? "Sensor unavailable" : "Add temperature", health.ready ? "good" : "warning")}</div><div class="room-snapshot"><span>${this.temp(live.temperature)}${this.data.unit}</span><span>${live.occupancy || 0}% occupancy history</span></div>${this.field("Room name", `rooms.${i}.name`)}<div class="space">${this.picker("Temperature sensors", `rooms.${i}.temperature_sensors`, "temperature", true, "Select original room sensors; multiple readings are combined.", "Required")}${this.selectionNote(r.temperature_sensors)}</div><div class="space">${this.picker("Occupancy sensors", `rooms.${i}.occupancy_sensors`, "binary_sensor", true, "Without occupancy, the room can still contribute to Average.", "Optional")}${this.selectionNote(r.occupancy_sensors, "binary_sensor")}</div><details ${r.tuning_mode === "manual" ? "open" : ""}><summary>Room tuning · ${r.tuning_mode === "auto" ? "Automatic" : "Manual"}</summary>${this.select("PID tuning", `rooms.${i}.tuning_mode`, { auto: "Automatic · recommended", manual: "Manual PID values" })}${r.tuning_mode === "manual" ? this.gains(`rooms.${i}.`) : `<p class="hint">Learns from normal heating. Fallback gains are used until a model is accepted.</p>`}</details><details class="room-options"><summary>Room options</summary><button class="button danger" data-remove-room="${i}" aria-label="Remove ${escapeHTML(r.name)}">Remove room</button></details></section>`;
        })
        .join("")}</div>
      <details class="card disclosure"><summary><span>Room behavior</span><span class="summary-value">${escapeHTML(this.draft.reaction_time)} · ${this.draft.occupancy_margin}% grouping</span></summary><div class="field"><span>Reaction speed</span><div class="segments">${[
        ["fast", "Fast", "10-minute history"],
        ["medium", "Medium", "30-minute history"],
        ["slow", "Slow", "60-minute history"],
      ]
        .map(
          ([id, n, h]) =>
            `<button data-reaction="${id}" aria-pressed="${this.draft.reaction_time === id}"><strong>${n}</strong><small>${h}</small></button>`,
        )
        .join(
          "",
        )}</div></div><div class="space">${this.number("Group similarly occupied rooms (%)", "occupancy_margin", "Rooms within this occupancy margin are averaged together.", 'min="0" max="100"')}</div><button class="button quiet" data-tab="equipment">Room temperature protection →</button></details>`
    );
  }
  externalSchedules() {
    const schedules = this.entry.external_schedules;
    if (!schedules.length) return "";
    const names = {
      mon: "Monday",
      tue: "Tuesday",
      wed: "Wednesday",
      thu: "Thursday",
      fri: "Friday",
      sat: "Saturday",
      sun: "Sunday",
    };
    const overlaps = [
      ...new Set(
        schedules.flatMap((s, i) =>
          schedules.slice(i + 1).flatMap((t) => s.days.filter((day) => t.days.includes(day))),
        ),
      ),
    ];
    return `<section class="card external-card"><div class="cardhead"><h2>External preset schedules</h2>${this.pill(`${schedules.length} connected`, overlaps.length ? "warning" : "")}</div>${overlaps.length ? `<div class="notice warning"><strong>${overlaps.map((d) => names[d] || d).join(", ")} has overlapping schedules</strong><span>Both schedules can send preset changes on the same day.</span></div>` : ""}<p class="compact-copy">These schedules also change the target. Boost uses the ${this.draft.boost_minutes}-minute thermostat timer.</p><details><summary>View external schedules</summary>${schedules.map((s) => `<div class="plan"><strong>${escapeHTML(s.name)}</strong><span class="muted">${escapeHTML(s.days.map((d) => names[d] || d).join(", "))}</span><span class="state-note">${escapeHTML(s.timeslots.join(" / "))}</span></div>`).join("")}</details></section>`;
  }
  morningSummary() {
    if (!this.draft.morning_enabled)
      return "Optional · use phone wake-up times instead of fixed morning times.";
    if (!this.draft.alarm_sensors.length) return "Choose a phone’s next-alarm sensor to finish setup.";
    return `${escapeHTML(this.sourceName(this.draft.morning_source))} to ${this.temp(this.draft.morning_target)}${this.data.unit} by the earliest wake alarm · hold ${this.draft.morning_duration} min`;
  }
  schedules() {
    return (
      this.heading(
        "Schedules",
        "Choose when you want comfort. Weekly times and phone alarms can work together.",
      ) +
      `<section class="card routine-summary"><div class="cardhead"><h2>Your routine</h2>${this.pill(`${this.draft.schedules.length} weekly · ${this.draft.morning_enabled ? "alarms on" : "alarms off"}`)}</div>${this.planPreview()}<p class="state-note">${escapeHTML(this.entry.live.morning)}</p></section>${this.externalSchedules()}
      <div class="section-heading"><div><h2>Weekly comfort</h2><span class="hint">Connect native Home Assistant Schedule helpers.</span></div><button class="button" data-add-schedule>+ Connect schedule</button></div>
      ${this.draft.schedules.length ? `<div class="grid schedule-editors">${this.draft.schedules.map((s, i) => `<details class="card disclosure schedule-editor" ${s.name && s.entity_id ? "" : "open"}><summary><span>${escapeHTML(s.name || "New weekly schedule")}</span><span class="summary-value">${this.temp(s.target)}${this.data.unit} · ${escapeHTML(this.sourceName(s.source))}</span></summary>${this.field("Schedule name", `schedules.${i}.name`)}<div class="space">${this.picker("Schedule helper", `schedules.${i}.entity_id`, "schedule", false, "Edit its weekly time blocks in Home Assistant.", "Required")}</div>${s.weekly && !s.entity_id ? `<p class="notice">Migrated weekly times are preserved until you select a helper.</p>` : ""}<div class="fields space">${this.select("Rooms", `schedules.${i}.source`, this.sources())}${this.number(`Target (${this.data.unit})`, `schedules.${i}.target`)}</div>${this.toggle("Ready when the block starts", `schedules.${i}.preheat`, "Start warming early enough to aim for the target at the block’s start.")}<details><summary>Priority & block-data settings</summary><div class="fields">${this.number("Priority", `schedules.${i}.priority`, "Higher wins when connected schedules overlap.", 'min="0" max="100"')}${this.select("Additional block-data units", `schedules.${i}.data_temperature_unit`, { "°C": "Celsius", "°F": "Fahrenheit" })}</div></details><button class="button quiet danger space" data-remove-schedule="${i}">Remove schedule</button></details>`).join("")}</div>` : `<div class="empty compact-empty">No weekly helper connected. This is optional if you use phone alarms or another scheduler.</div>`}
      <p><a class="help-link" href="/config/helpers">Open HA’s weekly schedule editor →</a></p>
      <section class="card alarm-card"><div class="cardhead"><h2>Phone wake-up alarms</h2>${this.pill(this.draft.morning_enabled ? "Enabled" : "Optional", this.draft.morning_enabled ? "good" : "")}</div><p class="routine-copy">${this.morningSummary()}</p><details ${this.draft.morning_enabled && !this.draft.alarm_sensors.length ? "open" : ""}><summary>${this.draft.morning_enabled ? "Edit morning alarms" : "Set up morning alarms"}</summary>${this.toggle("Follow phone wake-up alarms", "morning_enabled", "Use the earliest valid alarm from the selected phones.")}${this.draft.morning_enabled ? `<div class="space">${this.picker("Next-alarm sensors", "alarm_sensors", "timestamp", true, "Choose each phone’s next-alarm timestamp sensor.", "Required when enabled")}</div><div class="fields space">${this.number(`Ready-by temperature (${this.data.unit})`, "morning_target")}${this.select("Warm these rooms", "morning_source", this.sources())}</div><details><summary>Wake-up window & people · ${escapeHTML(this.draft.alarm_window_start)}–${escapeHTML(this.draft.alarm_window_end)}</summary><div class="fields">${this.field("Accept alarms after", "alarm_window_start", "time")}${this.field("Accept alarms before", "alarm_window_end", "time")}${this.number("Morning hold (minutes)", "morning_duration", "Maintain comfort after the alarm.", 'min="1" max="240"')}</div><p class="hint">Alarms outside this window are ignored, including bedtime events.</p>${this.draft.alarm_sensors.map((e) => `<div class="space">${this.picker(`Person for ${escapeHTML(this.data.entities.find((x) => x.entity_id === e)?.name || e)}`, `alarm_owners.${e}`, "person", false, "Skip this phone when its person is away.", "Optional")}</div>`).join("")}</details>` : ""}</details></section>`
    );
  }
  equipment() {
    const heater = this.inputHealth(this.draft.heater, "switch"),
      outdoor = this.inputHealth(this.draft.outdoor_sensor),
      home = this.inputHealth(this.draft.home_sensor, "presence");
    return (
      this.heading("Heating", "Connect the heating zone first. Add context for learning and Away mode.") +
      `<section class="card heater-card"><div class="cardhead"><div><span class="eyebrow">Required for heating</span><h2>Heater connection</h2></div>${this.pill(heater.ok ? "Connected" : "Offline", heater.ok ? "good" : "warning")}</div>${this.picker("Heater relay", "heater", "switch", false, "The switch that controls this thermostat’s heating zone.", "Required")}${this.selectionNote(this.draft.heater, "switch")}${!heater.ok ? `<div class="notice warning"><strong>Check the heater device</strong><span>The selected relay needs to report On or Off before heating control and learning can run.</span></div>` : ""}<div class="divider"></div><h3>Operating mode</h3>${this.toggle("Observation only (Shadow mode)", "shadow", "Enabled: observe rooms without sending heater commands.")}<p class="mode-caption">${this.draft.shadow ? "Observation only · your existing controller remains responsible for heat." : "Active control · stop other controllers of this relay before saving."}</p></section>
      <div class="section-heading"><h2>Optional inputs</h2><span class="muted">Enable the features you need</span></div><div class="grid"><section class="card"><div class="cardhead"><h2>Outdoor temperature</h2>${this.pill(outdoor.ok ? "Connected" : "For learning", outdoor.ok ? "good" : "")}</div>${this.picker("Outdoor temperature", "outdoor_sensor", "temperature", false, "Needed for thermal learning; basic temperature control can work without it.", "For learning")}${this.selectionNote(this.draft.outdoor_sensor)}</section><section class="card"><div class="cardhead"><h2>Home presence</h2>${this.pill(home.ok ? "Connected" : "Optional", home.ok ? "good" : "")}</div>${this.picker("Home presence", "home_sensor", "presence", false, "Use Away temperature after nobody is home.", "Optional")}${this.selectionNote(this.draft.home_sensor, "presence")}</section></div>
      <details class="card disclosure protection-settings"><summary><span>Protection & cycling</span><span class="summary-value">${this.draft.min_on_seconds / 60} min on · ${this.draft.min_off_seconds / 60} min off</span></summary><div class="fields">${this.minutes("Minimum on time (minutes)", "min_on_seconds", "Complete a heating run, except when a safety cutoff takes priority.")}${this.minutes("Minimum off time (minutes)", "min_off_seconds", "Wait between runs, including after restart.")}${this.minutes("Heating cycle (minutes)", "pwm_seconds", "Must cover the minimum on + off time.", 2, 120)}${this.number(`Room protection buffer (${this.data.unit})`, "room_buffer", "One shared warm/cold buffer around the target. Set 0 to disable.", 'min="0"')}${this.number(`Absolute temperature limit (${this.data.unit})`, "max_temperature", "Safety cutoff above all preset targets.")}</div></details>
      <details class="card disclosure"><summary><span>Thermostat identity</span><span class="summary-value">${escapeHTML(this.draft.name)}</span></summary>${this.field("Thermostat name", "name")}</details>`
    );
  }
  advanced() {
    const manual =
      this.draft.rooms.filter((r) => r.tuning_mode === "manual").length +
      (this.draft.average_tuning_mode === "manual" ? 1 : 0);
    return (
      this.heading("Preferences", "Preset temperatures are ready to use. Fine-tuning is optional.") +
      `<section class="card"><div class="cardhead"><h2>Temperature presets</h2>${this.pill("Used by the thermostat and schedules")}</div><div class="preset-grid">${["comfort", "sleep", "away", "boost"].map((p) => `<div class="preset-tile">${this.number(`${p[0].toUpperCase() + p.slice(1)} (${this.data.unit})`, `${p}_temperature`)}</div>`).join("")}</div><details><summary>Preset behavior · Boost ${this.draft.boost_minutes} min</summary><div class="fields">${this.number("Boost duration (minutes)", "boost_minutes", "External preset schedules use this timer too.", 'min="1" max="240"')}${this.select("Sleep room", "sleep_room", { "": "Use thermostat source", ...Object.fromEntries(this.draft.rooms.map((r) => [r.id, r.name])) })}${this.number("Away delay (minutes)", "away_delay_minutes", "Wait before using the Away temperature.", 'min="0" max="180"')}</div></details></section>
      <details class="card disclosure" ${this.draft.average_tuning_mode === "manual" ? "open" : ""}><summary><span>PID tuning & learning</span><span class="summary-value">${manual ? `${manual} manual controllers` : "All controllers automatic"}</span></summary><div class="notice"><strong>Automatic is the default</strong><span>Room and Average controllers learn independently from normal heating.</span></div>${this.select("Average PID tuning", "average_tuning_mode", { auto: "Automatic · recommended", manual: "Manual PID values" })}${this.draft.average_tuning_mode === "manual" ? this.gains("average_") : `<p class="state-note">${escapeHTML(this.entry.live.average_learning)}</p>`}<button class="button quiet" data-tab="rooms">Individual room tuning →</button></details>
      <details class="card disclosure"><summary><span>Advanced sensor & warm-up settings</span><span class="summary-value">Usually no changes needed</span></summary><div class="fields">${this.number("Temperature timeout (minutes)", "sensor_timeout_minutes", "Exclude sensors that have stopped reporting.", 'min="5" max="1440"')}${this.number("Maximum preheat (minutes)", "max_preheat_minutes", "Limit how early warm-up may begin.", 'min="15" max="480"')}${this.number(`Fallback heating rate (${this.data.unit}/hour)`, "fallback_heat_rate", "Estimate used before a thermal model is accepted.")}</div></details>`
    );
  }
  planPreview() {
    const plans = this.entry.live.plans || [];
    if (!plans.length) return `<span class="muted">No upcoming comfort deadline.</span>`;
    return plans
      .slice(0, 5)
      .map(
        (p) =>
          `<div class="plan row between"><div><strong>${escapeHTML(p.name)}</strong><span class="muted">${escapeHTML(this.sourceName(p.source))} · ${this.temp(this.data.unit === "°F" ? p.target * 1.8 + 32 : p.target)}${this.data.unit}</span></div><div class="right"><strong>${new Date(p.start * 1000).toLocaleTimeString(this._hass.locale?.language, { hour: "numeric", minute: "2-digit" })}</strong><span class="muted">${p.confidence === "learned" ? "Learned warm-up" : "Estimated warm-up"}</span></div></div>`,
      )
      .join("");
  }
  sourceName(id) {
    return (
      this.draft.rooms?.find((r) => r.id === id)?.name ||
      { Auto: "Occupied rooms", Average: "Whole-home average" }[id] ||
      id
    );
  }
  field(label, path, type = "text", hint = "", attrs = "") {
    const value = this.value(path);
    return `<label class="field"><span>${label}</span><input class="input" data-field="${path}" type="${type}" value="${escapeHTML(value)}" ${attrs}>${hint ? `<span class="hint">${hint}</span>` : ""}</label>`;
  }
  number(label, path, hint = "", attrs = "") {
    return this.field(label, path, "number", hint, `step="any" ${attrs}`);
  }
  select(label, path, choices, hint = "") {
    return `<label class="field"><span>${label}</span><select data-field="${path}">${Object.entries(choices)
      .map(
        ([v, n]) =>
          `<option value="${escapeHTML(v)}" ${String(this.value(path)) === v ? "selected" : ""}>${escapeHTML(n)}</option>`,
      )
      .join("")}</select>${hint ? `<span class="hint">${hint}</span>` : ""}</label>`;
  }
  toggle(label, path, hint = "") {
    return `<label class="toggle"><span><strong>${label}</strong>${hint ? `<span class="hint">${hint}</span>` : ""}</span><input type="checkbox" role="switch" aria-label="${label}" data-field="${path}" ${this.value(path) ? "checked" : ""}></label>`;
  }
  picker(label, path, kind, multiple = false, hint = "", requirement = "") {
    const id = `picker-${this.pick++}`;
    this.pickers.push({ id, path, kind, multiple, label, timeZone: this._hass?.config?.time_zone });
    return `<div class="field"><div class="field-head"><label id="${id}-label">${label}</label>${requirement ? `<span class="requirement">${requirement}</span>` : ""}</div><sense-entity-picker id="${id}" aria-labelledby="${id}-label"></sense-entity-picker>${hint ? `<span class="hint">${hint}</span>` : ""}</div>`;
  }
  sources(blank = false) {
    return {
      ...(blank ? { "": "Whole-home average" } : {}),
      Auto: "Follow occupancy",
      Average: "Whole-home average",
      ...Object.fromEntries(this.draft.rooms.map((r) => [r.id, r.name || "Unnamed room"])),
    };
  }
  gains(prefix) {
    return `<div class="fields space">${this.number("Proportional · Kp", prefix + "kp", "", 'min="0" max="2"')}${this.number("Integral · Ki", prefix + "ki", "", 'min="0" max="0.001"')}${this.number("Derivative · Kd", prefix + "kd", "", 'min="0" max="3600"')}</div><span class="hint">Controller units: heat fraction per °C, per °C·second, and seconds per °C.</span>`;
  }
  value(path) {
    if (path.startsWith("alarm_owners.")) return this.draft.alarm_owners[path.slice(13)] || "";
    return path.split(".").reduce((v, k) => v?.[k], this.draft);
  }
  setValue(path, value) {
    if (path.startsWith("alarm_owners.")) {
      if (value) this.draft.alarm_owners[path.slice(13)] = value;
      else delete this.draft.alarm_owners[path.slice(13)];
    } else {
      const parts = path.split("."),
        key = parts.pop();
      let node = parts.reduce((v, k) => v[k], this.draft);
      node[key] = value;
    }
    if (path === "alarm_sensors")
      this.draft.alarm_owners = Object.fromEntries(
        Object.entries(this.draft.alarm_owners).filter(([k]) => value.includes(k)),
      );
    if (/^schedules\.\d+\.entity_id$/.test(path) && value) {
      delete this.draft.schedules[Number(path.split(".")[1])].weekly;
    }
    this.dirty = JSON.stringify(this.draft) !== JSON.stringify(this.base);
    this.updateTop();
  }
  updateTop() {
    const s = this.shadowRoot.querySelector("#save-state");
    if (s) s.textContent = this.dirty ? "Unsaved changes" : "All changes saved";
    this.shadowRoot
      .querySelectorAll("[data-review],[data-discard]")
      .forEach((b) => (b.disabled = !this.dirty));
  }
  updateOverview() {
    if (this.pendingRender) return;
    this.pendingRender = requestAnimationFrame(() => {
      this.pendingRender = null;
      if (this.tab !== "overview" || !this.data) return;
      this.pickers = [];
      this.shadowRoot.querySelector("#content")?.replaceChildren();
      const c = this.shadowRoot.querySelector("#content");
      if (c) c.innerHTML = this.overview();
      this.bindContent();
    });
  }
  bind() {
    this.shadowRoot
      .querySelector("[data-menu]")
      ?.addEventListener("click", () =>
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true })),
      );
    this.shadowRoot.querySelector("[data-thermostat]")?.addEventListener("change", (e) => {
      if (this.dirty && !confirm("Discard unsaved changes to this thermostat?")) {
        e.target.value = this.entryId;
        return;
      }
      this.entryId = e.target.value;
      this.dirty = false;
      this.draft = clone(this.entry.config);
      this.base = clone(this.draft);
      this.baseRevision = this.entry.revision;
      this.error = "";
      this.render();
    });
    this.shadowRoot.querySelectorAll("[data-tab]").forEach(
      (b) =>
        (b.onclick = () => {
          this.tab = b.dataset.tab;
          this.render();
          this.scrollTop = 0;
        }),
    );
    this.shadowRoot.querySelector("[data-reload]")?.addEventListener("click", () => {
      if (!this.dirty || confirm("Discard your draft and load the latest settings?")) {
        this.dirty = false;
        this.load();
      }
    });
    this.shadowRoot.querySelector("[data-discard]")?.addEventListener("click", () => {
      this.draft = clone(this.base);
      this.dirty = false;
      this.render();
    });
    this.shadowRoot.querySelector("[data-review]")?.addEventListener("click", () => this.review());
    this.bindContent();
  }
  bindContent() {
    this.shadowRoot.querySelector("[data-controls]")?.addEventListener("click", () =>
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: this.entry.climate_entity },
          bubbles: true,
          composed: true,
        }),
      ),
    );
    this.shadowRoot.querySelectorAll("#content [data-tab]").forEach(
      (b) =>
        (b.onclick = () => {
          this.tab = b.dataset.tab;
          this.render();
          this.scrollTop = 0;
        }),
    );
    this.shadowRoot.querySelectorAll("[data-field]").forEach((input) => {
      const handler = () => {
        this.setValue(
          input.dataset.field,
          input.type === "checkbox"
            ? input.checked
            : input.type === "number"
              ? input.value === ""
                ? null
                : Number(input.value) * Number(input.dataset.scale || 1)
              : input.value,
        );
        if (input.type === "checkbox" || input.dataset.field.endsWith("tuning_mode")) this.render();
      };
      input.addEventListener(
        input.tagName === "INPUT" && !["checkbox"].includes(input.type) ? "input" : "change",
        handler,
      );
    });
    this.pickers.forEach(({ id, path, kind, multiple, label }) => {
      const el = this.shadowRoot.getElementById(id);
      el?.configure({
        entities: this.data.entities,
        selected: this.value(path),
        kind,
        multiple,
        label,
        timeZone: this._hass?.config?.time_zone,
      });
      el?.addEventListener("selection-changed", (e) => {
        this.setValue(path, e.detail);
        if (path === "alarm_sensors") this.render();
      });
    });
    this.shadowRoot.querySelectorAll("[data-reaction]").forEach(
      (b) =>
        (b.onclick = () => {
          this.setValue("reaction_time", b.dataset.reaction);
          this.render();
        }),
    );
    this.shadowRoot.querySelector("[data-add-room]")?.addEventListener("click", () => {
      if (this.draft.rooms.length >= 20) {
        this.notice("Maximum 20 rooms");
        return;
      }
      this.draft.rooms.push({
        id: newId(),
        name: "",
        temperature_sensors: [],
        occupancy_sensors: [],
        tuning_mode: "auto",
        kp: 0.2,
        ki: 0.000035,
        kd: 0,
        target: this.base.comfort_temperature,
      });
      this.dirty = true;
      this.render();
    });
    this.shadowRoot.querySelectorAll("[data-remove-room]").forEach(
      (b) =>
        (b.onclick = () => {
          let i = Number(b.dataset.removeRoom),
            r = this.draft.rooms[i];
          if (!confirm(`Remove ${r.name || "this room"}? Any schedules targeting it will also be removed.`))
            return;
          this.draft.rooms.splice(i, 1);
          this.draft.schedules = this.draft.schedules.filter((s) => s.source !== r.id);
          if (this.draft.sleep_room === r.id) this.draft.sleep_room = "";
          if (this.draft.morning_source === r.id) this.draft.morning_source = "Average";
          this.dirty = true;
          this.render();
        }),
    );
    this.shadowRoot.querySelector("[data-add-schedule]")?.addEventListener("click", () => {
      this.draft.schedules.push({
        id: newId(),
        name: "",
        entity_id: "",
        source: "Average",
        target: this.draft.comfort_temperature,
        preheat: true,
        priority: 0,
        data_temperature_unit: this.data.unit,
      });
      this.dirty = true;
      this.render();
    });
    this.shadowRoot.querySelectorAll("[data-remove-schedule]").forEach(
      (b) =>
        (b.onclick = () => {
          this.draft.schedules.splice(Number(b.dataset.removeSchedule), 1);
          this.dirty = true;
          this.render();
        }),
    );
  }
  review() {
    const changed = Object.keys(this.draft).filter(
      (k) => JSON.stringify(this.draft[k]) !== JSON.stringify(this.base[k]),
    );
    const labels = {
      rooms: "Room sensors and tuning",
      schedules: "Weekly schedule connections",
      shadow: this.draft.shadow ? "Switch to observation only" : "Enable active heater control",
      heater: "Heater relay",
      alarm_sensors: "Phone alarm sensors",
      alarm_owners: "Alarm owner associations",
      room_buffer: "Room protection buffer",
      reaction_time: "Occupancy reaction time",
      occupancy_margin: "Occupancy grouping tolerance",
    };
    const active = !this.draft.shadow && (this.base.shadow || this.base.heater !== this.draft.heater);
    const dialog = document.createElement("div");
    dialog.className = "review";
    dialog.innerHTML = `<section class="dialog" role="dialog" aria-modal="true" aria-label="Review changes"><h1>Ready to save?</h1><p class="muted">Only ${escapeHTML(this.entry.name)} will be updated. The thermostat may briefly reload.</p><ul>${changed.map((k) => `<li>${escapeHTML(labels[k] || k.replaceAll("_", " "))}</li>`).join("")}</ul>${active ? `<div class="errorbox"><strong>Active heater control</strong><p>Comfort Sense will control the selected relay. The thermostat starts Off after an equipment or control-mode change.</p><label class="row"><input type="checkbox" id="acknowledge">I have stopped other controllers of this relay.</label></div>` : ""}<div class="errorbox" id="save-error" role="alert" hidden></div><div class="row between space"><button class="button" data-cancel>Keep editing</button><button class="button primary" data-save ${active ? "disabled" : ""}>Save changes</button></div></section>`;
    this.shadowRoot.append(dialog);
    const cancel = () => {
      dialog.remove();
      this.shadowRoot.querySelector("[data-review]")?.focus();
    };
    dialog.querySelector("[data-cancel]").onclick = cancel;
    const button = dialog.querySelector("[data-save]"),
      ack = dialog.querySelector("#acknowledge");
    if (ack) ack.onchange = () => (button.disabled = !ack.checked);
    dialog.onkeydown = (e) => {
      if (e.key === "Escape") cancel();
      if (e.key === "Tab") {
        const nodes = [...dialog.querySelectorAll("button:not(:disabled),input")],
          first = nodes[0],
          last = nodes.at(-1);
        if (e.shiftKey && this.shadowRoot.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && this.shadowRoot.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    dialog.querySelector("[data-cancel]").focus();
    button.onclick = async () => {
      button.disabled = true;
      button.textContent = "Saving…";
      try {
        await this._hass.callWS({
          type: "comfort_sense/save",
          entry_id: this.entry.entry_id,
          revision: this.baseRevision,
          unit: this.data.unit,
          config: this.draft,
          acknowledge_active: !!ack?.checked,
        });
        this.dirty = false;
        dialog.remove();
        await new Promise((r) => setTimeout(r, 1000));
        await this.load();
        this.notice("Settings saved");
      } catch (e) {
        const error = dialog.querySelector("#save-error");
        error.hidden = false;
        error.textContent = e.message || "Could not save. Review the selected fields.";
        button.disabled = false;
        button.textContent = "Save changes";
      }
    };
  }
  notice(message) {
    const el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    el.textContent = message;
    this.shadowRoot.append(el);
    setTimeout(() => el.remove(), 4500);
  }
}
customElements.define("comfort-sense-panel", ComfortSensePanel);
