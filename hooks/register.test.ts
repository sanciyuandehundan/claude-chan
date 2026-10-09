import { expect, mock, test } from 'claude-code/testing'

const PLAN = {
  plan: {
    status: 'ok',
    plan: 'Pro',
    windows: [
      { label: '5-hour limit', percentUsed: 15, resetsAt: '2026-10-09T09:50:00.099Z' },
      { label: 'Weekly · Fable', percentUsed: 11, resetsAt: '2026-10-14T20:00:00.099Z' },
    ],
  },
}

function setup(on: Parameters<Parameters<typeof test>[1]>[1]) {
  const writes: { path: string; text: string }[] = []
  const runs: string[][] = []
  mock.env(on, { USERPROFILE: 'C:\\Users\\me' })
  on('tool.call', { tool: 'mcp__ccd_session_mgmt__get_usage' }, () => ({ result: PLAN, text: JSON.stringify(PLAN) }))
  on('fs.read', () => ({ deny: 'ENOENT' }))
  on('fs.write', (_$, e) => {
    writes.push(e)
    return { value: undefined }
  })
  on('process.run', (_$, e) => {
    runs.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  return { writes, runs }
}

test('会话开始时把额度写到 ~/.claude/clawd-widget/usage.json，并拉起挂件', async ($, on) => {
  const { writes, runs } = setup(on)
  mock.clock(on, { now: Date.parse('2026-10-09T09:00:00Z') })

  await $.session.start({ cwd: '/work', surface: 'desktop', isInteractive: true })

  expect(writes.length).toBe(1)
  expect(writes[0].path).toMatch(/^C:\\Users\\me\\\.claude\\clawd-widget\\usage\.json$/)
  const body = JSON.parse(writes[0].text)
  expect(body.plan).toBe('Pro')
  expect(body.windows[1].label).toBe('Weekly · Fable')

  expect(runs.length).toBe(1)
  expect(runs[0][0]).toBe('powershell.exe')
  expect(runs[0][runs[0].length - 1]).toContain('widget.pyw')
})

test('非交互会话（claude -p）只写额度，不拉挂件', async ($, on) => {
  const { writes, runs } = setup(on)
  await $.session.start({ cwd: '/work', surface: null, isInteractive: false })
  expect(writes.length).toBe(1)
  expect(runs.length).toBe(0)
})

test('桌面版接口拿不到时退回引擎自己的额度窗口', async ($, on) => {
  const writes: { path: string; text: string }[] = []
  mock.env(on, { USERPROFILE: 'C:\\Users\\me' })
  on('tool.call', { tool: 'mcp__ccd_session_mgmt__get_usage' }, () => ({ isError: true, result: 'no such tool', text: 'no such tool' }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: { tokens: 0, window: 1, percent: 0 },
      rateLimits: [{ kind: 'five_hour', percentUsed: 42, resetsAt: '2026-10-09T12:00:00Z' }],
      changed: [],
    },
  }))
  on('fs.read', () => ({ deny: 'ENOENT' }))
  on('fs.write', (_$, e) => {
    writes.push(e)
    return { value: undefined }
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/work', surface: null, isInteractive: false })
  expect(writes.length).toBe(1)
  const body = JSON.parse(writes[0].text)
  expect(body.windows[0].label).toBe('5-hour limit')
  expect(body.windows[0].percentUsed).toBe(42)
})

test('一分钟内别的会话刚写过，定时刷新就跳过', async ($, on) => {
  const clock = mock.clock(on, { now: Date.parse('2026-10-09T09:00:00Z') })
  let calls = 0
  let fresh = ''
  mock.env(on, { USERPROFILE: 'C:\\Users\\me' })
  on('tool.call', { tool: 'mcp__ccd_session_mgmt__get_usage' }, () => {
    calls += 1
    return { result: PLAN, text: JSON.stringify(PLAN) }
  })
  on('fs.read', () => (fresh ? { value: fresh } : { deny: 'ENOENT' }))
  on('fs.write', (_$, e) => {
    fresh = e.text
    return { value: undefined }
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/work', surface: null, isInteractive: false })
  expect(calls).toBe(1)

  fresh = JSON.stringify({ fetchedAt: new Date(Date.now()).toISOString() })
  await clock.advance(2 * 60_000)
  expect(calls).toBe(1)

  fresh = JSON.stringify({ fetchedAt: new Date(Date.now() - 5 * 60_000).toISOString() })
  await clock.advance(2 * 60_000)
  expect(calls).toBe(2)
})
