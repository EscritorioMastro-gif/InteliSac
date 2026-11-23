import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import Icon from "../components/Icon";
import BrandMark from "../components/BrandMark";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [verSenha, setVerSenha] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const navigate = useNavigate();

  const entrar = async (e) => {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    try {
      await login(email.trim(), senha);
      navigate("/", { replace: true });
    } catch (err) {
      setErro(err.message);
    } finally {
      setCarregando(false);
    }
  };

  // Avisa quando o Caps Lock está ligado (causa comum de senha "errada")
  const conferirCaps = (e) => setCapsLock(!!e.getModifierState?.("CapsLock"));

  return (
    <div className="login-page">
      <section className="login-side">
        <span className="login-orb" aria-hidden="true" />
        <div className="brand">
          <BrandMark size={38} />
          <span className="brand-name">Inteli<span>Sac</span></span>
        </div>
        <div>
          <div className="login-kicker">Atendimento em tempo real</div>
          <h1>Toda a equipe no mesmo WhatsApp, <em>sem perder nenhum cliente.</em></h1>
          <p>Fila por departamento, transferência, protocolo e o histórico de cada cliente num lugar só.</p>
          <ul className="login-feats">
            <li><Icon name="whatsapp" /> WhatsApp conectado ao sistema</li>
            <li><Icon name="transfer" /> Fila, transferência e protocolo de chamados</li>
            <li><Icon name="pulse" /> Painel com o que está acontecendo agora</li>
          </ul>
        </div>
        <small>InteliSac</small>
      </section>

      <div className="login-form-wrap">
        <form className="login-card" onSubmit={entrar}>
          <div className="brand brand-mobile">
            <BrandMark size={36} />
            <span className="brand-name">Inteli<span>Sac</span></span>
          </div>
          <h2>Boas-vindas de volta</h2>
          <p className="muted">Entre com o e-mail e a senha cadastrados pelo administrador.</p>
          <label>
            E-mail
            <div className="input-icon">
              <Icon name="user" size={17} />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                placeholder="voce@empresa.com.br"
                autoFocus
                required
              />
            </div>
          </label>
          <label className="password-field">
            Senha
            <div className="input-icon">
              <Icon name="lock" size={17} />
              <input
                type={verSenha ? "text" : "password"}
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                onKeyUp={conferirCaps}
                onKeyDown={conferirCaps}
                onBlur={() => setCapsLock(false)}
                autoComplete="current-password"
                placeholder="Sua senha"
                required
              />
            </div>
            <button type="button" className="icon-btn" onClick={() => setVerSenha((v) => !v)} aria-label={verSenha ? "Esconder senha" : "Mostrar senha"} title={verSenha ? "Esconder senha" : "Mostrar senha"}>
              <Icon name={verSenha ? "eyeOff" : "eye"} />
            </button>
          </label>
          {capsLock && <span className="field-hint" role="status"><Icon name="alert" size={13} /> Caps Lock ligado</span>}
          {erro && <div className="error" role="alert">{erro}</div>}
          <button className="primary" disabled={carregando}>
            {carregando ? <><span className="spinner" aria-hidden="true" />Entrando…</> : <>Entrar<Icon name="chevronRight" size={17} /></>}
          </button>
          <div className="login-help">
            <Icon name="info" size={16} />
            <span>Esqueceu a senha? Peça ao administrador para definir uma nova em Configurações → Usuários.</span>
          </div>
        </form>
      </div>
    </div>
  );
}
