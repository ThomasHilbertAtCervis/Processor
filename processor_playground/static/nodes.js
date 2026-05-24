// ReactFlow node components.
// Pure view + view-data. No fetch calls, no App state.
//
// Domain knowledge — which kinds of nodes exist, what their default labels
// are, which primitive types the platform recognises — lives in the backend
// and is fetched at runtime. See ARCHITECTURE.md ("Backend is the sole
// source of truth").

import { Handle, Position } from 'reactflow';
import { html } from './lib/html.js';

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

const SubmoduleNode = ({ data, selected }) => {
  // Prefer v2 node ports (hydrated into data._ports by app.js); fall back to
  // the older data.inputs/outputs the PropertiesPanel still writes when the
  // user picks a sub-module from the dropdown.
  const ports = data._ports || {};
  const inputs = (ports.inputs && ports.inputs.length ? ports.inputs : data.inputs) || [];
  const outputs = (ports.outputs && ports.outputs.length ? ports.outputs : data.outputs) || [];
  const rowCount = Math.max(inputs.length, outputs.length, 1);
  return html`
    <div className=${`node-submodule${selected ? ' selected' : ''}`}>
      <div className="node-submodule-header">
        <span className="node-submodule-name">${data.label || 'Sub-module'}</span>
        <span className="node-submodule-icon" title="Sub-module">⊞</span>
      </div>
      <div className="node-submodule-body" style=${{ minHeight: `${rowCount * 28}px` }}>
        <div className="node-submodule-col node-submodule-col-in">
          ${inputs.map((port) => html`
            <div key=${`in-${port.name}`} className="node-port node-port-in">
              <${Handle}
                type="target"
                position=${Position.Left}
                id=${port.name}
                className="node-port-handle"
              />
              <span className="node-port-label">${port.name}</span>
              ${port.type_ref && port.type_ref !== 'any'
                ? html`<span className="node-port-type">[${port.type_ref}]</span>`
                : null}
            </div>
          `)}
        </div>
        <div className="node-submodule-col node-submodule-col-out">
          ${outputs.map((port) => html`
            <div key=${`out-${port.name}`} className="node-port node-port-out">
              ${port.type_ref && port.type_ref !== 'any'
                ? html`<span className="node-port-type">[${port.type_ref}]</span>`
                : null}
              <span className="node-port-label">${port.name}</span>
              <${Handle}
                type="source"
                position=${Position.Right}
                id=${port.name}
                className="node-port-handle"
              />
            </div>
          `)}
        </div>
      </div>
    </div>
  `;
};

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

const ModuleInputNode = ({ data, selected }) => {
  const ports = data._ports || {};
  const outputs = ports.outputs || [];
  return html`
    <div className=${`node-module-input${selected ? ' selected' : ''}`}>
      <div className="node-module-io-label">
        ▷ ${data.label || data.signal_name || 'input'}
      </div>
      ${outputs.map((port) => html`
        <${Handle}
          key=${port.name}
          type="source"
          position=${Position.Right}
          id=${port.name}
          className="node-port-handle"
        />
      `)}
    </div>
  `;
};

const ModuleOutputNode = ({ data, selected }) => {
  const ports = data._ports || {};
  const inputs = ports.inputs || [];
  return html`
    <div className=${`node-module-output${selected ? ' selected' : ''}`}>
      ${inputs.map((port) => html`
        <${Handle}
          key=${port.name}
          type="target"
          position=${Position.Left}
          id=${port.name}
          className="node-port-handle"
        />
      `)}
      <div className="node-module-io-label">
        ${data.label || data.signal_name || 'output'} ◉
      </div>
    </div>
  `;
};

const PythonNode = ({ data, selected }) => {
  const ports = data._ports || {};
  const inputs = ports.inputs || [];
  const outputs = ports.outputs || [];
  const rowCount = Math.max(inputs.length, outputs.length, 1);
  return html`
    <div className=${`node-python${selected ? ' selected' : ''}`}>
      <div className="node-python-header">
        <span className="node-python-icon">λ</span>
        <span className="node-python-name">${data.label || 'Python'}</span>
      </div>
      <div className="node-python-body" style=${{ minHeight: `${rowCount * 24}px` }}>
        <div className="node-submodule-col node-submodule-col-in">
          ${inputs.map((port) => html`
            <div key=${`in-${port.name}`} className="node-port node-port-in">
              <${Handle}
                type="target"
                position=${Position.Left}
                id=${port.name}
                className="node-port-handle"
              />
              <span className="node-port-label">${port.name}</span>
            </div>
          `)}
        </div>
        <div className="node-submodule-col node-submodule-col-out">
          ${outputs.map((port) => html`
            <div key=${`out-${port.name}`} className="node-port node-port-out">
              <span className="node-port-label">${port.name}</span>
              <${Handle}
                type="source"
                position=${Position.Right}
                id=${port.name}
                className="node-port-handle"
              />
            </div>
          `)}
        </div>
      </div>
    </div>
  `;
};

export const NODE_TYPES = {
  module_input: ModuleInputNode,
  module_output: ModuleOutputNode,
  python: PythonNode,
  submodule: SubmoduleNode,
  // Legacy v1 visual kinds — still mapped so historical screenshots/tests
  // don't crash if they sneak into a v2 module.
  start: StartNode,
  event: EventNode,
  condition: ConditionNode,
  foreach: ForeachNode,
  emit: EmitNode,
  end: EndNode,
  datamapping: DataMappingNode,
};
