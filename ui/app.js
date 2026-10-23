(() => {
  'use strict';

  const token = document.querySelector('meta[name="local-api-token"]')?.content || '';
  const state = {
    bootstrap: null,
    config: {},
    configPath: '',
    configOrigin: 'template',
    configDirty: false,
    inspect: null,
    inspectedInput: '',
    inputDir: '',
    selectedRun: null,
    activeRun: null,
    activeRunId: null,
    poll: null,
    browse: { mode: 'directory', target: '', path: '', selected: '' },
    bootstrapped: false,
    formKind: 'compression',
  };

  const $ = (id) => document.getElementById(id);
  const clone = (value) => JSON.parse(JSON.stringify(value ?? {}));
  const text = (value) => value == null ? '' : String(value);
  const icon = (id) => `<svg aria-hidden="true"><use href="#${id}"></use></svg>`;

  const api = async (path, options = {}) => {
    const headers = { 'X-Clean-Number-Token': token, ...(options.headers || {}) };
    const request = { ...options, headers };
    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      request.body = JSON.stringify(options.body);
    }
    const response = await fetch(path, request);
    let body = {};
    try { body = await response.json(); } catch (_) { /* handled below */ }
    if (!response.ok) throw new Error(body.error || `请求失败（${response.status}）`);
    return body;
  };

  const showAlert = (message) => {
    const element = $('alert');
    element.textContent = message || '';
    element.hidden = !message;
    if (message) element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const clearAlert = () => showAlert('');

  const pathValue = (object, path, fallback = '') => {
    let value = object;
    for (const key of path) {
      if (!value || value[key] === undefined) return fallback;
      value = value[key];
    }
    return value == null ? fallback : value;
  };

  const setPath = (object, path, value) => {
    let cursor = object;
    path.slice(0, -1).forEach((key) => {
      if (!cursor[key] || typeof cursor[key] !== 'object') cursor[key] = {};
      cursor = cursor[key];
    });
    cursor[path[path.length - 1]] = value;
  };

  const configShape = () => {
    if (!state.config || typeof state.config !== 'object') state.config = {};
    state.config.methods ||= {};
    state.config.methods.compression ||= {};
    state.config.methods.flexural ||= {};
    state.config.methods.compression.modulus ||= {};
    state.config.methods.flexural.modulus ||= {};
    state.config.methods.flexural.geometry ||= {};
    state.config.project ||= {};
    state.config.condition_mapping ||= {};
    state.config.mixes ||= {};
  };

  const numberField = (id, label, { min = null, max = null, percent = false } = {}) => {
    const raw = $(id).value.trim();
    if (raw === '') throw new Error(`请填写${label}。`);
    const value = Number(raw);
    if (!Number.isFinite(value)) throw new Error(`${label}必须是数字。`);
    if (min !== null && value < min) throw new Error(`${label}必须不小于 ${min}。`);
    if (max !== null && value > max) throw new Error(`${label}必须不大于 ${max}。`);
    return percent ? value / 100 : value;
  };

  const writeFormToConfig = (kind = $('kind').value) => {
    configShape();
    setPath(state.config, ['project', 'name'], $('project-name').value);
    setPath(state.config, ['methods', kind, 'modulus', 'lower_fraction'], numberField('lower-fraction', '模量下限', { min: 0, max: 100, percent: true }));
    setPath(state.config, ['methods', kind, 'modulus', 'upper_fraction'], numberField('upper-fraction', '模量上限', { min: 0, max: 100, percent: true }));
    if (kind === 'flexural') {
      ['span_mm', 'width_mm', 'depth_mm'].forEach((key) => {
        const id = key.replace('_mm', '-mm');
        setPath(state.config, ['methods', 'flexural', 'geometry', key], numberField(id, `${key} 参数`, { min: 0 }));
      });
    }
    state.configDirty = true;
    return state.config;
  };

  const thresholdValue = () => numberField('force-threshold', '力阈值', { min: 0 });

  const renderForm = () => {
    configShape();
    const kind = $('kind').value;
    const method = state.config.methods[kind] || {};
    const modulus = method.modulus || {};
    $('project-name').value = text(pathValue(state.config, ['project', 'name'], ''));
    $('lower-fraction').value = pathValue(modulus, ['lower_fraction'], '') === '' ? '' : Number(pathValue(modulus, ['lower_fraction'])) * 100;
    $('upper-fraction').value = pathValue(modulus, ['upper_fraction'], '') === '' ? '' : Number(pathValue(modulus, ['upper_fraction'])) * 100;
    ['span_mm', 'width_mm', 'depth_mm'].forEach((key) => {
      $(key.replace('_mm', '-mm')).value = pathValue(state.config, ['methods', 'flexural', 'geometry', key], '');
    });
    $('geometry-card').hidden = kind !== 'flexural';
    renderMappings();
  };

  const markConfigEdited = () => {
    state.configDirty = true;
    state.configOrigin = 'edited';
    $('config-status').textContent = '配置已编辑，尚未检查';
    $('config-status').className = 'config-status';
  };

  const renderMappings = () => {
    const body = $('mapping-body');
    body.replaceChildren();
    const mappings = state.config.condition_mapping || {};
    Object.entries(mappings).forEach(([condition, mapping]) => {
      const row = document.createElement('tr');
      const values = [condition, mapping.label_cn, mapping.label_en, mapping.group_id, mapping.mix_id];
      const fields = ['condition', 'label_cn', 'label_en', 'group_id', 'mix_id'];
      values.forEach((value, index) => {
        const cell = document.createElement('td');
        const input = document.createElement('input');
        input.value = text(value);
        input.disabled = false;
        input.dataset.condition = condition;
        input.dataset.field = fields[index];
        input.addEventListener('change', (event) => {
          const field = event.target.dataset.field;
          const nextCondition = event.target.value.trim();
          if (field === 'condition') {
            if (!nextCondition) {
              event.target.value = condition;
              showAlert('条件标识不能为空。');
              return;
            }
            if (nextCondition !== condition && Object.prototype.hasOwnProperty.call(state.config.condition_mapping, nextCondition)) {
              event.target.value = condition;
              showAlert(`条件标识“${nextCondition}”已存在。`);
              return;
            }
            if (nextCondition !== condition) {
              const original = state.config.condition_mapping[condition] || {};
              delete state.config.condition_mapping[condition];
              state.config.condition_mapping[nextCondition] = original;
              markConfigEdited();
              renderMappings();
            }
            return;
          }
          const current = state.config.condition_mapping[condition] || {};
          current[field] = event.target.value;
          if (field === 'mix_id' && event.target.value && !state.config.mixes[event.target.value]) {
            state.config.mixes[event.target.value] = {};
          }
          markConfigEdited();
        });
        cell.append(input);
        row.append(cell);
      });
      const removeCell = document.createElement('td');
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'table-remove';
      remove.title = '移除映射';
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        delete state.config.condition_mapping[condition];
        markConfigEdited();
        renderMappings();
      });
      removeCell.append(remove);
      row.append(removeCell);
      body.append(row);
    });
    if (!Object.keys(mappings).length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 6;
      cell.className = 'empty-cell';
      cell.textContent = '暂无条件映射，请添加一行';
      row.append(cell);
      body.append(row);
    }
  };

  const clearInspection = () => {
    state.inspect = null;
    state.inspectedInput = '';
    $('inspect-empty').hidden = false;
    $('inspect-result').hidden = true;
  };

  const resetForInputChange = () => {
    const input = $('input-dir').value.trim();
    if (input === state.inputDir) return;
    state.inputDir = input;
    clearInspection();
    state.configPath = '';
    state.configOrigin = 'template';
    state.configDirty = false;
    state.config = clone(state.bootstrap?.template_config || {});
    renderForm();
    $('config-status').textContent = input ? '输入目录已更换，请重新检查' : '等待输入目录';
    $('config-status').className = 'config-status';
  };

  const renderPresets = () => {
    const select = $('preset-select');
    select.replaceChildren();
    const current = document.createElement('option');
    current.value = '';
    current.textContent = '当前配置（未保存）';
    select.append(current);
    (state.bootstrap?.presets || []).forEach((preset) => {
      const option = document.createElement('option');
      option.value = preset.id;
      option.textContent = preset.name;
      select.append(option);
    });
  };

  const statusLabel = (status) => ({
    queued: '排队中', running: '处理中', succeeded: '已完成', failed: '失败',
    cancelled: '已取消', interrupted: '已中断',
  }[status] || '尚未运行');

  const renderHistory = () => {
    const list = $('history-list');
    list.replaceChildren();
    const runs = state.bootstrap?.runs || [];
    $('history-count').textContent = runs.length;
    if (!runs.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state compact';
      empty.innerHTML = icon('i-clock');
      const p = document.createElement('p');
      p.textContent = '还没有运行记录';
      empty.append(p);
      list.append(empty);
      return;
    }
    runs.forEach((run) => {
      const item = document.createElement('div');
      item.className = 'history-item';
      const info = document.createElement('div');
      info.className = 'history-info';
      const name = document.createElement('b');
      name.textContent = run.input_dir || run.id;
      const small = document.createElement('small');
      small.textContent = `${run.kind === 'flexural' ? '抗折' : '抗压'} · ${statusLabel(run.status)} · ${run.finished_at || run.started_at || '—'}`;
      info.append(name, small);
      const side = document.createElement('div');
      side.className = 'history-side';
      const badge = document.createElement('span');
      badge.className = `run-badge ${run.status || ''}`;
      badge.textContent = statusLabel(run.status);
      const open = document.createElement('button');
      open.className = 'button small secondary';
      open.type = 'button';
      open.textContent = '查看';
      open.addEventListener('click', () => loadRun(run.id));
      side.append(badge, open);
      item.append(info, side);
      list.append(item);
    });
  };

  const renderInspect = (data) => {
    state.inspect = data;
    $('inspect-empty').hidden = true;
    $('inspect-result').hidden = false;
    const stats = $('inspect-stats');
    stats.replaceChildren();
    [['total', '总文件'], ['valid', '命名通过'], ['invalid', '需检查']].forEach(([key, label]) => {
      const item = document.createElement('div');
      item.className = 'stat';
      const value = document.createElement('b');
      value.textContent = data.counts?.[key] ?? '—';
      const caption = document.createElement('span');
      caption.textContent = label;
      item.append(value, caption);
      stats.append(item);
    });
    const body = $('inspect-body');
    body.replaceChildren();
    (data.files || []).forEach((file) => {
      const row = document.createElement('tr');
      [file.name, file.condition, file.age, file.specimen].forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value == null || value === '' ? '—' : value;
        row.append(cell);
      });
      const status = document.createElement('td');
      status.className = file.error ? 'state-error' : 'state-ok';
      status.textContent = file.error || '已识别';
      row.append(status);
      body.append(row);
    });
  };

  const columnLabels = {
    filename: '文件名', status: '状态', strength_MPa: '强度（MPa）', modulus_GPa: '模量（GPa）',
    condition: '条件', age: '龄期', specimen: '试件', end: '端次', group_key: '分组', mix_id: '配方',
    error: '错误', error_msg: '失败原因', stress_MPa: '应力（MPa）', strain_pct: '应变（%）', deform_mm: '变形（mm）', force_kN: '力（kN）',
  };
  const primaryColumns = ['filename', 'status', 'condition', 'age', 'specimen', 'end', 'strength_MPa', 'modulus_GPa', 'group_key', 'mix_id', 'error'];
  const numericColumns = new Set(['age', 'end', 'strength_MPa', 'modulus_GPa', 'stress_MPa', 'strain_pct', 'deform_mm', 'force_kN']);

  const resultStatusLabel = (status) => ({
    ok: '成功', success: '成功', succeeded: '成功', error: '失败', failed: '失败',
  }[status] || (status == null || status === '' ? '—' : text(status)));

  const resultDisplayValue = (column, value) => {
    if (value == null || value === '') return '—';
    if (typeof value === 'number' || numericColumns.has(column)) {
      const number = Number(value);
      if (Number.isFinite(number)) return String(Number(number.toPrecision(6)));
    }
    return String(value);
  };

  const renderTable = (headId, bodyId, columns, rows) => {
    const head = $(headId);
    head.replaceChildren();
    const headRow = document.createElement('tr');
    columns.forEach((column) => {
      const cell = document.createElement('th');
      cell.textContent = columnLabels[column] || column;
      headRow.append(cell);
    });
    head.append(headRow);
    const body = $(bodyId);
    body.replaceChildren();
    rows.forEach((record) => {
      const row = document.createElement('tr');
      columns.forEach((column) => {
        const cell = document.createElement('td');
        const value = record[column];
        cell.textContent = column === 'status' ? resultStatusLabel(value) : resultDisplayValue(column, value);
        if (column === 'status') cell.className = value === 'ok' ? 'state-ok' : 'state-error';
        row.append(cell);
      });
      body.append(row);
    });
  };

  const renderResults = (data) => {
    $('results').hidden = false;
    const stats = $('result-stats');
    stats.replaceChildren();
    Object.entries(data.stats || {}).forEach(([key, value]) => {
      const item = document.createElement('span');
      const number = document.createElement('b');
      number.textContent = value ?? '—';
      item.append(number, document.createTextNode({ files: '文件', succeeded: '成功', failed: '失败', groups: '分组', specimens: '试件' }[key] || key));
      stats.append(item);
    });
    const columns = data.columns || [];
    const hasFailedRows = (data.rows || []).some((row) => row.status && row.status !== 'ok');
    const preferredColumns = hasFailedRows ? [...primaryColumns, 'error_msg'] : primaryColumns;
    const visibleColumns = preferredColumns.filter((column) => columns.includes(column));
    const technicalColumns = columns.filter((column) => !visibleColumns.includes(column));
    renderTable('result-head', 'result-body', visibleColumns, data.rows || []);
    renderTable('technical-head', 'technical-body', technicalColumns, data.rows || []);
    $('technical-fields').hidden = technicalColumns.length === 0;

    const figureGrid = $('figure-grid');
    figureGrid.replaceChildren();
    (data.figures || []).forEach((figure) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'figure-card';
      card.title = '放大查看';
      const image = document.createElement('img');
      image.src = figure.url;
      image.alt = figure.name || '图表';
      const label = document.createElement('span');
      label.textContent = figure.name || '图表';
      card.append(image, label);
      card.addEventListener('click', () => window.open(figure.url, '_blank', 'noopener'));
      figureGrid.append(card);
    });
    if (!(data.figures || []).length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state compact';
      empty.textContent = '暂无曲线预览';
      figureGrid.append(empty);
    }

    const links = $('table-links');
    links.replaceChildren();
    (data.tables || []).forEach((table) => {
      const link = document.createElement('a');
      link.className = 'result-file-link';
      link.href = table.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = table.name || '结果表';
      links.append(link);
    });
    if (!(data.tables || []).length) links.textContent = '暂无结果文件';
  };

  const loadResults = async (id) => {
    try {
      renderResults(await api(`/api/runs/${encodeURIComponent(id)}/results`));
    } catch (error) {
      showAlert(error.message);
    }
  };

  const clearResults = () => {
    $('results').hidden = true;
    ['result-stats', 'result-head', 'result-body', 'technical-head', 'technical-body', 'figure-grid', 'table-links']
      .forEach((id) => $(id)?.replaceChildren());
  };

  const updateRunView = (run) => {
    state.selectedRun = run;
    const status = run?.status || '';
    const badge = $('run-status');
    badge.className = `run-badge ${status}`;
    badge.textContent = statusLabel(status);
    $('run-title').textContent = status ? `${statusLabel(status)}：${run.input_dir || run.id}` : '准备开始一次处理';
    $('run-message').textContent = run?.message || (status ? '正在等待后台记录最新状态。' : '处理完成后，汇总表与曲线预览会出现在这里。');
    $('open-output').disabled = !run?.output_dir;
    $('cancel-run').hidden = !(state.activeRun && ['queued', 'running'].includes(state.activeRun.status));
    const logs = run?.logs || [];
    $('log-output').textContent = logs.slice(-80).join('\n') || '等待运行...';
    $('log-count').textContent = `${logs.length} 行`;
    if (['succeeded', 'failed', 'cancelled', 'interrupted'].includes(status)) loadResults(run.id);
    else if (!status) $('results').hidden = true;
  };

  const setConnection = (connected) => {
    $('connection-state').classList.toggle('offline', !connected);
    $('connection-label').textContent = connected ? '本地服务已连接' : '本地服务不可用';
  };

  const configControls = () => [
    $('input-dir'), $('output-base'), $('kind'), $('force-threshold'), $('lower-fraction'), $('upper-fraction'),
    $('span-mm'), $('width-mm'), $('depth-mm'), $('project-name'), $('preset-select'), $('load-config'),
    $('save-preset'), $('add-mapping'), $('inspect'), $('load-example'), $('start-run'),
  ].filter(Boolean);

  const setBusy = (busy) => {
    state.busy = busy;
    configControls().forEach((element) => { element.disabled = busy; });
    document.querySelectorAll('.browse-button').forEach((element) => { element.disabled = busy; });
    document.querySelectorAll('#mapping-body input, #mapping-body button').forEach((element) => { element.disabled = busy; });
    $('cancel-run').disabled = false;
    $('cancel-run').hidden = !(state.activeRun && ['queued', 'running'].includes(state.activeRun.status));
    $('open-output').disabled = !state.selectedRun?.output_dir;
  };

  const pollRun = (id) => {
    clearInterval(state.poll);
    state.poll = setInterval(async () => {
      try {
        const run = await api(`/api/runs/${encodeURIComponent(id)}`);
        state.activeRun = run;
        if (state.selectedRun?.id === id) updateRunView(run);
        if (['succeeded', 'failed', 'cancelled', 'interrupted'].includes(run.status)) {
          clearInterval(state.poll);
          state.poll = null;
          if (state.activeRunId === id) {
            state.activeRunId = null;
            state.activeRun = null;
          }
          setBusy(Boolean(state.activeRunId));
          await refreshBootstrap();
          if (state.selectedRun?.id === id) updateRunView(run);
        }
      } catch (error) {
        clearInterval(state.poll);
        state.poll = null;
        state.activeRunId = null;
        state.activeRun = null;
        setBusy(false);
        showAlert(error.message);
      }
    }, 1000);
  };

  const loadRun = async (id) => {
    try {
      const run = await api(`/api/runs/${encodeURIComponent(id)}`);
      updateRunView(run);
      if (state.activeRunId && ['queued', 'running'].includes(run.status)) {
        setBusy(true);
      } else if (['queued', 'running'].includes(run.status) && !state.activeRunId) {
        state.activeRunId = id;
        state.activeRun = run;
        setBusy(true);
        pollRun(id);
      }
      document.querySelector('.run-panel')?.scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
      showAlert(error.message);
    }
  };

  const refreshBootstrap = async () => {
    try {
      const data = await api('/api/bootstrap');
      state.bootstrap = data;
      setConnection(true);
      $('app-version').textContent = data.version || '—';
      if (!state.bootstrapped) {
        $('input-dir').value = data.default_input || '';
        $('output-base').value = data.default_output || '';
        state.config = clone(data.template_config || {});
        renderForm();
      }
      state.bootstrapped = true;
      renderPresets();
      renderHistory();
      const active = (data.runs || []).find((run) => ['queued', 'running'].includes(run.status));
      if (active) {
        state.activeRunId = active.id;
        state.activeRun = active;
        if (!state.selectedRun || state.selectedRun.id === active.id) updateRunView(active);
        setBusy(true);
        pollRun(active.id);
      }
    } catch (error) {
      setConnection(false);
      throw error;
    }
  };

  const inspect = async () => {
    clearAlert();
    const input = $('input-dir').value.trim();
    if (!input) {
      showAlert('请先选择输入文件夹。');
      return;
    }
    if (input !== state.inputDir) resetForInputChange();
    try {
      const request = { input_dir: input };
      if (state.configPath && (state.configOrigin === 'yaml' || state.configOrigin === 'preset')) request.config_path = state.configPath;
      const data = await api('/api/inspect', { method: 'POST', body: request });
      const preserveEdited = state.configDirty || ['yaml', 'preset', 'example'].includes(state.configOrigin);
      if (!preserveEdited && data.config) {
        state.config = clone(data.config);
        state.configPath = data.config_path || '';
        state.configOrigin = 'inspect';
        state.configDirty = false;
        renderForm();
        $('config-status').textContent = '已载入检查返回配置';
        $('config-status').className = 'config-status ok';
      }
      state.inputDir = input;
      state.inspectedInput = input;
      renderInspect(data);
    } catch (error) {
      showAlert(error.message);
    }
  };

  const startRun = async () => {
    clearAlert();
    if (state.busy) return;
    const input = $('input-dir').value.trim();
    const output = $('output-base').value.trim();
    if (!input || !output) {
      showAlert('请填写输入文件夹和输出目录。');
      return;
    }
    try {
      writeFormToConfig($('kind').value);
      const threshold = thresholdValue();
      clearResults();
      setBusy(true);
      const validation = await api('/api/config/validate', {
        method: 'POST',
        body: { config: state.config, kind: $('kind').value, threshold },
      });
      if (validation.valid !== true) throw new Error('配置未通过检查。');
      const run = await api('/api/runs', {
        method: 'POST',
        body: { input_dir: input, output_base: output, kind: $('kind').value, threshold, config: state.config },
      });
      state.inputDir = input;
      state.activeRunId = run.id;
      state.activeRun = run;
      state.selectedRun = run;
      $('config-status').textContent = '当前配置已用于本次运行';
      $('config-status').className = 'config-status ok';
      updateRunView(run);
      pollRun(run.id);
      document.querySelector('.run-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      await refreshBootstrap();
    } catch (error) {
      state.activeRunId = null;
      state.activeRun = null;
      setBusy(false);
      showAlert(error.message);
    }
  };

  const cancelRun = async () => {
    if (!state.activeRunId) return;
    try {
      const run = await api(`/api/runs/${encodeURIComponent(state.activeRunId)}/cancel`, { method: 'POST', body: {} });
      state.activeRun = run;
      if (state.selectedRun?.id === run.id) updateRunView(run);
    } catch (error) {
      showAlert(error.message);
    }
  };

  const openBrowse = async (mode, target, startPath = '') => {
    state.browse = { mode, target, path: startPath, selected: startPath };
    $('browse-modal').hidden = false;
    $('browse-path').value = startPath;
    await browse(startPath);
    $('browse-path').focus();
  };

  const addBrowserRow = (entry, directory) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'browser-row';
    row.innerHTML = icon(directory ? 'i-folder' : 'i-file');
    const label = document.createElement('span');
    label.textContent = entry.name;
    row.append(label);
    row.title = entry.path || '';
    row.addEventListener('click', () => {
      state.browse.selected = entry.path;
      $('browse-selection').textContent = entry.path;
    });
    row.addEventListener('dblclick', () => directory ? browse(entry.path) : selectBrowse(entry.path));
    $('browser-list').append(row);
  };

  const browse = async (path) => {
    const modal = $('browse-modal').querySelector('.modal');
    modal.setAttribute('aria-busy', 'true');
    try {
      const query = `mode=${encodeURIComponent(state.browse.mode)}&path=${encodeURIComponent(path || '')}`;
      const data = await api(`/api/browse?${query}`);
      state.browse.path = data.path || '';
      state.browse.selected = data.path || '';
      $('browse-path').value = data.path || '';
      $('browse-location').textContent = data.path || '根目录';
      const list = $('browser-list');
      list.replaceChildren();
      if (data.parent && data.path) {
        const up = document.createElement('button');
        up.type = 'button';
        up.className = 'browser-row';
        up.innerHTML = icon('i-chevron');
        const label = document.createElement('span');
        label.textContent = '返回上一级';
        up.append(label);
        up.addEventListener('click', () => browse(data.parent));
        list.append(up);
      }
      (data.directories || []).forEach((entry) => addBrowserRow(entry, true));
      (data.files || []).forEach((entry) => addBrowserRow(entry, false));
      $('browse-selection').textContent = data.path ? `当前：${data.path}` : '请选择一个目录';
    } catch (error) {
      showAlert(error.message);
    } finally {
      modal.removeAttribute('aria-busy');
    }
  };

  const selectBrowse = (path) => {
    if (!path) return;
    if (state.browse.mode === 'config') {
      loadConfig(path);
      $('browse-modal').hidden = true;
      return;
    }
    $(state.browse.target).value = path;
    if (state.browse.target === 'input-dir') resetForInputChange();
    $('browse-modal').hidden = true;
  };

  const loadConfig = async (path) => {
    try {
      const data = await api('/api/config/load', { method: 'POST', body: { path } });
      state.config = clone(data.config || {});
      state.configPath = data.config_path || path;
      state.configOrigin = 'yaml';
      state.configDirty = false;
      $('force-threshold').value = '0.25';
      renderForm();
      $('config-status').textContent = '已加载本地 YAML 配置';
      $('config-status').className = 'config-status ok';
    } catch (error) {
      showAlert(error.message);
    }
  };

  const loadPreset = async (id) => {
    if (!id) return;
    try {
      const data = await api(`/api/presets/${encodeURIComponent(id)}`);
      state.config = clone(data.config || {});
      state.configPath = '';
      state.configOrigin = 'preset';
      state.configDirty = false;
      $('kind').value = data.kind || $('kind').value;
      state.formKind = $('kind').value;
      $('force-threshold').value = data.threshold !== undefined && data.threshold !== null ? data.threshold : '0.25';
      renderForm();
      $('config-status').textContent = `已加载预设：${data.name}`;
      $('config-status').className = 'config-status ok';
    } catch (error) {
      showAlert(error.message);
    }
  };

  const loadExample = async () => {
    clearAlert();
    const example = state.bootstrap?.examples?.[$('kind').value];
    if (!example) {
      showAlert('当前方法没有可用合成示例。');
      return;
    }
    $('input-dir').value = example.input_dir || '';
    resetForInputChange();
    state.config = clone(example.config || state.config);
    state.configPath = '';
    state.configOrigin = 'example';
    state.configDirty = false;
    $('force-threshold').value = '0.25';
    renderForm();
    $('config-status').textContent = '已载入合成示例配置；尚未运行';
    $('config-status').className = 'config-status ok';
    await inspect();
  };

  const savePreset = () => {
    $('preset-name').value = '';
    $('preset-modal').hidden = false;
    $('preset-name').focus();
  };

  const confirmPreset = async () => {
    const name = $('preset-name').value.trim();
    if (!name) {
      showAlert('请填写预设名称。');
      return;
    }
    try {
      writeFormToConfig($('kind').value);
      const threshold = thresholdValue();
      const data = await api('/api/presets', {
        method: 'POST',
        body: { name, config: state.config, kind: $('kind').value, threshold },
      });
      $('preset-modal').hidden = true;
      await refreshBootstrap();
      $('preset-select').value = data.id;
      $('config-status').textContent = `已保存预设：${data.name}`;
      $('config-status').className = 'config-status ok';
    } catch (error) {
      showAlert(error.message);
    }
  };

  $('kind').addEventListener('change', () => {
    const previousKind = state.formKind;
    try {
      writeFormToConfig(previousKind);
    } catch (error) {
      $('kind').value = previousKind;
      showAlert(error.message);
      return;
    }
    state.formKind = $('kind').value;
    renderForm();
  });
  $('input-dir').addEventListener('change', resetForInputChange);
  $('project-name').addEventListener('input', markConfigEdited);
  ['lower-fraction', 'upper-fraction', 'span-mm', 'width-mm', 'depth-mm']
    .forEach((id) => $(id).addEventListener('change', markConfigEdited));
  $('inspect').addEventListener('click', inspect);
  $('start-run').addEventListener('click', startRun);
  $('cancel-run').addEventListener('click', cancelRun);
  $('load-example').addEventListener('click', loadExample);
  $('save-preset').addEventListener('click', savePreset);
  $('confirm-preset').addEventListener('click', confirmPreset);
  $('preset-select').addEventListener('change', (event) => loadPreset(event.target.value));
  $('load-config').addEventListener('click', () => openBrowse('config', 'config-path'));
  $('refresh-bootstrap').addEventListener('click', () => refreshBootstrap().catch((error) => showAlert(error.message)));
  $('open-output').addEventListener('click', async () => {
    if (!state.selectedRun) return;
    try {
      await api('/api/open-output', { method: 'POST', body: { run_id: state.selectedRun.id } });
    } catch (error) {
      showAlert(error.message);
    }
  });
  document.querySelectorAll('.browse-button').forEach((button) => {
    button.addEventListener('click', () => openBrowse(button.dataset.browse, button.dataset.target, $(button.dataset.target).value));
  });
  $('browse-go').addEventListener('click', () => browse($('browse-path').value.trim()));
  $('browse-path').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') browse($('browse-path').value.trim());
  });
  $('browse-select').addEventListener('click', () => selectBrowse(state.browse.selected || state.browse.path));
  $('add-mapping').addEventListener('click', () => {
    const base = 'condition';
    let key = base;
    let index = 1;
    while (state.config.condition_mapping[key]) key = `${base}_${index++}`;
    state.config.condition_mapping[key] = { group_id: key, mix_id: key, label_cn: '', label_en: '', factors: {} };
    state.config.mixes[key] ||= {};
    markConfigEdited();
    renderMappings();
  });
  document.querySelectorAll('[data-close-modal]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.modal-backdrop').hidden = true);
  });
  document.querySelectorAll('.modal-backdrop').forEach((backdrop) => {
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) backdrop.hidden = true;
    });
  });
  document.querySelectorAll('[data-scroll]').forEach((button) => {
    button.addEventListener('click', () => document.getElementById(button.dataset.scroll)?.scrollIntoView({ behavior: 'smooth' }));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') document.querySelectorAll('.modal-backdrop').forEach((modal) => { modal.hidden = true; });
  });

  refreshBootstrap().catch((error) => showAlert(`无法连接本地服务：${error.message}`));
})();
