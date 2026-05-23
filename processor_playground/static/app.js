// Entry point.
//
// Responsibilities (see ARCHITECTURE.md):
//   - own the app-level state (current module, modules, data types, selection),
//   - decide WHEN to talk to the API (the only file that imports lib/api.js),
//   - compose the UI from the components in `components.js`.
//
// It does NOT own component markup (that's in components.js / nodes.js)
// and does NOT own fetch (that's in lib/api.js).

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { addEdge, applyEdgeChanges, applyNodeChanges } from 'reactflow';

import { html, debounce, genId } from './lib/html.js';
import { apiGet, apiPut, apiDelete } from './lib/api.js';
import { DEFAULT_NODE_LABELS } from './nodes.js';
import {
  EDGE_MARKER,
  PropertiesPanel,
  Sidebar,
  DiagramCanvas,
} from './components.js';

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
    setNodes((items) => [
      ...items,
      {
        id: genId(),
        type,
        position,
        data: { label: DEFAULT_NODE_LABELS[type] || type },
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
