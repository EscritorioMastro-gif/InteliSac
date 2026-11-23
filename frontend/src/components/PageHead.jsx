// Cabeçalho padrão das páginas: ícone, seção, título (com contagem), explicação e ações à direita.
import Icon from "./Icon";

export default function PageHead({ icone, secao, titulo, contagem, subtitulo, children }) {
  return (
    <header className="page-head">
      <div className="page-title">
        {icone && <span className="page-icon" aria-hidden="true"><Icon name={icone} size={22} /></span>}
        <div className="page-title-text">
          {secao && <div className="page-kicker">{secao}</div>}
          <h2>
            {titulo}
            {contagem != null && <span className="page-count">{contagem}</span>}
          </h2>
          {subtitulo && <p className="page-sub">{subtitulo}</p>}
        </div>
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}
