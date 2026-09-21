/**
 * PyLearn Block Programming Editor
 * Drag-and-drop block editor that generates Python code
 */

const BLOCK_DEFINITIONS = {
  print: {
    label: 'print( __ )',
    template: () => `<span>print(</span><input type="text" class="block-input" placeholder="текст или переменная" style="width:120px"><span>)</span>`,
    codegen: (el) => {
      const val = el.querySelector('.block-input').value || '""';
      const v = val.trim();
      if (/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(v) || v.startsWith('"') || v.startsWith("'") || !isNaN(v) || /[-+*/%><!=()[\].]/.test(v)) {
        return `print(${v})`;
      }
      return `print("${v}")`;
    },
    color: 'print', indent: 0,
  },
  string: {
    label: '"текст"',
    template: () => `<span>"</span><input type="text" class="block-input" placeholder="текст" style="width:100px"><span>"</span>`,
    codegen: (el) => `"${el.querySelector('.block-input').value}"`,
    color: 'string', indent: 0, inline: true,
  },
  number: {
    label: '123',
    template: () => `<input type="number" class="block-input" placeholder="0" style="width:70px" value="0">`,
    codegen: (el) => el.querySelector('.block-input').value || '0',
    color: 'number', indent: 0, inline: true,
  },
  var_set: {
    label: 'переменная = _',
    template: () => `<input type="text" class="block-input" placeholder="имя" style="width:70px"><span> = </span><input type="text" class="block-input" placeholder="значение" style="width:90px">`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('.block-input');
      const name = inputs[0].value || 'x';
      const val = inputs[1].value || '0';
      const v = val.trim();
      if (/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(v) || !isNaN(v) || v.startsWith('"') || v.startsWith("'") || /[-+*/%><!=()[\].]/.test(v)) {
        return `${name} = ${v}`;
      }
      return `${name} = "${v}"`;
    },
    color: 'var_set', indent: 0,
  },
  var_get: {
    label: 'переменная',
    template: () => `<input type="text" class="block-input" placeholder="имя" style="width:80px">`,
    codegen: (el) => el.querySelector('.block-input').value || 'x',
    color: 'var_get', indent: 0, inline: true,
  },
  arith: {
    label: '_ + _',
    template: () => `<input type="text" class="block-input" placeholder="a" style="width:50px">
      <select class="block-input" style="width:50px">
        <option>+</option><option>-</option><option>*</option><option>/</option><option>%</option><option>**</option>
      </select>
      <input type="text" class="block-input" placeholder="b" style="width:50px">`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('input.block-input');
      const sel = el.querySelector('select');
      return `${inputs[0].value || '0'} ${sel.value} ${inputs[1].value || '0'}`;
    },
    color: 'arith', indent: 0, inline: true,
  },
  compare: {
    label: '_ == _',
    template: () => `<input type="text" class="block-input" placeholder="a" style="width:60px">
      <select class="block-input" style="width:55px">
        <option>==</option><option>!=</option><option>&gt;</option><option>&lt;</option><option>&gt;=</option><option>&lt;=</option>
      </select>
      <input type="text" class="block-input" placeholder="b" style="width:60px">`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('input.block-input');
      const sel = el.querySelector('select');
      return `${inputs[0].value || '0'} ${sel.value} ${inputs[1].value || '0'}`;
    },
    color: 'compare', indent: 0, inline: true,
  },
  if: {
    label: 'если (if)',
    template: () => `<span>if </span><input type="text" class="block-input" placeholder="условие" style="width:130px"><span>:</span>`,
    codegen: (el) => `if ${el.querySelector('.block-input').value || 'True'}:`,
    color: 'if', indent: 0, opens: true,
  },
  else: {
    label: 'иначе (else)',
    template: () => `<span>else:</span>`,
    codegen: () => 'else:',
    color: 'else', indent: 0, opens: true,
  },
  for: {
    label: 'цикл for',
    template: () => `<span>for </span><input type="text" class="block-input" placeholder="i" style="width:40px"><span> in range(</span><input type="text" class="block-input" placeholder="0" style="width:40px"><span>,</span><input type="text" class="block-input" placeholder="10" style="width:40px"><span>):</span>`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('.block-input');
      return `for ${inputs[0].value || 'i'} in range(${inputs[1].value || '0'}, ${inputs[2].value || '10'}):`;
    },
    color: 'for', indent: 0, opens: true,
  },
  for_list: {
    label: 'for в списке',
    template: () => `<span>for </span><input type="text" class="block-input" placeholder="элемент" style="width:70px"><span> in </span><input type="text" class="block-input" placeholder="список" style="width:70px"><span>:</span>`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('.block-input');
      return `for ${inputs[0].value || 'x'} in ${inputs[1].value || 'lst'}:`;
    },
    color: 'for_list', indent: 0, opens: true,
  },
  while: {
    label: 'пока (while)',
    template: () => `<span>while </span><input type="text" class="block-input" placeholder="условие" style="width:120px"><span>:</span>`,
    codegen: (el) => `while ${el.querySelector('.block-input').value || 'True'}:`,
    color: 'while', indent: 0, opens: true,
  },
  end: {
    label: '⬆ конец блока',
    template: () => `<span>— конец блока —</span>`,
    codegen: () => null,  // signals dedent
    color: 'end', indent: 0, closes: true,
  },
  def: {
    label: 'def функция():',
    template: () => `<span>def </span><input type="text" class="block-input" placeholder="имя" style="width:80px"><span>(</span><input type="text" class="block-input" placeholder="параметры" style="width:80px"><span>):</span>`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('.block-input');
      return `def ${inputs[0].value || 'func'}(${inputs[1].value || ''}):`;
    },
    color: 'def', indent: 0, opens: true,
  },
  call: {
    label: 'вызов функции()',
    template: () => `<input type="text" class="block-input" placeholder="имя" style="width:80px"><span>(</span><input type="text" class="block-input" placeholder="аргументы" style="width:80px"><span>)</span>`,
    codegen: (el) => {
      const inputs = el.querySelectorAll('.block-input');
      return `${inputs[0].value || 'func'}(${inputs[1].value || ''})`;
    },
    color: 'call', indent: 0,
  },
  list: {
    label: '[список]',
    template: () => `<span>[</span><input type="text" class="block-input" placeholder="1, 2, 3" style="width:120px"><span>]</span>`,
    codegen: (el) => `[${el.querySelector('.block-input').value || ''}]`,
    color: 'list', indent: 0, inline: true,
  },
};

let workspaceBlocks = [];  // ordered list of {type, element}
let blockChangeCallback = null;

function initBlockEditor(available) {
  const palette = document.getElementById('paletteBlocks');
  if (!palette) return;

  // Build palette
  (available.length ? available : Object.keys(BLOCK_DEFINITIONS)).forEach(type => {
    const def = BLOCK_DEFINITIONS[type];
    if (!def) return;
    const block = document.createElement('div');
    block.className = `palette-block block-type-${def.color}`;
    block.textContent = def.label;
    block.draggable = true;
    block.dataset.type = type;

    block.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('blockType', type);
      e.dataTransfer.effectAllowed = 'copy';
    });
    // Also support click-to-add for mobile/ease
    block.addEventListener('click', () => addBlockToWorkspace(type));
    palette.appendChild(block);
  });

  // Make workspace a drop target
  const workspace = document.getElementById('blockWorkspace');
  workspace.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  workspace.addEventListener('drop', (e) => {
    e.preventDefault();
    const type = e.dataTransfer.getData('blockType');
    if (type) addBlockToWorkspace(type);
  });
}

function addBlockToWorkspace(type) {
  const def = BLOCK_DEFINITIONS[type];
  if (!def) return;

  const hint = document.getElementById('workspaceHint');
  if (hint) hint.style.display = 'none';

  const el = document.createElement('div');
  el.className = `workspace-block block-type-${def.color}`;
  el.dataset.type = type;
  el.innerHTML = def.template() + `<span class="block-delete" title="Удалить">✕</span>`;

  // Delete button
  el.querySelector('.block-delete').addEventListener('click', (e) => {
    e.stopPropagation();
    removeBlock(el);
  });

  // Drag to reorder within workspace
  el.draggable = true;
  el.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData('reorderIndex', workspaceBlocks.indexOf(el));
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => el.style.opacity = '0.4', 0);
  });
  el.addEventListener('dragend', () => { el.style.opacity = '1'; });
  el.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  });
  el.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const fromIndex = parseInt(e.dataTransfer.getData('reorderIndex'));
    if (!isNaN(fromIndex) && fromIndex >= 0) {
      const toIndex = workspaceBlocks.indexOf(el);
      reorderBlock(fromIndex, toIndex);
    }
  });

  document.getElementById('blockWorkspace').appendChild(el);
  workspaceBlocks.push(el);
  updateIndentation();
  if (blockChangeCallback) blockChangeCallback();
}

function removeBlock(el) {
  const idx = workspaceBlocks.indexOf(el);
  if (idx !== -1) workspaceBlocks.splice(idx, 1);
  el.remove();
  updateIndentation();
  if (workspaceBlocks.length === 0) {
    const hint = document.getElementById('workspaceHint');
    if (hint) hint.style.display = 'block';
  }
  if (blockChangeCallback) blockChangeCallback();
}

function reorderBlock(fromIdx, toIdx) {
  if (fromIdx === toIdx || fromIdx < 0 || toIdx < 0) return;
  const [moved] = workspaceBlocks.splice(fromIdx, 1);
  workspaceBlocks.splice(toIdx, 0, moved);
  // Re-render order in DOM
  const workspace = document.getElementById('blockWorkspace');
  workspaceBlocks.forEach(el => workspace.appendChild(el));
  updateIndentation();
  if (blockChangeCallback) blockChangeCallback();
}

function updateIndentation() {
  let indent = 0;
  workspaceBlocks.forEach(el => {
    const def = BLOCK_DEFINITIONS[el.dataset.type];
    if (def.closes) indent = Math.max(0, indent - 1);
    el.style.marginLeft = `${indent * 24}px`;
    if (def.opens) indent++;
  });
}

function generateCodeFromBlocks() {
  if (workspaceBlocks.length === 0) return '';
  let lines = [];
  let indent = 0;
  workspaceBlocks.forEach(el => {
    const def = BLOCK_DEFINITIONS[el.dataset.type];
    if (def.closes) {
      indent = Math.max(0, indent - 1);
      return;
    }
    const code = def.codegen(el);
    if (code === null) return;
    lines.push('    '.repeat(indent) + code);
    if (def.opens) indent++;
  });
  return lines.join('\n');
}

function clearBlocks() {
  workspaceBlocks = [];
  const workspace = document.getElementById('blockWorkspace');
  if (workspace) workspace.innerHTML = '<div class="workspace-hint" id="workspaceHint">Перетащи блоки сюда →</div>';
}

function getWorkspaceState() {
  return workspaceBlocks.map(el => {
    const inputs = el.querySelectorAll('.block-input');
    return {
      type: el.dataset.type,
      values: Array.from(inputs).map(inp => inp.value)
    };
  });
}

function setWorkspaceState(state) {
  if (!state || !state.length) return;
  clearBlocks();
  const prev = blockChangeCallback;
  blockChangeCallback = null;  // suppress callbacks during restore
  state.forEach(item => {
    addBlockToWorkspace(item.type);
    const el = workspaceBlocks[workspaceBlocks.length - 1];
    const inputs = el.querySelectorAll('.block-input');
    item.values.forEach((v, i) => { if (inputs[i]) inputs[i].value = v; });
  });
  updateIndentation();
  blockChangeCallback = prev;
}
