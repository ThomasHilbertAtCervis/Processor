// Entry point.
//
// Responsibilities (see ARCHITECTURE.md):
//   - own the app-level state (current module, modules, data types, selection),
//   - decide WHEN to talk to the API (the only file that imports lib/api.js),
//   - compose the UI from the components in `components.js`.
//
// It does NOT own component markup (that's in components.js / nodes.js)
// and does NOT own fetch (that's in lib/api.js).

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { addEdge, applyEdgeChanges, applyNodeChanges } from 'reactflow';

import { html, debounce, genId } from './lib/html.js';
import { apiGet, apiPut, apiPost, apiDelete } from './lib/api.js';
import {
  EDGE_MARKER,
  PropertiesPanel,
  RunPanel,
  Sidebar,
  DiagramCanvas,
} from './components.js';

// React Flow only passes `data` to custom node components, so we mirror the
// v2 port arrays into data._ports for the renderer. dehydrate strips them
// before persisting so the wire model stays single-sourced.
function hydrateNodeForFlow(node) {
  return {
    ...node,
    data: {
      ...(node.data || {}),
      _ports: {
        inputs: node.inputs || [],
        outputs: node.outputs || [],
      },
    },
  };
}

function dehydrateNodeForWire(node) {
  const { _ports, ...restData } = node.data || {};
  return { ...node, data: restData };
}

// Seed default ports / data for a freshly-dropped palette node. Each kind
// starts immediately connectable: a module_input has one source port, a
// module_output has one target port, a python node starts with one of each
// (the user adds more from the script as needed), and a submodule starts
// portless until the user picks which module to embed.
function makeNodeDefaults(type, label) {
  const defaultDataPort = (name) => ({ name, type_ref: 'any', kind: 'data' });
  if (type === 'module_input') {
    const outputs = [defaultDataPort('value')];
    return {
      inputs: [],
      outputs,
      data: { label, signal_name: '', signal_type: 'any', _ports: { inputs: [], outputs } },
    };
  }
  if (type === 'module_output') {
    const inputs = [defaultDataPort('value')];
    return {
      inputs,
      outputs: [],
      data: { label, signal_name: '', signal_type: 'any', _ports: { inputs, outputs: [] } },
    };
  }
  if (type === 'python') {
    const inputs = [defaultDataPort('in')];
    const outputs = [defaultDataPort('out')];
    return {
      inputs,
      outputs,
      data: {
        label,
        code: "outputs['out'] = inputs['in']\n",
        _ports: { inputs, outputs },
      },
    };
  }
  if (type === 'db_read' || type === 'db_create') {
    const defaultQuery = type === 'db_read'
      ? 'SELECT * FROM table_name WHERE column = :param'
      : 'INSERT INTO table_name (column) VALUES (:param)';
    const { inputs, outputs } = deriveDbPorts(type, defaultQuery);
    return {
      inputs,
      outputs,
      data: {
        label,
        database_name: '',
        query: defaultQuery,
        _ports: { inputs, outputs },
      },
    };
  }
  // submodule and any future kind: empty until configured.
  return {
    inputs: [],
    outputs: [],
    data: { label, _ports: { inputs: [], outputs: [] } },
  };
}

// Extract :placeholder names from a SQL-ish query string, in order, de-duped.
// Mirrors processor_playground.sql.placeholder_names — kept tiny so the UI
// can derive db node input ports as the user edits the query.
export function extractPlaceholders(query) {
  if (!query) return [];
  const matches = String(query).match(/:[A-Za-z_][A-Za-z_0-9]*/g) || [];
  const seen = new Set();
  const out = [];
  for (const raw of matches) {
    const name = raw.slice(1);
    if (seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}

// Rebuild a db node's input ports from the placeholders in its query, and
// its single output port from its kind. Returns { inputs, outputs }.
function deriveDbPorts(nodeType, query) {
  const placeholders = extractPlaceholders(query);
  const inputs = placeholders.length
    ? placeholders.map((name) => ({ name, type_ref: 'any', kind: 'data' }))
    // No placeholders -> a single "trigger" input so the node is reachable
    // from the graph at all (queries with all-literal values still need a
    // wire to know when to fire).
    : [{ name: 'trigger', type_ref: 'any', kind: 'data' }];
  const outputName = nodeType === 'db_read' ? 'rows' : 'created';
  const outputs = [{ name: outputName, type_ref: 'any', kind: 'data' }];
  return { inputs, outputs };
}

// Module interface nodes whose signal_name was never set (legacy data, or the
// user cleared the field) silently disappear from the derived inputs/outputs
// list and break ``Simulator.run``. Whenever we load a module we backfill an
// auto-numbered default name so every interface node is functional from the
// moment the user opens the module.
function backfillInterfaceSignalNames(nodes) {
  const takenInputs = new Set();
  const takenOutputs = new Set();
  for (const node of nodes) {
    const name = node.data && node.data.signal_name;
    if (!name) continue;
    if (node.type === 'module_input') takenInputs.add(name);
    if (node.type === 'module_output') takenOutputs.add(name);
  }
  const pickName = (taken, base) => {
    let candidate = base;
    let counter = 2;
    while (taken.has(candidate)) {
      candidate = `${base}_${counter}`;
      counter += 1;
    }
    taken.add(candidate);
    return candidate;
  };
  return nodes.map((node) => {
    if (node.type !== 'module_input' && node.type !== 'module_output') return node;
    const existing = node.data && node.data.signal_name;
    if (existing) return node;
    const base = node.type === 'module_input' ? 'input' : 'output';
    const name = pickName(node.type === 'module_input' ? takenInputs : takenOutputs, base);
    return { ...node, data: { ...(node.data || {}), signal_name: name } };
  });
}

function App() {
  const [modules, setModules] = useState([]);
  const [dataTypes, setDataTypes] = useState([]);
  const [databases, setDatabases] = useState([]);
  const [primitives, setPrimitives] = useState([]);
  const [nodeKinds, setNodeKinds] = useState([]);
  const [currentModuleId, setCurrentModuleId] = useState(null);
  const [currentModule, setCurrentModule] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selected, setSelected] = useState(null);
  const [activeTab, setActiveTab] = useState('modules');
  const [status, setStatus] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(360);
  const reactFlowWrapper = useRef(null);
  const [reactFlowInstance, setReactFlowInstance] = useState(null);
  const saveRef = useRef(() => {});
  const showStatusRef = useRef(null);
  const resizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);
  // Live mirror of currentModuleId so async callbacks (in-flight save
  // responses, debounced timers) can tell whether the user has navigated
  // away from the module they were originally working on.
  const currentModuleIdRef = useRef(null);
  useEffect(() => { currentModuleIdRef.current = currentModuleId; }, [currentModuleId]);

  // Derived from the server-owned catalog so a freshly dropped node gets the
  // same starter label every client agrees on.
  const defaultNodeLabels = useMemo(() => {
    const map = {};
    for (const kind of nodeKinds) {
      map[kind.type] = kind.default_label;
    }
    return map;
  }, [nodeKinds]);

  // The module's external inputs are derived from the module_input nodes on
  // the canvas, so the Run panel can offer freshly-added inputs immediately,
  // before the next auto-save round-trips through the server.
  const liveModuleInputs = useMemo(() => {
    const out = [];
    const seen = new Set();
    for (const node of nodes) {
      if (node.type !== 'module_input') continue;
      const name = node.data && node.data.signal_name;
      if (!name || seen.has(name)) continue;
      seen.add(name);
      const port = node.outputs && node.outputs[0];
      const type_ref = (node.data && node.data.signal_type) || (port && port.type_ref) || 'any';
      out.push({ name, type_ref });
    }
    return out;
  }, [nodes]);

  const showStatus = useCallback((message, isErr = false) => {
    if (showStatusRef.current) {
      window.clearTimeout(showStatusRef.current);
    }
    setStatus({ msg: message, isErr });
    showStatusRef.current = window.setTimeout(() => setStatus(null), 2500);
  }, []);

  const onResizerMouseDown = useCallback((event) => {
    resizingRef.current = true;
    startXRef.current = event.clientX;
    startWidthRef.current = sidebarWidth;
  }, [sidebarWidth]);

  useEffect(() => {
    const onMouseMove = (event) => {
      if (!resizingRef.current) return;
      const delta = event.clientX - startXRef.current;
      const newWidth = Math.max(200, Math.min(600, startWidthRef.current + delta));
      setSidebarWidth(newWidth);
    };

    const onMouseUp = () => {
      resizingRef.current = false;
    };

    if (resizingRef.current) {
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      return () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
      };
    }
  }, [sidebarWidth]);

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

  const refreshDatabases = useCallback(async () => {
    const payload = await apiGet('/api/databases');
    setDatabases(payload);
    return payload;
  }, []);

  const loadModule = useCallback(async (moduleId) => {
    const modulePayload = await apiGet(`/api/modules/${moduleId}`);
    setCurrentModuleId(moduleId);
    setCurrentModule(modulePayload);
    setNodes(backfillInterfaceSignalNames((modulePayload.nodes || []).map(hydrateNodeForFlow)));
    setEdges(modulePayload.edges || []);
    setSelected(null);
    return modulePayload;
  }, []);

  useEffect(() => {
    Promise.all([
      refreshModules(),
      refreshDataTypes(),
      refreshDatabases(),
      apiGet('/api/data-types/primitives').then(setPrimitives),
      apiGet('/api/node-kinds').then(setNodeKinds),
    ])
      .then(async ([modulePayload]) => {
        if (modulePayload.length) {
          await loadModule(modulePayload[0].module_id);
        }
      })
      .catch((error) => showStatus(`Failed to load: ${error.message}`, true));
  }, [loadModule, refreshDataTypes, refreshDatabases, refreshModules, showStatus]);

  const saveCurrentDiagram = useCallback(async () => {
    if (!currentModuleId || !currentModule) {
      return;
    }
    // Guard against a transient mismatch right after switching modules: if
    // ``currentModule`` hasn't caught up to the new id yet, skip — the
    // follow-up render will save with consistent state.
    if (currentModule.module_id && currentModule.module_id !== currentModuleId) {
      return;
    }
    const payload = {
      ...currentModule,
      // Always pin module_id to the URL so the server's path/payload
      // consistency check can't be tripped by stale closures.
      module_id: currentModuleId,
      nodes: nodes.map(dehydrateNodeForWire),
      edges,
      inputs: currentModule.inputs || [],
      outputs: currentModule.outputs || [],
      submodules: currentModule.submodules || [],
    };
    const saved = await apiPut(`/api/modules/${currentModuleId}`, payload);
    // The user may have switched modules while this PUT was in flight; if so,
    // don't overwrite the now-active module's state with the response from a
    // previous one (that's how the sidebar and header used to disagree about
    // which module is open).
    if (currentModuleIdRef.current !== saved.module_id) {
      setModules((items) => items.map((item) => (item.module_id === saved.module_id ? saved : item)));
      return;
    }
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
    // While ``currentModule`` is catching up to a freshly-selected id, the
    // ``nodes``/``edges`` state already belongs to the new module — comparing
    // them to ``currentModule`` (still pointing at the previous module) would
    // produce a spurious diff and fire an auto-save against the wrong id.
    if (currentModule.module_id && currentModule.module_id !== currentModuleId) {
      return;
    }
    const savedNodes = JSON.stringify(currentModule.nodes || []);
    const savedEdges = JSON.stringify(currentModule.edges || []);
    // Compare the *dehydrated* shape against the server copy — the live
    // ``nodes`` state carries an extra ``data._ports`` mirror added by
    // ``hydrateNodeForFlow`` that the server never sees. Comparing the
    // hydrated form to the saved form would always diff and trigger a
    // save-loop every 900ms, eventually starving the UI of events.
    const liveNodes = JSON.stringify(nodes.map(dehydrateNodeForWire));
    const liveEdges = JSON.stringify(edges);
    if (savedNodes === liveNodes && savedEdges === liveEdges) {
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
    setNodes((items) => items.map((node) => {
      if (node.id !== nodeId) {
        return node;
      }
      const mergedData = { ...node.data, ...newData };
      let inputs = node.inputs;
      let outputs = node.outputs;
      // module_input / module_output nodes carry exactly one data port; the
      // user picks its type via the "Data type" dropdown in the properties
      // panel, which we mirror onto the port so the derived Module.inputs /
      // Module.outputs round-trips with the right type_ref.
      if (node.type === 'module_input' && newData.signal_type !== undefined) {
        const port = (outputs && outputs[0]) || { name: 'value', kind: 'data' };
        outputs = [{ ...port, type_ref: newData.signal_type || 'any' }];
      }
      if (node.type === 'module_output' && newData.signal_type !== undefined) {
        const port = (inputs && inputs[0]) || { name: 'value', kind: 'data' };
        inputs = [{ ...port, type_ref: newData.signal_type || 'any' }];
      }
      // db_read / db_create derive their inputs from the :placeholders in
      // their SQL query. Whenever the query (or kind) changes we rebuild
      // the port list so the visible handles always match what the
      // simulator will demand at run time.
      if ((node.type === 'db_read' || node.type === 'db_create')
          && (newData.query !== undefined || node.inputs === undefined)) {
        const derived = deriveDbPorts(node.type, mergedData.query || '');
        inputs = derived.inputs;
        outputs = derived.outputs;
      }
      // Keep the view-only ports mirror in sync so the canvas renders the
      // updated handle without a reload.
      mergedData._ports = { inputs: inputs || [], outputs: outputs || [] };
      return { ...node, data: mergedData, inputs, outputs };
    }));
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
    // Each node kind starts with sensible default ports so it's immediately
    // connectable. The user can refine names/types from the properties
    // panel (signal_name + Data type for module_input/output; per-port
    // editing is on the backlog for python/submodule).
    setNodes((items) => {
      const defaults = makeNodeDefaults(type, defaultNodeLabels[type] || type);
      // module_input / module_output contribute to the module's external
      // interface. We assign a unique default signal_name on drop so the
      // node is immediately recognised as an input/output (and the Run
      // button appears); the user can rename it from the properties panel.
      if (type === 'module_input' || type === 'module_output') {
        const base = type === 'module_input' ? 'input' : 'output';
        const taken = new Set(
          items
            .filter((node) => node.type === type)
            .map((node) => (node.data && node.data.signal_name) || '')
            .filter(Boolean),
        );
        let name = base;
        let counter = 2;
        while (taken.has(name)) {
          name = `${base}_${counter}`;
          counter += 1;
        }
        defaults.data = { ...defaults.data, signal_name: name };
      }
      return [
        ...items,
        {
          id: genId(),
          type,
          position,
          inputs: defaults.inputs,
          outputs: defaults.outputs,
          data: defaults.data,
        },
      ];
    });
  }, [reactFlowInstance, defaultNodeLabels]);

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
      // The backend constructs the empty-module shape from its own template
      // (templates.new_module) so every client — UI, MCP server, scripts —
      // starts from the same skeleton.
      const saved = await apiPost('/api/modules', { module_id: moduleId, name });
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

  const runModule = useCallback(async (inputSignal, inputValue, opts = {}) => {
    if (!currentModuleId) {
      return;
    }
    setRunning(true);
    try {
      const result = await apiPost(`/api/modules/${currentModuleId}/run`, {
        input_signal: inputSignal,
        input_value: inputValue,
        persist: Boolean(opts.persist),
      });
      setRunResult(result);
      showStatus(`Run ${result.status}`);
      if (opts.persist) {
        // Pick up any db_create writes that hit disk.
        refreshDatabases().catch(() => {});
      }
    } catch (error) {
      setRunResult({ status: 'error', outputs: {}, error: error.message });
      showStatus(`Run failed: ${error.message}`, true);
    } finally {
      setRunning(false);
    }
  }, [currentModuleId, refreshDatabases, showStatus]);

  useEffect(() => {
    setRunResult(null);
  }, [currentModuleId]);

  // ---------------------------------------------------- database callbacks

  const onCreateDatabase = useCallback(async (name) => {
    try {
      await apiPost('/api/databases', { name, tables: {} });
      await refreshDatabases();
      showStatus('Database created');
    } catch (error) {
      showStatus(`Create failed: ${error.message}`, true);
    }
  }, [refreshDatabases, showStatus]);

  const onDeleteDatabase = useCallback(async (name) => {
    if (!window.confirm(`Delete database "${name}"?`)) return;
    try {
      await apiDelete(`/api/databases/${name}`);
      await refreshDatabases();
      showStatus('Deleted');
    } catch (error) {
      showStatus(`Delete failed: ${error.message}`, true);
    }
  }, [refreshDatabases, showStatus]);

  const onAddTable = useCallback(async (dbName, typeId) => {
    const db = databases.find((d) => d.name === dbName);
    if (!db) return;
    const nextTables = { ...(db.tables || {}) };
    if (nextTables[typeId]) {
      showStatus('Table already exists');
      return;
    }
    nextTables[typeId] = [];
    try {
      await apiPut(`/api/databases/${dbName}`, { name: dbName, tables: nextTables });
      await refreshDatabases();
    } catch (error) {
      showStatus(`Add table failed: ${error.message}`, true);
    }
  }, [databases, refreshDatabases, showStatus]);

  const onAddRow = useCallback(async (dbName, typeId, row) => {
    try {
      await apiPost(`/api/databases/${dbName}/tables/${typeId}/rows`, { row });
      await refreshDatabases();
    } catch (error) {
      showStatus(`Add row failed: ${error.message}`, true);
    }
  }, [refreshDatabases, showStatus]);

  const onDeleteRow = useCallback(async (dbName, typeId, index) => {
    try {
      await apiDelete(`/api/databases/${dbName}/tables/${typeId}/rows/${index}`);
      await refreshDatabases();
    } catch (error) {
      showStatus(`Delete row failed: ${error.message}`, true);
    }
  }, [refreshDatabases, showStatus]);

  return html`
    <div id="app" style=${{ '--sidebar-width': `${sidebarWidth}px` }}>
      <${Sidebar}
        modules=${modules}
        currentModuleId=${currentModuleId}
        onSelectModule=${onSelectModule}
        onNewModule=${onNewModule}
        onDeleteModule=${onDeleteModule}
        dataTypes=${dataTypes}
        primitives=${primitives}
        nodeKinds=${nodeKinds}
        onSaveDt=${onSaveDt}
        onDeleteDt=${onDeleteDt}
        databases=${databases}
        onCreateDatabase=${onCreateDatabase}
        onDeleteDatabase=${onDeleteDatabase}
        onAddTable=${onAddTable}
        onAddRow=${onAddRow}
        onDeleteRow=${onDeleteRow}
        currentModule=${currentModule}
        activeTab=${activeTab}
        setActiveTab=${setActiveTab}
        onResizerMouseDown=${onResizerMouseDown}
      />
      <div className="main-area">
        ${currentModule
          ? html`
              <div className="canvas-header">
                <span className="canvas-module-name">${currentModule.name}</span>
                <button className="btn-save-manual" onClick=${() => saveCurrentDiagram().catch((error) => showStatus(`Save failed: ${error.message}`, true))}>💾 Save</button>
                ${status ? html`<span className=${`status-badge${status.isErr ? ' error' : ''}`}>${status.msg}</span>` : null}
              </div>
              <${RunPanel} module=${currentModule} liveInputs=${liveModuleInputs} onRun=${runModule} lastResult=${runResult} running=${running} />
              <${DiagramCanvas}
              key=${currentModule.module_id}
              currentModule=${currentModule}
              nodes=${nodes.map((node) => ({ ...node, type: node.type || 'python' }))}
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
        primitives=${primitives}
        modules=${modules}
        databases=${databases}
      />
    </div>
  `;
}

const root = createRoot(document.getElementById('root'));
root.render(html`<${App} />`);
