/**
 * Renderiza el Sidebar lateral.
 * @param {string} rootPath - La ruta relativa a la raíz (ej: "../" o "./")
 */
function renderSidebar(rootPath) {
    const sidebarHTML = `
<style>
  .brand{
    display:flex;
    align-items:center;   /* centra verticalmente */
    gap:8px;
    padding:9px 16px;
  }

  .brand-logo{
    height:80px;          /* tamaño tipo emoji */
    width:80px;
    object-fit:contain;
    display:block;        /* evita “saltos” de baseline */
    flex:0 0 auto;
  }

  .brand-text{
    line-height:1;        /* aplica al texto, no al contenedor */
    display:block;
  }
    .brand-text-link{
  text-decoration:none;   /* quita subrayado */
  color:inherit;          /* no azul */
  cursor:pointer;
}

.brand-text-link:hover{
  text-decoration:none;
}

</style>
<div class="brand">
  <img src="${rootPath}media/botscape-logo.png" alt="BotScape Logo" class="brand-logo">
  <a href="${rootPath}index.html" class="brand-text-link">
    <span class="brand-text">BotScape</span>
  </a>
</div>

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

    <a href="https://github.com/Letee2/Botscape" target="_blank" class="github-btn">
        <svg height="20" width="20" viewBox="0 0 16 16" fill="white">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
        </svg>
        Ver Código
    </a>
    `;

    // 1. Inyectar HTML
    document.getElementById('sidebar-placeholder').innerHTML = sidebarHTML;

    // 2. Marcar enlace activo
    const currentPage = window.location.pathname.split("/").pop();
    const links = document.querySelectorAll('.nav-link');
    
    links.forEach(link => {
        // Obtenemos el nombre del archivo del href (ej: 'listener.html')
        const hrefFile = link.getAttribute('href').split("/").pop();
        if(hrefFile === currentPage) {
            link.classList.add('active');
        }
    });
}