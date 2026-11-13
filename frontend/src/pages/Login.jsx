import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import Icon from "../components/Icon";
import BrandMark from "../components/BrandMark";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [verSenha, setVerSenha] = useState(false);
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

  return (
    <div className="login-page">
      <section className="login-side">
        <div className="brand">
          <BrandMark size={38} />
          <span className="brand-name">Inteli<span>Sac</span></span>
        </div>
        <div>
          <h1>Atendimento multicanal, em tempo real.</h1>
          <p>Toda a equipe atendendo pelo mesmo WhatsApp, com fila por departamento, transferência e histórico de cada cliente.</p>
          <ul>
            <li><Icon name="whatsapp" /> WhatsApp conectado ao sistema</li>
            <li><Icon name="transfer" /> Fila, transferência e protocolo de chamados</li>
            <li><Icon name="pulse" /> Painel com o que está acontecendo agora</li>
          </ul>
        </div>
        <small style={{ opacity: 0.6 }}>InteliSac</small>
      </section>

      <div className="login-form-wrap">
        <form className="login-card" onSubmit={entrar}>
          <h2>Entrar</h2>
          <p className="muted">Use o e-mail e a senha cadastrados pelo administrador.</p>
          <label>
            E-mail
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" autoFocus required />
          </label>
          <label className="password-field">
            Senha
            <input type={verSenha ? "text" : "password"} value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="current-password" required />
            <button type="button" className="icon-btn" onClick={() => setVerSenha((v) => !v)} aria-label={verSenha ? "Esconder senha" : "Mostrar senha"} title={verSenha ? "Esconder senha" : "Mostrar senha"}>
              <Icon name={verSenha ? "eyeOff" : "eye"} />
            </button>
          </label>
          {erro && <div className="error" role="alert">{erro}</div>}
          <button className="primary" disabled={carregando}>{carregando ? "Entrando…" : "Entrar"}</button>
          <p className="muted small" style={{ marginTop: 16 }}>Esqueceu a senha? Peça ao administrador para definir uma nova em Usuários.</p>
        </form>
      </div>
    </div>
  );
}
