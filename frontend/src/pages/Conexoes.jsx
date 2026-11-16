// Conexões (canais). Para WhatsApp por QR code: conectar, mostrar o QR ao vivo e desconectar.
import { useCallback, useEffect, useState } from "react";
import { api, resource } from "../api";
import { getSocket } from "../socket";
import Modal from "../components/Modal";
import Icon from "../components/Icon";
import { dolares } from "../App";

const TIPOS = [
  { value: "whatsapp", label: "WhatsApp (QR code)" },
  { value: "simulador", label: "Simulador (teste)" },
  { value: "whatsapp-business", label: "WhatsApp API oficial (em breve)" },
  { value: "telegram", label: "Telegram (em breve)" },
  { value: "instagram", label: "Instagram (em breve)" },
  { value: "email", label: "E-mail (em breve)" },
  { value: "webchat", label: "Chat do site (em breve)" },
];

const STATUS = {
  connected: { label: "Conectado", cls: "ok" },
  qr: { label: "Aguardando leitura do QR", cls: "warn" },
  connecting: { label: "Conectando…", cls: "warn" },
  disconnected: { label: "Desconectado", cls: "off" },
};

const MOTIVO = {
  qr_timeout: "O QR code expirou sem ser lido.",
  logged_out: "O aparelho foi desconectado (pelo sistema ou pelo celular).",
};

function statusDe(s) {
  if (s.type === "simulador") return { label: "Sempre ativo", cls: "ok" };
  if (s.type !== "whatsapp") return { label: "Não disponível ainda", cls: "off" };
  return STATUS[s.data?.status] || STATUS.disconnected;
}

export default function Conexoes() {
  const res = resource("/services");
  const [itens, setItens] = useState([]);
  const [editando, setEditando] = useState(null);
  const [qrDe, setQrDe] = useState(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(() => {
    api("/services", { params: { perPage: 100 } }).then((r) => setItens(r.data)).catch((e) => setErro(e.message));
  }, []);

  useEffect(() => {
    carregar();
    const s = getSocket();
    // O estado da conexão chega para todos SEM o QR; o QR vem à parte, só para administradores.
    const onUpd = (svc) =>
      setItens((prev) =>
        prev.some((x) => x.id === svc.id)
          ? prev.map((x) => {
              if (x.id !== svc.id) return x;
              const qrCode = svc.data?.status === "qr" ? svc.data?.qrCode || x.data?.qrCode || null : null;
              return { ...svc, data: { ...svc.data, qrCode } };
            })
          : [...prev, svc]
      );
    const onQr = ({ id, qrCode }) =>
      setItens((prev) => prev.map((x) => (x.id === id ? { ...x, data: { ...x.data, qrCode: qrCode || null } } : x)));
    s.on("service.updated", onUpd);
    s.on("service.created", onUpd);
    s.on("service.qr", onQr);
    return () => {
      s.off("service.updated", onUpd);
      s.off("service.created", onUpd);
      s.off("service.qr", onQr);
    };
  }, [carregar]);

  const conectar = async (svc) => {
    setErro("");
    setQrDe(svc.id);
    try {
      await api(`/services/${svc.id}/start`, { method: "POST" });
    } catch (e) {
      setErro(e.message);
      setQrDe(null);
    }
  };

  const desconectar = async (svc) => {
    if (!window.confirm(`Desconectar "${svc.name}"? Para voltar será preciso ler o QR code de novo no celular.`)) return;
    try {
      await api(`/services/${svc.id}/logout`, { method: "POST" });
    } catch (e) {
      setErro(e.message);
    }
  };

  const svcQr = itens.find((x) => x.id === qrDe);

  return (
    <div className="page">
      <div className="page-head">
        <h2>Conexões</h2>
        <button className="primary" onClick={() => setEditando({ name: "", type: "whatsapp" })}><Icon name="plus" size={16} />Nova conexão</button>
      </div>
      <p className="page-sub">Uma conexão é compartilhada por todos os atendentes: as mensagens entram e saem por ela em tempo real.</p>
      {erro && <div className="error" onClick={() => setErro("")}>{erro}</div>}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Nome</th><th>Canal</th><th>Status</th><th>Número</th><th /></tr></thead>
          <tbody>
            {itens.length === 0 && <tr className="empty"><td colSpan={5}>Nenhuma conexão. Clique em Nova conexão para ligar o WhatsApp.</td></tr>}
            {itens.map((s) => {
              const st = statusDe(s);
              return (
                <tr key={s.id}>
                  <td><span className="row gap"><Icon name={s.type.startsWith("whatsapp") ? "whatsapp" : s.type === "simulador" ? "phone" : "plug"} />{s.name}</span></td>
                  <td>{TIPOS.find((t) => t.value === s.type)?.label || s.type}</td>
                  <td>
                    <span className={`status ${st.cls}`}>{st.label}</span>
                    {s.data?.status === "disconnected" && MOTIVO[s.data?.reason] && <div className="muted small" style={{ marginTop: 4 }}>{MOTIVO[s.data.reason]}</div>}
                  </td>
                  <td>{s.data?.me?.number || <span className="muted">—</span>}</td>
                  <td className="right">
                    {s.type === "whatsapp" && s.data?.status !== "connected" && (
                      <button className="link" onClick={() => conectar(s)}><Icon name="whatsapp" size={15} />{s.data?.status === "qr" ? "Ver QR code" : "Conectar"}</button>
                    )}
                    {s.type === "whatsapp" && ["connected", "connecting", "qr"].includes(s.data?.status) && (
                      <button className="link danger" onClick={() => desconectar(s)}><Icon name="x" size={15} />Desconectar</button>
                    )}
                    <button className="link" onClick={() => setEditando(s)}><Icon name="edit" size={15} />Editar</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <CorretorQuadro />

      {qrDe && svcQr && (
        <Modal titulo={`Conectar WhatsApp — ${svcQr.name}`} onClose={() => setQrDe(null)}>
          {svcQr.data?.status === "connected" ? (
            <div className="qr-ok">
              <div className="big-check"><Icon name="check" size={28} /></div>
              <strong>Conectado!</strong>
              <p>Número {svcQr.data?.me?.number}. As mensagens já estão chegando no Atendimento.</p>
              <button className="primary" onClick={() => setQrDe(null)}>Fechar</button>
            </div>
          ) : svcQr.data?.status === "qr" && svcQr.data?.qrCode ? (
            <div className="qr-box">
              <img src={svcQr.data.qrCode} alt="QR code do WhatsApp" />
              <ol>
                <li>Abra o WhatsApp no celular do número que vai atender.</li>
                <li>Toque em <b>Configurações</b> (ou nos três pontinhos) &gt; <b>Aparelhos conectados</b>.</li>
                <li>Toque em <b>Conectar um aparelho</b> e aponte a câmera para este código.</li>
              </ol>
              <p className="muted small">O código muda a cada ~20 segundos sozinho. O Digisac continua funcionando: o InteliSac entra como mais um aparelho.</p>
            </div>
          ) : svcQr.data?.status === "disconnected" ? (
            <div>
              <p>{MOTIVO[svcQr.data?.reason] || "Desconectado."}</p>
              <button className="primary" onClick={() => conectar(svcQr)}>Gerar novo QR code</button>
            </div>
          ) : (
            <p className="muted">Gerando QR code…</p>
          )}
        </Modal>
      )}

      {editando && (
        <ConexaoForm
          inicial={editando}
          onClose={() => setEditando(null)}
          onSave={async (body) => {
            const svc = editando.id ? await res.updateById(editando.id, body) : await res.create(body);
            setEditando(null);
            carregar();
            if (!editando.id && svc.type === "whatsapp") conectar(svc);
          }}
          onArchive={editando.id ? async () => { await res.archive(editando.id, true); setEditando(null); carregar(); } : null}
        />
      )}
    </div>
  );
}

// Botão "Corrigir" com o Claude: gasto do mês, saldo estimado e quando avisar
function CorretorQuadro() {
  const [st, setSt] = useState(null);
  const [saldo, setSaldo] = useState("");
  const [aviso, setAviso] = useState("");
  const [msg, setMsg] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    api("/text/correct/status")
      .then((s) => {
        setSt(s);
        setAviso(String(s.alertBelowUsd ?? 3).replace(".", ","));
      })
      .catch((e) => setErro(e.message));
    const so = getSocket();
    so.on("corretor.updated", setSt);
    return () => so.off("corretor.updated", setSt);
  }, []);

  const salvar = async (e) => {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    setMsg("");
    try {
      const body = { alertBelowUsd: aviso };
      if (saldo.trim()) body.balanceUsd = saldo;
      const s = await api("/text/correct/status", { method: "PUT", body });
      setSt(s);
      setMsg(saldo.trim() ? "Saldo registrado. O gasto das correções passa a ser descontado a partir de agora." : "Aviso atualizado.");
      setSaldo("");
    } catch (err) {
      setErro(err.message);
    } finally {
      setSalvando(false);
    }
  };

  if (!st) return erro ? <div className="error">{erro}</div> : null;
  const claude = st.provider === "claude";
  const situacao = st.alert === "sem_credito" ? "o crédito acabou" : st.alert === "saldo_baixo" ? "saldo acabando" : st.estimatedBalanceUsd == null ? "saldo não informado" : "tudo certo";
  return (
    <section className="panel-box">
      <div className="panel-box-head">
        <Icon name="wand" />
        <h3>Corretor de texto (botão Corrigir)</h3>
        <span className={`status ${claude ? (st.alert ? "warn" : "ok") : "off"}`}>{claude ? `Claude · ${st.model}` : "LanguageTool grátis"}</span>
      </div>
      {!claude ? (
        <p className="muted">Para usar o Claude, coloque a chave <b>ANTHROPIC_API_KEY</b> no Environment do serviço <b>intelisac</b> no Render.</p>
      ) : (
        <>
          <div className="stats">
            <div>
              <span>Gasto neste mês</span>
              <strong>{dolares(st.monthCostUsd)}</strong>
              <small>{st.monthCorrections} {st.monthCorrections === 1 ? "correção" : "correções"}</small>
            </div>
            <div>
              <span>Saldo estimado na Anthropic</span>
              <strong>{st.estimatedBalanceUsd == null ? "—" : dolares(st.estimatedBalanceUsd)}</strong>
              <small>{st.balanceAt ? `informado ${dolares(st.balanceUsd)} em ${new Date(st.balanceAt).toLocaleDateString("pt-BR")}` : "informe o saldo abaixo"}</small>
            </div>
            <div className={st.alert ? "warn" : ""}>
              <span>Avisar abaixo de</span>
              <strong>{dolares(st.alertBelowUsd)}</strong>
              <small>{situacao}</small>
            </div>
          </div>
          <form className="saldo-form" onSubmit={salvar}>
            <label>
              Saldo atual na Anthropic (US$)
              <input inputMode="decimal" placeholder="Ex.: 20,00" value={saldo} onChange={(e) => setSaldo(e.target.value)} />
            </label>
            <label>
              Avisar quando ficar abaixo de (US$)
              <input inputMode="decimal" value={aviso} onChange={(e) => setAviso(e.target.value)} />
            </label>
            <button className="primary" disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
          </form>
          {msg && <div className="ok-msg">{msg}</div>}
          <p className="muted small">
            A Anthropic não informa o saldo para o InteliSac. Depois de cada recarga, copie o saldo que aparece em
            console.anthropic.com → Billing e salve aqui: o InteliSac desconta o custo de cada correção (estimativa, pode
            variar alguns centavos) e avisa os administradores quando estiver acabando. Para nunca ficar sem, ligue a
            recarga automática (auto-reload) no Billing da Anthropic.
          </p>
        </>
      )}
      {erro && <div className="error">{erro}</div>}
    </section>
  );
}

function ConexaoForm({ inicial, onClose, onSave, onArchive }) {
  const [name, setName] = useState(inicial.name || "");
  const [type, setType] = useState(inicial.type || "whatsapp");
  const [assinar, setAssinar] = useState(inicial.data?.signMessages !== false);
  const [erro, setErro] = useState("");
  const ehWhatsapp = type.startsWith("whatsapp");
  return (
    <Modal titulo={inicial.id ? "Editar conexão" : "Nova conexão"} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSave({ name, type, ...(ehWhatsapp ? { signMessages: assinar } : {}) }).catch((err) => setErro(err.message)); }}>
        <label>Nome<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex.: WhatsApp Atendimento" required /></label>
        <label>Canal
          <select value={type} onChange={(e) => setType(e.target.value)} disabled={!!inicial.id}>
            {TIPOS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        {ehWhatsapp && (
          <>
            <label className="check" style={{ margin: "12px 0 2px" }}>
              <input type="checkbox" checked={assinar} onChange={(e) => setAssinar(e.target.checked)} /> Assinar mensagens com o nome do colaborador
            </label>
            <p className="muted small" style={{ margin: "0 0 4px 24px" }}>O cliente recebe: <b>*Gabriel:*</b> Bom dia… (o nome aparece em negrito no WhatsApp)</p>
          </>
        )}
        {erro && <div className="error">{erro}</div>}
        <div className="modal-actions">
          {onArchive && <button type="button" className="link danger" onClick={() => window.confirm("Arquivar esta conexão?") && onArchive().catch((e) => setErro(e.message))}>Arquivar</button>}
          <button type="button" onClick={onClose}>Cancelar</button>
          <button className="primary">{inicial.id ? "Salvar" : "Criar e conectar"}</button>
        </div>
      </form>
    </Modal>
  );
}
