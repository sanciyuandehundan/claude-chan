# Clawd 酱额度挂件

贴在 Claude 桌面版窗口右下角的像素记账大小姐：橙发、抱着账本、头顶站着戴王冠的小 Clawd。气泡里显示 5 小时额度的重置倒计时和已用百分比、本周和 Fable 的进度条；点她会说话、跳一下、撒粒子、放音效。

![Clawd 酱](preview/clawd_chan_big.png)

挂件不在会话界面里，而是一个独立的透明小窗，跟着 Claude 窗口走：Claude 在前台时浮在最上面，切到别的软件就退到 Claude 后面，最小化时隐藏。所以 Chat 页面也能看到。

## 安装

Windows，需要 Python 3 和 Pillow（`pip install pillow`）。

```
/plugin install clawd-chan --marketplace sanciyuandehundan/clawd-chan
```

在 Claude Code 终端里输入，回答 `y` 添加市场，再选一个安装范围（选 user 就每个会话都有）。

之后每次 Code 会话启动时，插件会写一次额度并拉起挂件（已经开着就不会重复开）。想让它开机就在，把 `widget/widget.pyw` 的快捷方式放进「启动」文件夹。

插件设置（`/plugin` 里这个插件的 Configure options）：

- **会话启动时拉起挂件**：关掉就只写额度，不拉窗口
- **pythonw.exe 路径**：默认从 PATH 找

## 组成

| 路径 | 作用 |
| --- | --- |
| `hooks/register.ts` | 每个会话启动时、之后每 60 秒、额度每动一个百分点时，把额度写到数据目录；启动时拉起挂件 |
| `widget/widget.pyw` | 挂件本体（无控制台窗口） |
| `widget/art.py` | 像素立绘、表情、小 Clawd、像素数字、粒子；`python art.py` 导出预览 |
| `widget/lines.py` | 台词，按额度高低、时间段分池 |
| `widget/sounds.py` / `audio.py` | 合成 8-bit 音效；自己开输出流混音播放，鼠标靠近时先叫醒蓝牙耳机 |

数据目录 `~/.claude/clawd-widget/`（插件更新不会动它）：

| 文件 | 作用 |
| --- | --- |
| `usage.json` | 额度，插件写、挂件读 |
| `config.json` | 位置、音量、静音、气泡常驻、缩放 |
| `assets/*.wav` | 音效，缺了自动重新生成 |
| `widget.log` | 出错记录 |

## 表情和状态

| 状态 | 表情 |
| --- | --- |
| 5 小时额度回满（<4%） | 得意 |
| 正常使用 | 微笑 |
| 用量过半 | 平静 |
| 快用完（≥80%） | 皱眉（><） |
| 额度耗尽 | 哭 |
| 刚跨过 80% / 95% / 100% 那几秒 | 惊讶 |
| 数据超过 10 分钟没刷新 | 打瞌睡，头顶飘 z |
| 点一下 | wink（偶尔开心） |
| 2.5 秒内连点 5 下 | 生气 |

每隔几秒眨一次眼（只换眼睛）；头和小 Clawd 每秒上下错一格当呼吸。

## 操作

- 左键点：换一句台词、跳一下、撒粒子、放音效
- 按住拖动：挪位置（记住相对右下角的偏移）
- 右键：静音、气泡常驻、隐藏 30 分钟、回到右下角、打开数据目录、退出

## 设置（config.json）

- `scale`：像素放大倍数，默认 2（按屏幕缩放再乘）
- `offset`：相对右下角的偏移
- `volume`：音效音量 0～1，默认 0.1
- `muted` / `bubble`：静音、气泡常驻

## 开发

```
claude plugin validate .
claude plugin test .
cd widget && python art.py   # 导出 preview/
```
