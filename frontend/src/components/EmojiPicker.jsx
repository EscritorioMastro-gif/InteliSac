import { useEffect, useRef, useState } from "react";

// Seletor de emojis do campo de mensagem. Emojis do próprio sistema (sem imagens de fora),
// os usados por último ficam guardados neste navegador.
const GRUPOS = [
  {
    id: "carinhas",
    icone: "😀",
    nome: "Carinhas",
    lista: "😀 😃 😄 😁 😆 😅 🤣 😂 🙂 🙃 😉 😊 😇 🥰 😍 🤩 😘 😗 😚 😙 😋 😛 😜 🤪 😝 🤑 🤗 🤭 🤫 🤔 🤐 🤨 😐 😑 😶 😏 😒 🙄 😬 😌 😔 😪 😴 😷 🤒 🤕 🤧 🥵 🥶 😵 🤯 🤠 🥳 😎 🤓 🧐 😕 😟 🙁 😮 😯 😲 😳 🥺 😦 😧 😨 😰 😥 😢 😭 😱 😖 😣 😞 😓 😩 😫 🥱 😤 😡 😠 🤬",
  },
  {
    id: "gestos",
    icone: "👍",
    nome: "Gestos e pessoas",
    lista: "👍 👎 👌 🤌 ✌️ 🤞 🤟 🤘 🤙 👈 👉 👆 👇 ☝️ ✋ 🤚 🖐️ 🖖 👋 👏 🙌 👐 🤲 🤝 🙏 ✍️ 💪 🫡 🫶 👀 🧠 🙋 🙋‍♂️ 🙋‍♀️ 🤷 🤷‍♂️ 🤷‍♀️ 🤦 🤦‍♂️ 🤦‍♀️ 🙇 💁 👨‍💼 👩‍💼 👨‍💻 👩‍💻",
  },
  {
    id: "coracoes",
    icone: "❤️",
    nome: "Corações",
    lista: "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💔 ❣️ 💕 💞 💓 💗 💖 💘 💝 💯 ✨ ⭐ 🌟 🔥 🎉 🎊 🥂 🍾 🎁 🏆 🥇",
  },
  {
    id: "escritorio",
    icone: "📄",
    nome: "Escritório",
    lista: "📄 📃 📑 📊 📈 📉 🗂️ 📁 📂 🗃️ 🧾 💰 💵 💸 💳 🏦 🧮 📅 📆 🗓️ ⏰ ⏳ ⌛ 📌 📍 📎 🖇️ ✏️ 🖊️ 📝 📧 📨 📩 📤 📥 📦 📞 ☎️ 📱 💻 🖥️ 🖨️ 🔒 🔓 🔑 🏢 🏠 🚗 ✈️ ☕",
  },
  {
    id: "simbolos",
    icone: "✅",
    nome: "Símbolos",
    lista: "✅ ☑️ ✔️ ❌ ❎ ⚠️ 🚫 ⛔ ❗ ❓ ❕ ❔ ‼️ ⁉️ 🔴 🟠 🟡 🟢 🔵 🟣 ⚫ ⚪ 🔺 🔻 ➡️ ⬅️ ⬆️ ⬇️ ↩️ 🔁 🔄 🆗 🆕 🆓 ℹ️ 🔔 🔕 📢 💬 💭",
  },
].map((g) => ({ ...g, lista: g.lista.split(" ") }));

const CHAVE = "intelisac.emojisRecentes";
const MAX_RECENTES = 24;

function lerRecentes() {
  try {
    const v = JSON.parse(localStorage.getItem(CHAVE) || "[]");
    return Array.isArray(v) ? v.filter((e) => typeof e === "string").slice(0, MAX_RECENTES) : [];
  } catch {
    return [];
  }
}

export default function EmojiPicker({ onEscolher, onFechar }) {
  const [recentes, setRecentes] = useState(lerRecentes);
  const [grupo, setGrupo] = useState(() => (lerRecentes().length ? "recentes" : "carinhas"));
  const caixaRef = useRef(null);

  // Clique fora ou Esc fecha
  useEffect(() => {
    const fora = (e) => {
      if (caixaRef.current && !caixaRef.current.contains(e.target) && !e.target.closest?.(".emoji-btn")) onFechar();
    };
    const esc = (e) => e.key === "Escape" && onFechar();
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [onFechar]);

  const escolher = (emoji) => {
    const novos = [emoji, ...recentes.filter((e) => e !== emoji)].slice(0, MAX_RECENTES);
    setRecentes(novos);
    try {
      localStorage.setItem(CHAVE, JSON.stringify(novos));
    } catch {
      /* navegador sem armazenamento: só não lembra os recentes */
    }
    onEscolher(emoji);
  };

  const grupos = recentes.length ? [{ id: "recentes", icone: "🕘", nome: "Usados por último", lista: recentes }, ...GRUPOS] : GRUPOS;
  const atual = grupos.find((g) => g.id === grupo) || grupos[0];

  return (
    <div className="emoji-picker" ref={caixaRef} role="dialog" aria-label="Escolher emoji">
      <div className="emoji-tabs" role="tablist">
        {grupos.map((g) => (
          <button
            key={g.id}
            type="button"
            role="tab"
            aria-selected={g.id === atual.id}
            className={g.id === atual.id ? "active" : ""}
            title={g.nome}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => setGrupo(g.id)}
          >
            {g.icone}
          </button>
        ))}
      </div>
      <div className="emoji-title">{atual.nome}</div>
      <div className="emoji-grid">
        {atual.lista.map((e) => (
          <button key={e} type="button" title={e} onMouseDown={(ev) => ev.preventDefault()} onClick={() => escolher(e)}>
            {e}
          </button>
        ))}
      </div>
    </div>
  );
}
