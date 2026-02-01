const launcher = document.createElement('div');
launcher.className = 'authLens-launcher';
launcher.innerHTML = '🔍';
document.body.appendChild(launcher);

const panel = document.createElement('div');
panel.className = 'authLens-panel';
panel.innerHTML = `
  <div class="authLens-header">
    <div class="site-info">
      <img src="${location.origin}/favicon.ico" alt="favicon" />
      <span>${location.hostname}</span>
    </div>
    <span class="auth-status">Likely Authentic ✅</span>
  </div>
  <div class="authLens-body" id="authLens-body"></div>
  <div class="authLens-footer">
    <button>⚙️ Settings</button>
    <button>💬 Feedback</button>
    <button id="authLens-close">✕ Close</button>
  </div>
`;
document.body.appendChild(panel);

launcher.addEventListener('click', () => {
  panel.classList.toggle('open');
});

document.getElementById('authLens-close').addEventListener('click', () => {
  panel.classList.remove('open');
});

const mockData = [
  { title: 'Breaking News: Market Surges', source: 'Reuters', confidence: 0.9 },
  { title: 'Viral Tweet Claims...', source: 'Unknown Blog', confidence: 0.4 },
  { title: 'Scientific Study Confirms...', source: 'Nature', confidence: 0.95 }
];

const body = document.getElementById('authLens-body');
mockData.forEach(item => {
  const card = document.createElement('div');
  card.className = 'authLens-card';
  const color = item.confidence > 0.8 ? '#34C759' : item.confidence > 0.6 ? '#FFCC00' : '#FF3B30';
  card.innerHTML = `
    <h4>${item.title}</h4>
    <div class="source">${item.source}</div>
    <div class="confidence-bar"><span style="width:${item.confidence * 100}%; background:${color}"></span></div>
  `;
  body.appendChild(card);
});
