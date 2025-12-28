/**
 * Renderiza el Sidebar lateral con arquitectura Sticky Footer corregida.
 * @param {string} rootPath - La ruta relativa a la raíz (ej: "../" o "./")
 */
function renderSidebar(rootPath) {
    const sidebarHTML = `
<style>
  /* Base del Sidebar */
  .sidebar {
    display: flex !important;
    flex-direction: column !important;
    height: 100vh !important;
    padding: 0 !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
  }

  /* 1. Header */
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 24px 20px;
    flex-shrink: 0;
  }

  .brand-logo {
    height: 80px; width: 80px;
    object-fit: contain;
    display: block; flex: 0 0 auto;
  }

  .brand-text {
    font-size: 22px; font-weight: 600;
    color: var(--text-main); line-height: 1;
  }

  .brand-text-link { text-decoration: none; color: inherit; }

  /* 2. Cuerpo de navegación (Scrollable) */
  .nav-content {
    flex: 1;
    overflow-y: auto;
    padding: 10px 20px;
    box-sizing: border-box;
  }

  /* 3. Footer (Fijo abajo con corrección de padding) */
  .sidebar-footer {
    padding: 20px; /* Espaciado uniforme en todos los lados */
    border-top: 1px solid var(--border-color);
    background-color: var(--sidebar-bg);
    flex-shrink: 0;
    box-sizing: border-box; /* Asegura que el padding no desborde el contenedor */
  }

  .github-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background-color: #24292e;
    color: white !important;
    padding: 12px;
    border-radius: 6px;
    text-decoration: none;
    font-size: 13px;
    font-weight: 600;
    transition: background-color 0.2s;
    
    /* CORRECCIÓN CRÍTICA */
    width: 100%;
    box-sizing: border-box; /* Hace que el ancho incluya el padding interno */
  }

  .github-btn:hover {
    background-color: #000;
  }
</style>

<div class="brand">
  <img src="${rootPath}media/botscape-logo.png" alt="BotScape Logo" class="brand-logo">
  <a href="${rootPath}index.html" class="brand-text-link">
    <span class="brand-text">BotScape</span>
  </a>
</div>

<div class="nav-content">
    <div class="nav-group">
        <div class="nav-title">Introducción</div>
        <a href="${rootPath}index.html" class="nav-link">El Proyecto</a>
    </div>

    <div class="nav-group">
        <div class="nav-title">Ingesta & Core</div>
        <a href="${rootPath}modules/listener.html" class="nav-link">Listener Engine</a>
        <a href="${rootPath}modules/hunter.html" class="nav-link">Hunter Engine</a>
    </div>

    <div class="nav-group">
        <div class="nav-title">Análisis & UI</div>
        <a href="${rootPath}modules/dashboard.html" class="nav-link">Dashboard UI</a>
        <a href="${rootPath}modules/enrichment.html" class="nav-link">Enrichment & Utils</a>
    </div>

    <div class="nav-group">
        <div class="nav-title">Datos & Backend</div>
        <a href="${rootPath}modules/database.html" class="nav-link">Modelo de Datos</a>
        <a href="${rootPath}modules/data_access.html" class="nav-link">Acceso a Datos</a>
    </div>

    <div class="nav-group">
        <div class="nav-title">Investigación</div>
        <a href="${rootPath}report.html" class="nav-link">📄 Informe Cluster</a>
    </div>
</div>

<div class="sidebar-footer">
    <a href="https://github.com/Letee2/Botscape" target="_blank" class="github-btn">
        <svg height="20" width="20" viewBox="0 0 16 16" fill="white">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
        </svg>
        Ver Código
    </a>
</div>
    `;

    document.getElementById('sidebar-placeholder').innerHTML = sidebarHTML;

    // Lógica de marcado de enlace activo
    const currentPage = window.location.pathname.split("/").pop();
    const links = document.querySelectorAll('.nav-link');
    links.forEach(link => {
        const hrefFile = link.getAttribute('href').split("/").pop();
        if(hrefFile === currentPage) {
            link.classList.add('active');
        }
    });

    // Crear botón toggle después de renderizar el sidebar
    initSidebarToggle();
}

/**
 * Inicializa el botón toggle del sidebar
 */
function initSidebarToggle() {
    // Crear el botón toggle si no existe
    if (!document.getElementById('sidebar-toggle')) {
        const toggleBtn = document.createElement('button');
        toggleBtn.id = 'sidebar-toggle';
        toggleBtn.innerHTML = '☰';
        toggleBtn.setAttribute('aria-label', 'Toggle sidebar');
        document.body.appendChild(toggleBtn);
    }

    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');

    // Restaurar estado del sidebar desde localStorage
    const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (isCollapsed) {
        sidebar.classList.add('collapsed');
        document.body.classList.add('sidebar-collapsed');
        toggleBtn.innerHTML = '☰';
    } else {
        toggleBtn.innerHTML = '✕';
    }

    // Toggle al hacer clic
    toggleBtn.addEventListener('click', () => {
        const isCurrentlyCollapsed = sidebar.classList.contains('collapsed');
        
        if (isCurrentlyCollapsed) {
            sidebar.classList.remove('collapsed');
            document.body.classList.remove('sidebar-collapsed');
            toggleBtn.innerHTML = '✕';
            localStorage.setItem('sidebarCollapsed', 'false');
        } else {
            sidebar.classList.add('collapsed');
            document.body.classList.add('sidebar-collapsed');
            toggleBtn.innerHTML = '☰';
            localStorage.setItem('sidebarCollapsed', 'true');
        }
    });
}