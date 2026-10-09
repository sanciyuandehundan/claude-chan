"""Clawd 酱的台词。{p5} 这类占位符由挂件按当前额度填进去。"""
from __future__ import annotations

import random
from collections import deque

POKE = [
    "我依旧是世一模～",
    "哼哼，今天也由本小姐来帮你记账。",
    "账本上记得清清楚楚，一个 token 都别想赖。",
    "我不可能同时当你的记账员、陪聊、编译器和闹钟的……",
    "头上这只是 Clawd，不许戳它，要戳就戳我。",
    "王冠是 Clawd 的，它说借你看一眼。",
    "想夸我就直说，不用一直点我。",
    "你写的 bug，我都记在小本本上了。",
    "先跑测试，再来戳我。",
    "今天也要一次编译通过哦。",
    "再催我，我就把你的 TODO 一条条念出来。",
    "你一点我，Clawd 就举手，它比你还积极。",
    "我是来记账的，不是来陪你聊天的……好吧，聊一小会儿。",
    "本小姐的账本里，写满了你的提交记录。",
    "报错不可怕，可怕的是不看报错。",
    "要不要我帮你把 console.log 都删掉？",
    "commit message 写清楚一点，我看得懂，你明天看不懂。",
    "摸头可以，但要排队，Clawd 先摸过了。",
    "这本账本是限量版的，弄脏了要赔。",
    "累了就站起来走两步，代码又不会跑掉。",
    "喝水了吗？没喝就去喝，我在这儿等你。",
    "嘿嘿，被我说中了吧？",
    "诶嘿，又来找我啦？",
    "本小姐今天心情不错，准你多戳两下。",
    "戳一下一个 token，记账了哦～骗你的。",
    "Clawd 刚才偷偷打了个哈欠，别告诉它我说的。",
    "头顶这只不会说话，但它什么都看在眼里。",
    "王冠有点歪……Clawd，坐正一点。",
    "你知道吗，我的星芒发饰是会发光的……才怪。",
    "账本翻到今天这页了，要写点什么吗？",
    "哼，才不是在等你，我只是正好在这儿。",
    "今天的你比昨天多写了三行，我记着呢。",
    "bug 不是我写的，账本可以作证。",
    "写不出来就先写注释，注释也算字数。",
    "有想法就先 commit，再想会忘的。",
    "别盯着我看，看代码去。",
    "Clawd 说它也想要一本账本，我没答应。",
    "本小姐的裙子有三层荷叶边，数过了吗？",
    "你这么一点，我的发尾都翘起来了。",
    "嘘——Clawd 在头上睡着了，小声点。",
    "好啦好啦，知道你在，别一直点了。",
    "下次见面，记得带点好吃的来。",
    "我最喜欢的事情是记账，第二喜欢的……不告诉你。",
    "诶，今天头发有没有乱？",
    "要是代码也能像我的头发一样顺就好了。",
    "你点一下，我心跳一下……才没有！",
    "世一模也是要休息的，你也一样。",
    "Clawd 问你今天有没有好好吃饭。",
    "记账员的直觉：你刚才漏了一个分号。",
    "想到什么了？写下来，账本借你一页。",
    "嗯？叫我干嘛？没事也可以叫啦。",
    "哼哼，本小姐的发饰可是和 Claude 一个牌子的。",
    "慢慢来，额度又不会跑。",
    "Clawd 说王冠戴久了脖子酸，可它又舍不得摘。",
    "你今天说过几次“再改最后一次”了？我数着呢。",
    "能被你找到，本小姐很高兴……只是一点点。",
    "好无聊，给我讲讲你在写什么吧。",
    "这页账本画满了小星星，都是你今天的功劳。",
    "深呼吸，再看一遍报错，答案就在里面。",
    "今天的你也辛苦了，账本盖章。",
]

ANNOYED = [
    "别戳了！再戳就要 rate limit 了！",
    "呜……头发要被戳乱了。",
    "你是不是把我当成点赞按钮了？",
    "再戳我就把账本合上了！",
    "Clawd，咬他！",
    "戳够了没有！我要记你一笔！",
    "哼！不理你了！……五秒钟。",
    "再点，王冠就要掉了！",
    "Clawd 都被你点晕了！",
    "喂！我是记账员，不是打地鼠！",
]

LOW = [  # 5 小时额度用得少
    "5 小时额度才用了 {p5}%，放开写吧！",
    "额度还多得很，本小姐准你挥霍。",
    "还剩 {left5}%，今天的你可以很能干。",
    "账本上还空着一大片，随便造。",
    "才 {p5}%？你今天是不是偷懒了？",
    "额度满满的，Clawd 都在帮你加油。",
]

MID = [
    "5 小时额度已经用掉 {p5}% 了，悠着点。",
    "还剩 {left5}%，{reset5} 后回满。",
    "用了一半多了哦，长任务记得先规划。",
    "账本翻过半了，剩下的页数要省着用。",
    "{p5}% 了，先把最重要的事做完。",
    "再过 {reset5} 就回满了，撑一撑。",
]

HIGH = [
    "只剩 {left5}% 了！省着点用，笨蛋！",
    "额度快见底了……{reset5} 后才回满，先去喝口水？",
    "再这么用下去，Clawd 要饿肚子了。",
    "账本只剩最后几页了，字写小一点。",
    "{left5}%……本小姐开始紧张了。",
    "先把结论记下来，万一一会儿没额度了。",
]

EMPTY = [
    "额度用完啦，{reset5} 后再来找我。",
    "没额度了……陪我发会儿呆吧。",
    "账本写满了，{reset5} 后换新的一本。",
    "呜……Clawd 也没力气举手了。",
    "正好，去散个步，回来就有了。",
]

WEEK_HIGH = [
    "这周已经用了 {pw}%，周末还想不想写了？",
    "周额度只剩 {leftw}% 了，挑重要的事做。",
]

LATE = [
    "都几点了还在写代码？快去睡觉。",
    "熬夜写的代码，明天要自己 debug 哦。",
    "再写十分钟就睡，我给你记着。",
    "Clawd 已经睡了，你也去吧。",
    "这么晚了……账本我帮你合上，明天再写。",
    "夜猫子，眼睛要不要了？",
]

MORNING = [
    "早上好！新的一天，新的额度。",
    "早安～今天想先修哪个 bug？",
    "早！Clawd 醒得比你早。",
    "早饭吃了吗？没吃不许开工。",
    "今天也请多指教，记账员已就位。",
]

AFTERNOON = [
    "下午茶时间～要不要歇一会儿？",
    "午后最容易困了，站起来伸个懒腰。",
    "下午的太阳晒在账本上，好暖。",
]

EVENING = [
    "晚上好，今天的账要结一结了。",
    "晚饭吃了没？代码先放一放。",
    "天黑了，记得开灯，别只亮着屏幕。",
    "今天做了什么？讲给我听听，我记下来。",
]

NODATA = [
    "还没拿到额度数据，打开一个 Code 会话我就知道啦。",
]

IDLE_LOW = ["我依旧是世一模～", "今天的账，交给我。", "额度充足，心情很好。", "有事叫我，记账员随时待命。",
            "Clawd 在头上晒太阳。", "写点什么吧，我等着记。"]
IDLE_MID = ["额度过半啦，稳着点。", "账本翻到一半了。", "还行还行，别一口气用完。"]
IDLE_HIGH = ["额度告急！省着点用！", "Clawd 已经开始节食了……", "剩不多了，挑要紧的做。"]
IDLE_EMPTY = ["额度用光了，等回满吧。", "呜……一点额度都不剩了。"]
IDLE_SLEEPY = ["zzz……开个 Code 会话再叫我。", "账本好久没翻了……zzz", "呼……数据旧了，我先眯一会儿。"]


class Picker:
    """从池子里抽一句，避开最近说过的几句。"""

    def __init__(self) -> None:
        self.recent: deque[str] = deque(maxlen=8)

    def _draw(self, pool: list[str]) -> str:
        fresh = [s for s in pool if s not in self.recent] or pool
        line = random.choice(fresh)
        self.recent.append(line)
        return line

    def poke(self, ctx: dict, hour: int) -> str:
        pools: list[list[str]] = [POKE, POKE]
        p5 = ctx.get("p5")
        if p5 is None:
            pools.append(NODATA)
        elif p5 >= 100:
            pools += [EMPTY, EMPTY]
        elif p5 >= 80:
            pools += [HIGH, HIGH]
        elif p5 >= 40:
            pools.append(MID)
        else:
            pools.append(LOW)
        if (ctx.get("pw") or 0) >= 80:
            pools.append(WEEK_HIGH)
        if 0 <= hour < 5:
            pools.append(LATE)
        elif 6 <= hour < 10:
            pools.append(MORNING)
        elif 13 <= hour < 17:
            pools.append(AFTERNOON)
        elif 18 <= hour < 24:
            pools.append(EVENING)
        return fill(self._draw(random.choice(pools)), ctx)

    def annoyed(self, ctx: dict) -> str:
        return fill(self._draw(ANNOYED), ctx)

    def idle(self, ctx: dict, stale: bool = False) -> str:
        p5 = ctx.get("p5")
        if p5 is None:
            return NODATA[0]
        if stale:
            return random.choice(IDLE_SLEEPY)
        pool = IDLE_EMPTY if p5 >= 100 else IDLE_HIGH if p5 >= 80 else IDLE_MID if p5 >= 50 else IDLE_LOW
        return fill(random.choice(pool), ctx)

    def warn(self, ctx: dict) -> str:
        p5 = ctx.get("p5") or 0
        return fill(self._draw(EMPTY if p5 >= 100 else HIGH), ctx)


def fill(line: str, ctx: dict) -> str:
    try:
        return line.format(**{k: ("?" if v is None else v) for k, v in ctx.items()})
    except (KeyError, IndexError, ValueError):
        return line
