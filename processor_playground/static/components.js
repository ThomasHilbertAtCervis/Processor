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

export function PropertiesPanel({ selected, nodes, edges, onUpdateNode, onUpdateEdge, dataTypes, primitives = [], modules, databases = [] }) {
  const [localData, setLocalData] = useState({});
  const item = selected
    ? selected.type === 'node'
      ? nodes.find((node) => node.id === selected.id)
      : edges.find((edge) => edge.id === selected.id)
    : null;

  useEffect(() => {
    if (!item) { setLocalData({}); return; }
    const base = { ...(item.data || {}), label: item.label || item.data?.label || '' };
    // Seed signal_type from the existing port so the select reflects reality
    // for module_input/output nodes that were created before this field existed.
    if (item.type === 'module_input' && item.outputs && item.outputs[0] && !base.signal_type) {
      base.signal_type = item.outputs[0].type_ref || 'any';
    } else if (item.type === 'module_output' && item.inputs && item.inputs[0] && !base.signal_type) {
      base.signal_type = item.inputs[0].type_ref || 'any';
    }
    setLocalData(base);
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
          ${(nodeType === 'module_input' || nodeType === 'module_output') && html`
            <div className="prop-row">
              <label>Signal name</label>
              <input
                value=${localData.signal_name || ''}
                placeholder="e.g. order_received"
                onInput=${(event) => setField('signal_name', event.target.value)}
              />
            </div>
            <div className="prop-row">
              <label>Data type</label>
              <select
                value=${localData.signal_type
                  || (nodeType === 'module_input'
                        ? (item.outputs && item.outputs[0] && item.outputs[0].type_ref)
                        : (item.inputs && item.inputs[0] && item.inputs[0].type_ref))
                  || 'any'}
                onChange=${(event) => setField('signal_type', event.target.value)}
              >
                ${[...primitives, ...dataTypes.map((dt) => dt.type_id)].map((typeName) => html`
                  <option key=${typeName} value=${typeName}>${typeName}</option>
                `)}
              </select>
            </div>
            <p className="prop-hint">
              This node is the module's external
              ${nodeType === 'module_input' ? ' input' : ' output'}.
              Its signal name and data type define the module's
              ${nodeType === 'module_input' ? ' inputs' : ' outputs'} entry.
            </p>
          `}
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
          ${(nodeType === 'db_read' || nodeType === 'db_create') && html`
            <div className="prop-row">
              <label>Database</label>
              <select
                value=${localData.database_name || ''}
                onChange=${(event) => setField('database_name', event.target.value)}
              >
                <option value="">— select database —</option>
                ${databases.map((db) => html`
                  <option key=${db.name} value=${db.name}>${db.name}</option>
                `)}
              </select>
            </div>
            <div className="prop-row prop-row-code">
              <label>Query (SQL-ish)</label>
              <textarea
                className="prop-code"
                spellCheck=${false}
                rows="5"
                value=${localData.query || ''}
                placeholder=${nodeType === 'db_read'
                  ? 'SELECT * FROM customer WHERE region = :region'
                  : 'INSERT INTO customer (name) VALUES (:name)'}
                onInput=${(event) => setField('query', event.target.value)}
              />
              <div className="prop-hint">
                Each <code>:placeholder</code> becomes an input port on this node.
                Output port: <code>${nodeType === 'db_read' ? 'rows' : 'created'}</code>.
                ${nodeType === 'db_read'
                  ? ' Supported: SELECT * FROM <table> [WHERE col op val [AND ...]].'
                  : ' Supported: INSERT INTO <table> (cols) VALUES (vals).'}
              </div>
            </div>
          `}
          ${nodeType === 'submodule' && html`
            <div className="prop-row">
              <label>Sub-module</label>
              <select
                value=${localData.module_id || ''}
                onChange=${(event) => {
                  const module = modules.find((candidate) => candidate.module_id === event.target.value);
                  setField('module_id', event.target.value);
                  if (module) {
                    setLocalData((previous) => ({
                      ...previous,
                      module_id: module.module_id,
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
  const [newField, setNewField] = useState({ name: '', type_ref: 'string', kind: 'primitive' });

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
                    <span className="dt-field-type">
                      ${field.kind && field.kind !== 'primitive' ? `${field.kind}<${field.type_ref}>` : `(${field.type_ref})`}
                    </span>
                    <button className="btn-icon" onClick=${() => setEditing((draft) => ({ ...draft, fields: draft.fields.filter((_, i) => i !== idx) }))}>✕</button>
                  </div>
                `)}
                <div className="dt-field-add">
                  <input
                    value=${newField.name}
                    placeholder="field name"
                    onInput=${(event) => setNewField((draft) => ({ ...draft, name: event.target.value }))}
                  />
                  <select value=${newField.kind} onChange=${(event) => setNewField((draft) => ({ ...draft, kind: event.target.value }))}>
                    <option value="primitive">Type</option>
                    <option value="array">Array of</option>
                    <option value="dict">Dict of</option>
                  </select>
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
                        fields: [...(draft.fields || []), { name: newField.name.trim(), type_ref: newField.type_ref, kind: newField.kind }],
                      }));
                      setNewField({ name: '', type_ref: 'string', kind: 'primitive' });
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
                    <div key=${`${dataType.type_id}-${idx}`} className="dt-item-field">
                      ${field.name}
                      ${field.kind && field.kind !== 'primitive'
                        ? html`<span className="dt-field-kind">${field.kind}&lt;${field.type_ref}&gt;</span>`
                        : html`<span className="dt-field-kind">(${field.type_ref})</span>`}
                    </div>
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

// ------------------------------------------------------ (ModuleSignalsPanel removed)
//
// Module inputs/outputs are no longer maintained through a separate
// Signals tab. They are derived from the ``module_input``/``module_output``
// nodes on the canvas (see models._derive_signals_from_nodes). To add or
// rename a module signal, drop the corresponding node from the palette and
// edit its ``Signal name`` / ``Data type`` in the properties panel.

// --------------------------------------------------------- DatabasePanel

export function DatabasePanel({
  databases,
  dataTypes,
  onCreateDatabase,
  onDeleteDatabase,
  onAddTable,
  onAddRow,
  onDeleteRow,
}) {
  const [selectedName, setSelectedName] = useState(databases[0]?.name ?? null);
  const [newDbName, setNewDbName] = useState('');
  const [tableToAdd, setTableToAdd] = useState('');
  const [rowDraft, setRowDraft] = useState({});

  // Keep the selection valid as the list mutates.
  useEffect(() => {
    if (!databases.find((db) => db.name === selectedName)) {
      setSelectedName(databases[0]?.name ?? null);
    }
  }, [databases, selectedName]);

  const selected = databases.find((db) => db.name === selectedName) || null;
  const selectedTables = selected ? Object.keys(selected.tables || {}) : [];
  const [activeTable, setActiveTable] = useState(null);
  useEffect(() => {
    if (!selectedTables.includes(activeTable)) {
      setActiveTable(selectedTables[0] || null);
    }
  }, [selectedName, selectedTables.join('|')]);

  const tableType = activeTable
    ? dataTypes.find((dt) => dt.type_id === activeTable)
    : null;
  const columns = (tableType && tableType.kind === 'struct')
    ? (tableType.fields || []).map((field) => field.name)
    : [];

  const create = async () => {
    const name = newDbName.trim();
    if (!name) return;
    await onCreateDatabase(name);
    setNewDbName('');
    setSelectedName(name);
  };

  const addTable = async () => {
    if (!selected || !tableToAdd) return;
    await onAddTable(selected.name, tableToAdd);
    setActiveTable(tableToAdd);
    setTableToAdd('');
  };

  const submitRow = async () => {
    if (!selected || !activeTable) return;
    const row = { ...rowDraft };
    // Coerce numeric-looking strings — every field is a free text input.
    for (const key of Object.keys(row)) {
      const value = row[key];
      if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) {
        const num = Number(value);
        if (String(num) === value.trim()) row[key] = num;
      }
    }
    await onAddRow(selected.name, activeTable, row);
    setRowDraft({});
  };

  const availableTypeIds = dataTypes
    .map((dt) => dt.type_id)
    .filter((id) => !selectedTables.includes(id));

  return html`
    <div className="db-panel">
      <div className="db-list">
        ${databases.length === 0
          ? html`<p className="empty-hint">No databases yet.</p>`
          : databases.map((db) => html`
              <div
                key=${db.name}
                className=${`db-item${db.name === selectedName ? ' active' : ''}`}
                onClick=${() => setSelectedName(db.name)}
              >
                <span className="db-item-name">${db.name}</span>
                <span className="db-item-meta">${Object.keys(db.tables || {}).length} tables</span>
                <button
                  className="btn-icon btn-del"
                  onClick=${(event) => { event.stopPropagation(); onDeleteDatabase(db.name); }}
                >✕</button>
              </div>
            `)}
        <div className="new-module-form">
          <input
            value=${newDbName}
            placeholder="database name"
            onInput=${(event) => setNewDbName(event.target.value)}
          />
          <button onClick=${create}>+ Create</button>
        </div>
      </div>

      ${selected && html`
        <div className="db-detail">
          <div className="db-detail-header">${selected.name}</div>
          <div className="db-tables-row">
            ${selectedTables.map((typeId) => html`
              <button
                key=${typeId}
                className=${`db-tab${typeId === activeTable ? ' active' : ''}`}
                onClick=${() => setActiveTable(typeId)}
              >${typeId}</button>
            `)}
          </div>
          ${availableTypeIds.length > 0 && html`
            <div className="db-add-table">
              <select value=${tableToAdd} onChange=${(event) => setTableToAdd(event.target.value)}>
                <option value="">— pick data type —</option>
                ${availableTypeIds.map((id) => html`<option key=${id} value=${id}>${id}</option>`)}
              </select>
              <button onClick=${addTable} disabled=${!tableToAdd}>+ Add table</button>
            </div>
          `}
          ${activeTable && html`
            <div className="db-rows">
              ${columns.length === 0
                ? html`<p className="empty-hint">Data type <code>${activeTable}</code> has no struct fields.</p>`
                : html`
                    <table className="db-rows-table">
                      <thead>
                        <tr>${columns.map((column) => html`<th key=${column}>${column}</th>`)}<th></th></tr>
                      </thead>
                      <tbody>
                        ${(selected.tables[activeTable] || []).map((row, idx) => html`
                          <tr key=${idx}>
                            ${columns.map((column) => html`<td key=${column}>${row[column] === undefined ? '' : String(row[column])}</td>`)}
                            <td>
                              <button
                                className="btn-icon btn-del"
                                onClick=${() => onDeleteRow(selected.name, activeTable, idx)}
                              >✕</button>
                            </td>
                          </tr>
                        `)}
                        <tr className="db-row-add">
                          ${columns.map((column) => html`
                            <td key=${column}>
                              <input
                                value=${rowDraft[column] ?? ''}
                                placeholder=${column}
                                onInput=${(event) => setRowDraft((previous) => ({ ...previous, [column]: event.target.value }))}
                              />
                            </td>
                          `)}
                          <td><button onClick=${submitRow}>+ Add</button></td>
                        </tr>
                      </tbody>
                    </table>
                  `}
            </div>
          `}
        </div>
      `}
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

export function RunPanel({ module, liveInputs, onRun, lastResult, running }) {
  // Prefer the live, canvas-derived list when present so the user can run a
  // newly-added input signal immediately, without waiting for the auto-save
  // to round-trip through the server.
  const inputs = liveInputs && liveInputs.length ? liveInputs : (module?.inputs ?? []);
  const [signal, setSignal] = useState(inputs[0]?.name ?? '');
  const [valueText, setValueText] = useState('');
  const [persist, setPersist] = useState(false);
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
    await onRun(signal, value, { persist });
  };

  if (inputs.length === 0) {
    return html`
      <div className="run-panel">
        <div className="run-panel-empty">
          No module inputs yet. Drag a <strong>Module Input</strong> node from
          the palette onto the canvas and give it a signal name in the
          properties panel — the Run controls will appear automatically.
        </div>
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
        <label className="run-persist" title="Persist any db_create writes back to disk">
          <input type="checkbox" checked=${persist} onChange=${(event) => setPersist(event.target.checked)} />
          persist DB
        </label>
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
  databases = [],
  onCreateDatabase,
  onDeleteDatabase,
  onAddTable,
  onAddRow,
  onDeleteRow,
  currentModule,
  activeTab,
  setActiveTab,
  onResizerMouseDown,
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
        <button className=${`tab${activeTab === 'databases' ? ' active' : ''}`} onClick=${() => setActiveTab('databases')}>
          Databases${databases.length ? html` <span className="tab-count">${databases.length}</span>` : null}
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
              <div className="sidebar-section sidebar-hint">
                <div className="section-header">Module signals</div>
                <p className="section-hint">
                  Drag <em>Module Input</em> / <em>Module Output</em> nodes from the
                  <strong>Palette</strong> onto the canvas. Set each node's signal name
                  and data type from the properties panel — the module's external
                  inputs/outputs are derived from those nodes.
                </p>
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

      ${activeTab === 'databases' && html`
        <div className="sidebar-section">
          <div className="section-header">Databases</div>
          <p className="section-hint">
            Global, named tables. Each table is one of the data types above.
            Used by <code>db_read</code> / <code>db_create</code> nodes.
          </p>
          <${DatabasePanel}
            databases=${databases}
            dataTypes=${dataTypes}
            onCreateDatabase=${onCreateDatabase}
            onDeleteDatabase=${onDeleteDatabase}
            onAddTable=${onAddTable}
            onAddRow=${onAddRow}
            onDeleteRow=${onDeleteRow}
          />
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
      <div className="sidebar-resizer" onMouseDown=${onResizerMouseDown}></div>
    </div>
  `;
}
