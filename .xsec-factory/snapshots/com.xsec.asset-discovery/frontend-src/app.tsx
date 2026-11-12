import { Field, Input, Tabs, Textarea, useThemeSettings } from "@xsec/ui-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { AssetDiscoveryApi } from "./host";
import type { CollectionStatusFilter, CollectorProvider, CollectorSettings, ExecutionDefaults, PluginHost } from "./types";
import { approvalModeLabel, collectionMetrics, fofaScopeRequiresTianyan, normalizeCollectorScope, validateCollectorScope } from "./utils";
import { AssetPool } from "./asset-pool";
import { useDashboardState } from "./dashboard-state";
import { RunsPanel } from "./runs-panel";
import { Button, Modal, Notice, Select } from "./ui";

type DashboardProps = { api: AssetDiscoveryApi; host: PluginHost };
type DashboardTab = "runs" | "assets";
type StartInput = { prompt: string; name?: string; provider: CollectorProvider; workdir?: string };
type CollectModalProps = {
  settings?: CollectorSettings;
  settingsReady: boolean;
  settingsError?: string;
  defaults?: ExecutionDefaults;
  defaultsReady: boolean;
  defaultsError?: string;
  onClose: () => void;
  onOpenSettings: () => Promise<void>;
  onStart: (input: StartInput) => Promise<void>;
};

function providerConfigured(settings: CollectorSettings, provider: CollectorProvider, prompt: string): boolean {
  if (provider === "hunter") return settings.hunterApiKeyConfigured && Boolean(settings.hunterApiBaseUrl.trim());
  return settings.fofaApiKeyConfigured
    && Boolean(settings.fofaApiBaseUrl.trim())
    && (!fofaScopeRequiresTianyan(prompt) || settings.tianyanApiKeyConfigured);
}

function DashboardHeader({ onOpenCollect, onRefresh }: { onOpenCollect: () => void; onRefresh: () => void }) {
  return <header className="ad-header">
    <div>
      <p className="ad-eyebrow">ASSET DISCOVERY CONSOLE</p>
      <h1 className="ad-title">资产发现</h1>
      <p className="ad-description">管理资产收集任务、执行过程和跨项目资产池。</p>
    </div>
    <div className="ad-actions">
      <Button className="primary" onClick={onOpenCollect}>启动资产收集</Button>
      <Button onClick={onRefresh}>刷新</Button>
    </div>
  </header>;
}

export function AssetDiscoveryApp({ api }: DashboardProps) {
  const dashboard = useDashboardState(api);
  const { colorMode } = useThemeSettings();
  const [tab, setTab] = useState<DashboardTab>("runs");
  const [selectedRunId, setSelectedRunId] = useState<string>();
  const [assetRunId, setAssetRunId] = useState<string>();
  const [filter, setFilter] = useState<CollectionStatusFilter>("all");
  const [query, setQuery] = useState("");
  const [collectOpen, setCollectOpen] = useState(false);
  const [notice, setNotice] = useState<string>();
  const metrics = useMemo(() => collectionMetrics(dashboard.runs), [dashboard.runs]);
  const openAssets = useCallback((runId: string) => {
    setAssetRunId(runId);
    setTab("assets");
  }, []);
  const openSettings = useCallback(async () => { await api.openSettings(); }, [api]);
  const startCollection = useCallback(async (input: StartInput) => {
    const result = await api.start(input);
    const runId = result.collection_run_id || result.run_id || result.process.id;
    setFilter("all");
    setTab("runs");
    setCollectOpen(false);
    const loadState = await dashboard.loadRuns(true);
    if (loadState === "ok") setSelectedRunId(runId);
    setNotice(`资产收集已启动（任务 ID：${runId}）`);
  }, [api, dashboard.loadRuns]);
  useEffect(() => {
    if (assetRunId && !dashboard.runs.some((run) => run.id === assetRunId)) setAssetRunId(undefined);
  }, [assetRunId, dashboard.runs]);

  return <main className="ad-app" data-color-mode={colorMode}>
    <DashboardHeader onOpenCollect={() => setCollectOpen(true)} onRefresh={() => void dashboard.refresh()} />
    {notice ? <p className="ad-muted">{notice}</p> : null}
    <div className="ad-kpis"><span>运行 <strong>{metrics.running}</strong></span><span>完成 <strong>{metrics.completed}</strong></span><span>失败 <strong>{metrics.failed}</strong></span><span>资产 <strong>{metrics.assets}</strong></span></div>
    <Tabs label="资产发现页面" value={tab} onValueChange={value => { if (value !== "runs" && value !== "assets") throw new Error("Invalid asset discovery tab"); setTab(value); }} items={[
      { value: "runs", label: `收集操作台${metrics.running ? ` · ${metrics.running}` : ""}`, content: <RunsPanel api={api} runs={dashboard.runs} loading={dashboard.runsLoading} error={dashboard.runsError} selectedRunId={selectedRunId} filter={filter} query={query} onSelect={setSelectedRunId} onDeleted={(runId) => { dashboard.removeRun(runId); setSelectedRunId(undefined); }} onFilter={setFilter} onQuery={setQuery} onRefresh={async () => { await dashboard.loadRuns(true); }} onStart={() => setCollectOpen(true)} onOpenAssets={openAssets} onOpenSettings={openSettings} /> },
      { value: "assets", label: `资产池 · ${metrics.assets}`, content: <AssetPool api={api} runs={dashboard.runs} selectedRunId={assetRunId} onSelectedRunId={setAssetRunId} /> },
    ]} />
    {collectOpen ? <CollectModal settings={dashboard.settings} settingsReady={dashboard.settingsReady} settingsError={dashboard.settingsError} defaults={dashboard.defaults} defaultsReady={dashboard.defaultsReady} defaultsError={dashboard.defaultsError} onClose={() => setCollectOpen(false)} onOpenSettings={openSettings} onStart={startCollection} /> : null}
  </main>;
}

function CollectFields({ provider, prompt, name, workdir, saving, onProvider, onPrompt, onName, onWorkdir }: {
  provider: CollectorProvider;
  prompt: string;
  name: string;
  workdir: string;
  saving: boolean;
  onProvider: (provider: CollectorProvider) => void;
  onPrompt: (value: string) => void;
  onName: (value: string) => void;
  onWorkdir: (value: string) => void;
}) {
  return <>
    <Field label="任务名称（可选）">{props => <Input {...props} value={name} disabled={saving} onChange={(event) => onName(event.target.value)} placeholder="留空则自动生成" />}</Field>
    <Field label="收集数据源">{props => <Select {...props} value={provider} disabled={saving} options={[{ value: "hunter", label: "鹰图 Hunter（通配符域名 / HackerOne）" }, { value: "fofa", label: "FOFA + 天眼查（企业名称 / 通配符域名）" }]} onChange={value => { if (value !== "hunter" && value !== "fofa") throw new Error("Invalid collector provider"); onProvider(value); }} />}</Field>
    <Field label="授权收集范围">{props => <Textarea {...props} className="ad-textarea" value={prompt} disabled={saving} onChange={(event) => onPrompt(event.target.value)} placeholder={"https://hackerone.com/example\n*.example.com"} />}</Field>
    <Field label="工作目录（可选）">{props => <Input {...props} value={workdir} disabled={saving} onChange={(event) => onWorkdir(event.target.value)} placeholder="留空则使用全局配置" />}</Field>
  </>;
}

function CollectModal({ settings, settingsReady, settingsError, defaults, defaultsReady, defaultsError, onClose, onOpenSettings, onStart }: CollectModalProps) {
  const [provider, setProvider] = useState<CollectorProvider>(settings?.provider === "fofa" ? "fofa" : "hunter");
  const [providerTouched, setProviderTouched] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [workdir, setWorkdir] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  useEffect(() => {
    if (!providerTouched && settings) setProvider(settings.provider === "fofa" ? "fofa" : "hunter");
  }, [providerTouched, settings]);
  const settingsUnavailable = !settingsReady || !settings;
  const configurationIncomplete = !settings || !providerConfigured(settings, provider, prompt);
  const close = () => { if (!saving) onClose(); };
  const openSettings = async () => {
    try {
      await onOpenSettings();
      onClose();
    } catch (reason) {
      setError(`打开插件设置失败：${String(reason)}`);
    }
  };
  const start = async () => {
    const normalizedPrompt = normalizeCollectorScope(prompt);
    const scopeError = validateCollectorScope(provider, normalizedPrompt);
    if (scopeError) return setError(scopeError);
    if (settingsUnavailable) return setError(settingsError || "资产发现设置尚未读取成功。");
    if (configurationIncomplete) return setError("当前数据源配置不完整，请先完成插件设置。");
    if (!defaultsReady || !defaults) return setError(defaultsError || "任务默认设置尚未读取成功。");
    setSaving(true);
    setError(undefined);
    try {
      await onStart({ prompt: normalizedPrompt, name: name.trim() || undefined, provider, workdir: workdir.trim() || undefined });
    } catch (reason) {
      setError(`启动资产收集失败：${String(reason)}`);
    } finally {
      setSaving(false);
    }
  };
  return <Modal title="启动资产收集" busy={saving} onClose={close} footer={<><Button disabled={saving} onClick={close}>取消</Button><Button className="primary" loading={saving} disabled={settingsUnavailable || configurationIncomplete || !defaultsReady || !defaults} onClick={() => void start()}>启动</Button></>}>
    <CollectFields provider={provider} prompt={prompt} name={name} workdir={workdir} saving={saving} onProvider={(value) => { setProviderTouched(true); setProvider(value); }} onPrompt={setPrompt} onName={setName} onWorkdir={setWorkdir} />
    <p className="ad-muted">访问模式：{defaultsReady && defaults ? `继承批量默认：${approvalModeLabel(defaults.approval_mode)}` : defaultsError ? "任务默认设置不可用" : "正在读取任务默认设置…"}</p>
    {configurationIncomplete ? <Notice action={<Button className="compact" disabled={saving} onClick={() => void openSettings()}>前往插件设置</Button>}>当前数据源配置不完整，无法启动收集任务。</Notice> : null}
    {settingsError ? <p className="ad-field-error">{settingsError}</p> : null}{defaultsError ? <p className="ad-field-error">{defaultsError}</p> : null}{error ? <p className="ad-field-error">{error}</p> : null}
  </Modal>;
}
