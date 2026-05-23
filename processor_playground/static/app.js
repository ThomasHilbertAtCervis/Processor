import { html } from 'htm/react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from 'reactflow';

const PRIMITIVES = ['int', 'decimal', 'string', 'bool', 'timestamp', 'any'];
// esm.sh/reactflow builds can differ slightly in enum shape, so keep a string fallback.
const EDGE_MARKER = MarkerType?.ArrowClosed ?? 'arrowclosed';

async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function apiPut(path, body) {
  const response = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function apiDelete(path) {
  const response = await fetch(path, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  if (response.status === 204) {
    return null;
  }
  return response.json().catch(() => null);
}

function debounce(fn, delayMs) {
  let timeoutId = null;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => fn(...args), delayMs);
  };
}

const StartNode = ({ selected }) => html`
  <div className=${`node-start${selected ? ' selected' : ''}`}>
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const EventNode = ({ data, selected }) => html`
  <div className=${`node-event${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
    <div className="node-label">${data.label || 'Event Trigger'}</div>
    ${data.signalType ? html`<div className="node-signal-badge">[${data.signalType}]</div>` : null}
    ${data.filter ? html`<div className="node-filter">${data.filter}</div>` : null}
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const ConditionNode = ({ data, selected }) => html`
  <div className=${`node-condition${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
    <div className="node-label">${data.label || 'Condition'}</div>
    ${data.filter ? html`<div className="node-filter">${data.filter}</div>` : null}
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const ForeachNode = ({ data, selected }) => html`
  <div className=${`node-foreach${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
    <div className="node-foreach-label">${data.iteratorExpr || data.label || 'foreach'}</div>
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const SubmoduleNode = ({ data, selected }) => html`
  <div className=${`node-submodule${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
    <div className="node-submodule-header">
      <span className="node-submodule-icon">⊞</span>
      <span className="node-submodule-name">${data.label || 'Sub-module'}</span>
    </div>
    <div className="node-submodule-signals">
      ${(data.inputs || []).map((sig, idx) => html`
        <div key=${`in-${idx}`} className="node-signal node-signal-in">
          ▶ ${sig.name}${sig.type_ref && sig.type_ref !== 'any' ? ` [${sig.type_ref}]` : ''}
        </div>
      `)}
      ${(data.outputs || []).map((sig, idx) => html`
        <div key=${`out-${idx}`} className="node-signal node-signal-out">
          ${sig.name}${sig.type_ref && sig.type_ref !== 'any' ? ` [${sig.type_ref}]` : ''} ▶
        </div>
      `)}
    </div>
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const EmitNode = ({ data, selected }) => html`
  <div className=${`node-emit${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
    <div className="node-label">${data.label || 'Emit Event'}</div>
    ${data.signalType ? html`<div className="node-signal-badge">[${data.signalType}]</div>` : null}
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const EndNode = ({ selected }) => html`
  <div className=${`node-end${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
  </div>
`;

const DataMappingNode = ({ data, selected }) => html`
  <div className=${`node-datamapping${selected ? ' selected' : ''}`}>
    <${Handle} type="target" position=${Position.Left} />
    <div className="node-label">${data.label || 'Data Mapping'}</div>
    ${data.mappings?.length
      ? html`
          <div className="node-mappings">
            ${data.mappings.map((mapping, idx) => html`<div key=${idx} className="node-mapping">${mapping}</div>`)}
          </div>
        `
      : null}
    <${Handle} type="source" position=${Position.Right} />
  </div>
`;

const NODE_TYPES = {
  start: StartNode,
  event: EventNode,
  condition: ConditionNode,
  foreach: ForeachNode,
  submodule: SubmoduleNode,
  emit: EmitNode,
  end: EndNode,
  datamapping: DataMappingNode,
};

const PALETTE_NODES = [
  { type: 'start', label: '● Start' },
  { type: 'event', label: '▷ Event Trigger' },
  { type: 'condition', label: '□ Condition / Action' },
  { type: 'foreach', label: '‖ For Each' },
  { type: 'submodule', label: '⊞ Sub-module' },
  { type: 'emit', label: '▶ Emit Event' },
  { type: 'datamapping', label: '⇄ Data Mapping' },
  { type: 'end', label: '◉ End' },
];


function PropertiesPanel({ selected, nodes, edges, onUpdateNode, onUpdateEdge, dataTypes, modules }) {
  const [localData, setLocalData] = useState({});
  const item = selected
    ? selected.type === 'node'
      ? nodes.find((node) => node.id === selected.id)
      : edges.find((edge) => edge.id === selected.id)
    : null;

  useEffect(() => {
    setLocalData(item ? { ...(item.data || {}), label: item.label || item.data?.label || '' } : {});
  }, [item?.id, selected?.type]);

  if (!selected || !item) {
    return html`
      <div className="properties-shell">
        <div className="properties-panel properties-empty">
          <p>Select a node or edge to edit its properties.</p>
        </div>
      </div>
    `;
  }

  const setField = (key, value) => setLocalData((previous) => ({ ...previous, [key]: value }));
  const save = () => {
    if (selected.type === 'node') {
      onUpdateNode(selected.id, localData);
      return;
    }
    onUpdateEdge(selected.id, localData);
  };

  if (selected.type === 'node') {
    const nodeType = item.type;
    return html`
      <div className="properties-shell">
        <div className="properties-panel">
          <h3 className="props-title">Node: ${nodeType}</h3>
          <div className="prop-row">
            <label>Label</label>
            <input value=${localData.label || ''} onInput=${(event) => setField('label', event.target.value)} />
          </div>
          ${(nodeType === 'event' || nodeType === 'emit') && html`
            <div className="prop-row">
              <label>Signal Type</label>
              <select value=${localData.signalType || ''} onChange=${(event) => setField('signalType', event.target.value)}>
                <option value="">— none —</option>
                ${dataTypes.map((dataType) => html`
                  <option key=${dataType.type_id} value=${dataType.type_id}>${dataType.name}</option>
                `)}
              </select>
            </div>
          `}
          ${(nodeType === 'event' || nodeType === 'condition') && html`
            <div className="prop-row">
              <label>Filter Expression</label>
              <input
                value=${localData.filter || ''}
                placeholder="event.location == 'Berlin'"
                onInput=${(event) => setField('filter', event.target.value)}
              />
            </div>
          `}
          ${nodeType === 'foreach' && html`
            <div className="prop-row">
              <label>Iterator Expression</label>
              <input
                value=${localData.iteratorExpr || ''}
                placeholder="stockItem in event.contents"
                onInput=${(event) => setField('iteratorExpr', event.target.value)}
              />
            </div>
          `}
          ${nodeType === 'submodule' && html`
            <div className="prop-row">
              <label>Sub-module</label>
              <select
                value=${localData.moduleId || ''}
                onChange=${(event) => {
                  const module = modules.find((candidate) => candidate.module_id === event.target.value);
                  setField('moduleId', event.target.value);
                  if (module) {
                    setLocalData((previous) => ({
                      ...previous,
                      moduleId: module.module_id,
                      label: module.name,
                      inputs: module.inputs || [],
                      outputs: module.outputs || [],
                    }));
                  }
                }}
              >
                <option value="">— select module —</option>
                ${modules.map((module) => html`
                  <option key=${module.module_id} value=${module.module_id}>${module.name}</option>
                `)}
              </select>
            </div>
          `}
          ${nodeType === 'datamapping' && html`
            <div className="prop-row">
              <label>Mappings (one per line)</label>
              <textarea
                rows="5"
                value=${(localData.mappings || []).join('\n')}
                onInput=${(event) => setField('mappings', event.target.value.split('\n').map((line) => line.trim()).filter(Boolean))}
              />
            </div>
          `}
          <button className="btn-save" onClick=${save}>Apply</button>
        </div>
      </div>
    `;
  }

  return html`
    <div className="properties-shell">
      <div className="properties-panel">
        <h3 className="props-title">Connection</h3>
        <div className="prop-row">
          <label>Label</label>
          <input value=${localData.label || ''} onInput=${(event) => setField('label', event.target.value)} />
        </div>
        <div className="prop-row">
          <label>Signal Type</label>
          <select value=${localData.signalType || ''} onChange=${(event) => setField('signalType', event.target.value)}>
            <option value="">— none —</option>
            ${dataTypes.map((dataType) => html`
              <option key=${dataType.type_id} value=${dataType.type_id}>${dataType.name}</option>
            `)}
          </select>
        </div>
        <button className="btn-save" onClick=${save}>Apply</button>
      </div>
    </div>
  `;
}

function DataTypePanel({ dataTypes, onSave, onDelete }) {
  const [editing, setEditing] = useState(null);
  const [newField, setNewField] = useState({ name: '', type_ref: 'string' });

  const beginNew = () => setEditing({ type_id: '', name: '', kind: 'struct', fields: [], element_type: 'any' });
  const beginEdit = (dataType) => setEditing(JSON.parse(JSON.stringify(dataType)));
  const allTypes = [...PRIMITIVES, ...dataTypes.map((dataType) => dataType.type_id)];

  if (editing) {
    return html`
      <div className="dt-editor">
        <h4>${editing._saved ? 'Edit Data Type' : 'New Data Type'}</h4>
        <div className="prop-row">
          <label>ID</label>
          <input
            value=${editing.type_id}
            disabled=${Boolean(editing._saved)}
            placeholder="ShipmentEvent"
            onInput=${(event) => setEditing((draft) => ({ ...draft, type_id: event.target.value }))}
          />
        </div>
        <div className="prop-row">
          <label>Name</label>
          <input
            value=${editing.name}
            placeholder="Display name"
            onInput=${(event) => setEditing((draft) => ({ ...draft, name: event.target.value }))}
          />
        </div>
        <div className="prop-row">
          <label>Kind</label>
          <select value=${editing.kind} onChange=${(event) => setEditing((draft) => ({ ...draft, kind: event.target.value }))}>
            <option value="struct">Struct</option>
            <option value="array">Array</option>
            <option value="dict">Dict</option>
          </select>
        </div>
        ${editing.kind === 'struct'
          ? html`
              <div className="dt-fields">
                <div className="dt-fields-header">Fields</div>
                ${(editing.fields || []).map((field, idx) => html`
                  <div key=${idx} className="dt-field-row">
                    <span>${field.name}</span>
                    <span className="dt-field-type">(${field.type_ref})</span>
                    <button className="btn-icon" onClick=${() => setEditing((draft) => ({ ...draft, fields: draft.fields.filter((_, i) => i !== idx) }))}>✕</button>
                  </div>
                `)}
                <div className="dt-field-add">
                  <input
                    value=${newField.name}
                    placeholder="field name"
                    onInput=${(event) => setNewField((draft) => ({ ...draft, name: event.target.value }))}
                  />
                  <select value=${newField.type_ref} onChange=${(event) => setNewField((draft) => ({ ...draft, type_ref: event.target.value }))}>
                    ${allTypes.map((typeName) => html`<option key=${typeName} value=${typeName}>${typeName}</option>`)}
                  </select>
                  <button
                    onClick=${() => {
                      if (!newField.name.trim()) {
                        return;
                      }
                      setEditing((draft) => ({
                        ...draft,
                        fields: [...(draft.fields || []), { name: newField.name.trim(), type_ref: newField.type_ref }],
                      }));
                      setNewField({ name: '', type_ref: 'string' });
                    }}
                  >
                    + Add
                  </button>
                </div>
              </div>
            `
          : html`
              <div className="prop-row">
                <label>Element Type</label>
                <select
                  value=${editing.element_type || 'any'}
                  onChange=${(event) => setEditing((draft) => ({ ...draft, element_type: event.target.value }))}
                >
                  ${allTypes.map((typeName) => html`<option key=${typeName} value=${typeName}>${typeName}</option>`)}
                </select>
              </div>
            `}
        <div className="dt-actions">
          <button
            className="btn-save"
            onClick=${() => {
              onSave({
                type_id: editing.type_id,
                name: editing.name,
                kind: editing.kind,
                fields: editing.kind === 'struct' ? (editing.fields || []) : [],
                element_type: editing.kind === 'struct' ? null : editing.element_type || 'any',
              });
              setEditing(null);
            }}
          >
            Save
          </button>
          <button className="btn-cancel" onClick=${() => setEditing(null)}>Cancel</button>
        </div>
      </div>
    `;
  }

  return html`
    <div className="dt-list">
      ${!dataTypes.length ? html`<p className="empty-hint">No data types yet.</p>` : null}
      ${dataTypes.map((dataType) => html`
        <div key=${dataType.type_id} className="dt-item">
          <div className="dt-item-header">
            <span className="dt-item-name">${dataType.name}</span>
            <span className="dt-item-kind">${dataType.kind}</span>
          </div>
          ${dataType.kind === 'struct'
            ? html`
                <div className="dt-item-fields">
                  ${(dataType.fields || []).map((field, idx) => html`
                    <div key=${`${dataType.type_id}-${idx}`} className="dt-item-field">${field.name} (${field.type_ref})</div>
                  `)}
                </div>
              `
            : html`<div className="dt-item-element-type">elements: ${dataType.element_type}</div>`}
          <div className="dt-item-actions">
            <button className="btn-small" onClick=${() => beginEdit({ ...dataType, _saved: true })}>Edit</button>
            <button className="btn-small btn-danger" onClick=${() => onDelete(dataType.type_id)}>Delete</button>
          </div>
        </div>
      `)}
      <button className="btn-add-dt" onClick=${beginNew}>+ New Data Type</button>
    </div>
  `;
}

function ModuleSignalsPanel({ module, dataTypes, onSave }) {
  const [inputs, setInputs] = useState(module?.inputs || []);
  const [outputs, setOutputs] = useState(module?.outputs || []);
  const typeOptions = [...PRIMITIVES, ...dataTypes.map((dataType) => dataType.type_id)];

  useEffect(() => {
    setInputs(module?.inputs || []);
    setOutputs(module?.outputs || []);
  }, [module?.module_id]);

  const renderSignals = (signals, setSignals, heading, buttonText) => html`
    <div className="signals-section">
      <div className="signals-header">${heading}</div>
      ${signals.map((signal, idx) => html`
        <div key=${idx} className="signal-row">
          <input
            value=${signal.name || ''}
            placeholder="name"
            onInput=${(event) => setSignals((items) => items.map((item, itemIndex) => itemIndex === idx ? { ...item, name: event.target.value } : item))}
          />
          <select
            value=${signal.type_ref || 'any'}
            onChange=${(event) => setSignals((items) => items.map((item, itemIndex) => itemIndex === idx ? { ...item, type_ref: event.target.value } : item))}
          >
            ${typeOptions.map((typeName) => html`<option key=${typeName} value=${typeName}>${typeName}</option>`)}
          </select>
          <button className="btn-icon" onClick=${() => setSignals((items) => items.filter((_, itemIndex) => itemIndex !== idx))}>✕</button>
        </div>
      `)}
      <button className="btn-small" onClick=${() => setSignals((items) => [...items, { name: '', type_ref: 'any', filter: null }])}>${buttonText}</button>
    </div>
  `;

  return html`
    <div className="module-signals">
      ${renderSignals(inputs, setInputs, 'Inputs', '+ Add Input')}
      ${renderSignals(outputs, setOutputs, 'Outputs', '+ Add Output')}
      <button className="btn-save" onClick=${() => onSave({ inputs, outputs })}>Save Signals</button>
    </div>
  `;
}

function DiagramCanvas({
  currentModule,
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeClick,
  onEdgeClick,
  onNodeDoubleClick,
  onPaneClick,
  onDrop,
  onDragOver,
  reactFlowWrapper,
  setReactFlowInstance,
}) {
  return html`
    <div className="canvas-wrap" ref=${reactFlowWrapper}>
      <div className="module-frame"></div>
      <div className="module-frame-label">${currentModule.name}</div>
      <${ReactFlow}
        nodes=${nodes}
        edges=${edges}
        nodeTypes=${NODE_TYPES}
        onNodesChange=${onNodesChange}
        onEdgesChange=${onEdgesChange}
        onConnect=${onConnect}
        onNodeClick=${onNodeClick}
        onEdgeClick=${onEdgeClick}
        onNodeDoubleClick=${onNodeDoubleClick}
        onPaneClick=${onPaneClick}
        onDrop=${onDrop}
        onDragOver=${onDragOver}
        onInit=${setReactFlowInstance}
        fitView=${true}
        snapToGrid=${true}
        snapGrid=${[16, 16]}
        deleteKeyCode="Delete"
        defaultEdgeOptions=${{ markerEnd: { type: EDGE_MARKER }, style: { strokeWidth: 1.5 } }}
      >
        <${Controls} />
        <${Background} variant="dots" gap=${16} size=${1} />
        <${MiniMap} zoomable=${true} pannable=${true} nodeStrokeWidth=${3} />
      </${ReactFlow}>
    </div>
  `;
}

function Sidebar({
  modules,
  currentModuleId,
  onSelectModule,
  onNewModule,
  onDeleteModule,
  dataTypes,
  onSaveDt,
  onDeleteDt,
  currentModule,
  onSaveSignals,
  activeTab,
  setActiveTab,
}) {
  const [creatingModule, setCreatingModule] = useState(false);
  const [newModuleId, setNewModuleId] = useState('');
  const [newModuleName, setNewModuleName] = useState('');

  const createModule = async () => {
    if (!newModuleId.trim() || !newModuleName.trim()) {
      return;
    }
    await onNewModule(newModuleId.trim(), newModuleName.trim());
    setNewModuleId('');
    setNewModuleName('');
    setCreatingModule(false);
  };

  const onPaletteDragStart = (event, nodeType) => {
    event.dataTransfer.setData('application/reactflow', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  return html`
    <div className="sidebar">
      <div className="sidebar-logo">Process Playground</div>
      <div className="sidebar-tabs">
        <button className=${`tab${activeTab === 'modules' ? ' active' : ''}`} onClick=${() => setActiveTab('modules')}>Modules</button>
        <button className=${`tab${activeTab === 'types' ? ' active' : ''}`} onClick=${() => setActiveTab('types')}>
          Types${dataTypes.length ? html` <span className="tab-count">${dataTypes.length}</span>` : null}
        </button>
        <button className=${`tab${activeTab === 'palette' ? ' active' : ''}`} onClick=${() => setActiveTab('palette')}>Palette</button>
      </div>

      ${activeTab === 'modules' && html`
        <div className="sidebar-section">
          <div className="section-header">Modules</div>
          ${modules.map((module) => html`
            <div key=${module.module_id} className=${`module-item${module.module_id === currentModuleId ? ' active' : ''}`} onClick=${() => onSelectModule(module.module_id)}>
              <span className="module-item-name">${module.name}</span>
              <button className="btn-icon btn-del" onClick=${(event) => { event.stopPropagation(); onDeleteModule(module.module_id); }}>✕</button>
            </div>
          `)}
          ${creatingModule
            ? html`
                <div className="new-module-form">
                  <input value=${newModuleId} placeholder="module-id" onInput=${(event) => setNewModuleId(event.target.value)} />
                  <input value=${newModuleName} placeholder="Module name" onInput=${(event) => setNewModuleName(event.target.value)} />
                  <button onClick=${createModule}>Create</button>
                  <button className="btn-cancel" onClick=${() => setCreatingModule(false)}>Cancel</button>
                </div>
              `
            : html`<button className="btn-add-module" onClick=${() => setCreatingModule(true)}>+ New Module</button>`}
        </div>
        ${currentModule
          ? html`
              <div className="sidebar-section">
                <div className="section-header">Signals: ${currentModule.name}</div>
                <${ModuleSignalsPanel} module=${currentModule} dataTypes=${dataTypes} onSave=${onSaveSignals} />
              </div>
            `
          : null}
      `}

      ${activeTab === 'types' && html`
        <div className="sidebar-section">
          <div className="section-header">Global Data Types</div>
          <p className="section-hint">Shared across all modules. Used to type signals and connections.</p>
          <${DataTypePanel} dataTypes=${dataTypes} onSave=${onSaveDt} onDelete=${onDeleteDt} />
        </div>
      `}

      ${activeTab === 'palette' && html`
        <div className="sidebar-section">
          <div className="section-header">Node Palette</div>
          <p className="palette-hint">Drag a node onto the canvas.</p>
          ${PALETTE_NODES.map((node) => html`
            <div
              key=${node.type}
              className=${`palette-item palette-${node.type}`}
              draggable=${true}
              onDragStart=${(event) => onPaletteDragStart(event, node.type)}
            >
              ${node.label}
            </div>
          `)}
        </div>
      `}
    </div>
  `;
}

const genId = () => {
  if (globalThis.crypto?.randomUUID) {
    return `node_${globalThis.crypto.randomUUID()}`;
  }
  return `node_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
};

function App() {
  const [modules, setModules] = useState([]);
  const [dataTypes, setDataTypes] = useState([]);
  const [currentModuleId, setCurrentModuleId] = useState(null);
  const [currentModule, setCurrentModule] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState('modules');
  const [status, setStatus] = useState(null);
  const reactFlowWrapper = useRef(null);
  const [reactFlowInstance, setReactFlowInstance] = useState(null);
  const saveRef = useRef(() => {});
  const showStatusRef = useRef(null);

  const showStatus = useCallback((message, isErr = false) => {
    if (showStatusRef.current) {
      window.clearTimeout(showStatusRef.current);
    }
    setStatus({ msg: message, isErr });
    showStatusRef.current = window.setTimeout(() => setStatus(null), 2500);
  }, []);

  const refreshModules = useCallback(async () => {
    const modulesPayload = await apiGet('/api/modules');
    setModules(modulesPayload);
    return modulesPayload;
  }, []);

  const refreshDataTypes = useCallback(async () => {
    const typesPayload = await apiGet('/api/data-types');
    setDataTypes(typesPayload);
    return typesPayload;
  }, []);

  const loadModule = useCallback(async (moduleId) => {
    const modulePayload = await apiGet(`/api/modules/${moduleId}`);
    setCurrentModuleId(moduleId);
    setCurrentModule(modulePayload);
    setNodes(modulePayload.nodes || []);
    setEdges(modulePayload.edges || []);
    setSelected(null);
    return modulePayload;
  }, []);

  useEffect(() => {
    Promise.all([refreshModules(), refreshDataTypes()])
      .then(async ([modulePayload]) => {
        if (modulePayload.length) {
          await loadModule(modulePayload[0].module_id);
        }
      })
      .catch((error) => showStatus(`Failed to load: ${error.message}`, true));
  }, [loadModule, refreshDataTypes, refreshModules, showStatus]);

  const saveCurrentDiagram = useCallback(async () => {
    if (!currentModuleId || !currentModule) {
      return;
    }
    const payload = {
      ...currentModule,
      nodes,
      edges,
      inputs: currentModule.inputs || [],
      outputs: currentModule.outputs || [],
      flow: currentModule.flow || [],
      submodules: currentModule.submodules || [],
    };
    const saved = await apiPut(`/api/modules/${currentModuleId}`, payload);
    setCurrentModule(saved);
    setModules((items) => items.map((item) => (item.module_id === saved.module_id ? saved : item)));
    showStatus('Saved ✓');
  }, [currentModule, currentModuleId, edges, nodes, showStatus]);

  useEffect(() => {
    saveRef.current = debounce(() => {
      saveCurrentDiagram().catch((error) => showStatus(`Save failed: ${error.message}`, true));
    }, 900);
  }, [saveCurrentDiagram, showStatus]);

  useEffect(() => {
    if (!currentModuleId || !currentModule) {
      return;
    }
    const savedNodes = JSON.stringify(currentModule.nodes || []);
    const savedEdges = JSON.stringify(currentModule.edges || []);
    if (savedNodes === JSON.stringify(nodes) && savedEdges === JSON.stringify(edges)) {
      return;
    }
    saveRef.current();
  }, [nodes, edges, currentModuleId, currentModule]);

  const onNodesChange = useCallback((changes) => {
    setNodes((items) => applyNodeChanges(changes, items));
  }, []);

  const onEdgesChange = useCallback((changes) => {
    setEdges((items) => applyEdgeChanges(changes, items));
  }, []);

  const onConnect = useCallback((connection) => {
    setEdges((items) => addEdge({ ...connection, markerEnd: { type: EDGE_MARKER } }, items));
  }, []);

  const onNodeClick = useCallback((_, node) => setSelected({ type: 'node', id: node.id }), []);
  const onEdgeClick = useCallback((_, edge) => setSelected({ type: 'edge', id: edge.id }), []);
  const onPaneClick = useCallback(() => setSelected(null), []);

  const onNodeDoubleClick = useCallback((_, node) => {
    if (node.type === 'submodule' && node.data?.moduleId) {
      loadModule(node.data.moduleId).catch((error) => showStatus(`Load failed: ${error.message}`, true));
      setActiveTab('modules');
    }
  }, [loadModule, showStatus]);

  const onUpdateNode = useCallback((nodeId, newData) => {
    setNodes((items) => items.map((node) => (
      node.id === nodeId
        ? { ...node, data: { ...node.data, ...newData } }
        : node
    )));
  }, []);

  const onUpdateEdge = useCallback((edgeId, newData) => {
    setEdges((items) => items.map((edge) => (
      edge.id === edgeId
        ? {
            ...edge,
            data: { ...edge.data, ...newData },
            label: newData.label || '',
          }
        : edge
    )));
  }, []);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((event) => {
    event.preventDefault();
    const type = event.dataTransfer.getData('application/reactflow');
    if (!type || !reactFlowInstance || !reactFlowWrapper.current) {
      return;
    }
    const bounds = reactFlowWrapper.current.getBoundingClientRect();
    const position = reactFlowInstance.project({
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    });
    const defaultLabels = {
      start: 'Start',
      event: 'Event Trigger',
      condition: 'Condition',
      foreach: 'foreach',
      submodule: 'Sub-module',
      emit: 'Emit Event',
      datamapping: 'Data Mapping',
      end: 'End',
    };
    setNodes((items) => [
      ...items,
      {
        id: genId(),
        type,
        position,
        data: { label: defaultLabels[type] || type },
      },
    ]);
  }, [reactFlowInstance]);

  const onSelectModule = useCallback(async (moduleId) => {
    try {
      await loadModule(moduleId);
      setActiveTab('modules');
    } catch (error) {
      showStatus(`Load failed: ${error.message}`, true);
    }
  }, [loadModule, showStatus]);

  const onNewModule = useCallback(async (moduleId, name) => {
    try {
      const saved = await apiPut(`/api/modules/${moduleId}`, {
        module_id: moduleId,
        name,
        inputs: [],
        outputs: [],
        nodes: [],
        edges: [],
        flow: [],
        submodules: [],
      });
      setModules((items) => [...items, saved].sort((left, right) => left.name.localeCompare(right.name, undefined, { sensitivity: 'base' })));
      await loadModule(moduleId);
      showStatus('Module created');
    } catch (error) {
      showStatus(`Create failed: ${error.message}`, true);
    }
  }, [loadModule, showStatus]);

  const onDeleteModule = useCallback(async (moduleId) => {
    if (!window.confirm(`Delete module "${moduleId}"?`)) {
      return;
    }
    try {
      await apiDelete(`/api/modules/${moduleId}`);
      const remaining = modules.filter((module) => module.module_id !== moduleId);
      setModules(remaining);
      if (currentModuleId === moduleId) {
        setCurrentModuleId(null);
        setCurrentModule(null);
        setNodes([]);
        setEdges([]);
        setSelected(null);
        if (remaining[0]) {
          await loadModule(remaining[0].module_id);
        }
      }
      showStatus('Deleted');
    } catch (error) {
      showStatus(`Delete failed: ${error.message}`, true);
    }
  }, [currentModuleId, loadModule, modules, showStatus]);

  const onSaveSignals = useCallback(async ({ inputs, outputs }) => {
    if (!currentModuleId || !currentModule) {
      return;
    }
    try {
      const saved = await apiPut(`/api/modules/${currentModuleId}`, {
        ...currentModule,
        inputs,
        outputs,
        nodes,
        edges,
      });
      setCurrentModule(saved);
      setModules((items) => items.map((item) => (item.module_id === saved.module_id ? saved : item)));
      setNodes((items) => items.map((node) => (
        node.type === 'submodule' && node.data?.moduleId === currentModuleId
          ? { ...node, data: { ...node.data, label: saved.name, inputs: saved.inputs || [], outputs: saved.outputs || [] } }
          : node
      )));
      showStatus('Signals saved');
    } catch (error) {
      showStatus(`Save failed: ${error.message}`, true);
    }
  }, [currentModule, currentModuleId, edges, nodes, showStatus]);

  const onSaveDt = useCallback(async (dataType) => {
    try {
      const saved = await apiPut(`/api/data-types/${dataType.type_id}`, dataType);
      setDataTypes((items) => {
        const existingIndex = items.findIndex((item) => item.type_id === saved.type_id);
        if (existingIndex === -1) {
          return [...items, saved].sort((left, right) => left.name.localeCompare(right.name, undefined, { sensitivity: 'base' }));
        }
        return items.map((item, index) => (index === existingIndex ? saved : item));
      });
      showStatus('Data type saved');
    } catch (error) {
      showStatus(`Save failed: ${error.message}`, true);
    }
  }, [showStatus]);

  const onDeleteDt = useCallback(async (typeId) => {
    if (!window.confirm(`Delete data type "${typeId}"?`)) {
      return;
    }
    try {
      await apiDelete(`/api/data-types/${typeId}`);
      setDataTypes((items) => items.filter((item) => item.type_id !== typeId));
      showStatus('Deleted');
    } catch (error) {
      showStatus(`Delete failed: ${error.message}`, true);
    }
  }, [showStatus]);

  const nodeTypes = useMemo(() => NODE_TYPES, []);

  return html`
    <div id="app">
      <${Sidebar}
        modules=${modules}
        currentModuleId=${currentModuleId}
        onSelectModule=${onSelectModule}
        onNewModule=${onNewModule}
        onDeleteModule=${onDeleteModule}
        dataTypes=${dataTypes}
        onSaveDt=${onSaveDt}
        onDeleteDt=${onDeleteDt}
        currentModule=${currentModule}
        onSaveSignals=${onSaveSignals}
        activeTab=${activeTab}
        setActiveTab=${setActiveTab}
      />
      <div className="main-area">
        ${currentModule
          ? html`
              <div className="canvas-header">
                <span className="canvas-module-name">${currentModule.name}</span>
                <button className="btn-save-manual" onClick=${() => saveCurrentDiagram().catch((error) => showStatus(`Save failed: ${error.message}`, true))}>💾 Save</button>
                ${status ? html`<span className=${`status-badge${status.isErr ? ' error' : ''}`}>${status.msg}</span>` : null}
              </div>
              <${DiagramCanvas}
              key=${currentModule.module_id}
              currentModule=${currentModule}
              nodes=${nodes.map((node) => ({ ...node, type: node.type || 'condition' }))}
              edges=${edges}
              onNodesChange=${onNodesChange}
              onEdgesChange=${onEdgesChange}
              onConnect=${onConnect}
              onNodeClick=${onNodeClick}
              onEdgeClick=${onEdgeClick}
              onNodeDoubleClick=${onNodeDoubleClick}
              onPaneClick=${onPaneClick}
              onDrop=${onDrop}
              onDragOver=${onDragOver}
              reactFlowWrapper=${reactFlowWrapper}
              setReactFlowInstance=${setReactFlowInstance}
              />
            `
          : html`
              <div className="canvas-empty">
                <div className="canvas-empty-inner">
                  <h2>Process Playground</h2>
                  <p>Select or create a module in the sidebar to start designing.</p>
                </div>
              </div>
            `}
      </div>
      <${PropertiesPanel}
        selected=${selected}
        nodes=${nodes}
        edges=${edges}
        onUpdateNode=${onUpdateNode}
        onUpdateEdge=${onUpdateEdge}
        dataTypes=${dataTypes}
        modules=${modules}
      />
    </div>
  `;
}

const root = createRoot(document.getElementById('root'));
root.render(html`<${App} />`);
