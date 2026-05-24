// Stateless / locally-stateful UI components.
//
// Rules (see ARCHITECTURE.md):
//   - No fetch calls here.
//   - No knowledge of API URLs or persistence.
//   - All persistence intent is emitted via callbacks (onSave..., onDelete...).

import React, { useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
} from 'reactflow';
import { html } from './lib/html.js';
import { NODE_TYPES } from './nodes.js';

// esm.sh/reactflow builds can differ slightly in enum shape, so keep a string fallback.
export const EDGE_MARKER = MarkerType?.ArrowClosed ?? 'arrowclosed';

// --------------------------------------------------------- PropertiesPanel

export function PropertiesPanel({ selected, nodes, edges, onUpdateNode, onUpdateEdge, dataTypes, modules }) {
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
          ${nodeType === 'python' && html`
            <div className="prop-row">
              <label>Input ports</label>
              <div className="prop-portlist">
                ${(item.inputs || []).length === 0
                  ? html`<span className="prop-portlist-empty">(none)</span>`
                  : (item.inputs || []).map((port) => html`
                      <code key=${port.name} className="prop-port">inputs['${port.name}']</code>
                    `)}
              </div>
            </div>
            <div className="prop-row">
              <label>Output ports</label>
              <div className="prop-portlist">
                ${(item.outputs || []).length === 0
                  ? html`<span className="prop-portlist-empty">(none)</span>`
                  : (item.outputs || []).map((port) => html`
                      <code key=${port.name} className="prop-port">outputs['${port.name}']</code>
                    `)}
              </div>
            </div>
            <div className="prop-row prop-row-code">
              <label>Python script</label>
              <textarea
                className="prop-code"
                spellCheck=${false}
                rows="14"
                value=${localData.code || ''}
                placeholder="outputs['result'] = inputs['value']"
                onInput=${(event) => setField('code', event.target.value)}
                onKeyDown=${(event) => {
                  if (event.key === 'Tab') {
                    event.preventDefault();
                    const ta = event.target;
                    const start = ta.selectionStart;
                    const end = ta.selectionEnd;
                    const next = ta.value.slice(0, start) + '    ' + ta.value.slice(end);
                    setField('code', next);
                    requestAnimationFrame(() => { ta.selectionStart = ta.selectionEnd = start + 4; });
                  }
                }}
              />
              <div className="prop-hint">
                Reads <code>inputs['port']</code>, writes <code>outputs['port'] = value</code>.
                Sandboxed: <code>if</code>, <code>for</code>, arithmetic,
                <code> len/range/min/max/sum</code>. No imports, no attribute access.
              </div>
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

// ------------------------------------------------------------ DataTypePanel

export function DataTypePanel({ dataTypes, primitives, onSave, onDelete }) {
  const [editing, setEditing] = useState(null);
  const [newField, setNewField] = useState({ name: '', type_ref: 'string' });

  const beginNew = () => setEditing({ type_id: '', name: '', kind: 'struct', fields: [], element_type: 'any' });
  const beginEdit = (dataType) => setEditing(JSON.parse(JSON.stringify(dataType)));
  const allTypes = [...primitives, ...dataTypes.map((dataType) => dataType.type_id)];

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
              // No kind/fields/element_type normalisation here — the backend
              // owns the invariant (see DataType.from_dict). We just send
              // exactly what the editor has, and let the server canonicalise.
              onSave({
                type_id: editing.type_id,
                name: editing.name,
                kind: editing.kind,
                fields: editing.fields || [],
                element_type: editing.element_type || null,
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

// ------------------------------------------------------ ModuleSignalsPanel

export function ModuleSignalsPanel({ module, dataTypes, primitives, onSave }) {
  const [inputs, setInputs] = useState(module?.inputs || []);
  const [outputs, setOutputs] = useState(module?.outputs || []);
  const typeOptions = [...primitives, ...dataTypes.map((dataType) => dataType.type_id)];

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

// --------------------------------------------------------- DiagramCanvas

export function DiagramCanvas({
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

// ----------------------------------------------------------------- Sidebar

export function RunPanel({ module, onRun, lastResult, running }) {
  const inputs = module?.inputs ?? [];
  const [signal, setSignal] = useState(inputs[0]?.name ?? '');
  const [valueText, setValueText] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!inputs.find((s) => s.name === signal)) {
      setSignal(inputs[0]?.name ?? '');
    }
  }, [module?.module_id, inputs.map((s) => s.name).join('|')]);

  const submit = async () => {
    setError(null);
    let value = null;
    const trimmed = valueText.trim();
    if (trimmed !== '') {
      try {
        value = JSON.parse(trimmed);
      } catch (err) {
        setError('Value must be valid JSON (e.g. 42, "abc", true, null, [1,2]).');
        return;
      }
    }
    if (!signal) {
      setError('Pick an input signal.');
      return;
    }
    await onRun(signal, value);
  };

  if (inputs.length === 0) {
    return html`
      <div className="run-panel">
        <div className="run-panel-empty">No module inputs defined. Add one in the Signals panel to enable runs.</div>
      </div>
    `;
  }

  return html`
    <div className="run-panel">
      <div className="run-row">
        <label>Input</label>
        <select value=${signal} onChange=${(event) => setSignal(event.target.value)}>
          ${inputs.map((sig) => html`<option key=${sig.name} value=${sig.name}>${sig.name} (${sig.type_ref})</option>`)}
        </select>
        <label>Value (JSON)</label>
        <input
          className="run-value"
          placeholder='e.g. 42 or "hello"'
          value=${valueText}
          onInput=${(event) => setValueText(event.target.value)}
          onKeyDown=${(event) => { if (event.key === 'Enter') submit(); }}
        />
        <button className="btn-run" disabled=${running} onClick=${submit}>${running ? 'Running…' : '▶ Run'}</button>
      </div>
      ${error ? html`<div className="run-error">${error}</div>` : null}
      ${lastResult ? html`
        <div className=${`run-result run-status-${lastResult.status}`}>
          <div className="run-result-header">status: <strong>${lastResult.status}</strong></div>
          <div className="run-result-section">
            <div className="run-result-label">outputs</div>
            <pre>${JSON.stringify(lastResult.outputs ?? {}, null, 2)}</pre>
          </div>
          ${lastResult.trace ? html`
            <details>
              <summary>trace (${lastResult.trace.length})</summary>
              <pre>${JSON.stringify(lastResult.trace, null, 2)}</pre>
            </details>
          ` : null}
        </div>
      ` : null}
    </div>
  `;
}

export function Sidebar({
  modules,
  currentModuleId,
  onSelectModule,
  onNewModule,
  onDeleteModule,
  dataTypes,
  primitives,
  nodeKinds,
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
                <${ModuleSignalsPanel} module=${currentModule} dataTypes=${dataTypes} primitives=${primitives} onSave=${onSaveSignals} />
              </div>
            `
          : null}
      `}

      ${activeTab === 'types' && html`
        <div className="sidebar-section">
          <div className="section-header">Global Data Types</div>
          <p className="section-hint">Shared across all modules. Used to type signals and connections.</p>
          <${DataTypePanel} dataTypes=${dataTypes} primitives=${primitives} onSave=${onSaveDt} onDelete=${onDeleteDt} />
        </div>
      `}

      ${activeTab === 'palette' && html`
        <div className="sidebar-section">
          <div className="section-header">Node Palette</div>
          <p className="palette-hint">Drag a node onto the canvas.</p>
          ${nodeKinds.map((node) => html`
            <div
              key=${node.type}
              className=${`palette-item palette-${node.type}`}
              draggable=${true}
              onDragStart=${(event) => onPaletteDragStart(event, node.type)}
            >
              ${node.palette_label}
            </div>
          `)}
        </div>
      `}
    </div>
  `;
}
