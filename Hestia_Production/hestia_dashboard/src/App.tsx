import "./App.css";

function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brandMark">H</div>
          <div>
            <div className="brandName">Hestia</div>
            <div className="brandTag">Hotel Operations Dashboard</div>
          </div>
        </div>

        <nav className="nav">
          <span className="navItem active">Inicio</span>
          <span className="navItem">Tickets</span>
          <span className="navItem">Áreas</span>
          <span className="navItem">Reportes</span>
        </nav>

        <div className="userChip" title="Demo user">
          <span className="userDot" />
          demo@hestia.local
        </div>
      </header>

      <main className="container">
        <section className="hero">
          <h1>Dashboard</h1>
          <p>
            Vista base del panel operativo. Desde aquí se monitorean tickets, estados por área y
            prioridades.
          </p>
          <div className="heroActions">
            <button className="btnPrimary">Crear ticket</button>
            <button className="btnGhost">Ver tickets</button>
          </div>
        </section>

        <section className="grid">
          <div className="card">
            <h3>Tickets abiertos</h3>
            <div className="metric">12</div>
            <div className="hint">Últimas 24 horas</div>
          </div>

          <div className="card">
            <h3>Alta prioridad</h3>
            <div className="metric">3</div>
            <div className="hint">Requiere atención</div>
          </div>

          <div className="card">
            <h3>Tiempo promedio</h3>
            <div className="metric">18m</div>
            <div className="hint">Desde creación a asignación</div>
          </div>

          <div className="card">
            <h3>Áreas</h3>
            <ul className="list">
              <li>
                Housekeeping <span className="pill ok">OK</span>
              </li>
              <li>
                Mantención <span className="pill warn">Pendiente</span>
              </li>
              <li>
                Recepción <span className="pill ok">OK</span>
              </li>
            </ul>
          </div>
        </section>

        <footer className="footer">
          <span>Hestia MVP • React + TypeScript</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
