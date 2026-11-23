// Finge ser um cliente mandando mensagem por uma conexão do tipo "simulador".
// Serve para testar o atendimento sem WhatsApp conectado.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { getSocket } from "../socket";
import Icon from "../components/Icon";
import Avatar from "../components/Avatar";
import PageHead from "../components/PageHead";
import TextoComLinks from "../components/TextoComLinks";

const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "");

export default function Simulador() {
  const [services, setServices] = useState([]);
  const [serviceId, setServiceId] = useState("");
  const [numero, setNumero] = useState("5511988887777");
  const [nome, setNome] = useState("Cliente Teste");
  const [texto, setTexto] = useState("");
  const [contactId, setContactId] = useState(null);
  const [mensagens, setMensagens] = useState([]);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const fimRef = useRef(null);
  const campoRef = useRef(null);

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
    if (!texto.trim() || enviando) return;
    setEnviando(true);
    try {
      const m = await api("/simulator/inbound", { method: "POST", body: { serviceId, from: numero, name: nome, text: texto } });
      setTexto("");
      setErro("");
      if (!contactId) setContactId(m.contactId);
      setMensagens((p) => (p.some((x) => x.id === m.id) ? p : [...p, m]));
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
      campoRef.current?.focus();
    }
  };

  return (
    <div className="page">
      <PageHead icone="phone" secao="Dia a dia" titulo="Simulador de cliente" subtitulo="Envie mensagens como se fosse um cliente. Elas chegam na tela de Atendimento em tempo real." />
      {services.length === 0 && <div className="error">Crie uma conexão do tipo “Simulador (teste)” em Conexões.</div>}
      <div className="sim-layout">
        <section className="panel">
          <div className="panel-head"><Icon name="user" size={18} /><h3>Quem é o cliente</h3></div>
          <div className="sim-form">
            <label>Conexão
              <select value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
                {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
            <label>Número do cliente
              <input value={numero} onChange={(e) => setNumero(e.target.value)} inputMode="numeric" />
              <span className="field-hint">Trocar o número começa outra conversa.</span>
            </label>
            <label>Nome<input value={nome} onChange={(e) => setNome(e.target.value)} /></label>
          </div>
        </section>
        <div className="phone">
          <div className="phone-top">
            <Avatar nome="InteliSac" size={34} />
            <div className="grow">
              <strong>Atendimento</strong>
              <small>você está escrevendo como {nome || "cliente"}</small>
            </div>
          </div>
          <div className="messages">
            {mensagens.length === 0 && <div className="event"><Icon name="chat" size={13} />Escreva a primeira mensagem do cliente</div>}
            {mensagens.map((m) =>
              m.type === "ticket" ? null : (
                <div key={m.id} className={`bubble ${m.isFromMe ? "them" : "me"}`}>
                  <div className="text">{m.text ? <TextoComLinks texto={m.text} /> : "[arquivo]"}</div>
                  <div className="time">{hora(m.createdAt)}</div>
                </div>
              )
            )}
            <div ref={fimRef} />
          </div>
          <form className="composer" onSubmit={enviar}>
            <div className="composer-box">
              <input ref={campoRef} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Mensagem do cliente" aria-label="Mensagem do cliente" className="composer-input" />
            </div>
            <button className="primary send-btn" disabled={!serviceId || !texto.trim() || enviando} title="Enviar (Enter)" aria-label="Enviar"><Icon name="send" size={17} /></button>
          </form>
        </div>
      </div>
      {erro && <div className="error" onClick={() => setErro("")}>{erro}</div>}
    </div>
  );
}
