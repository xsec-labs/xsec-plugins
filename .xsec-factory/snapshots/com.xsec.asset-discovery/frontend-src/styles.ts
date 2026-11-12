export const styles = `
[data-xui] { --xsec-surface-base:var(--xui-canvas); --xsec-surface-container:var(--xui-surface); --xsec-surface-subtle:var(--xui-subtle); --xsec-surface-hover:var(--xui-hover); --xsec-text-primary:var(--xui-text); --xsec-text-secondary:var(--xui-muted); --xsec-text-tertiary:var(--xui-muted); --xsec-border:var(--xui-border); --xsec-border-subtle:var(--xui-border); --xsec-accent:var(--xui-primary); --xsec-accent-strong:var(--xui-primary); --xsec-accent-soft:var(--xui-subtle); --xsec-status-info:var(--xui-primary); --xsec-status-error:var(--xui-danger); --xsec-status-warning:var(--xui-warning); --xsec-status-success:var(--xui-success); --xsec-radius-sm:5px; --xsec-radius-md:var(--xui-radius-control); --xsec-radius-lg:var(--xui-radius-panel); --xsec-control-height:var(--xui-control-height); }
.ad-shared-dialog { width:min(680px,calc(100vw - 32px)); }
.ad-sr-only { position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0; }
.ad-filter-row>.xui-select-trigger { width:180px; }
.ad-filter-row>.xui-input { width:240px;max-width:100%; }
.ad-pagination>.xui-select-trigger { width:120px; }
.ad-kpis { display:flex;align-items:center;gap:16px;margin:16px 0; }
.xui-table .ellipsis { max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
:root { color: var(--xsec-text-primary); background: var(--xsec-surface-base); font-family: var(--xsec-font-family); color-scheme: var(--xsec-color-mode); }
* { box-sizing: border-box; }
body { margin: 0; background: var(--xsec-surface-base); }
button, input, select, textarea { font: inherit; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: .56; }
.ad-app { min-height: 100vh; padding: 24px; color: var(--xsec-text-primary); background: var(--xsec-surface-base); }
.ad-header, .ad-toolbar, .ad-tab-row, .ad-console-header, .ad-section-title, .ad-actions, .ad-filter-row, .ad-form-actions { display: flex; align-items: center; gap: 10px; }
.ad-header, .ad-console-header { justify-content: space-between; align-items: flex-start; }
.ad-eyebrow { margin: 0 0 6px; color: var(--xsec-text-tertiary); font-size: calc(11px * var(--xui-font-scale)); font-weight: 700; letter-spacing: .08em; }
.ad-title { margin: 0; font-size: calc(24px * var(--xui-font-scale)); line-height: 1.25; letter-spacing: -.02em; }
.ad-description, .ad-muted { color: var(--xsec-text-secondary); }
.ad-description { margin: 7px 0 0; max-width: 720px; font-size: calc(13px * var(--xui-font-scale)); }
.ad-input, .ad-select, .ad-textarea { border: 1px solid var(--xsec-border); border-radius: var(--xsec-radius-md); color: var(--xsec-text-primary); background: var(--xsec-surface-container); }
.ad-kpis { color: var(--xsec-text-secondary); font-size: calc(12px * var(--xui-font-scale)); }
.ad-kpis strong { color: var(--xsec-text-primary); }
.ad-runs, .ad-assets { margin-top: 18px; }
.ad-toolbar, .ad-filter-row { flex-wrap: wrap; margin-bottom: 14px; }
.ad-input, .ad-select { min-height: var(--xsec-control-height); padding: 0 10px; }
.ad-input.search { min-width: 260px; }
.ad-input:focus, .ad-select:focus, .ad-textarea:focus { outline: 2px solid var(--xsec-accent); outline-offset: 1px; }
.ad-status-tabs { display:flex; flex-wrap:wrap; gap:8px; }
.ad-status-tab { flex-direction:column; align-items:flex-start; gap:0; height:auto; min-width:72px; padding:8px 10px; border:1px solid var(--xsec-border-subtle); border-radius:var(--xsec-radius-md); color:var(--xsec-text-secondary); background:var(--xsec-surface-container); text-align:left; }
.ad-status-tab strong { display: block; margin-top: 2px; color: var(--xsec-text-primary); font-size: calc(16px * var(--xui-font-scale)); }
.ad-status-tab.active { border-color: var(--xsec-accent); background: var(--xsec-accent-soft); }
.ad-master-detail { display: grid; grid-template-columns: minmax(270px, 31%) minmax(0, 1fr); min-height: 560px; border: 1px solid var(--xsec-border-subtle); border-radius: var(--xsec-radius-lg); overflow: hidden; background: var(--xsec-surface-container); }
.ad-run-list { min-height: 0; border-right: 1px solid var(--xsec-border-subtle); overflow: auto; background: var(--xsec-surface-subtle); }
.ad-run-card { display:block; width:100%; height:auto; min-height:var(--xui-control-height); padding:14px; border:0; border-bottom:1px solid var(--xsec-border-subtle); border-radius:0; color:inherit; background:transparent; text-align:left; white-space:normal; }
.ad-run-card:hover, .ad-run-card.active { background: var(--xsec-accent-soft); }
.ad-run-card-title, .ad-metadata { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ad-run-card-title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ad-run-card p { margin: 7px 0; overflow: hidden; color: var(--xsec-text-secondary); text-overflow: ellipsis; white-space: nowrap; font-size: calc(12px * var(--xui-font-scale)); }
.ad-run-outcome { display: block; margin: 0 0 7px; overflow: hidden; color: var(--xsec-status-error); text-overflow: ellipsis; white-space: nowrap; font-size: calc(11px * var(--xui-font-scale)); }
.ad-metadata { color: var(--xsec-text-tertiary); font-size: calc(11px * var(--xui-font-scale)); }
.ad-console { min-width: 0; overflow: auto; }
.ad-console-header { padding: 20px 20px 16px; border-bottom: 1px solid var(--xsec-border-subtle); }
.ad-console-header h2 { margin: 0; font-size: calc(18px * var(--xui-font-scale)); }
.ad-console-body { display: grid; gap: 16px; padding: 18px 20px 24px; }
.ad-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.ad-flow-card { min-height: 96px; padding: 11px; border: 1px solid var(--xsec-border-subtle); border-radius: var(--xsec-radius-md); background: var(--xsec-surface-subtle); }
.ad-flow-card.active { border-color: var(--xsec-status-info); }
.ad-flow-card.failed { border-color: var(--xsec-status-error); }
.ad-flow-card.done { border-color: var(--xsec-status-success); }
.ad-flow-card strong, .ad-flow-card small { display: block; }
.ad-flow-card small { margin-top: 8px; color: var(--xsec-text-secondary); font-size: calc(11px * var(--xui-font-scale)); line-height: 1.4; }
.ad-card, .ad-section { border: 1px solid var(--xsec-border-subtle); border-radius: var(--xsec-radius-md); background: var(--xsec-surface-container); }
.ad-section-title { justify-content: space-between; min-height: 42px; padding: 0 13px; border-bottom: 1px solid var(--xsec-border-subtle); font-size: calc(13px * var(--xui-font-scale)); }
.ad-section-body { padding: 13px; }
.ad-split { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(250px, .8fr); gap: 14px; }
.ad-code { max-height: 260px; margin: 0; overflow: auto; padding: 12px; border-radius: var(--xsec-radius-sm); color: var(--xsec-text-primary); background: var(--xsec-surface-subtle); font: calc(12px * var(--xui-font-scale))/1.55 var(--xsec-font-family); white-space: pre-wrap; word-break: break-word; }
.ad-process { display: grid; gap: 8px; max-height: 360px; overflow: auto; }
.ad-process-wrap { display: grid; gap: 9px; }
.ad-process-live { margin: 0; color: var(--xsec-status-info); font-size: calc(12px * var(--xui-font-scale)); }
.ad-new-records { justify-self: end; }
.ad-message, .ad-tool { padding: 10px; border: 1px solid var(--xsec-border-subtle); border-radius: var(--xsec-radius-sm); background: var(--xsec-surface-subtle); }
.ad-message header, .ad-tool summary { color: var(--xsec-text-secondary); font-size: calc(11px * var(--xui-font-scale)); font-weight: 700; }
.ad-message p { margin: 7px 0 0; white-space: pre-wrap; word-break: break-word; }
.ad-message pre { margin: 7px 0 0; overflow: auto; color: var(--xsec-text-primary); font: calc(12px * var(--xui-font-scale))/1.55 var(--xsec-font-family); white-space: pre-wrap; word-break: break-word; }
.ad-tool summary { cursor: pointer; }
.ad-tool .ad-code { margin-top: 8px; max-height: 180px; }
.ad-tool-value { margin-top: 10px; }
.ad-tool-value > strong { color: var(--xsec-text-tertiary); font-size: calc(11px * var(--xui-font-scale)); }
.ad-inspector { display: grid; grid-template-columns: 120px minmax(0, 1fr); margin: 0; }
.ad-inspector dt, .ad-inspector dd { margin: 0; padding: 8px 0; border-bottom: 1px solid var(--xsec-border-subtle); font-size: calc(12px * var(--xui-font-scale)); }
.ad-inspector dt { color: var(--xsec-text-tertiary); }
.ad-inspector dd { overflow: hidden; color: var(--xsec-text-secondary); text-overflow: ellipsis; }
.ad-pagination { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 14px; color: var(--xsec-text-secondary); font-size: calc(12px * var(--xui-font-scale)); }
.ad-empty, .ad-error { padding: 40px 24px; color: var(--xsec-text-secondary); text-align: center; }
.ad-error { color: var(--xsec-status-error); }
.ad-notice { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--xsec-status-warning); border-radius: var(--xsec-radius-md); color: var(--xsec-text-primary); background: var(--xsec-surface-subtle); }
.ad-field { display: grid; gap: 7px; margin-bottom: 15px; color: var(--xsec-text-secondary); font-size: calc(12px * var(--xui-font-scale)); font-weight: 650; }
.ad-field .ad-input, .ad-field .ad-select, .ad-field .ad-textarea { width: 100%; color: var(--xsec-text-primary); font-weight: 400; }
.ad-textarea { min-height: 142px; padding: 10px; resize: vertical; }
.ad-field-error { color: var(--xsec-status-error); font-weight: 500; }
.ad-confirm-detail { margin: 0; color: var(--xsec-text-secondary); line-height: 1.65; }
.ad-credential { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:8px; align-items:center; }
.ad-settings { max-width: 760px; }
.ad-settings .ad-runs { display:grid; gap:16px; }
.ad-shared-dialog .xui-field { margin-bottom:16px; }
@media (max-width: 900px) { .ad-master-detail, .ad-split { grid-template-columns: 1fr; } .ad-run-list { max-height: 300px; border-right: 0; border-bottom: 1px solid var(--xsec-border-subtle); } .ad-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .ad-app { padding: 16px; } .ad-header, .ad-tab-row, .ad-console-header { display: grid; } .ad-kpis { flex-wrap: wrap; } .ad-filter-row>.xui-select-trigger { flex:1 1 150px;min-width:0;width:auto; } .ad-filter-row>.xui-input { flex:1 1 220px;width:auto; } .ad-flow { grid-template-columns: 1fr; } .ad-credential { grid-template-columns: 1fr; } .ad-actions { flex-wrap: wrap; } }
`;
