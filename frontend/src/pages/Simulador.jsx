// Finge ser um cliente mandando mensagem por uma conexão do tipo "simulador".
// Serve para testar o atendimento sem WhatsApp conectado.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { getSocket } from "../socket";

export default function Simulador() {
  const [services, setServices] = useState([]);
  const [serviceId, setServiceId] = useState("");
  const [numero, setNumero] = useState("5511988887777");
  const [nome, setNome] = useState("Cliente Teste");
  const [texto, setTexto] = useState("");
  const [contactId, setContactId] = useState(null);
  const [mensagens, setMensagens] = useState([]);
  const [erro, setErro] = useState("");
  const fimRef = useRef(null);

  useEffect(() => {
    api("/services", { params: { perPage: 100 } }).then((r) => {
      const sims = r.data.filter((s) => s.type === "simulador");
      setServices(sims);
      setServiceId(sims[0]?.id || "");
    });
  }, []);

  const carregar = useCallback(async () => {
    if (!serviceId || !numero) return;
    const r = await api("/contacts", { params: { serviceId, number: numero, perPage: 1 } });
    const c = r.data[0];
    setContactId(c?.id || null);
    if (c) setMensagens((await api("/messages", { params: { contactId: c.id, perPage: 100 } })).data);
    else setMensagens([]);
  }, [serviceId, numero]);

  useEffect(() => {
    const t = setTimeout(() => carregar().catch((e) => setErro(e.message)), 300);
    return () => clearTimeout(t);
  }, [carregar]);

  useEffect(() => {
    const s = getSocket();
    const onMsg = (m) => {
      if (m.contactId === contactId) setMensagens((p) => (p.some((x) => x.id === m.id) ? p : [...p, m]));
    };
    s.on("message.created", onMsg);
    return () => s.off("message.created", onMsg);
  }, [contactId]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ block: "end" });
  }, [mensagens]);

  const enviar = async (e) => {
    e.preventDefault();
    if (!texto.trim()) return;
    try {
      const m = await api("/simulator/inbound", { method: "POST", body: { serviceId, from: numero, name: nome, text: texto } });
      setTexto("");
      if (!contactId) setContactId(m.contactId);
      setMensagens((p) => (p.some((x) => x.id === m.id) ? p : [...p, m]));
    } catch (err) {
      setErro(err.message);
    }
  };

  return (
    <div className="page">
      <div className="page-head"><h2>Simulador de cliente</h2></div>
      <p className="muted">Envie mensagens como se fosse um cliente. Elas chegam na tela de Atendimento em tempo real.</p>
      {services.length === 0 && <div className="error">Crie uma conexão do tipo "simulador" em Conexões.</div>}
      <div className="row gap wrap">
        <label>Conexão
          <select value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
            {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label>Número do cliente<input value={numero} onChange={(e) => setNumero(e.target.value)} /></label>
        <label>Nome<input value={nome} onChange={(e) => setNome(e.target.value)} /></label>
      </div>
      <div className="phone">
        <div className="messages">
          {mensagens.map((m) =>
            m.type === "ticket" ? null : (
              <div key={m.id} className={`bubble ${m.isFromMe ? "them" : "me"}`}><div className="text">{m.text}</div></div>
            )
          )}
          <div ref={fimRef} />
        </div>
        <form className="composer" onSubmit={enviar}>
          <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Mensagem do cliente" />
          <button className="primary" disabled={!serviceId}>Enviar</button>
        </form>
      </div>
      {erro && <div className="error" onClick={() => setErro("")}>{erro}</div>}
    </div>
  );
}
