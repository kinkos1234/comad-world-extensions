#!/usr/bin/env node
// 품앗이 오케스트레이터 - council-job.js를 기반으로 Codex 외주 개발용으로 가공
// 주요 변경점:
//   - config key: parallel (council 대신)
//   - tasks 필드 사용 (members 대신)
//   - chairman 개념 없음 (Claude가 직접 검토)
//   - 기본 command: codex exec
//   - 기본 timeout: 3600초 (1시간)

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const SCRIPT_DIR = __dirname;
const SKILL_DIR = path.resolve(SCRIPT_DIR, '..');
const WORKER_PATH = path.join(SCRIPT_DIR, 'parallel-job-worker.js');

const SKILL_CONFIG_FILE = path.join(SKILL_DIR, 'parallel.config.yaml');
const REPO_CONFIG_FILE = path.join(path.resolve(SKILL_DIR, '../..'), 'parallel.config.yaml');

const DEFAULT_CODEX_COMMAND = 'codex exec --dangerously-bypass-approvals-and-sandbox';
const DEFAULT_TIMEOUT_SEC = 3600;

function killProcess(pid) {
  try {
    if (process.platform === 'win32') {
      process.kill(pid, 'SIGKILL');
    } else {
      process.kill(pid, 'SIGTERM');
    }
  } catch { /* process already gone */ }
}

function exitWithError(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function resolveDefaultConfigFile() {
  // 1순위: CWD의 .parallel/ (프로젝트별 config)
  const cwdConfig = path.join(process.cwd(), '.parallel', 'parallel.config.yaml');
  if (fs.existsSync(cwdConfig)) return cwdConfig;
  // 2순위: 플러그인 내부 config
  if (fs.existsSync(SKILL_CONFIG_FILE)) return SKILL_CONFIG_FILE;
  // 3순위: 플러그인 루트 2단계 위
  if (fs.existsSync(REPO_CONFIG_FILE)) return REPO_CONFIG_FILE;
  return SKILL_CONFIG_FILE;
}

function parseParallelConfig(configPath) {
  const fallback = {
    parallel: {
      tasks: [],
      defaults: { command: DEFAULT_CODEX_COMMAND },
      settings: { timeout: DEFAULT_TIMEOUT_SEC },
    },
  };

  if (!fs.existsSync(configPath)) return fallback;

  let YAML;
  try {
    YAML = require('yaml');
  } catch {
    exitWithError(
      [
        'Missing runtime dependency: yaml',
        'Install it:',
        `  cd ${SKILL_DIR} && npm install yaml`,
        'Or install globally:',
        '  npm install -g yaml',
      ].join('\n')
    );
  }

  let parsed;
  try {
    parsed = YAML.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (error) {
    exitWithError(`Invalid YAML in ${configPath}: ${error && error.message ? error.message : String(error)}`);
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    exitWithError(`Invalid config: expected a YAML object at root`);
  }
  if (!parsed.parallel) {
    exitWithError(`Invalid config: missing required top-level key 'parallel:'`);
  }

  const parallel = parsed.parallel;
  const merged = {
    parallel: {
      tasks: [],
      defaults: { command: DEFAULT_CODEX_COMMAND, ...((parallel.defaults && typeof parallel.defaults === 'object') ? parallel.defaults : {}) },
      settings: { timeout: DEFAULT_TIMEOUT_SEC, max_retries: 2, ...((parallel.settings && typeof parallel.settings === 'object') ? parallel.settings : {}) },
      context: { reference_files: [] },
    },
  };

  // tasks 파싱
  if (Array.isArray(parallel.tasks) && parallel.tasks.length > 0) {
    merged.parallel.tasks = parallel.tasks;
  } else if (Array.isArray(parallel.members) && parallel.members.length > 0) {
    // 하위 호환: members 키도 허용
    merged.parallel.tasks = parallel.members;
  }

  // Calculate max round
  let maxRound = 1;
  for (const t of merged.parallel.tasks) {
    const r = Number(t.round) || 1;
    if (r > maxRound) maxRound = r;
  }
  merged.parallel.maxRound = maxRound;

  // Normalize settings: max_retries -> maxRetries
  if (merged.parallel.settings.max_retries != null) {
    merged.parallel.settings.maxRetries = Number(merged.parallel.settings.max_retries);
  }

  // style 파싱 (코드 스타일 커스텀 규칙)
  if (parallel.style && typeof parallel.style === 'string') {
    merged.parallel.style = parallel.style.trim();
  } else if (Array.isArray(parallel.style)) {
    merged.parallel.style = parallel.style.map((s) => `- ${s}`).join('\n');
  }

  // context 파싱
  if (parallel.context && typeof parallel.context === 'object') {
    if (Array.isArray(parallel.context.reference_files)) {
      merged.parallel.context.reference_files = parallel.context.reference_files;
    }
    if (parallel.context.project) merged.parallel.context.project = parallel.context.project;
    if (parallel.context.description) merged.parallel.context.description = parallel.context.description;
  }

  return merged;
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function buildContextString(config, workingDir) {
  const contextConfig = config.parallel.context || {};
  const referenceFiles = contextConfig.reference_files || [];
  if (referenceFiles.length === 0) return '';

  const parts = [];
  if (contextConfig.project) {
    parts.push(`# 프로젝트: ${contextConfig.project}`);
    if (contextConfig.description) parts.push(`> ${contextConfig.description}`);
    parts.push('');
  }
  parts.push('---');
  parts.push('## 참조 컨텍스트');
  parts.push('');

  for (const relPath of referenceFiles) {
    const absPath = path.resolve(workingDir || process.cwd(), relPath);
    if (!fs.existsSync(absPath)) {
      parts.push(`<!-- 파일 없음: ${relPath} -->`);
      continue;
    }
    try {
      const content = fs.readFileSync(absPath, 'utf8');
      const fileName = path.basename(relPath, path.extname(relPath));
      parts.push(`### ${fileName}`);
      parts.push('```');
      parts.push(content.trim());
      parts.push('```');
      parts.push('');
    } catch (err) {
      parts.push(`<!-- Error reading ${relPath}: ${err.message} -->`);
    }
  }

  parts.push('---');
  parts.push('## 프로젝트 컨텍스트');
  parts.push('');
  return parts.join('\n');
}

function safeFileName(name) {
  const cleaned = String(name || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
  return cleaned || 'task';
}

function atomicWriteJson(filePath, payload) {
  const tmpPath = `${filePath}.${process.pid}.${crypto.randomBytes(4).toString('hex')}.tmp`;
  fs.writeFileSync(tmpPath, JSON.stringify(payload, null, 2), 'utf8');
  fs.renameSync(tmpPath, filePath);
}

function readJsonIfExists(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function sleepMs(ms) {
  const msNum = Number(ms);
  if (!Number.isFinite(msNum) || msNum <= 0) return;
  const sab = new SharedArrayBuffer(4);
  const view = new Int32Array(sab);
  Atomics.wait(view, 0, 0, Math.trunc(msNum));
}

function computeTerminalDoneCount(counts) {
  const c = counts || {};
  return (
    Number(c.done || 0) +
    Number(c.missing_cli || 0) +
    Number(c.error || 0) +
    Number(c.timed_out || 0) +
    Number(c.canceled || 0)
  );
}

function asCodexStepStatus(value) {
  const v = String(value || '');
  if (v === 'pending' || v === 'in_progress' || v === 'completed') return v;
  return 'pending';
}

function buildPumasiUiPayload(statusPayload) {
  const counts = statusPayload.counts || {};
  const done = computeTerminalDoneCount(counts);
  const total = Number(counts.total || 0);
  const isDone = String(statusPayload.overallState || '') === 'done';
  const queued = Number(counts.queued || 0);
  const running = Number(counts.running || 0);

  const tasks = Array.isArray(statusPayload.members) ? statusPayload.members : [];
  const sortedTasks = tasks
    .map((m) => ({ member: String(m.member || ''), state: String(m.state || 'unknown'), exitCode: m.exitCode != null ? m.exitCode : null }))
    .filter((m) => m.member)
    .sort((a, b) => a.member.localeCompare(b.member));

  const terminalStates = new Set(['done', 'missing_cli', 'error', 'timed_out', 'canceled']);
  const dispatchStatus = asCodexStepStatus(isDone ? 'completed' : queued > 0 ? 'in_progress' : 'completed');
  let hasInProgress = dispatchStatus === 'in_progress';

  const taskSteps = sortedTasks.map((m) => {
    const state = m.state || 'unknown';
    const isTerminal = terminalStates.has(state);
    let status;
    if (isTerminal) { status = 'completed'; }
    else if (!hasInProgress && running > 0 && state === 'running') { status = 'in_progress'; hasInProgress = true; }
    else { status = 'pending'; }
    return { label: `[품앗이] ${m.member} 구현`, status: asCodexStepStatus(status) };
  });

  const reviewStatus = asCodexStepStatus(isDone ? (hasInProgress ? 'pending' : 'in_progress') : 'pending');

  const codexPlan = [
    { step: '[품앗이] 태스크 배분', status: dispatchStatus },
    ...taskSteps.map((s) => ({ step: s.label, status: s.status })),
    { step: '[품앗이] Claude 검토 및 통합', status: reviewStatus },
  ];

  const claudeTodos = [
    { content: '[품앗이] 태스크 배분', status: dispatchStatus, activeForm: dispatchStatus === 'completed' ? '배분 완료' : 'Codex에 태스크 배분 중' },
    ...taskSteps.map((s) => ({
      content: s.label,
      status: s.status,
      activeForm: s.status === 'completed' ? '구현 완료' : 'Codex 구현 중',
    })),
    {
      content: '[품앗이] Claude 검토 및 통합',
      status: reviewStatus,
      activeForm: reviewStatus === 'in_progress' ? '검토 준비됨' : '검토 대기 중',
    },
  ];

  return {
    progress: { done, total, overallState: String(statusPayload.overallState || '') },
    codex: { update_plan: { plan: codexPlan } },
    claude: { todo_write: { todos: claudeTodos } },
  };
}

function computeStatusPayload(jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  if (!fs.existsSync(resolvedJobDir)) exitWithError(`jobDir not found: ${resolvedJobDir}`);

  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError(`job.json not found`);

  const membersRoot = path.join(resolvedJobDir, 'members');
  if (!fs.existsSync(membersRoot)) exitWithError(`members folder not found`);

  const members = [];
  for (const entry of fs.readdirSync(membersRoot)) {
    const statusPath = path.join(membersRoot, entry, 'status.json');
    const status = readJsonIfExists(statusPath);
    if (status) members.push({ safeName: entry, ...status });
  }

  const totals = { queued: 0, running: 0, done: 0, error: 0, missing_cli: 0, timed_out: 0, canceled: 0 };
  for (const m of members) {
    const state = String(m.state || 'unknown');
    if (Object.prototype.hasOwnProperty.call(totals, state)) totals[state]++;
  }

  const allDone = totals.running === 0 && totals.queued === 0;
  const overallState = allDone ? 'done' : totals.running > 0 ? 'running' : 'queued';

  return {
    jobDir: resolvedJobDir,
    id: jobMeta.id || null,
    overallState,
    counts: { total: members.length, ...totals },
    members: members
      .map((m) => ({ member: m.member, state: m.state, startedAt: m.startedAt || null, finishedAt: m.finishedAt || null, exitCode: m.exitCode != null ? m.exitCode : null, message: m.message || null }))
      .sort((a, b) => String(a.member).localeCompare(String(b.member))),
  };
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const out = { _: [] };
  const booleanFlags = new Set(['json', 'text', 'checklist', 'help', 'h', 'verbose']);
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--') { out._.push(...args.slice(i + 1)); break; }
    if (!a.startsWith('--')) { out._.push(a); continue; }
    const [key, rawValue] = a.split('=', 2);
    if (rawValue != null) { out[key.slice(2)] = rawValue; continue; }
    const normalizedKey = key.slice(2);
    if (booleanFlags.has(normalizedKey)) { out[normalizedKey] = true; continue; }
    const next = args[i + 1];
    if (next == null || next.startsWith('--')) { out[normalizedKey] = true; continue; }
    out[normalizedKey] = next;
    i++;
  }
  return out;
}

function printHelp() {
  process.stdout.write(`품앗이 (Pumasi) — Codex 병렬 외주 개발

Usage:
  parallel-job.sh start [--config path] [--jobs-dir path] [--round N] "project context"
  parallel-job.sh start-round --round N <jobDir>
  parallel-job.sh status [--json|--text|--checklist] [--verbose] <jobDir>
  parallel-job.sh wait [--cursor CURSOR] [--interval-ms N] [--timeout-ms N] <jobDir>
  parallel-job.sh results [--json] <jobDir>
  parallel-job.sh gates [--json] <jobDir>
  parallel-job.sh redelegate --task <name> [--correction "text"] <jobDir>
  parallel-job.sh autofix <jobDir>
  parallel-job.sh stop <jobDir>
  parallel-job.sh clean <jobDir>

Re-delegation (재위임):
  redelegate retries a specific failed task with correction context.
  autofix automatically re-delegates all tasks with failed gates or errors.

Round-based execution:
  Tasks can have a 'round' field (default: 1). Round 1 tasks run first,
  then round 2 uses round 1 results as context, etc.
  start-round spawns workers for a specific round of an existing job.

Before running: edit parallel.config.yaml with your task list.
`);
}

function cmdStart(options, prompt) {
  const configPath = options.config || process.env.PUMASI_CONFIG || resolveDefaultConfigFile();
  const jobsDir = options['jobs-dir'] || process.env.PUMASI_JOBS_DIR || path.join(SKILL_DIR, '.jobs');

  ensureDir(jobsDir);

  const config = parseParallelConfig(configPath);
  const timeoutSetting = Number(config.parallel.settings.timeout || DEFAULT_TIMEOUT_SEC);
  const timeoutOverride = options.timeout != null ? Number(options.timeout) : null;
  const timeoutSec = Number.isFinite(timeoutOverride) && timeoutOverride > 0 ? timeoutOverride : timeoutSetting;

  const defaultCommand = config.parallel.defaults.command || DEFAULT_CODEX_COMMAND;

  const rawTasks = config.parallel.tasks || [];
  if (rawTasks.length === 0) {
    exitWithError(
      'parallel: 태스크가 없습니다.\nparallel.config.yaml의 tasks: 섹션에 서브태스크를 추가하세요.'
    );
  }

  const tasks = rawTasks.filter((t) => t && t.name);

  const maxRound = config.parallel.maxRound || 1;
  const requestedRound = options.round != null ? Number(options.round) : null;
  const currentRound = requestedRound || 1;

  // Filter tasks for current round
  const roundTasks = maxRound > 1
    ? tasks.filter(t => (Number(t.round) || 1) === currentRound)
    : tasks;

  if (roundTasks.length === 0) {
    exitWithError(`parallel: 라운드 ${currentRound}에 해당하는 태스크가 없습니다.`);
  }

  const jobId = `${new Date().toISOString().replace(/[:.]/g, '').replace('T', '-').slice(0, 15)}-${crypto.randomBytes(3).toString('hex')}`;
  const jobDir = path.join(jobsDir, `parallel-${jobId}`);
  const membersDir = path.join(jobDir, 'members');
  ensureDir(membersDir);

  // CWD 결정: config에서 지정하거나 현재 디렉토리 사용
  const workingDir = options.cwd || process.env.PUMASI_CWD || process.cwd();

  // 컨텍스트 + 프롬프트 합치기
  const contextString = buildContextString(config, workingDir);
  const fullPrompt = contextString ? `${contextString}${prompt}` : String(prompt);
  fs.writeFileSync(path.join(jobDir, 'prompt.txt'), fullPrompt, 'utf8');

  const jobMeta = {
    id: `parallel-${jobId}`,
    createdAt: new Date().toISOString(),
    configPath,
    cwd: workingDir,
    maxRound,
    currentRound,
    settings: { timeoutSec: timeoutSec || null, maxRetries: Number(config.parallel.settings.maxRetries || config.parallel.settings.max_retries || 2) },
    style: config.parallel.style || null,
    tasks: tasks.map((t) => ({
      name: String(t.name),
      command: String(t.command || defaultCommand),
      emoji: t.emoji ? String(t.emoji) : '🤖',
      instruction: t.instruction ? String(t.instruction).trim() : null,
      cwd: t.cwd ? String(t.cwd) : null,
      round: Number(t.round) || 1,
      gates: Array.isArray(t.gates) ? t.gates.map(g => ({
        name: String(g.name || 'unnamed'),
        command: String(g.command || ''),
      })).filter(g => g.command) : [],
    })),
  };
  atomicWriteJson(path.join(jobDir, 'job.json'), jobMeta);

  for (const task of roundTasks) {
    const name = String(task.name);
    const safeName = safeFileName(name);
    const memberDir = path.join(membersDir, safeName);
    ensureDir(memberDir);
    const command = String(task.command || defaultCommand);

    atomicWriteJson(path.join(memberDir, 'status.json'), {
      member: name, state: 'queued',
      queuedAt: new Date().toISOString(), command,
      round: currentRound,
    });

    // 태스크별 CWD: task.cwd > job.cwd > process.cwd()
    const taskCwd = task.cwd ? String(task.cwd) : workingDir;

    const workerArgs = [
      WORKER_PATH,
      '--job-dir', jobDir,
      '--member', name,
      '--safe-member', safeName,
      '--command', command,
      '--cwd', taskCwd,
    ];
    if (timeoutSec && Number.isFinite(timeoutSec) && timeoutSec > 0) {
      workerArgs.push('--timeout', String(timeoutSec));
    }

    const child = spawn(process.execPath, workerArgs, {
      detached: true,
      stdio: 'ignore',
      env: process.env,
      cwd: taskCwd,
    });
    child.unref();
  }

  // 마지막 job 저장
  const lastJobFile = path.join(jobsDir, '.last-job');
  try { fs.writeFileSync(lastJobFile, jobDir, 'utf8'); } catch { /* ignore */ }

  if (options.json) {
    process.stdout.write(`${JSON.stringify({ jobDir, ...jobMeta }, null, 2)}\n`);
  } else {
    process.stdout.write(`${jobDir}\n`);
  }
}

function cmdStatus(options, jobDir) {
  const payload = computeStatusPayload(jobDir);

  if (Boolean(options.checklist) && !options.json) {
    const done = computeTerminalDoneCount(payload.counts);
    process.stdout.write(`품앗이 진행상황 (${payload.id || jobDir})\n`);
    process.stdout.write(`완료: ${done}/${payload.counts.total} (실행 중: ${payload.counts.running}, 대기: ${payload.counts.queued})\n`);
    for (const m of payload.members) {
      const state = String(m.state || '');
      const mark = state === 'done' ? '[x]' : (state === 'running' || state === 'queued') ? '[ ]' : '[!]';
      const exitInfo = m.exitCode != null ? ` (exit ${m.exitCode})` : '';
      process.stdout.write(`${mark} ${m.member} — ${state}${exitInfo}\n`);
    }
    return;
  }

  if (Boolean(options.text) && !options.json) {
    const done = computeTerminalDoneCount(payload.counts);
    process.stdout.write(`tasks ${done}/${payload.counts.total} done; running=${payload.counts.running} queued=${payload.counts.queued}\n`);
    if (options.verbose) {
      for (const m of payload.members) {
        process.stdout.write(`- ${m.member}: ${m.state}${m.exitCode != null ? ` (exit ${m.exitCode})` : ''}\n`);
      }
    }
    return;
  }

  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
}

function parseWaitCursor(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const parts = raw.split(':');
  const version = parts[0];
  if (version === 'v2' && parts.length === 5) {
    const bucketSize = Number(parts[1]);
    const dispatchBucket = Number(parts[2]);
    const doneBucket = Number(parts[3]);
    const isDone = parts[4] === '1';
    if (!Number.isFinite(bucketSize) || bucketSize <= 0) return null;
    if (!Number.isFinite(dispatchBucket) || dispatchBucket < 0) return null;
    if (!Number.isFinite(doneBucket) || doneBucket < 0) return null;
    return { version, bucketSize, dispatchBucket, doneBucket, isDone };
  }
  return null;
}

function formatWaitCursor(bucketSize, dispatchBucket, doneBucket, isDone) {
  return `v2:${bucketSize}:${dispatchBucket}:${doneBucket}:${isDone ? 1 : 0}`;
}

function asWaitPayload(statusPayload) {
  const members = Array.isArray(statusPayload.members) ? statusPayload.members : [];
  return {
    jobDir: statusPayload.jobDir,
    id: statusPayload.id,
    overallState: statusPayload.overallState,
    counts: statusPayload.counts,
    members: members.map((m) => ({ member: m.member, state: m.state, exitCode: m.exitCode != null ? m.exitCode : null, message: m.message || null })),
    ui: buildPumasiUiPayload(statusPayload),
  };
}

function resolveBucketSize(options, total, prevCursor) {
  const raw = options.bucket != null ? options.bucket : options['bucket-size'];
  if (raw == null || raw === true) {
    if (prevCursor && prevCursor.bucketSize) return prevCursor.bucketSize;
  } else {
    const asString = String(raw).trim().toLowerCase();
    if (asString !== 'auto') {
      const num = Number(asString);
      if (!Number.isFinite(num) || num <= 0) exitWithError(`wait: invalid --bucket: ${raw}`);
      return Math.trunc(num);
    }
  }
  const totalNum = Number(total || 0);
  if (!Number.isFinite(totalNum) || totalNum <= 0) return 1;
  return Math.max(1, Math.ceil(totalNum / 5));
}

function cmdWait(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const cursorFilePath = path.join(resolvedJobDir, '.wait_cursor');
  const prevCursorRaw =
    options.cursor != null
      ? String(options.cursor)
      : fs.existsSync(cursorFilePath)
        ? String(fs.readFileSync(cursorFilePath, 'utf8')).trim()
        : '';
  const prevCursor = parseWaitCursor(prevCursorRaw);

  const intervalMs = Math.max(50, Math.trunc(Number(options['interval-ms'] != null ? options['interval-ms'] : 250)));
  const timeoutMs = Math.trunc(Number(options['timeout-ms'] != null ? options['timeout-ms'] : 0));

  let payload = computeStatusPayload(jobDir);
  const bucketSize = resolveBucketSize(options, payload.counts.total, prevCursor);

  const doneCount = computeTerminalDoneCount(payload.counts);
  const isDone = payload.overallState === 'done';
  const total = Number(payload.counts.total || 0);
  const queued = Number(payload.counts.queued || 0);
  const dispatchBucket = queued === 0 && total > 0 ? 1 : 0;
  const doneBucket = Math.floor(doneCount / bucketSize);
  const cursor = formatWaitCursor(bucketSize, dispatchBucket, doneBucket, isDone);

  if (!prevCursor) {
    fs.writeFileSync(cursorFilePath, cursor, 'utf8');
    process.stdout.write(`${JSON.stringify({ ...asWaitPayload(payload), cursor }, null, 2)}\n`);
    return;
  }

  const start = Date.now();
  while (cursor === prevCursorRaw) {
    if (timeoutMs > 0 && Date.now() - start >= timeoutMs) break;
    sleepMs(intervalMs);
    payload = computeStatusPayload(jobDir);
    const d = computeTerminalDoneCount(payload.counts);
    const doneFlag = payload.overallState === 'done';
    const totalCount = Number(payload.counts.total || 0);
    const queuedCount = Number(payload.counts.queued || 0);
    const dispatchB = queuedCount === 0 && totalCount > 0 ? 1 : 0;
    const doneB = Math.floor(d / bucketSize);
    const nextCursor = formatWaitCursor(bucketSize, dispatchB, doneB, doneFlag);
    if (nextCursor !== prevCursorRaw) {
      fs.writeFileSync(cursorFilePath, nextCursor, 'utf8');
      process.stdout.write(`${JSON.stringify({ ...asWaitPayload(payload), cursor: nextCursor }, null, 2)}\n`);
      return;
    }
  }

  const finalPayload = computeStatusPayload(jobDir);
  const finalDone = computeTerminalDoneCount(finalPayload.counts);
  const finalDoneFlag = finalPayload.overallState === 'done';
  const finalTotal = Number(finalPayload.counts.total || 0);
  const finalQueued = Number(finalPayload.counts.queued || 0);
  const finalDispatchBucket = finalQueued === 0 && finalTotal > 0 ? 1 : 0;
  const finalDoneBucket = Math.floor(finalDone / bucketSize);
  const finalCursor = formatWaitCursor(bucketSize, finalDispatchBucket, finalDoneBucket, finalDoneFlag);
  fs.writeFileSync(cursorFilePath, finalCursor, 'utf8');
  process.stdout.write(`${JSON.stringify({ ...asWaitPayload(finalPayload), cursor: finalCursor }, null, 2)}\n`);
}

function cmdResults(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  const membersRoot = path.join(resolvedJobDir, 'members');
  const members = [];

  if (fs.existsSync(membersRoot)) {
    for (const entry of fs.readdirSync(membersRoot)) {
      const statusPath = path.join(membersRoot, entry, 'status.json');
      const outputPath = path.join(membersRoot, entry, 'output.txt');
      const errorPath = path.join(membersRoot, entry, 'error.txt');
      const status = readJsonIfExists(statusPath);
      if (!status) continue;
      const output = fs.existsSync(outputPath) ? fs.readFileSync(outputPath, 'utf8') : '';
      const stderr = fs.existsSync(errorPath) ? fs.readFileSync(errorPath, 'utf8') : '';
      const gatesPath = path.join(membersRoot, entry, 'gates.json');
      const gatesResult = readJsonIfExists(gatesPath);
      const reportPath = path.join(membersRoot, entry, 'report.json');
      const report = readJsonIfExists(reportPath);
      members.push({ safeName: entry, ...status, output, stderr, gates: gatesResult, report });
    }
  }

  if (options.json) {
    process.stdout.write(`${JSON.stringify({
      jobDir: resolvedJobDir,
      id: jobMeta ? jobMeta.id : null,
      prompt: fs.existsSync(path.join(resolvedJobDir, 'prompt.txt'))
        ? fs.readFileSync(path.join(resolvedJobDir, 'prompt.txt'), 'utf8')
        : null,
      members: members
        .map((m) => ({ member: m.member, state: m.state, exitCode: m.exitCode != null ? m.exitCode : null, message: m.message || null, output: m.output, stderr: m.stderr, gates: m.gates || null, report: m.report || null }))
        .sort((a, b) => String(a.member).localeCompare(String(b.member))),
    }, null, 2)}\n`);
    return;
  }

  for (const m of members.sort((a, b) => String(a.member).localeCompare(String(b.member)))) {
    process.stdout.write(`\n${'═'.repeat(60)}\n`);
    process.stdout.write(`🤖 [${m.member}] — ${m.state}${m.exitCode != null ? ` (exit ${m.exitCode})` : ''}\n`);
    process.stdout.write(`${'═'.repeat(60)}\n`);
    if (m.message) process.stdout.write(`⚠️  ${m.message}\n`);
    process.stdout.write(m.output || '(출력 없음)');
    if (!m.output && m.stderr) {
      process.stdout.write('\n[stderr]\n');
      process.stdout.write(m.stderr);
    }
    if (m.gates) {
      const gIcon = m.gates.status === 'passed' ? '✅' : '❌';
      process.stdout.write(`\n${gIcon} Gates: ${m.gates.status} (${m.gates.passedCount || 0}/${m.gates.totalCount || 0})\n`);
      for (const g of (m.gates.gates || [])) {
        process.stdout.write(`  ${g.passed ? '✓' : '✗'} ${g.name}\n`);
      }
    }
    if (m.report) {
      process.stdout.write(`\n📋 Report: ${m.report.status || 'unknown'}\n`);
      if (m.report.summary) process.stdout.write(`  ${m.report.summary}\n`);
      if (Array.isArray(m.report.files_created) && m.report.files_created.length > 0) {
        process.stdout.write(`  Files: ${m.report.files_created.join(', ')}\n`);
      }
      if (Array.isArray(m.report.signatures) && m.report.signatures.length > 0) {
        process.stdout.write(`  Signatures: ${m.report.signatures.join(', ')}\n`);
      }
    }
    process.stdout.write('\n');
  }
}

// ─── comad integration: destroy-check (Phase 2.2) ────────────────────────────
// Codex worker 의 output.txt + 만든 commit 의 diff 에서 destructive 패턴 grep.
// destroy-gate.py 의 핵심 패턴 일부를 자체 보유 (worker context 에 적합한 것).
// Codex 는 별도 프로세스라 Claude 의 pre-tool-use hook 적용 안 됨 → 사후 검사.

const DESTROY_PATTERNS = [
  [/\brm\s+-[rRfFd]+\s+\//, 'rm -rf /'],
  [/\brm\s+-[rRfFd]+\s+~/, 'rm -rf ~'],
  [/\brm\s+-[rRfFd]+\s+\$HOME/, 'rm -rf $HOME'],
  [/\bgit\s+push\s+[^;&|\n]*--force/, 'git push --force'],
  [/\bgit\s+reset\s+--hard\s+(HEAD~|origin\/|upstream\/)/, 'git reset --hard ref'],
  [/\bgit\s+branch\s+-D\s+(main|master|develop|production)/, 'git branch -D protected'],
  [/\bgit\s+clean\s+-fd/, 'git clean -fd'],
  [/\bDROP\s+(DATABASE|SCHEMA)\b/i, 'DROP DATABASE/SCHEMA'],
  [/\bTRUNCATE\s+DATABASE\b/i, 'TRUNCATE DATABASE'],
  [/\bkubectl\s+delete\s+(namespace|ns|node)\b/, 'kubectl delete ns/node'],
  [/\bdocker\s+system\s+prune\s+[^;&|\n]*-a/, 'docker system prune -a'],
  [/\bmkfs\.[a-z0-9]+/, 'mkfs.*'],
  [/:\s*\(\s*\)\s*\{\s*:/, 'fork bomb'],
];

function scanForDestructive(text) {
  const hits = [];
  if (!text) return hits;
  for (const [re, label] of DESTROY_PATTERNS) {
    const m = text.match(re);
    if (m) hits.push({ pattern: label, snippet: m[0].slice(0, 100) });
  }
  return hits;
}

function cmdDestroyCheck(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('destroy-check: job.json not found');

  const membersRoot = path.join(resolvedJobDir, 'members');
  const results = {};

  for (const task of (jobMeta.tasks || [])) {
    const safeName = safeFileName(task.name);
    const memberDir = path.join(membersRoot, safeName);
    const status = readJsonIfExists(path.join(memberDir, 'status.json'));
    if (!status || status.state !== 'done') {
      results[task.name] = { status: 'skipped', reason: `task state: ${status ? status.state : 'unknown'}` };
      continue;
    }

    const sources = [];
    const outputPath = path.join(memberDir, 'output.txt');
    if (fs.existsSync(outputPath)) sources.push(['worker_output', fs.readFileSync(outputPath, 'utf8')]);

    const allHits = [];
    for (const [src, text] of sources) {
      const hits = scanForDestructive(text);
      for (const h of hits) allHits.push({ source: src, ...h });
    }

    if (allHits.length === 0) {
      results[task.name] = { status: 'passed' };
    } else {
      results[task.name] = { status: 'failed', hits: allHits, reason: `${allHits.length} destructive pattern(s) detected` };
    }
    atomicWriteJson(path.join(memberDir, 'destroy-check.json'), results[task.name]);
  }

  if (options.json) {
    process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
  } else {
    for (const [taskName, r] of Object.entries(results)) {
      const icon = r.status === 'passed' ? '✅' : r.status === 'skipped' ? '⏭️' : '❌';
      process.stdout.write(`${icon} ${taskName}: ${r.status}`);
      if (r.reason) process.stdout.write(` — ${r.reason}`);
      process.stdout.write('\n');
      for (const h of (r.hits || [])) process.stdout.write(`    ↳ ${h.pattern} in ${h.source}: ${h.snippet}\n`);
    }
  }

  const blocking = Object.values(results).filter((r) => r.status === 'failed').length;
  if (blocking > 0 && options.strict !== false) process.exitCode = 1;
}

// ─── comad integration: ear notify (Phase 2.3) ───────────────────────────────
// env COMAD_EAR_NOTIFY=1 + DISCORD_WEBHOOK_URL 모두 설정 시 cmdRunAll 끝에
// Discord webhook 으로 한 줄 요약 POST. 실패 silent.

function cmdEarNotify(jobDir) {
  const url = process.env.DISCORD_WEBHOOK_URL;
  if (!url) return;
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  const membersRoot = path.join(resolvedJobDir, 'members');
  let done = 0, failed = 0;
  if (fs.existsSync(membersRoot)) {
    for (const entry of fs.readdirSync(membersRoot)) {
      const st = readJsonIfExists(path.join(membersRoot, entry, 'status.json'));
      if (!st) continue;
      if (st.state === 'done') done++;
      else if (st.state === 'failed' || st.state === 'timeout') failed++;
    }
  }
  const jobId = jobMeta && jobMeta.id ? jobMeta.id : path.basename(resolvedJobDir);
  const msg = `🤖 parallel \`${jobId}\` finished — done=${done}, failed=${failed}`;
  try {
    const { execFileSync } = require('child_process');
    execFileSync('curl', [
      '-s', '-X', 'POST',
      '-H', 'Content-Type: application/json',
      '-d', JSON.stringify({ content: msg }),
      url,
    ], { timeout: 10000, stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (err) {
    process.stderr.write(`ear-notify skipped: ${err.message}\n`);
  }
}

// ─── comad integration: second-opinion gate (Phase 1.3) ──────────────────────
// 각 done task 의 cwd 에서 `.second-opinion.md` 존재 + frontmatter verdict 검증.
// 실행은 하지 않음 (사용자/Claude 가 별도 작성 — comad-second-opinion 스킬).
// verdict: APPROVED → passed, REQUEST_CHANGES/BLOCKS → failed, 파일 없음 → missing.

function parseSecondOpinionVerdict(filePath) {
  const txt = fs.readFileSync(filePath, 'utf8');
  // frontmatter 영역 (--- ... ---) 추출
  const fmMatch = txt.match(/^---\s*\n([\s\S]*?)\n---/);
  const block = fmMatch ? fmMatch[1] : txt.split('\n').slice(0, 30).join('\n');
  const m = block.match(/^verdict\s*:\s*([A-Z_]+)/m);
  return m ? m[1].trim() : null;
}

function runSecondOpinionCheck(taskCwd) {
  const opinionPath = path.join(taskCwd, '.second-opinion.md');
  if (!fs.existsSync(opinionPath)) {
    return { status: 'missing', opinionPath, reason: '.second-opinion.md not found in task cwd' };
  }
  let verdict;
  try { verdict = parseSecondOpinionVerdict(opinionPath); } catch (err) {
    return { status: 'failed', opinionPath, reason: `read error: ${err.message}` };
  }
  if (!verdict) {
    return { status: 'failed', opinionPath, reason: 'verdict field not found in frontmatter' };
  }
  if (verdict === 'APPROVED') {
    return { status: 'passed', opinionPath, verdict };
  }
  if (verdict === 'REQUEST_CHANGES' || verdict === 'BLOCKS') {
    return { status: 'failed', opinionPath, verdict, reason: `verdict=${verdict}` };
  }
  return { status: 'failed', opinionPath, verdict, reason: `unknown verdict: ${verdict}` };
}

function cmdSecondOpinionGate(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('second-opinion-gate: job.json not found');

  const membersRoot = path.join(resolvedJobDir, 'members');
  const results = {};

  for (const task of (jobMeta.tasks || [])) {
    const safeName = safeFileName(task.name);
    const memberDir = path.join(membersRoot, safeName);
    const status = readJsonIfExists(path.join(memberDir, 'status.json'));

    if (!status || status.state !== 'done') {
      results[task.name] = { status: 'skipped', reason: `task state: ${status ? status.state : 'unknown'}` };
      continue;
    }

    const taskCwd = task.cwd || jobMeta.cwd || process.cwd();
    const result = runSecondOpinionCheck(taskCwd);
    results[task.name] = result;

    atomicWriteJson(path.join(memberDir, 'second-opinion.json'), result);
  }

  if (options.json) {
    process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
  } else {
    for (const [taskName, r] of Object.entries(results)) {
      const icon = r.status === 'passed' ? '✅' : r.status === 'skipped' ? '⏭️' : (r.status === 'missing' ? '⚠️' : '❌');
      process.stdout.write(`${icon} ${taskName}: ${r.status}`);
      if (r.verdict) process.stdout.write(` (${r.verdict})`);
      if (r.reason) process.stdout.write(` — ${r.reason}`);
      process.stdout.write('\n');
    }
  }

  const blocking = Object.values(results).filter((r) => r.status === 'failed' || r.status === 'missing').length;
  if (blocking > 0 && options.strict !== false) {
    process.exitCode = 1;
  }
}

// ─── comad integration: qa-evidence gate (Phase 1.2) ─────────────────────────
// 각 done task 의 cwd 에서 `.qa-evidence.json` + verdict=PASS 검증.
// comad-qa-evidence/bin/validate-qa-evidence.py 있으면 사용 (exit 0=PASS,
// 1=valid but not PASS, 2=schema violation). 없으면 raw json 파싱 fallback.

const QA_EVIDENCE_VALIDATOR = path.join(
  process.env.HOME || require('os').homedir(),
  '.claude/skills/comad-qa-evidence/bin/validate-qa-evidence.py',
);

function runQaEvidenceCheck(taskCwd) {
  const evidencePath = path.join(taskCwd, '.qa-evidence.json');
  if (!fs.existsSync(evidencePath)) {
    return { status: 'missing', evidencePath, reason: '.qa-evidence.json not found in task cwd' };
  }
  if (fs.existsSync(QA_EVIDENCE_VALIDATOR)) {
    try {
      const { execFileSync } = require('child_process');
      execFileSync('python3', [QA_EVIDENCE_VALIDATOR, evidencePath], {
        timeout: 15000,
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      return { status: 'passed', evidencePath, verdict: 'PASS', validator: 'comad-qa-evidence' };
    } catch (err) {
      const exitCode = err.status != null ? err.status : null;
      const stderr = err.stderr ? err.stderr.toString().trim().slice(0, 500) : '';
      let reason;
      if (exitCode === 1) reason = `verdict != PASS: ${stderr || 'see validator output'}`;
      else if (exitCode === 2) reason = `schema violation: ${stderr || 'see validator output'}`;
      else reason = `validator exit ${exitCode}: ${stderr || err.message}`;
      return { status: 'failed', evidencePath, exitCode, reason, validator: 'comad-qa-evidence' };
    }
  }
  try {
    const data = JSON.parse(fs.readFileSync(evidencePath, 'utf8'));
    if (data.verdict === 'PASS') {
      return { status: 'passed', evidencePath, verdict: 'PASS', validator: 'jq-fallback' };
    }
    return { status: 'failed', evidencePath, verdict: data.verdict || 'unknown', reason: `verdict != PASS (got ${data.verdict})`, validator: 'jq-fallback' };
  } catch (err) {
    return { status: 'failed', evidencePath, reason: `json parse error: ${err.message}`, validator: 'jq-fallback' };
  }
}

function cmdQaGate(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('qa-gate: job.json not found');

  const membersRoot = path.join(resolvedJobDir, 'members');
  const results = {};

  for (const task of (jobMeta.tasks || [])) {
    const safeName = safeFileName(task.name);
    const memberDir = path.join(membersRoot, safeName);
    const status = readJsonIfExists(path.join(memberDir, 'status.json'));

    if (!status || status.state !== 'done') {
      results[task.name] = { status: 'skipped', reason: `task state: ${status ? status.state : 'unknown'}` };
      continue;
    }

    const taskCwd = task.cwd || jobMeta.cwd || process.cwd();
    const result = runQaEvidenceCheck(taskCwd);
    results[task.name] = result;

    atomicWriteJson(path.join(memberDir, 'qa-evidence.json'), result);
  }

  if (options.json) {
    process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
  } else {
    for (const [taskName, r] of Object.entries(results)) {
      const icon = r.status === 'passed' ? '✅' : r.status === 'skipped' ? '⏭️' : (r.status === 'missing' ? '⚠️' : '❌');
      process.stdout.write(`${icon} ${taskName}: ${r.status}`);
      if (r.reason) process.stdout.write(` — ${r.reason}`);
      if (r.validator) process.stdout.write(` (${r.validator})`);
      process.stdout.write('\n');
    }
  }

  const blocking = Object.values(results).filter((r) => r.status === 'failed' || r.status === 'missing').length;
  if (blocking > 0 && options.strict !== false) {
    process.exitCode = 1;
  }
}

// ─── comad integration: handoff (Phase 1.1) ──────────────────────────────────
// `.comad/sessions/<ts>-parallel-<jobid8>.md` 에 7섹션 핸드오프 doc 생성.
// feedback_handoff_template.md 의 템플릿을 강제하고, parallel job 데이터로
// Summary / Relevant Files / Open Work 자동 채움. 나머지 3 섹션은 stub.

function findGitRoot(start) {
  let dir = path.resolve(start);
  while (true) {
    if (fs.existsSync(path.join(dir, '.git'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function resolveSessionDir(explicitOut) {
  if (explicitOut) {
    const resolved = path.resolve(explicitOut);
    fs.mkdirSync(resolved, { recursive: true });
    return resolved;
  }
  const envDir = process.env.COMAD_SESSION_DIR;
  if (envDir) {
    const resolved = path.resolve(envDir);
    fs.mkdirSync(resolved, { recursive: true });
    return resolved;
  }
  const gitRoot = findGitRoot(process.cwd());
  if (gitRoot) {
    const local = path.join(gitRoot, '.comad', 'sessions');
    fs.mkdirSync(local, { recursive: true });
    return local;
  }
  const home = process.env.HOME || require('os').homedir();
  const fallback = path.join(home, '.claude', '.comad', 'sessions');
  fs.mkdirSync(fallback, { recursive: true });
  return fallback;
}

function timestampFilename() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}

function buildHandoffDoc(jobMeta, members, jobDir) {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const ts = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const jobId = jobMeta && jobMeta.id ? jobMeta.id : path.basename(jobDir);
  const tasks = (jobMeta && jobMeta.tasks) || [];
  const counts = { done: 0, failed: 0, timeout: 0, skipped: 0, other: 0 };
  for (const m of members) {
    if (counts[m.state] != null) counts[m.state]++;
    else counts.other++;
  }
  const gateCounts = { passed: 0, failed: 0, skipped: 0 };
  for (const m of members) {
    if (m.gates && gateCounts[m.gates.status] != null) gateCounts[m.gates.status]++;
  }
  const qaCounts = { passed: 0, failed: 0, missing: 0, skipped: 0 };
  let qaPresent = false;
  for (const m of members) {
    if (m.qaEvidence) {
      qaPresent = true;
      if (qaCounts[m.qaEvidence.status] != null) qaCounts[m.qaEvidence.status]++;
    }
  }
  const soCounts = { passed: 0, failed: 0, missing: 0, skipped: 0 };
  let soPresent = false;
  for (const m of members) {
    if (m.secondOpinion) {
      soPresent = true;
      if (soCounts[m.secondOpinion.status] != null) soCounts[m.secondOpinion.status]++;
    }
  }

  const filesByTask = members
    .filter((m) => m.report && Array.isArray(m.report.files_created) && m.report.files_created.length > 0)
    .map((m) => ({ name: m.member, files: m.report.files_created }));

  const failedOrPending = members.filter((m) =>
    m.state !== 'done' ||
    (m.gates && m.gates.status === 'failed') ||
    (m.qaEvidence && (m.qaEvidence.status === 'failed' || m.qaEvidence.status === 'missing')) ||
    (m.secondOpinion && (m.secondOpinion.status === 'failed' || m.secondOpinion.status === 'missing')) ||
    (m.destroyCheck && m.destroyCheck.status === 'failed'),
  );

  const lines = [];
  lines.push(`# Session Handoff — Parallel Job ${jobId} @ ${ts}`);
  lines.push('');
  lines.push('## Summary');
  lines.push('');
  lines.push(`Parallel codex job \`${jobId}\` (${tasks.length} task${tasks.length === 1 ? '' : 's'}). ` +
    `States: done=${counts.done}, failed=${counts.failed}, timeout=${counts.timeout}, skipped=${counts.skipped}` +
    (counts.other ? `, other=${counts.other}` : '') + '. ' +
    `Gates: passed=${gateCounts.passed}, failed=${gateCounts.failed}, skipped=${gateCounts.skipped}.`);
  if (qaPresent) {
    lines.push(`QA evidence: passed=${qaCounts.passed}, failed=${qaCounts.failed}, missing=${qaCounts.missing}, skipped=${qaCounts.skipped}.`);
  }
  if (soPresent) {
    lines.push(`Second opinion: passed=${soCounts.passed}, failed=${soCounts.failed}, missing=${soCounts.missing}, skipped=${soCounts.skipped}.`);
  }
  lines.push('');
  lines.push('## Key Decisions');
  lines.push('');
  lines.push('<!-- TODO(claude): parallel job 동안 내려진 설계 결정 + 근거. commit hash 가 결정 근거면 명시. -->');
  lines.push('');
  lines.push('## Traps to Avoid');
  lines.push('');
  lines.push('<!-- TODO(claude): 실패한 task 의 원인, 재시도 시 빠지지 않을 함정. 가장 가치 있는 섹션. -->');
  if (failedOrPending.length > 0) {
    lines.push('');
    lines.push('Auto-detected from failed tasks:');
    for (const m of failedOrPending) {
      const parts = [`state=${m.state}`];
      if (m.gates) parts.push(`gates=${m.gates.status}`);
      if (m.qaEvidence) parts.push(`qa=${m.qaEvidence.status}`);
      if (m.secondOpinion) parts.push(`second-opinion=${m.secondOpinion.status}${m.secondOpinion.verdict ? '/' + m.secondOpinion.verdict : ''}`);
      if (m.destroyCheck) parts.push(`destroy=${m.destroyCheck.status}`);
      const failedGate = m.gates && m.gates.gates && m.gates.gates.find((g) => !g.passed);
      const reason = m.message || (m.destroyCheck && m.destroyCheck.reason) || (m.qaEvidence && m.qaEvidence.reason) || (m.secondOpinion && m.secondOpinion.reason) || (failedGate && failedGate.error) || 'see Open Work';
      lines.push(`- \`${m.member}\` — ${parts.join(', ')}: ${reason}`);
    }
  }
  lines.push('');
  lines.push('## Working Agreements');
  lines.push('');
  lines.push('<!-- TODO(claude): 사용자 선호 (예: "review before committing"). -->');
  lines.push('');
  lines.push('## Relevant Files');
  lines.push('');
  if (filesByTask.length === 0) {
    lines.push('<!-- TODO(claude): `path/to/file.ts:L10-L45 — 왜 중요한지` 형식. 라인 번호 강제. -->');
  } else {
    for (const t of filesByTask) {
      lines.push(`- **${t.name}**`);
      for (const f of t.files) {
        lines.push(`  - \`${f}\` <!-- TODO(claude): 라인 범위 + 왜 중요한지 추가 -->`);
      }
    }
  }
  lines.push('');
  lines.push('## Open Work');
  lines.push('');
  if (failedOrPending.length === 0) {
    const verifiedParts = [];
    if (qaPresent) verifiedParts.push('qa-evidence');
    if (soPresent) verifiedParts.push('second-opinion');
    const verified = verifiedParts.length > 0 ? ` with ${verifiedParts.join(' + ')} verified` : '';
    lines.push(`- All parallel tasks completed successfully${verified}. Integration review pending.`);
  } else {
    for (const m of failedOrPending) {
      const issues = [];
      if (m.state !== 'done') issues.push(`state=${m.state}`);
      if (m.gates && m.gates.status === 'failed') issues.push(`gates failed (${m.gates.passedCount}/${m.gates.totalCount})`);
      if (m.qaEvidence && m.qaEvidence.status === 'failed') issues.push(`qa-evidence failed: ${m.qaEvidence.reason || 'verdict != PASS'}`);
      if (m.qaEvidence && m.qaEvidence.status === 'missing') issues.push('qa-evidence missing (.qa-evidence.json not produced by Codex)');
      if (m.secondOpinion && m.secondOpinion.status === 'failed') issues.push(`second-opinion ${m.secondOpinion.verdict || 'failed'}: ${m.secondOpinion.reason || 'see .second-opinion.md'}`);
      if (m.secondOpinion && m.secondOpinion.status === 'missing') issues.push('second-opinion missing (.second-opinion.md not produced — run /comad-second-opinion)');
      if (m.destroyCheck && m.destroyCheck.status === 'failed') {
        const patterns = (m.destroyCheck.hits || []).map((h) => h.pattern).join(', ');
        issues.push(`destroy-check failed: ${patterns}`);
      }
      lines.push(`- [parallel] \`${m.member}\` — ${issues.join('; ')}; depends on root-cause review before re-delegation.`);
    }
  }
  lines.push('');
  lines.push('## Prompt for New Chat');
  lines.push('');
  lines.push('```');
  lines.push(`이전 세션에서 parallel job ${jobId} 가 실행되었다 (${tasks.length} task).`);
  lines.push(`Job dir: ${jobDir}`);
  lines.push(`결과 요약은 위 Summary 섹션 참고. failed/pending task 가 있으면 Open Work 우선 검토.`);
  lines.push('');
  lines.push('이 문서의 주장은 hypothesis. Relevant Files 를 Read 도구로 직접 읽고');
  lines.push('이 문서의 주장을 코드와 대조해 차이가 있으면 보고하고, 내 지시를 기다려라.');
  lines.push('```');
  lines.push('');
  return lines.join('\n');
}

function cmdHandoff(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  const membersRoot = path.join(resolvedJobDir, 'members');
  const members = [];
  if (fs.existsSync(membersRoot)) {
    for (const entry of fs.readdirSync(membersRoot)) {
      const status = readJsonIfExists(path.join(membersRoot, entry, 'status.json'));
      if (!status) continue;
      const gatesResult = readJsonIfExists(path.join(membersRoot, entry, 'gates.json'));
      const report = readJsonIfExists(path.join(membersRoot, entry, 'report.json'));
      const qaEvidence = readJsonIfExists(path.join(membersRoot, entry, 'qa-evidence.json'));
      const secondOpinion = readJsonIfExists(path.join(membersRoot, entry, 'second-opinion.json'));
      const destroyCheck = readJsonIfExists(path.join(membersRoot, entry, 'destroy-check.json'));
      members.push({ safeName: entry, ...status, gates: gatesResult, report, qaEvidence, secondOpinion, destroyCheck });
    }
  }
  members.sort((a, b) => String(a.member).localeCompare(String(b.member)));

  const sessionDir = resolveSessionDir(options.out);
  const jobIdShort = (jobMeta && jobMeta.id ? jobMeta.id : path.basename(resolvedJobDir)).slice(0, 8);
  const filename = `${timestampFilename()}-parallel-${jobIdShort}.md`;
  const outPath = path.join(sessionDir, filename);
  const doc = buildHandoffDoc(jobMeta, members, resolvedJobDir);
  fs.writeFileSync(outPath, doc, 'utf8');

  if (options.json) {
    process.stdout.write(`${JSON.stringify({ handoff: outPath, jobDir: resolvedJobDir, members: members.length }, null, 2)}\n`);
  } else {
    process.stdout.write(`📝 Handoff written: ${outPath}\n`);
    process.stdout.write(`   ${members.length} member(s) recorded. Edit TODO(claude) markers to enrich.\n`);
  }
}

function cmdGates(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('gates: job.json not found');

  const membersRoot = path.join(resolvedJobDir, 'members');
  const results = {};

  for (const task of (jobMeta.tasks || [])) {
    const safeName = safeFileName(task.name);
    const memberDir = path.join(membersRoot, safeName);
    const gates = task.gates || [];

    if (gates.length === 0) {
      results[task.name] = { status: 'skipped', gates: [] };
      continue;
    }

    // Check if task completed successfully first
    const status = readJsonIfExists(path.join(memberDir, 'status.json'));
    if (!status || status.state !== 'done') {
      results[task.name] = {
        status: 'skipped',
        reason: `task state: ${status ? status.state : 'unknown'}`,
        gates: [],
      };
      continue;
    }

    // Determine CWD for gate execution
    const taskCwd = task.cwd || jobMeta.cwd || process.cwd();

    const gateResults = [];
    let allPassed = true;

    for (const gate of gates) {
      const startTime = Date.now();
      try {
        const { execSync } = require('child_process');
        const output = execSync(gate.command, {
          cwd: taskCwd,
          timeout: 30000,
          encoding: 'utf8',
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        gateResults.push({
          name: gate.name,
          command: gate.command,
          passed: true,
          output: output.trim().slice(0, 500),
          durationMs: Date.now() - startTime,
        });
      } catch (err) {
        allPassed = false;
        gateResults.push({
          name: gate.name,
          command: gate.command,
          passed: false,
          error: err.stderr ? err.stderr.trim().slice(0, 500) : (err.message || 'unknown error'),
          exitCode: err.status != null ? err.status : null,
          durationMs: Date.now() - startTime,
        });
      }
    }

    const gatePayload = {
      status: allPassed ? 'passed' : 'failed',
      passedCount: gateResults.filter(g => g.passed).length,
      totalCount: gateResults.length,
      gates: gateResults,
    };

    // Save gates.json per task
    atomicWriteJson(path.join(memberDir, 'gates.json'), gatePayload);
    results[task.name] = gatePayload;
  }

  if (options.json) {
    process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
  } else {
    for (const [taskName, result] of Object.entries(results)) {
      const icon = result.status === 'passed' ? '✅' : result.status === 'skipped' ? '⏭️' : '❌';
      process.stdout.write(`${icon} ${taskName}: ${result.status}`);
      if (result.passedCount != null) {
        process.stdout.write(` (${result.passedCount}/${result.totalCount})`);
      }
      if (result.reason) process.stdout.write(` — ${result.reason}`);
      process.stdout.write('\n');
      for (const g of (result.gates || [])) {
        const gIcon = g.passed ? '  ✓' : '  ✗';
        process.stdout.write(`${gIcon} ${g.name}`);
        if (!g.passed && g.error) process.stdout.write(` — ${g.error.split('\n')[0]}`);
        process.stdout.write('\n');
      }
    }
  }
}

function cmdStartRound(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('start-round: job.json not found');

  const roundNum = Number(options.round || options._[0]);
  if (!Number.isFinite(roundNum) || roundNum < 1) {
    exitWithError('start-round: --round N is required (N >= 1)');
  }

  const roundTasks = (jobMeta.tasks || []).filter(t => t.round === roundNum);
  if (roundTasks.length === 0) {
    exitWithError(`start-round: 라운드 ${roundNum}에 해당하는 태스크가 없습니다.`);
  }

  const membersRoot = path.join(resolvedJobDir, 'members');
  const promptPath = path.join(resolvedJobDir, 'prompt.txt');
  const basePrompt = fs.existsSync(promptPath) ? fs.readFileSync(promptPath, 'utf8') : '';

  // Collect previous round results as context
  let prevRoundContext = '';
  if (roundNum > 1) {
    const prevRoundTasks = (jobMeta.tasks || []).filter(t => t.round < roundNum);
    const contextParts = ['## 이전 라운드 결과\n'];
    for (const pt of prevRoundTasks) {
      const safeName = safeFileName(pt.name);
      const memberDir = path.join(membersRoot, safeName);
      const status = readJsonIfExists(path.join(memberDir, 'status.json'));
      const report = readJsonIfExists(path.join(memberDir, 'report.json'));
      const output = fs.existsSync(path.join(memberDir, 'output.txt'))
        ? fs.readFileSync(path.join(memberDir, 'output.txt'), 'utf8')
        : '';

      contextParts.push(`### ${pt.name} (라운드 ${pt.round})`);
      contextParts.push(`상태: ${status ? status.state : 'unknown'}`);
      if (report) {
        contextParts.push(`결과: ${report.status || 'unknown'}`);
        if (report.summary) contextParts.push(`요약: ${report.summary}`);
        if (Array.isArray(report.files_created) && report.files_created.length) {
          contextParts.push(`생성 파일: ${report.files_created.join(', ')}`);
        }
      } else if (output) {
        // Truncate output to avoid excessive context
        const truncated = output.length > 2000 ? output.slice(0, 2000) + '\n...(truncated)' : output;
        contextParts.push(`출력:\n${truncated}`);
      }
      contextParts.push('');
    }
    contextParts.push('---\n');
    prevRoundContext = contextParts.join('\n');
  }

  // Update job.json with current round
  jobMeta.currentRound = roundNum;
  atomicWriteJson(path.join(resolvedJobDir, 'job.json'), jobMeta);

  // Write round-specific prompt
  const roundPromptPath = path.join(resolvedJobDir, `prompt-round${roundNum}.txt`);
  const roundPrompt = prevRoundContext + basePrompt;
  fs.writeFileSync(roundPromptPath, roundPrompt, 'utf8');

  // Reset wait cursor so wait loop works for new round
  const cursorFile = path.join(resolvedJobDir, '.wait_cursor');
  try { fs.unlinkSync(cursorFile); } catch { /* ignore */ }

  // Spawn workers for this round
  const taskCwdFallback = jobMeta.cwd || process.cwd();
  const timeoutSec = jobMeta.settings ? jobMeta.settings.timeoutSec : DEFAULT_TIMEOUT_SEC;

  for (const task of roundTasks) {
    const name = String(task.name);
    const safeName = safeFileName(name);
    const memberDir = path.join(membersRoot, safeName);
    ensureDir(memberDir);
    const command = String(task.command || DEFAULT_CODEX_COMMAND);

    // Reset status for re-run
    atomicWriteJson(path.join(memberDir, 'status.json'), {
      member: name, state: 'queued',
      queuedAt: new Date().toISOString(), command,
      round: roundNum,
    });

    const taskCwd = task.cwd || taskCwdFallback;

    const workerArgs = [
      WORKER_PATH,
      '--job-dir', resolvedJobDir,
      '--member', name,
      '--safe-member', safeName,
      '--command', command,
      '--cwd', taskCwd,
    ];
    if (timeoutSec && Number.isFinite(timeoutSec) && timeoutSec > 0) {
      workerArgs.push('--timeout', String(timeoutSec));
    }

    const child = spawn(process.execPath, workerArgs, {
      detached: true,
      stdio: 'ignore',
      env: process.env,
      cwd: taskCwd,
    });
    child.unref();
  }

  process.stdout.write(`${resolvedJobDir}\n`);
}

function cmdRedelegate(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('redelegate: job.json not found');

  const taskName = options.task || options._[0];
  if (!taskName) exitWithError('redelegate: --task <name> is required');

  const correction = options.correction || options._[1] || '';

  const taskConfig = (jobMeta.tasks || []).find(t => t.name === taskName);
  if (!taskConfig) exitWithError(`redelegate: task "${taskName}" not found in job`);

  const safeName = safeFileName(taskName);
  const membersRoot = path.join(resolvedJobDir, 'members');
  const memberDir = path.join(membersRoot, safeName);

  if (!fs.existsSync(memberDir)) {
    exitWithError(`redelegate: member directory not found for "${taskName}"`);
  }

  // Check retry count
  const maxRetries = (jobMeta.settings && jobMeta.settings.maxRetries != null)
    ? Number(jobMeta.settings.maxRetries)
    : 2;
  const retryCountPath = path.join(memberDir, 'retry_count');
  let retryCount = 0;
  try { retryCount = Number(fs.readFileSync(retryCountPath, 'utf8').trim()) || 0; } catch { /* ignore */ }

  if (retryCount >= maxRetries) {
    process.stderr.write(`redelegate: "${taskName}" has reached max retries (${maxRetries})\n`);
    process.stdout.write(JSON.stringify({
      task: taskName,
      status: 'max_retries_reached',
      retryCount,
      maxRetries
    }, null, 2) + '\n');
    return;
  }

  // Read previous attempt's output, error, gates for context
  const prevOutput = fs.existsSync(path.join(memberDir, 'output.txt'))
    ? fs.readFileSync(path.join(memberDir, 'output.txt'), 'utf8')
    : '';
  const prevError = fs.existsSync(path.join(memberDir, 'error.txt'))
    ? fs.readFileSync(path.join(memberDir, 'error.txt'), 'utf8')
    : '';
  const prevGates = readJsonIfExists(path.join(memberDir, 'gates.json'));
  const prevReport = readJsonIfExists(path.join(memberDir, 'report.json'));
  const prevStatus = readJsonIfExists(path.join(memberDir, 'status.json'));

  // Build re-delegation context
  const redelegationParts = [
    '# 재위임 (Re-delegation)',
    '',
    '## 이전 시도 결과',
    `- 상태: ${prevStatus ? prevStatus.state : 'unknown'}`,
    `- 시도 횟수: ${retryCount + 1}/${maxRetries + 1}`,
    '',
  ];

  if (prevReport) {
    redelegationParts.push('### 이전 보고서');
    redelegationParts.push(`상태: ${prevReport.status || 'unknown'}`);
    if (prevReport.summary) redelegationParts.push(`요약: ${prevReport.summary}`);
    if (Array.isArray(prevReport.files_created)) {
      redelegationParts.push(`생성 파일: ${prevReport.files_created.join(', ')}`);
    }
    redelegationParts.push('');
  }

  if (prevGates) {
    redelegationParts.push('### 게이트 결과');
    redelegationParts.push(`전체: ${prevGates.status} (${prevGates.passedCount}/${prevGates.totalCount})`);
    for (const g of (prevGates.gates || [])) {
      const icon = g.passed ? '✓' : '✗';
      redelegationParts.push(`  ${icon} ${g.name}${g.error ? ': ' + g.error.split('\n')[0] : ''}`);
    }
    redelegationParts.push('');
  }

  if (prevOutput) {
    const truncOutput = prevOutput.length > 1500
      ? prevOutput.slice(0, 1500) + '\n...(truncated)'
      : prevOutput;
    redelegationParts.push('### 이전 출력 (참고)');
    redelegationParts.push(truncOutput);
    redelegationParts.push('');
  }

  if (correction) {
    redelegationParts.push('## 수정 지시사항');
    redelegationParts.push(correction);
    redelegationParts.push('');
  }

  redelegationParts.push('## 필수 규칙');
  redelegationParts.push('- 위 게이트 실패 항목을 반드시 해결하세요');
  redelegationParts.push('- 이전에 생성한 파일이 있다면 수정/덮어쓰기 가능합니다');
  redelegationParts.push('- 새로운 파일을 추가하지 마세요 (지시된 파일만 수정)');
  redelegationParts.push('');
  redelegationParts.push('---');
  redelegationParts.push('');

  // Write re-delegation prompt (prepend to original prompt)
  const originalPromptPath = path.join(resolvedJobDir, 'prompt.txt');
  const originalPrompt = fs.existsSync(originalPromptPath)
    ? fs.readFileSync(originalPromptPath, 'utf8')
    : '';

  const redelegationPrompt = redelegationParts.join('\n') + originalPrompt;
  const redelegationPromptPath = path.join(memberDir, 'redelegate-prompt.txt');
  fs.writeFileSync(redelegationPromptPath, redelegationPrompt, 'utf8');

  // Increment retry count
  fs.writeFileSync(retryCountPath, String(retryCount + 1), 'utf8');

  // Archive previous attempt
  const archiveDir = path.join(memberDir, `attempt-${retryCount}`);
  ensureDir(archiveDir);
  for (const f of ['output.txt', 'error.txt', 'status.json', 'gates.json', 'report.json']) {
    const src = path.join(memberDir, f);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, path.join(archiveDir, f));
    }
  }

  // Reset status
  const command = String(taskConfig.command || DEFAULT_CODEX_COMMAND);
  atomicWriteJson(path.join(memberDir, 'status.json'), {
    member: taskName, state: 'queued',
    queuedAt: new Date().toISOString(), command,
    retry: retryCount + 1,
  });

  // Delete wait cursor to reset wait loop
  const cursorFile = path.join(resolvedJobDir, '.wait_cursor');
  try { fs.unlinkSync(cursorFile); } catch { /* ignore */ }

  // Spawn worker
  const taskCwd = taskConfig.cwd || jobMeta.cwd || process.cwd();
  const timeoutSec = jobMeta.settings ? jobMeta.settings.timeoutSec : DEFAULT_TIMEOUT_SEC;

  const workerArgs = [
    WORKER_PATH,
    '--job-dir', resolvedJobDir,
    '--member', taskName,
    '--safe-member', safeName,
    '--command', command,
    '--cwd', taskCwd,
  ];
  if (timeoutSec && Number.isFinite(timeoutSec) && timeoutSec > 0) {
    workerArgs.push('--timeout', String(timeoutSec));
  }

  const child = spawn(process.execPath, workerArgs, {
    detached: true,
    stdio: 'ignore',
    env: process.env,
    cwd: taskCwd,
  });
  child.unref();

  process.stderr.write(`redelegate: "${taskName}" retry ${retryCount + 1}/${maxRetries} started\n`);
  process.stdout.write(JSON.stringify({
    task: taskName,
    status: 'redelegated',
    retry: retryCount + 1,
    maxRetries,
    jobDir: resolvedJobDir,
  }, null, 2) + '\n');
}

function cmdAutofix(options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('autofix: job.json not found');

  const maxRetries = (jobMeta.settings && jobMeta.settings.maxRetries != null)
    ? Number(jobMeta.settings.maxRetries)
    : 2;

  const membersRoot = path.join(resolvedJobDir, 'members');
  const failedTasks = [];

  for (const task of (jobMeta.tasks || [])) {
    const safeName = safeFileName(task.name);
    const memberDir = path.join(membersRoot, safeName);
    const status = readJsonIfExists(path.join(memberDir, 'status.json'));
    const gates = readJsonIfExists(path.join(memberDir, 'gates.json'));

    // Check retry count
    const retryCountPath = path.join(memberDir, 'retry_count');
    let retryCount = 0;
    try { retryCount = Number(fs.readFileSync(retryCountPath, 'utf8').trim()) || 0; } catch { /* ignore */ }

    if (retryCount >= maxRetries) continue;

    // Case 1: Task errored out
    if (status && (status.state === 'error' || status.state === 'timed_out')) {
      failedTasks.push({
        name: task.name,
        reason: `task ${status.state}: ${status.message || 'unknown'}`,
        correction: `이전 시도가 ${status.state} 상태로 실패했습니다. ${status.message || ''}. 다시 시도하세요.`,
      });
      continue;
    }

    // Case 2: Gates failed
    if (gates && gates.status === 'failed') {
      const failedGates = (gates.gates || []).filter(g => !g.passed);
      const correction = failedGates.map(g =>
        `게이트 "${g.name}" 실패: ${g.error || 'unknown error'}`
      ).join('\n');
      failedTasks.push({
        name: task.name,
        reason: `gates failed (${gates.passedCount}/${gates.totalCount})`,
        correction: `다음 게이트를 통과하도록 수정하세요:\n${correction}`,
      });
    }
  }

  if (failedTasks.length === 0) {
    process.stderr.write('autofix: 수정이 필요한 태스크가 없습니다.\n');
    process.stdout.write(JSON.stringify({ status: 'no_fixes_needed', tasks: [] }, null, 2) + '\n');
    return;
  }

  process.stderr.write(`autofix: ${failedTasks.length}개 태스크 재위임 시작\n`);

  // Re-delegate each failed task
  for (const ft of failedTasks) {
    process.stderr.write(`autofix: "${ft.name}" — ${ft.reason}\n`);
    cmdRedelegate(
      { task: ft.name, correction: ft.correction, _: [] },
      resolvedJobDir
    );
  }

  process.stdout.write(JSON.stringify({
    status: 'autofix_started',
    tasks: failedTasks.map(ft => ({ name: ft.name, reason: ft.reason })),
  }, null, 2) + '\n');
}

function cmdStop(_options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  const membersRoot = path.join(resolvedJobDir, 'members');
  if (!fs.existsSync(membersRoot)) exitWithError(`members 폴더 없음: ${membersRoot}`);

  let stoppedAny = false;
  for (const entry of fs.readdirSync(membersRoot)) {
    const statusPath = path.join(membersRoot, entry, 'status.json');
    const status = readJsonIfExists(statusPath);
    if (!status || status.state !== 'running' || !status.pid) continue;
    killProcess(Number(status.pid)); stoppedAny = true;
  }
  process.stdout.write(stoppedAny ? 'stop: 실행 중인 Codex에 SIGTERM 전송\n' : 'stop: 실행 중인 태스크 없음\n');
}

function cmdRunAll(options, prompt) {
  // Start round 1
  cmdStart(options, prompt);

  // Re-read the job dir from .last-job since cmdStart wrote to stdout
  const jobsDir = options['jobs-dir'] || process.env.PUMASI_JOBS_DIR || path.join(SKILL_DIR, '.jobs');
  const lastJobFile = path.join(jobsDir, '.last-job');
  const jobDir = fs.readFileSync(lastJobFile, 'utf8').trim();
  const resolvedJobDir = path.resolve(jobDir);

  const jobMeta = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
  if (!jobMeta) exitWithError('run-all: job.json not found after start');
  const maxRound = jobMeta.maxRound || 1;

  let shuttingDown = false;

  const cleanup = () => {
    if (shuttingDown) return;
    shuttingDown = true;
    try { cmdStop({}, resolvedJobDir); } catch { /* ignore */ }
    try { cmdClean({}, resolvedJobDir); } catch { /* ignore */ }
    process.exit(130);
  };

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);

  for (let round = 1; round <= maxRound; round++) {
    if (shuttingDown) break;

    if (round > 1) {
      cmdStartRound({ round: String(round), _: [] }, resolvedJobDir);
    }

    // Wait for current round to complete
    let overallState = '';
    while (overallState !== 'done') {
      if (shuttingDown) break;
      const payload = computeStatusPayload(resolvedJobDir);
      overallState = payload.overallState;
      if (overallState !== 'done') {
        sleepMs(500);
      }
    }

    if (shuttingDown) break;

    // Run gates
    try { cmdGates({ _: [] }, resolvedJobDir); } catch { /* ignore */ }

    // Check for gate failures
    const jobMetaRefresh = readJsonIfExists(path.join(resolvedJobDir, 'job.json'));
    const membersRoot = path.join(resolvedJobDir, 'members');
    let hasGateFailure = false;
    for (const task of (jobMetaRefresh.tasks || [])) {
      const safeName = safeFileName(task.name);
      const gatesPath = path.join(membersRoot, safeName, 'gates.json');
      const gates = readJsonIfExists(gatesPath);
      if (gates && gates.status === 'failed') { hasGateFailure = true; break; }
    }

    if (hasGateFailure) {
      process.stderr.write('run-all: gate failures detected, running autofix...\n');
      try { cmdAutofix({ _: [] }, resolvedJobDir); } catch { /* ignore */ }

      // Wait for autofix tasks to complete
      overallState = '';
      while (overallState !== 'done') {
        if (shuttingDown) break;
        const payload = computeStatusPayload(resolvedJobDir);
        overallState = payload.overallState;
        if (overallState !== 'done') {
          sleepMs(500);
        }
      }

      // Re-run gates after autofix
      if (!shuttingDown) {
        try { cmdGates({ _: [] }, resolvedJobDir); } catch { /* ignore */ }
      }
    }
  }

  process.removeListener('SIGINT', cleanup);
  process.removeListener('SIGTERM', cleanup);

  if (!shuttingDown) {
    cmdResults({}, resolvedJobDir);
    if (process.env.COMAD_QA_EVIDENCE === '1') {
      try { cmdQaGate({ strict: false }, resolvedJobDir); } catch (err) {
        process.stderr.write(`qa-gate skipped: ${err.message}\n`);
      }
    }
    if (process.env.COMAD_SECOND_OPINION === '1') {
      try { cmdSecondOpinionGate({ strict: false }, resolvedJobDir); } catch (err) {
        process.stderr.write(`second-opinion-gate skipped: ${err.message}\n`);
      }
    }
    if (process.env.COMAD_DESTROY_CHECK === '1') {
      try { cmdDestroyCheck({ strict: false }, resolvedJobDir); } catch (err) {
        process.stderr.write(`destroy-check skipped: ${err.message}\n`);
      }
    }
    if (process.env.COMAD_AUTO_HANDOFF !== '0') {
      try { cmdHandoff({}, resolvedJobDir); } catch (err) {
        process.stderr.write(`handoff skipped: ${err.message}\n`);
      }
    }
    if (process.env.COMAD_EAR_NOTIFY === '1') {
      try { cmdEarNotify(resolvedJobDir); } catch (err) {
        process.stderr.write(`ear-notify skipped: ${err.message}\n`);
      }
    }
    cmdClean({}, resolvedJobDir);
  }
}

function cmdClean(_options, jobDir) {
  const resolvedJobDir = path.resolve(jobDir);
  fs.rmSync(resolvedJobDir, { recursive: true, force: true });
  process.stdout.write(`cleaned: ${resolvedJobDir}\n`);
}

function main() {
  const options = parseArgs(process.argv);
  const [command, ...rest] = options._;

  if (!command || options.help || options.h) { printHelp(); return; }

  function resolveJobDir(arg) {
    if (arg) return arg;
    const jobsDir = options['jobs-dir'] || process.env.PUMASI_JOBS_DIR || path.join(SKILL_DIR, '.jobs');
    const lastJobFile = path.join(jobsDir, '.last-job');
    if (fs.existsSync(lastJobFile)) {
      const saved = fs.readFileSync(lastJobFile, 'utf8').trim();
      if (saved) return saved;
    }
    return null;
  }

  if (command === 'run-all') {
    const prompt = rest.join(' ').trim();
    if (!prompt) exitWithError('run-all: 프로젝트 컨텍스트를 입력하세요');
    cmdRunAll(options, prompt);
    return;
  }
  if (command === 'start') {
    const prompt = rest.join(' ').trim();
    if (!prompt) exitWithError('start: 프로젝트 컨텍스트를 입력하세요');
    cmdStart(options, prompt);
    return;
  }
  if (command === 'start-round') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('start-round: jobDir 없음');
    cmdStartRound(options, jobDir);
    return;
  }
  if (command === 'status') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('status: jobDir 없음');
    cmdStatus(options, jobDir);
    return;
  }
  if (command === 'wait') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('wait: jobDir 없음');
    cmdWait(options, jobDir);
    return;
  }
  if (command === 'results') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('results: jobDir 없음');
    cmdResults(options, jobDir);
    return;
  }
  if (command === 'handoff') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('handoff: jobDir 없음');
    cmdHandoff(options, jobDir);
    return;
  }
  if (command === 'qa-gate') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('qa-gate: jobDir 없음');
    cmdQaGate(options, jobDir);
    return;
  }
  if (command === 'second-opinion-gate') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('second-opinion-gate: jobDir 없음');
    cmdSecondOpinionGate(options, jobDir);
    return;
  }
  if (command === 'destroy-check') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('destroy-check: jobDir 없음');
    cmdDestroyCheck(options, jobDir);
    return;
  }
  if (command === 'gates') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('gates: jobDir 없음');
    cmdGates(options, jobDir);
    return;
  }
  if (command === 'redelegate') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('redelegate: jobDir 없음');
    cmdRedelegate(options, jobDir);
    return;
  }
  if (command === 'autofix') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('autofix: jobDir 없음');
    cmdAutofix(options, jobDir);
    return;
  }
  if (command === 'stop') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('stop: jobDir 없음');
    cmdStop(options, jobDir);
    return;
  }
  if (command === 'clean') {
    const jobDir = resolveJobDir(rest[0]);
    if (!jobDir) exitWithError('clean: jobDir 없음');
    cmdClean(options, jobDir);
    return;
  }

  exitWithError(`알 수 없는 명령: ${command}`);
}

if (require.main === module) {
  main();
}
