import type { EngineInterface, Register } from 'claude-code'

type Window = { label: string; percentUsed: number; resetsAt?: string }
type Options = { autostart?: boolean; python?: string }

// 挂件的数据目录：~/.claude/clawd-widget（额度、设置、日志、音效都在这，插件更新不会丢）。
async function dataDir($: EngineInterface): Promise<string> {
  const root = $.plugin.root
  const sep = root.includes('\\') ? '\\' : '/'
  const home = (await $.env.get('USERPROFILE').catch(() => undefined)) ?? (await $.env.get('HOME').catch(() => undefined))
  if (home) return [home.replace(/[\\/]+$/, ''), '.claude', 'clawd-widget'].join(sep)
  // 拿不到用户目录就按插件自己的位置推：它总在 ~/.claude 下面某处
  const parts = root.split(/[\\/]+/).filter(p => p !== '')
  const at = parts.lastIndexOf('.claude')
  const head = root.startsWith(sep) ? sep : ''
  return head + [...(at >= 0 ? parts.slice(0, at + 1) : parts.slice(0, -2)), 'clawd-widget'].join(sep)
}

// 桌面版的 get_usage 带每个模型单独的周额度（Fable）；拿不到（终端会话、工具没接上）就退回引擎自己的
// 5 小时 / 本周两个窗口，挂件至少能跟着动。
async function fetchWindows($: EngineInterface): Promise<{ plan?: string; windows: Window[] } | null> {
  const r = await $.tool.call({ tool: 'mcp__ccd_session_mgmt__get_usage' }).catch(() => null)
  if (r && r.deny === undefined && !r.isError) {
    const plan = JSON.parse(r.text ?? '{}').plan
    if (plan?.status === 'ok') return { plan: plan.plan, windows: plan.windows }
  }
  const u = await $.session.usage().catch(() => null)
  if (!u || u.rateLimits.length === 0) return null
  const name: Record<string, string> = { five_hour: '5-hour limit', seven_day: 'Weekly · all models' }
  return {
    windows: u.rateLimits.map(w => ({ label: name[w.kind] ?? w.kind, percentUsed: w.percentUsed, resetsAt: w.resetsAt })),
  }
}

// 每个 Code 会话都会加载这个插件；别的会话一分钟内刚写过就不重复拉。
async function refresh($: EngineInterface, force: boolean) {
  const sep = $.plugin.root.includes('\\') ? '\\' : '/'
  const file = (await dataDir($)) + sep + 'usage.json'
  if (!force) {
    const old = await $.fs.read(file).then(t => JSON.parse(t), () => null)
    if (old !== null && Date.now() - Date.parse(old.fetchedAt) < 60_000) return
  }
  const got = await fetchWindows($)
  if (got === null) return
  await $.fs.write(file, JSON.stringify({ fetchedAt: new Date().toISOString(), ...got }))
}

// 把挂件拉成独立进程：经 PowerShell 的 Start-Process，不继承这边的管道，也不随插件重载被杀。
// 挂件自己有互斥锁，已经开着就立刻退出，所以每次会话启动都拉一下没关系。只在 Windows 上做。
async function launchWidget($: EngineInterface, options: Options) {
  if (options.autostart === false || !$.plugin.root.includes('\\')) return
  const widget = `${$.plugin.root}\\widget`
  const py = (options.python ?? '').trim() || 'pythonw.exe'
  const ps = `Start-Process -FilePath '${py}' -ArgumentList '"${widget}\\widget.pyw"' -WorkingDirectory '${widget}'`
  const r = await $.process.run(
    ['powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', ps],
    { timeoutMs: 8_000 },
  )
  if (r.exitCode !== 0) {
    const why = r.stderr.trim().split('\n')[0] ?? ''
    $.ui.toast(`Clawd 酱没拉起来：${why}（挂件要 Python 3 + Pillow，python 路径可在插件设置里改）`)
  }
}

export const register: Register = (on, options) => {
  const opts = (options ?? {}) as Options

  on('session.start', async ($, e, next) => {
    await refresh($, true).catch(() => undefined)
    if (e.isInteractive) await launchWidget($, opts).catch(() => undefined)
    $.clock.every(60_000, () => void refresh($, false).catch(() => undefined))
    return next(e)
  })

  // 额度每动一个百分点就写一次
  on('session.measure', async ($, e, next) => {
    if (e.changed.includes('rateLimits')) await refresh($, true).catch(() => undefined)
    return next(e)
  })
}
