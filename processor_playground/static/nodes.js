// ReactFlow node components and the palette/default-label configuration.
// Pure view + view-data. No fetch calls, no App state.

import { Handle, Position } from 'reactflow';
import { html } from './lib/html.js';

export const PRIMITIVES = ['int', 'decimal', 'string', 'bool', 'timestamp', 'any'];

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

export const NODE_TYPES = {
  start: StartNode,
  event: EventNode,
  condition: ConditionNode,
  foreach: ForeachNode,
  submodule: SubmoduleNode,
  emit: EmitNode,
  end: EndNode,
  datamapping: DataMappingNode,
};

export const PALETTE_NODES = [
  { type: 'start', label: '● Start' },
  { type: 'event', label: '▷ Event Trigger' },
  { type: 'condition', label: '□ Condition / Action' },
  { type: 'foreach', label: '‖ For Each' },
  { type: 'submodule', label: '⊞ Sub-module' },
  { type: 'emit', label: '▶ Emit Event' },
  { type: 'datamapping', label: '⇄ Data Mapping' },
  { type: 'end', label: '◉ End' },
];

// Default label for a node freshly dropped on the canvas. Living here keeps
// the App component free of business defaults (see ARCHITECTURE.md).
export const DEFAULT_NODE_LABELS = {
  start: 'Start',
  event: 'Event Trigger',
  condition: 'Condition',
  foreach: 'foreach',
  submodule: 'Sub-module',
  emit: 'Emit Event',
  datamapping: 'Data Mapping',
  end: 'End',
};
