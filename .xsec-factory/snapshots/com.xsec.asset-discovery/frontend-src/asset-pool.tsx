import { Badge, Checkbox, Field, Input, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@xsec/ui-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { AssetDiscoveryApi } from "./host";
import type { AssetFilters, AssetPage, CollectionRun, Project } from "./types";
import { formatTime, providerLabel, runTitle } from "./utils";
import { Button, ConfirmModal, EmptyState, ErrorState, Modal, Notice, Select } from "./ui";

const INITIAL_FILTERS: AssetFilters = { importedOnly: false, page: 1, pageSize: 50 };

type AssetPoolProps = {
  api: AssetDiscoveryApi;
  runs: CollectionRun[];
  selectedRunId?: string;
  onSelectedRunId: (value?: string) => void;
};

type AssetFilterToolbarProps = {
  filters: AssetFilters;
  queryDraft: string;
  runs: CollectionRun[];
  selectedCount: number;
  mutating: boolean;
  onSubmit: () => void;
  onQuery: (value: string) => void;
  onUpdate: (next: Partial<AssetFilters>) => void;
  onRun: (value?: string) => void;
  onImport: () => void;
  onDelete: () => void;
};

type AssetTableProps = {
  page: AssetPage;
  filters: AssetFilters;
  selected: string[];
  mutating: boolean;
  onSelected: (value: string[]) => void;
  onUpdate: (next: Partial<AssetFilters>) => void;
};

export function AssetPool({ api, runs, selectedRunId, onSelectedRunId }: AssetPoolProps) {
  const [filters, setFilters] = useState<AssetFilters>({ ...INITIAL_FILTERS, runId: selectedRunId });
  const [queryDraft, setQueryDraft] = useState("");
  const [page, setPage] = useState<AssetPage>();
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [importOpen, setImportOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>();
  const [projectsError, setProjectsError] = useState<string>();
  const [projectId, setProjectId] = useState("");
  const [mutating, setMutating] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const latestFilters = useRef(filters);
  const projectRequestGeneration = useRef(0);
  latestFilters.current = filters;

  const load = useCallback(async (requestedFilters = filters) => {
    setLoading(true); setError(undefined); setPage(undefined); setSelected([]);
    try {
      const next = await api.assets(requestedFilters);
      if (latestFilters.current !== requestedFilters) return;
      const lastPage = Math.max(1, Math.ceil(next.total / requestedFilters.pageSize));
      if (!next.items.length && requestedFilters.page > lastPage) {
        setFilters((current) => ({ ...current, page: lastPage }));
        return;
      }
      setPage(next);
      setSelected([]);
    } catch (reason) {
      if (latestFilters.current === requestedFilters) setError(`读取资产池失败：${String(reason)}`);
    } finally {
      if (latestFilters.current === requestedFilters) setLoading(false);
    }
  }, [api, filters]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (selectedRunId !== filters.runId) setFilters((current) => ({ ...current, runId: selectedRunId, page: 1 })); }, [filters.runId, selectedRunId]);

  const update = (next: Partial<AssetFilters>) => setFilters((current) => ({ ...current, ...next, page: next.page ?? 1 }));
  const openImport = async () => {
    const generation = ++projectRequestGeneration.current;
    setImportOpen(true); setProjectId(""); setProjects(undefined); setProjectsError(undefined);
    try {
      const next = await api.projects();
      if (generation === projectRequestGeneration.current) setProjects(next);
    } catch (reason) {
      if (generation === projectRequestGeneration.current) setProjectsError(`读取项目列表失败：${String(reason)}`);
    }
  };
  const confirmImport = async () => {
    if (!projectId) { setProjectsError("请选择目标项目。"); return; }
    setMutating(true);
    try { const result = await api.importAssets(selected, projectId); setImportOpen(false); setProjectId(""); await load(latestFilters.current); setNotice(`导入完成：新增 ${result.created}，跳过 ${result.skipped}，失败 ${result.failed}`); } catch (reason) { setProjectsError(`导入失败：${String(reason)}`); } finally { setMutating(false); }
  };
  const remove = async () => {
    const selectedCount = selected.length;
    setMutating(true);
    console.info("asset-discovery.assets.delete.started", { selectedCount });
    try {
      const result = await api.deleteAssets(selected);
      setDeleteOpen(false);
      await load(latestFilters.current);
      console.info("asset-discovery.assets.delete.completed", { selectedCount, deleted: result.deleted });
      setNotice(`已删除 ${result.deleted} 条资产。`);
    } catch (reason) {
      console.error("asset-discovery.assets.delete.failed", { selectedCount, message: String(reason) });
      setError(`删除资产失败：${String(reason)}`);
    } finally {
      setMutating(false);
    }
  };
  return <section className="ad-assets" aria-busy={loading}>
    <AssetFilterToolbar filters={filters} queryDraft={queryDraft} runs={runs} selectedCount={selected.length} mutating={mutating} onSubmit={() => update({ query: queryDraft.trim() || undefined })} onQuery={(value) => { setQueryDraft(value); if (!value) update({ query: undefined }); }} onUpdate={update} onRun={onSelectedRunId} onImport={() => void openImport()} onDelete={() => setDeleteOpen(true)} />
    {notice ? <Notice>{notice}</Notice> : null}
    {loading ? <p className="ad-muted" role="status">正在读取资产池…</p> : null}
    {error ? <ErrorState error={error} onRetry={() => void load()} /> : null}
    {!error && !loading && !page?.items.length ? <EmptyState>资产池为空</EmptyState> : null}
    {page?.items.length ? <AssetTable page={page} filters={filters} selected={selected} mutating={mutating} onSelected={setSelected} onUpdate={update} /> : null}
    {importOpen ? <ImportModal projects={projects} error={projectsError} projectId={projectId} count={selected.length} saving={mutating} onProject={setProjectId} onClose={() => setImportOpen(false)} onConfirm={() => void confirmImport()} /> : null}
    {deleteOpen ? <ConfirmModal title="删除发现资产" detail={`确认删除选中的 ${selected.length} 条资产？此操作不可恢复。`} confirmLabel="删除" danger busy={mutating} onClose={() => setDeleteOpen(false)} onConfirm={() => void remove()} /> : null}
  </section>;
}

function AssetFilterToolbar({ filters, queryDraft, runs, selectedCount, mutating, onSubmit, onQuery, onUpdate, onRun, onImport, onDelete }: AssetFilterToolbarProps) {
  const selectRun = (value: string) => {
    const runId = value || undefined;
    onRun(runId);
    onUpdate({ runId });
  };
  return <div className="ad-filter-row" role="search" aria-label="资产池筛选">
    <Select aria-label="收集任务筛选" value={filters.runId ?? ""} options={[{ value: "", label: "全部收集任务" }, ...runs.map(run => ({ value: run.id, label: runTitle(run) }))]} onChange={selectRun} />
    <Select aria-label="数据源筛选" value={filters.provider ?? ""} options={[{ value: "", label: "全部数据源" }, { value: "hunter", label: "鹰图 Hunter" }, { value: "fofa", label: "FOFA + 天眼查" }]} onChange={value => onUpdate({ provider: value || undefined })} />
    <Input aria-label="资产 Host 搜索" value={queryDraft} placeholder="按 Host 模糊搜索" onChange={(event) => onQuery(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); onSubmit(); } }} />
    <Button onClick={onSubmit}>搜索</Button>
    <Select aria-label="导入状态筛选" value={filters.importedOnly ? "imported" : "all"} options={[{ value: "all", label: "全部资产" }, { value: "imported", label: "仅已导入" }]} onChange={value => onUpdate({ importedOnly: value === "imported" })} />
    <Button disabled={!selectedCount || mutating} onClick={onImport}>导入到项目{selectedCount ? `（${selectedCount}）` : ""}</Button><Button className="danger" disabled={!selectedCount || mutating} onClick={onDelete}>删除选中</Button>
  </div>;
}

function AssetTable({ page, filters, selected, mutating, onSelected, onUpdate }: AssetTableProps) {
  const allSelected = Boolean(page.items.length) && page.items.every((asset) => selected.includes(asset.id));
  const lastPage = Math.max(1, Math.ceil(page.total / filters.pageSize));
  const toggleAsset = (id: string, checked: boolean) => onSelected(checked ? [...selected, id] : selected.filter((item) => item !== id));
  return <>
    <Table aria-label="发现资产"><TableHead><TableRow><TableHeader><Checkbox label={<span className="ad-sr-only">选择当前页资产</span>} disabled={mutating} checked={allSelected} onCheckedChange={checked => onSelected(checked ? page.items.map(asset => asset.id) : [])} /></TableHeader><TableHeader>类型</TableHeader><TableHeader>资产</TableHeader><TableHeader>Host</TableHeader><TableHeader>来源</TableHeader><TableHeader>导入状态</TableHeader><TableHeader>发现时间</TableHeader></TableRow></TableHead><TableBody>{page.items.map(asset => <TableRow key={asset.id} data-selected={selected.includes(asset.id)}><TableCell><Checkbox label={<span className="ad-sr-only">选择 {asset.raw_value}</span>} disabled={mutating} checked={selected.includes(asset.id)} onCheckedChange={checked => toggleAsset(asset.id, checked)} /></TableCell><TableCell>{asset.type}</TableCell><TableCell className="ellipsis" title={asset.raw_value}><strong>{asset.raw_value}</strong></TableCell><TableCell className="ellipsis" title={asset.host ?? ""}>{asset.host || "—"}</TableCell><TableCell>{asset.source_provider ? providerLabel(asset.source_provider) : "—"}</TableCell><TableCell><Badge tone={asset.imported ? "success" : "neutral"}>{asset.imported ? "已导入" : "未导入"}</Badge></TableCell><TableCell>{formatTime(asset.created_at)}</TableCell></TableRow>)}</TableBody></Table>
    <div className="ad-pagination"><span>共 {page.total} 条</span><Select aria-label="每页资产数量" value={String(filters.pageSize)} disabled={mutating} options={[25, 50, 100].map(size => ({ value: String(size), label: size + " / 页" }))} onChange={value => onUpdate({ pageSize: Number(value) })} /><Button className="compact" disabled={filters.page <= 1 || mutating} onClick={() => onUpdate({ page: filters.page - 1 })}>上一页</Button><span>{filters.page} / {lastPage}</span><Button className="compact" disabled={filters.page >= lastPage || mutating} onClick={() => onUpdate({ page: filters.page + 1 })}>下一页</Button></div>
  </>;
}

function ImportModal({ projects, error, projectId, count, saving, onProject, onClose, onConfirm }: {
  projects?: Project[]; error?: string; projectId: string; count: number; saving: boolean; onProject: (value: string) => void; onClose: () => void; onConfirm: () => void;
}) {
  const close = () => { if (!saving) onClose(); };
  return <Modal title="导入到项目" busy={saving} onClose={close} footer={<><Button disabled={saving} onClick={close}>取消</Button><Button variant="primary" loading={saving} disabled={!projectId} onClick={onConfirm}>导入</Button></>}><p className="ad-description">将把选中的 {count} 条资产导入到目标项目；已存在的资产会自动跳过。</p><Field label="目标项目" error={error}>{props => <Select {...props} value={projectId} disabled={saving || !projects} options={[{ value: "", label: "选择目标项目" }, ...(projects ?? []).map(project => ({ value: project.id, label: `${project.name}（${project.code}）` }))]} onChange={onProject} />}</Field>{projects && !projects.length ? <p className="ad-muted">暂无可导入项目。</p> : null}</Modal>;
}
