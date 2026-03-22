import { useState } from "react";
import "./App.css";

interface Message {
  id: number;
  role: "gm" | "player";
  text: string;
}

const MOCK_MESSAGES: Message[] = [
  {
    id: 1,
    role: "gm",
    text: "你推开沉重的橡木门，一阵潮湿的霉味扑面而来。\n火把的光芒在石壁上跳动，前方的走廊向左右两侧分岔。\n远处隐约传来金属碰撞的声响。",
  },
  { id: 2, role: "player", text: "我先停下来仔细听，判断声音从哪个方向传来。" },
  {
    id: 3,
    role: "gm",
    text: "请进行一次感知检定。\n（难度：普通 DC 12）",
  },
  { id: 4, role: "player", text: "我掷骰子——感知检定。" },
  {
    id: 5,
    role: "gm",
    text: "🎲 感知检定：14（骰子 11 + 感知修正 3）—— 成功！\n你辨别出声响来自左侧通道，听起来像是有人在敲打铁器。\n右侧通道则安静得不正常。",
  },
];

const MOCK_CHARACTER = {
  name: "艾拉·暮光",
  class: "游荡者",
  level: 3,
  hp: "18 / 24",
  ac: 15,
  stats: [
    { label: "力量", value: 10 },
    { label: "敏捷", value: 16 },
    { label: "体质", value: 12 },
    { label: "智力", value: 14 },
    { label: "感知", value: 13 },
    { label: "魅力", value: 8 },
  ],
};

const MOCK_LOG = [
  "进入地下城第一层",
  "触发入口叙事",
  "感知检定 DC12 → 14 成功",
];

function App() {
  const [messages, setMessages] = useState<Message[]>(MOCK_MESSAGES);
  const [input, setInput] = useState("");

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "player", text },
    ]);
    setInput("");
    // Mock GM reply
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "gm",
          text: "（GM 思考中……后端尚未接入）",
        },
      ]);
    }, 600);
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <h1>幻界</h1>
        <span>AI 跑团原型 · 前端壳子</span>
      </header>

      {/* Sidebar */}
      <aside className="sidebar">
        <section>
          <h2>场景</h2>
          <ul>
            <li className="active">地下城入口</li>
            <li>营地休息</li>
            <li>城镇集市</li>
          </ul>
        </section>
        <section>
          <h2>队伍</h2>
          <ul>
            <li>艾拉·暮光（玩家）</li>
            <li>铁锤·矮人战士</li>
            <li>薇安·精灵法师</li>
          </ul>
        </section>
      </aside>

      {/* Chat */}
      <main className="chat">
        <div className="messages">
          {messages.map((m) => (
            <div key={m.id} className={`message ${m.role}`}>
              <div className="role">{m.role === "gm" ? "GM" : "玩家"}</div>
              {m.text}
            </div>
          ))}
        </div>
        <div className="input-bar">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="输入你的行动…"
          />
          <button onClick={send}>发送</button>
        </div>
      </main>

      {/* Status Panel */}
      <aside className="status-panel">
        <section>
          <h2>角色</h2>
          <div className="stat-row">
            <span className="label">姓名</span>
            <span className="value">{MOCK_CHARACTER.name}</span>
          </div>
          <div className="stat-row">
            <span className="label">职业</span>
            <span className="value">
              {MOCK_CHARACTER.class} Lv.{MOCK_CHARACTER.level}
            </span>
          </div>
          <div className="stat-row">
            <span className="label">HP</span>
            <span className="value">{MOCK_CHARACTER.hp}</span>
          </div>
          <div className="stat-row">
            <span className="label">AC</span>
            <span className="value">{MOCK_CHARACTER.ac}</span>
          </div>
        </section>

        <section>
          <h2>属性</h2>
          {MOCK_CHARACTER.stats.map((s) => (
            <div key={s.label} className="stat-row">
              <span className="label">{s.label}</span>
              <span className="value">{s.value}</span>
            </div>
          ))}
        </section>

        <section>
          <h2>事件日志</h2>
          {MOCK_LOG.map((entry, i) => (
            <div key={i} className="log-entry">
              {entry}
            </div>
          ))}
        </section>
      </aside>
    </div>
  );
}

export default App;
