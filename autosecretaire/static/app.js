/* Auto-secrétaire — local browser client. No mail HTML or remote resources are executed. */
(() => {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const initials = value => String(value || '?').trim().split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase();
  const leaf = path => String(path || '').split('/').pop();
  const parentPath = path => String(path || '').split('/').slice(0, -1).join('/');
  const sortFolders = folders => [...new Set(folders)].sort((a, b) => {
    const left = a.split('/'); const right = b.split('/');
    for (let i = 0; i < Math.min(left.length, right.length); i++) {
      const comparison = left[i].localeCompare(right[i], 'fr', {numeric: true});
      if (comparison) return comparison;
    }
    return left.length - right.length;
  });
  function checkedFolder(path) {
    const value = String(path).trim();
    if (!value || value.startsWith('/') || value.includes('\\') || /[\x00-\x1f]/.test(value) || value.split('/').some(part => !part.trim() || part === '.' || part === '..')) {
      throw new Error('Utilisez un nom de dossier valide, sans chemin absolu ni « .. ».');
    }
    return value.split('/').map(part => part.trim()).join('/');
  }
  function withParents(folders) {
    const result = [];
    folders.forEach(path => {
      const parts = checkedFolder(path).split('/');
      parts.forEach((_, index) => result.push(parts.slice(0, index + 1).join('/')));
    });
    return sortFolders(result);
  }
  function changeBranch(folders, source, destination, copy = false) {
    const target = checkedFolder(destination);
    if (!folders.includes(source)) throw new Error('Le dossier à modifier est introuvable.');
    if (target === source) return [...folders];
    if (target.startsWith(source + '/')) throw new Error('Un dossier ne peut pas être déplacé dans sa propre branche.');
    const branch = folders.filter(path => path === source || path.startsWith(source + '/'));
    const rest = copy ? [...folders] : folders.filter(path => !branch.includes(path));
    const moved = branch.map(path => target + path.slice(source.length));
    if (moved.some(path => rest.includes(path))) throw new Error('Un dossier porte déjà ce nom à cet endroit.');
    return withParents([...rest, ...moved]);
  }
  const UPDATE_BUSY = new Set(['checking', 'installing', 'restarting']);
  const UPDATE_RESTART = new Set(['installing', 'restarting']);
  function updateView(state, {offline = false, stalled = false} = {}) {
    const status = state?.status || 'unconfigured';
    const titles = {unconfigured: 'Reliez votre source de mises à jour', idle: 'Prêt à vérifier les versions', checking: 'Recherche d’une nouvelle version…', available: 'Une nouvelle version est disponible', current: 'Votre application est à jour', installing: 'Installation en cours…', restarting: 'Votre application redémarre…', updated: 'La mise à jour est installée', error: 'La mise à jour demande votre attention'};
    const details = {unconfigured: 'Indiquez une fois le dépôt fourni par la personne qui maintient Auto-secrétaire.', idle: 'Vérifiez la disponibilité d’une version publiée sur la branche choisie.', checking: 'La branche publiée est consultée. Votre travail reste disponible.', available: 'Vous pouvez installer cette version quand vous le souhaitez.', current: 'Aucune nouvelle version n’a été trouvée sur la branche choisie.', installing: 'La nouvelle version est préparée et contrôlée avant le redémarrage.', restarting: 'Cette page se reconnectera automatiquement. Vous pouvez la laisser ouverte.', updated: 'Le service a redémarré. Votre espace est de nouveau disponible.', error: 'Consultez le détail ci-dessous, puis vérifiez à nouveau quand le problème est résolu.'};
    const reconnecting = offline && UPDATE_RESTART.has(status);
    return {
      status,
      title: reconnecting ? (stalled ? 'La reconnexion prend plus de temps' : 'Reconnexion à votre espace…') : offline ? 'Le service est momentanément indisponible' : titles[status] || 'État de mise à jour indisponible',
      description: reconnecting ? (stalled ? 'Le service ne répond pas encore. La page continue d’essayer ; vérifiez que le lanceur reste ouvert sur le Mac.' : 'Le service redémarre. La connexion sera rétablie dès qu’il sera prêt.') : offline ? 'Réessayez la connexion. Le panneau conserve votre configuration en attendant le retour du service.' : details[status] || 'Réessayez la connexion pour obtenir l’état courant.',
      busy: UPDATE_BUSY.has(status),
      canCheck: !UPDATE_BUSY.has(status) && !!state?.repository && !offline,
      canInstall: status === 'available' && !!state?.available_commit && state?.managed === true && !offline,
      tone: offline && (!reconnecting || stalled) || status === 'error' ? 'error' : status === 'available' ? 'available' : ['current', 'updated'].includes(status) ? 'success' : ''
    };
  }
  function updateRecovery(state, intent, now = Date.now()) {
    if (!intent) return {intent: null, reload: false};
    if (state.current_commit === intent.target || (['updated', 'error'].includes(state.status) && (intent.sawRestart || intent.hadDisconnection))) return {intent: null, reload: true};
    if (state.status === 'error') return {intent: null, reload: false};
    if (state.status === 'restarting') return {intent: {...intent, sawRestart: true}, reload: false};
    if (['idle', 'available', 'current', 'unconfigured'].includes(state.status) && now - intent.startedAt > 15000 && !intent.accepted) {
      return {intent: null, reload: false, notice: 'Aucune installation en cours n’a été confirmée. Vous pouvez vérifier les versions puis réessayer.'};
    }
    return {intent, reload: false};
  }
  async function sessionRequest(path, options, renewSession, fetcher = fetch) {
    let response = await fetcher(path, options);
    // A rejected mutation has not been executed. Refresh once, then retry only that rejection.
    if ([401, 403].includes(response.status) && options.method !== 'GET') {
      const token = await renewSession();
      if (typeof token !== 'string' || !token) throw new Error('Impossible de renouveler la session locale. Réessayez la connexion.');
      response = await fetcher(path, {...options, headers: {...options.headers, 'X-CSRF-Token': token}});
    }
    return response;
  }

  // Export deterministic transformations for focused tests without a browser.
  if (typeof module !== 'undefined' && module.exports) module.exports = {escape, checkedFolder, withParents, changeBranch, updateView, updateRecovery, sessionRequest};
  if (typeof document === 'undefined') return;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const model = {state: null, client: null, active: null, selected: new Set(), filter: 'all', query: '', clientQuery: '', refreshing: false, busy: new Set(), template: [], templateSelected: null, templateDirty: false, destination: '', foldersQuery: '', recent: {}, history: [], previousFocus: null};
  try { model.recent = JSON.parse(localStorage.getItem('autosecretaire.recent') || '{}'); } catch (_) { model.recent = {}; }
  const modal = $('#modal');
  const modalContent = $('#modal-content');
  let toastTimer;
  let disconnected = false;
  const updateMonitor = {state: null, timer: null, polling: false, offline: false, disconnectedAt: 0, awaitingRestart: false};

  function dateLabel(date, full = false) {
    if (!date || Number.isNaN(new Date(date).getTime())) return 'Date inconnue';
    return new Intl.DateTimeFormat('fr-FR', full ? {dateStyle: 'long', timeStyle: 'short'} : {day: '2-digit', month: 'short', year: 'numeric'}).format(new Date(date));
  }
  function relativeDate(date) {
    if (!date || Number.isNaN(new Date(date).getTime())) return 'Pas encore de relève';
    const seconds = Math.max(0, (Date.now() - new Date(date).getTime()) / 1000);
    if (seconds < 60) return 'Dernière relève à l’instant';
    if (seconds < 3600) return `Dernière relève il y a ${Math.floor(seconds / 60)} min`;
    return `Dernière relève ${dateLabel(date)}`;
  }
  function toast(message, error = false) {
    clearTimeout(toastTimer);
    $('#toast-region').innerHTML = `<div class="toast${error ? ' error' : ''}">${escape(message)}</div>`;
    toastTimer = setTimeout(() => { $('#toast-region').replaceChildren(); }, error ? 7000 : 4200);
  }
  function showError(error) {
    const message = error instanceof Error ? error.message : String(error);
    if (modal.open) {
      let box = $('#form-error', modal);
      if (!box) {
        box = document.createElement('div'); box.id = 'form-error'; box.className = 'form-error'; box.setAttribute('role', 'alert');
        ($('.modal-body', modal) || modalContent).prepend(box);
      }
      box.textContent = message; box.scrollIntoView({block: 'nearest'});
    } else toast(message, true);
  }
  function clearError() { $('#form-error', modal)?.remove(); }
  async function api(path, method = 'GET', data) {
    if (method !== 'GET' && !path.startsWith('/api/updates/') && updatesLocked()) throw new Error('La mise à jour est en cours. Attendez la reconnexion avant de modifier votre espace.');
    const headers = {Accept: 'application/json'};
    if (method !== 'GET') {
      if (!model.state?.csrf_token) throw new Error('Le service est déconnecté. Réessayez la connexion avant cette action.');
      headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = model.state.csrf_token;
    }
    let response;
    try {
      response = await sessionRequest(path, {method, headers, body: data === undefined ? undefined : JSON.stringify(data), credentials: 'same-origin'}, async () => {
        const fresh = await api('/api/state');
        if (!fresh.csrf_token) throw new Error('La session locale n’a pas pu être renouvelée.');
        model.state = fresh;
        acceptUpdateState(fresh.updates);
        return fresh.csrf_token;
      });
    } catch (cause) {
      if (cause.status) throw cause;
      const error = new Error('Le service local ne répond pas. Vérifiez qu’Auto-secrétaire est lancé, puis réessayez.');
      error.networkUnavailable = true; error.cause = cause; throw error;
    }
    let result;
    try { result = await response.json(); } catch (_) { throw new Error(`Réponse du service illisible (${response.status}). Réessayez dans un instant.`); }
    if (!response.ok) { const error = new Error(typeof result.detail === 'string' ? result.detail : `L’action n’a pas abouti (${response.status}). Vérifiez les réglages et réessayez.`); error.status = response.status; throw error; }
    return result;
  }
  async function action(key, work, button) {
    if (model.busy.has(key)) return;
    model.busy.add(key); clearError();
    const original = button?.innerHTML;
    if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
    try { await work(); } catch (error) { showError(error); }
    finally {
      model.busy.delete(key);
      if (button?.isConnected) { button.disabled = false; button.removeAttribute('aria-busy'); if (original !== undefined) button.innerHTML = original; }
    }
  }
  async function refresh({notify = false, quiet = false} = {}) {
    if (model.refreshing) return;
    model.refreshing = true;
    try {
      const next = await api('/api/state');
      if (!Array.isArray(next.clients) || !Array.isArray(next.messages)) throw new Error('État du service incomplet. Relancez la connexion.');
      const changed = JSON.stringify(model.state) !== JSON.stringify(next) || disconnected;
      model.state = next; disconnected = false;
      acceptUpdateState(next.updates);
      if (model.client && !next.clients.some(c => c.id === model.client)) model.client = null;
      model.selected = new Set([...model.selected].filter(id => next.messages.some(m => m.id === id)));
      if (!quiet || changed) render();
      if (notify) toast('État du service actualisé.');
    } catch (error) {
      disconnected = true;
      if (expectedUpdateRestart()) { markUpdateOffline(); return; }
      $('#global-error').classList.remove('hidden');
      $('#global-error').innerHTML = `<span>${escape(error.message)}</span><button class="button small" data-action="refresh">Réessayer</button>`;
      if (!model.state) $('#message-list').innerHTML = empty('Connexion interrompue', 'Votre espace apparaîtra dès que le service local sera disponible.', '<button class="button" data-action="refresh">Réessayer</button>');
      $('#connection-dot').classList.add('offline');
      $('#connection-label').innerHTML = 'Service déconnecté<small>Vérifiez le lancement local</small>';
    } finally { model.refreshing = false; }
  }
  function clients() { return model.state?.clients || []; }
  function messages() { return model.state?.messages || []; }
  function currentClient() { return clients().find(c => c.id === model.client); }
  function activeMessage() { return messages().find(m => m.id === model.active); }
  function messageClient(message) { return clients().find(c => c.id === message?.client_id); }
  function scopeMessages() { return messages().filter(m => !model.client || m.client_id === model.client); }
  function needsAttention(m) { return m.status === 'error' || ['error', 'uncertain'].includes(m.print_status); }
  function visibleMessages() {
    const q = model.query.toLocaleLowerCase('fr');
    return scopeMessages().filter(m => (model.filter !== 'pending' || m.classification !== 'classified') && (model.filter !== 'error' || needsAttention(m)) && (!q || [m.subject, m.sender, m.body, messageClient(m)?.name].join(' ').toLocaleLowerCase('fr').includes(q))).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }
  function selectedMessages() { const ids = model.selected.size ? model.selected : new Set([model.active]); return messages().filter(m => ids.has(m.id)); }
  function empty(title, description, extra = '') { return `<div class="empty-state"><span class="empty-icon" aria-hidden="true">▤</span><h3>${escape(title)}</h3><p>${escape(description)}</p>${extra}</div>`; }
  function chip(text, tone = '') { return `<span class="chip ${tone}">${escape(text)}</span>`; }
  function printLabel(status) { return ({pending: 'À imprimer', submitted: 'Envoyé à l’imprimante', simulated: 'Impression simulée', uncertain: 'Impression à vérifier', error: 'Erreur d’impression', historical: 'Historique · impression manuelle'})[status] || 'À imprimer'; }
  function printTone(status) { return ['uncertain', 'error'].includes(status) ? 'error' : ['submitted', 'simulated'].includes(status) ? '' : 'neutral'; }
  function render() {
    const state = model.state;
    if (!state) return;
    $('#global-error').classList.toggle('hidden', !state.sync_error);
    if (state.sync_error) $('#global-error').innerHTML = `<span><b>La relève demande votre attention.</b> ${escape(state.sync_error)}</span><button class="button small" data-action="sync">Réessayer</button>`;
    $('#connection-dot').classList.remove('offline');
    $('#connection-label').innerHTML = 'Service local actif<small>Sur cet ordinateur</small>';
    $('#mode-label').textContent = state.settings?.connector === 'demo' ? 'Espace de démonstration' : 'Espace local';
    const client = currentClient();
    $('#all-count').textContent = messages().length;
    $('#all-clients').classList.toggle('active', !client);
    $('#breadcrumb-current').textContent = client?.name || 'Vue d’ensemble';
    $('#page-title').textContent = client?.name || 'Tout est à sa place.';
    $('#page-subtitle').textContent = client ? 'Vos communications et documents, réunis dans le dossier de ce client.' : 'Les mails, les documents et leur classement. Un seul espace pour suivre l’essentiel.';
    $('#list-heading').textContent = client ? 'Communications du client' : 'Toutes les communications';
    $('#client-history').classList.toggle('hidden', !client);
    const notice = $('#context-notice');
    if (client && client.status !== 'ready') {
      notice.className = 'notice warning';
      notice.innerHTML = `<span><b>Création du client à terminer.</b> ${escape(client.error || 'La préparation des dossiers est en cours.')}</span><button class="button small" data-action="retry-client" data-id="${escape(client.id)}">Reprendre</button>`;
    } else if (state.settings?.connector === 'demo') {
      notice.className = 'notice';
      notice.innerHTML = '<span><b>Votre espace d’essai.</b> Explorez le classement avec les messages de démonstration. Le mode d’impression est indiqué dans les réglages.</span><button class="button quiet small" data-action="settings">Configurer ma messagerie ↗</button>';
    } else notice.className = 'notice hidden';
    renderClients(); renderSummary(); renderMessages(); renderDetail(); renderUpdateControls();
    $('#last-scan').textContent = relativeDate(state.last_scan);
  }
  function renderClients() {
    const q = model.clientQuery.toLocaleLowerCase('fr');
    const items = clients().filter(c => c.name.toLocaleLowerCase('fr').includes(q)).sort((a,b) => a.name.localeCompare(b.name, 'fr'));
    $('#client-list').innerHTML = items.length ? items.map(c => {
      const count = messages().filter(m => m.client_id === c.id && m.classification !== 'classified').length;
      return `<button class="client-item${model.client === c.id ? ' active' : ''}" data-action="client" data-id="${escape(c.id)}" aria-current="${model.client === c.id ? 'page' : 'false'}" title="${escape(c.name)}"><span class="client-initial" aria-hidden="true">${escape(initials(c.name))}</span><span class="client-name">${escape(c.name)}</span>${count ? `<span class="count" title="${count} à classer">${count}</span>` : ''}${c.status === 'error' ? '<span aria-label="Création incomplète">!</span>' : ''}</button>`;
    }).join('') : `<p class="subtle small loading-text">${q ? 'Aucun client ne correspond.' : 'Votre premier client commence ici.'}</p>`;
  }
  function renderSummary() {
    const list = scopeMessages();
    const pending = list.filter(m => m.classification !== 'classified').length;
    const archived = list.filter(m => m.status === 'ready').length;
    const attention = list.filter(needsAttention).length;
    const cards = [
      {label: 'Communications', value: list.length, note: currentClient() ? 'dans ce dossier client' : `${clients().length} client${clients().length > 1 ? 's' : ''} dans votre espace`, icon: '✉', filter: 'all'},
      {label: 'À classer', value: pending, note: pending ? 'un dossier, puis c’est rangé' : 'votre classement est à jour', icon: '▱', filter: 'pending', tone: 'amber'},
      {label: 'Mails exportés', value: archived, note: 'PDF disponibles localement', icon: '✓', filter: 'all'},
      {label: 'À vérifier', value: attention, note: attention ? 'une action est nécessaire' : 'aucune anomalie signalée', icon: '↻', filter: 'error', tone: attention ? 'error-card' : ''}
    ];
    $('#summary').innerHTML = cards.map(c => `<button class="summary-card ${c.tone || ''}" data-filter="${c.filter}"><span class="label">${c.label}</span><span class="metric">${c.value}</span><span class="metric-label">${c.note}</span><span class="metric-icon" aria-hidden="true">${c.icon}</span></button>`).join('');
    $('#pending-count').textContent = pending || '';
    $('#error-count').textContent = attention || '';
  }
  function renderMessages() {
    const list = visibleMessages();
    if (!list.some(m => m.id === model.active)) model.active = list[0]?.id || null;
    model.selected = new Set([...model.selected].filter(id => list.some(m => m.id === id)));
    $('#message-count').textContent = `${list.length} mail${list.length > 1 ? 's' : ''}`;
    $$('.filter').forEach(button => { const active = button.dataset.filter === model.filter; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
    $('#bulk-toolbar').classList.toggle('hidden', model.selected.size === 0);
    $('#selected-count').textContent = `${model.selected.size} sélectionné${model.selected.size > 1 ? 's' : ''}`;
    $('#select-all').checked = !!list.length && list.every(m => model.selected.has(m.id));
    $('#select-all').indeterminate = model.selected.size > 0 && !$('#select-all').checked;
    if (!list.length) {
      const hasClients = clients().length > 0;
      const filtered = model.filter !== 'all' || model.query;
      $('#message-list').innerHTML = empty(filtered ? 'Rien à afficher ici.' : hasClients ? 'La place est prête.' : 'Bienvenue dans votre espace.', filtered ? 'Aucune communication ne correspond à ce filtre.' : hasClients ? 'Relevez les mails pour retrouver les messages de vos dossiers clients.' : 'Créez un client pour relier son dossier mail à ses documents locaux.', `<button class="button" data-action="${filtered ? 'reset-filters' : hasClients ? 'sync' : 'new-client'}">${filtered ? 'Afficher tous les mails' : hasClients ? 'Relever les mails' : 'Créer mon premier client'}</button>`);
      return;
    }
    $('#message-list').innerHTML = list.map(m => {
      const client = messageClient(m);
      const sender = String(m.sender || 'Expéditeur inconnu').replace(/\s*<.*>$/, '');
      const docs = m.documents || [];
      return `<article class="message-row${model.active === m.id ? ' active' : ''}${model.selected.has(m.id) ? ' selected' : ''}" data-message="${escape(m.id)}" tabindex="0" aria-label="${escape(m.subject || 'Sans objet')}, ${escape(client?.name || '')}, ${escape(dateLabel(m.date))}" aria-current="${model.active === m.id ? 'true' : 'false'}"><input class="message-checkbox" type="checkbox" data-select="${escape(m.id)}" aria-label="Sélectionner ${escape(m.subject || 'ce mail')}" ${model.selected.has(m.id) ? 'checked' : ''}><span class="mail-avatar" aria-hidden="true">${escape(initials(client?.name || sender))}</span><div class="message-content"><div class="message-row-top"><span class="message-sender">${escape(model.client ? sender : client?.name || sender)}</span><time class="message-time" datetime="${escape(m.date)}">${escape(dateLabel(m.date))}</time></div><p class="message-subject">${escape(m.subject || 'Sans objet')}</p><p class="message-snippet">${escape(m.body?.replace(/\s+/g, ' ').slice(0, 120) || sender)}</p><div class="message-meta">${m.status === 'error' ? chip('Export à reprendre', 'error') : m.status === 'queued' ? chip('Export en attente', 'neutral') : chip('PDF disponible')}${chip(m.classification === 'classified' ? 'Classé' : 'À classer', m.classification === 'classified' ? '' : 'pending')}${needsAttention(m) && m.status !== 'error' ? chip('Impression à vérifier', 'error') : ''}${docs.length > 1 ? `<span class="attachment-count">↳ ${docs.length - 1} pièce${docs.length > 2 ? 's' : ''}</span>` : ''}</div></div></article>`;
    }).join('');
  }
  function renderDetail() {
    const m = activeMessage();
    const panel = $('#detail-panel');
    if (!m) { panel.innerHTML = `<div class="empty-state detail-empty"><span class="empty-icon" aria-hidden="true">↗</span><h3>Le détail, en un clic.</h3><p>Sélectionnez une communication pour consulter ses documents et choisir où les ranger.</p></div>`; return; }
    const client = messageClient(m);
    const docs = m.documents || [];
    const email = docs.find(d => d.kind === 'email');
    const canPrint = m.status === 'ready' && !['submitted', 'uncertain', 'simulated'].includes(m.print_status);
    panel.innerHTML = `<div class="detail-header"><span>APERÇU DE LA COMMUNICATION</span>${email ? `<button class="button quiet small" data-action="preview" data-id="${escape(email.id)}">Ouvrir le PDF ↗</button>` : ''}</div><div class="detail-content"><h2 class="detail-subject">${escape(m.subject || 'Sans objet')}</h2><dl class="detail-meta"><dt>De</dt><dd>${escape(m.sender || 'Expéditeur inconnu')}</dd><dt>À</dt><dd>${escape(Array.isArray(m.recipients) ? m.recipients.join(', ') : m.recipients || '—')}</dd><dt>Reçu</dt><dd>${escape(dateLabel(m.date, true))}</dd><dt>Client</dt><dd>${escape(client?.name || '—')}</dd></dl><div class="detail-statuses">${chip(m.status === 'ready' ? '✓ PDF disponible' : m.status === 'error' ? 'Export en erreur' : 'Export en attente', m.status === 'error' ? 'error' : m.status === 'queued' ? 'neutral' : '')}${chip(printLabel(m.print_status), printTone(m.print_status))}</div>${m.error ? `<div class="notice error"><span>${escape(m.error)}</span><button class="button small" data-action="process">Reprendre</button></div>` : ''}<div class="document-preview">${escape(m.body || 'Le contenu de ce mail sera disponible après son export.')}</div><h3 class="mini-heading">DOCUMENTS <small>${docs.length} fichier${docs.length > 1 ? 's' : ''}</small></h3><div class="document-list">${docs.length ? docs.map(d => `<div class="document"><input type="checkbox" data-document-select="${escape(d.id)}" aria-label="Inclure ${escape(d.original_name || d.name)} à l’impression" ${d.selected ? 'checked' : ''} ${!d.printable ? 'disabled' : ''}><span class="document-icon" aria-hidden="true">${escape((d.name || d.path || '').split('.').pop()?.slice(0, 4).toUpperCase() || 'DOC')}</span><div class="document-info"><p class="document-name">${escape(d.name || leaf(d.path) || d.original_name)}</p><small>${d.kind === 'email' ? 'Mail en PDF' : d.inline ? 'Image intégrée au message' : 'Pièce jointe originale'}${!d.printable ? ' · format non imprimable ici' : ''}</small></div><button class="icon-button" data-action="preview" data-id="${escape(d.id)}" title="Consulter le document" aria-label="Consulter ${escape(d.original_name || d.name)}">↗</button><button class="icon-button" data-action="reveal" data-id="${escape(d.id)}" title="Afficher dans le Finder" aria-label="Afficher dans le Finder">▱</button></div>`).join('') : '<p class="small subtle">Les documents apparaîtront après l’export.</p>'}</div>${(m.print_jobs || []).length ? `<h3 class="mini-heading">SUIVI DES IMPRESSIONS</h3>${m.print_jobs.map(job => `<p class="detail-note">${escape(docs.find(d => d.id === job.document_id)?.name || 'Document')} · ${escape(printLabel(job.status))}${job.job_id ? ` · ${escape(job.job_id)}` : ''}${job.error ? `<br><strong>${escape(job.error)}</strong>` : ''}</p>`).join('')}` : ''}<div class="destination-block"><div class="destination-label">${m.classification === 'classified' ? 'CLASSÉ DANS' : 'DESTINATION À CHOISIR'}</div><div class="destination-path">▱ ${escape(client?.name || '')}${m.destination ? ` / ${escape(m.destination)}` : ' / À classer'}</div></div><div class="detail-actions"><button class="button primary" data-action="classify" ${m.status !== 'ready' ? 'disabled' : ''}>${m.classification === 'classified' ? 'Changer de dossier' : 'Classer ce mail'} <span aria-hidden="true">↗</span></button>${canPrint ? '<button class="button" data-action="print">Imprimer</button>' : ['submitted', 'uncertain', 'simulated'].includes(m.print_status) ? `<button class="button" data-action="reprint" data-id="${escape(m.id)}">Réimprimer…</button>` : ''}</div><p class="detail-note">${m.historical ? 'Message de l’historique : aucune impression automatique. ' : ''}${model.state?.settings?.dry_run ? 'Mode simulation : aucun papier n’est imprimé. ' : ''}Une soumission confirme l’envoi à l’imprimante, pas la sortie du papier.</p></div>`;
  }

  function openModal(title, subtitle, body, footer = '', wide = false) {
    model.previousFocus = document.activeElement;
    modal.classList.toggle('wide', wide);
    modalContent.innerHTML = `<div class="modal-header"><div><h2 id="modal-title">${escape(title)}</h2>${subtitle ? `<p>${escape(subtitle)}</p>` : ''}</div><button class="icon-button" data-action="close-modal" aria-label="Fermer">×</button></div><div class="modal-body">${body}</div>${footer ? `<div class="modal-footer">${footer}</div>` : ''}`;
    if (!modal.open) modal.showModal();
    document.body.classList.add('no-scroll');
    requestAnimationFrame(() => { $('[autofocus]', modal)?.focus(); });
  }
  function closeModal() {
    if (model.templateDirty && modal.dataset.kind === 'template' && !window.confirm('Fermer sans enregistrer les modifications du modèle ?')) return;
    modal.close(); modal.dataset.kind = ''; model.templateDirty = false;
  }
  modal.addEventListener('close', () => { document.body.classList.remove('no-scroll'); if (model.previousFocus?.isConnected) model.previousFocus.focus(); });
  modal.addEventListener('cancel', event => { event.preventDefault(); closeModal(); });
  function newClient() {
    const folderOptions = (model.state?.folders || []).map(f => `<option value="${escape(f)}">${escape(f)}</option>`).join('');
    modal.dataset.kind = 'client';
    openModal('Un nouveau client', 'Son dossier mail et son espace documentaire seront reliés en une seule étape.', `<form id="client-form"><label class="field"><span>Nom du client</span><input name="name" id="client-name" required maxlength="160" placeholder="Ex. Atelier Martin" autofocus autocomplete="off"></label><div class="radio-options"><label class="radio-option"><input type="radio" name="mailbox_mode" value="new" checked>Créer un dossier mail</label><label class="radio-option"><input type="radio" name="mailbox_mode" value="existing">Relier un dossier existant</label></div><div id="existing-mailbox" class="hidden"><div class="field-row"><label class="field"><span>Dossier dans la messagerie</span><select name="mailbox" id="mailbox-select"><option value="">Choisir un dossier…</option>${folderOptions}</select></label><button class="button" type="button" data-action="refresh-folders">Actualiser</button></div></div><div class="path-preview" id="client-path-preview">Saisissez un nom pour prévisualiser les dossiers.</div><div class="dialog-note">Le modèle courant (version ${escape(model.state?.template?.version || 1)}) sera utilisé. Un dossier déjà présent sera réutilisé. En cas d’interruption, la création pourra être reprise.</div></form>`, '<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" type="submit" form="client-form">Créer le client</button>');
  }
  function clientPreview() {
    const name = $('#client-name')?.value.trim();
    const preview = $('#client-path-preview');
    if (!preview) return;
    const settings = model.state?.settings || {};
    const folder = (settings.client_folder_pattern || '{name}').replace('{name}', name || 'Nom du client');
    const existing = $('input[name="mailbox_mode"]:checked', modal)?.value === 'existing';
    const mail = existing ? $('#mailbox-select')?.value || 'Dossier existant à choisir' : name || 'Nom du client';
    preview.innerHTML = `<b>Messagerie</b> · ${escape(mail)}<br><b>Sur votre Mac</b> · ${escape(settings.archive_root || '')}/${escape(folder)}<br><small>${model.state?.template?.folders?.length || 0} dossiers dans le modèle</small>`;
  }
  function chosenForClassify() {
    const list = selectedMessages();
    if (!list.length) throw new Error('Sélectionnez d’abord une communication.');
    if (new Set(list.map(m => m.client_id)).size !== 1) throw new Error('Pour un classement groupé, sélectionnez les mails d’un même client.');
    if (list.some(m => m.status !== 'ready')) throw new Error('Attendez que tous les mails sélectionnés soient exportés avant de les classer.');
    return list;
  }
  function openClassify() {
    const list = chosenForClassify();
    const client = messageClient(list[0]);
    if (!client) throw new Error('Le dossier client est introuvable.');
    model.destination = list.length === 1 ? list[0].destination || '' : '';
    model.foldersQuery = '';
    modal.dataset.kind = 'classify';
    modal.dataset.client = client.id;
    modal.dataset.messages = JSON.stringify(list.map(m => m.id));
    openModal('Choisir un dossier', 'Le mail et ses pièces jointes seront rangés ensemble dans ce dossier.', `<div class="selection-summary"><span class="client-initial">${escape(initials(client.name))}</span><div>${escape(client.name)}<small>${list.length} communication${list.length > 1 ? 's' : ''} sélectionnée${list.length > 1 ? 's' : ''}</small></div></div><label class="search-field" style="margin-bottom:13px"><span aria-hidden="true">⌕</span><input id="folder-search" type="search" placeholder="Trouver un dossier…" aria-label="Rechercher un dossier de destination" autofocus></label><div id="folder-picker" class="folder-picker"></div><p class="dialog-note" style="margin-top:12px">★ Vos favoris restent accessibles pour ce client. Entrée valide le dossier choisi.</p>`, '<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" id="classify-confirm" data-action="confirm-classify">Classer ici</button>');
    renderFolders();
  }
  function renderFolders() {
    const client = clients().find(c => c.id === modal.dataset.client);
    if (!client) return;
    const all = sortFolders(client.folders || []);
    const q = model.foldersQuery.toLocaleLowerCase('fr');
    const filtered = all.filter(f => !q || f.toLocaleLowerCase('fr').includes(q));
    const favorite = (client.favorites || []).filter(f => filtered.includes(f));
    const recent = (Array.isArray(model.recent[client.id]) ? model.recent[client.id] : []).filter(f => filtered.includes(f) && !favorite.includes(f)).slice(0, 4);
    const rest = filtered.filter(f => !favorite.includes(f) && !recent.includes(f));
    const section = (title, folders) => folders.length ? `<div class="folder-section-title">${title}</div>${folders.map(f => `<div class="folder-row"><button class="folder-choice" data-action="choose-folder" data-folder="${escape(f)}" aria-pressed="${model.destination === f}"><span class="folder-icon" aria-hidden="true">▱</span><span class="folder-label">${escape(leaf(f))}${parentPath(f) ? `<span class="folder-parent">${escape(parentPath(f))}</span>` : ''}</span></button><button class="icon-button${(client.favorites || []).includes(f) ? ' favorite' : ''}" data-action="favorite" data-folder="${escape(f)}" aria-label="${(client.favorites || []).includes(f) ? 'Retirer des favoris' : 'Ajouter aux favoris'}" title="${(client.favorites || []).includes(f) ? 'Retirer des favoris' : 'Ajouter aux favoris'}">${(client.favorites || []).includes(f) ? '★' : '☆'}</button></div>`).join('')}` : '';
    $('#folder-picker').innerHTML = section('FAVORIS', favorite) + section('RÉCENTS', recent) + section('DOSSIERS DU CLIENT', rest) || '<p class="dialog-note" style="padding:16px;margin:0">Aucun dossier trouvé. Modifiez le modèle puis appliquez-le à ce client pour ajouter un dossier.</p>';
    $('#classify-confirm').disabled = !all.includes(model.destination);
    $('#classify-confirm').textContent = model.destination ? `Classer dans « ${leaf(model.destination)} »` : 'Choisissez un dossier';
  }
  function rememberFolder(client, folder) {
    model.recent[client] = [folder, ...(Array.isArray(model.recent[client]) ? model.recent[client] : []).filter(f => f !== folder)].slice(0, 5);
    try { localStorage.setItem('autosecretaire.recent', JSON.stringify(model.recent)); } catch (_) { /* Private mode may disable storage. */ }
  }
  function openTemplate() {
    model.template = withParents(model.state?.template?.folders || []);
    model.templateSelected = null; model.templateDirty = false;
    modal.dataset.kind = 'template';
    openModal('Votre modèle de dossiers', 'Une structure commune pour chaque nouveau client. Adaptez-la à votre façon de travailler.', `<div class="template-toolbar"><span class="version-tag" id="template-version">Version ${escape(model.state?.template?.version || 1)}</span><button class="button small" data-action="template-add-root">＋ Dossier à la racine</button></div><div id="template-tree" class="template-tree" aria-label="Arborescence du modèle"></div><div id="template-editor" class="template-editor hidden"></div><p class="template-hint">Sélectionnez un dossier pour le renommer, le déplacer, le dupliquer ou ajouter un sous-dossier. Vous pouvez aussi le glisser dans un autre dossier.</p><h3 class="mini-heading" style="margin-top:20px">APERÇU POUR UN NOUVEAU CLIENT</h3><div id="template-preview" class="template-preview"></div>${clients().length ? `<div class="apply-template"><h3>Compléter un client existant</h3><p>Enregistrez le modèle, puis ajoutez ses dossiers manquants. Les fichiers et dossiers existants sont conservés.</p><div class="field-row"><label class="field"><span>Client</span><select id="template-client">${clients().map(c => `<option value="${escape(c.id)}" ${c.id === model.client ? 'selected' : ''}>${escape(c.name)} · v${escape(c.template_version || 1)}</option>`).join('')}</select></label><button class="button" data-action="apply-template">Compléter les dossiers</button></div></div>` : ''}`, '<button class="button quiet" data-action="close-modal">Fermer</button><button class="button primary" data-action="save-template">Enregistrer le modèle</button>', true);
    renderTemplate();
  }
  function renderTemplate() {
    $('#template-tree').innerHTML = model.template.length ? model.template.map(f => `<div class="template-node" draggable="true" data-path="${escape(f)}" aria-selected="${model.templateSelected === f}"><span class="tree-indent" style="--indent:${(f.split('/').length - 1) * 19}px"></span><span class="folder-icon" aria-hidden="true">▱</span><button class="tree-name" data-action="template-select" data-folder="${escape(f)}">${escape(leaf(f))}</button><button class="icon-button" data-action="template-add-child" data-folder="${escape(f)}" title="Ajouter un sous-dossier" aria-label="Ajouter un sous-dossier à ${escape(f)}">＋</button></div>`).join('') : '<p class="dialog-note" style="padding:15px;margin:0">Le modèle est vide. Ajoutez un dossier à la racine pour commencer.</p>';
    const pattern = model.state?.settings?.client_folder_pattern || '{name}';
    $('#template-preview').textContent = pattern.replace('{name}', 'Nom du client') + '/\n' + model.template.map(f => '  '.repeat(f.split('/').length) + '└ ' + leaf(f) + '/').join('\n');
    const editor = $('#template-editor');
    if (!model.templateSelected || !model.template.includes(model.templateSelected)) { editor.classList.add('hidden'); return; }
    const path = model.templateSelected;
    const parents = model.template.filter(p => p !== path && !p.startsWith(path + '/'));
    editor.classList.remove('hidden');
    editor.innerHTML = `<h3>Modifier « ${escape(leaf(path))} »</h3><div class="form-grid"><label class="field"><span>Nom du dossier</span><input id="template-name" value="${escape(leaf(path))}" maxlength="160"></label><label class="field"><span>À l’intérieur de</span><select id="template-parent"><option value="">Racine du client</option>${parents.map(p => `<option value="${escape(p)}" ${p === parentPath(path) ? 'selected' : ''}>${escape(p)}</option>`).join('')}</select></label></div><div class="editor-actions"><button class="button small" data-action="template-update">Appliquer la modification</button><button class="button small" data-action="template-copy">Dupliquer la branche</button><button class="button small danger" data-action="template-remove">Retirer du modèle</button></div>`;
  }
  function addTemplate(parent = '') {
    const name = window.prompt(parent ? `Nom du sous-dossier dans « ${parent} » :` : 'Nom du nouveau dossier :');
    if (name === null) return;
    if (name.includes('/')) throw new Error('Saisissez un nom simple. Ajoutez ensuite ses sous-dossiers.');
    const path = checkedFolder(parent ? `${parent}/${name}` : name);
    if (model.template.includes(path)) throw new Error('Ce dossier existe déjà dans le modèle.');
    model.template = withParents([...model.template, path]); model.templateSelected = path; model.templateDirty = true; renderTemplate();
  }
  async function saveTemplate() {
    if (!model.template.length) throw new Error('Ajoutez au moins un dossier au modèle.');
    const template = await api('/api/template', 'PUT', {folders: model.template});
    model.state.template = template; model.templateDirty = false;
    $('#template-version').textContent = `Version ${template.version}`;
    toast('Modèle enregistré. Il sera utilisé pour les nouveaux clients.');
    await refresh();
  }
  function settingField(name, label, value, help = '', attrs = '') { return `<label class="field"><span>${escape(label)}</span><input name="${name}" value="${escape(value)}" ${attrs}>${help ? `<small>${escape(help)}</small>` : ''}</label>`; }
  function selectField(name, label, value, options, help = '', attrs = '') { return `<label class="field"><span>${escape(label)}</span><select name="${name}" ${attrs}>${options.map(([key, text]) => `<option value="${escape(key)}" ${String(value) === key ? 'selected' : ''}>${escape(text)}</option>`).join('')}</select>${help ? `<small>${escape(help)}</small>` : ''}</label>`; }
  function openSettings() {
    const s = model.state?.settings || {};
    const locked = clients().length ? 'disabled' : '';
    modal.dataset.kind = 'settings';
    openModal('Les réglages de votre espace', 'Une configuration locale. La messagerie et l’imprimante restent sous votre contrôle.', `<form id="settings-form"><fieldset class="form-section"><legend>Messagerie & dossiers</legend>${selectField('connector', 'Source des mails', s.connector, [['demo','Démonstration · messages d’essai'],['imap','Orange / serveur IMAP'],['apple_mail','Apple Mail · dossiers locaux ou compte']], clients().length ? 'Des clients sont déjà liés à cet espace. Pour changer de source, démarrez un nouvel espace selon le guide d’installation.' : '', locked)}<div id="apple-settings">${settingField('mail_account', 'Compte Apple Mail', s.mail_account, 'Laissez vide pour les boîtes « Sur mon Mac ». Sinon, indiquez le nom exact du compte dans Mail.', locked)}</div><div id="imap-settings"><div class="form-grid">${settingField('imap_host', 'Serveur IMAP', s.imap_host, '', `autocomplete="off" ${locked}`)}${settingField('imap_port', 'Port sécurisé', s.imap_port || 993, '', `type="number" min="1" max="65535" ${locked}`)}</div>${settingField('imap_user', 'Adresse de la boîte mail', s.imap_user, '', `autocomplete="off" ${locked}`)}${settingField('imap_password_env', 'Nom de la variable du mot de passe', s.imap_password_env, 'Ne saisissez pas le mot de passe ici. Le guide explique la configuration sécurisée avant le lancement du service.', `autocomplete="off" ${locked}`)}</div>${settingField('archive_root', 'Dossier des documents sur le Mac', s.archive_root, clients().length ? 'La racine est fixée pour préserver les liens existants. Une migration nécessite un nouvel espace.' : 'Choisissez un dossier local que votre outil cloud synchronise déjà, si nécessaire.', locked)}${settingField('client_folder_pattern', 'Nom des dossiers clients', s.client_folder_pattern || '{name}', 'Utilisez {name} une seule fois, sans séparateur de chemin. Exemple : Client - {name}.', 'required')}<div class="dialog-note">Les règles d’expéditeur se configurent dans Apple Mail. Auto-secrétaire surveille le dossier dans lequel le mail arrive.</div></fieldset><fieldset class="form-section"><legend>Nom des documents</legend><div class="form-grid">${selectField('date_source', 'Date à utiliser', s.date_source, [['received','Date de réception'],['sent','Date d’envoi du mail']])}${selectField('prefix_format', 'Préfixe chronologique', s.prefix_format, [['%Y-%m-%d','AAAA-MM-JJ - nom du document'],['%Y%m%d','AAAAMMJJ - nom du document']])}</div><div class="path-preview" id="naming-preview"></div><p class="dialog-note">Ces réglages s’appliquent aux prochains exports. Le nom d’origine est conservé après le préfixe.</p></fieldset><fieldset class="form-section"><legend>Impression</legend>${selectField('print_policy', 'Quand imprimer les nouveaux mails ?', s.print_policy, [['manual','À ma demande'],['after_classify','Après leur classement'],['after_export','Dès que les fichiers sont exportés']])}<div class="field-row">${settingField('printer', 'Imprimante', s.printer, 'Choisissez le nom exact d’une imprimante du Mac ; nécessaire pour l’impression réelle.', 'list="printers-list" autocomplete="off"')}<button type="button" class="button" data-action="refresh-printers">Rechercher</button></div><datalist id="printers-list">${(model.state?.printers || []).map(p => `<option value="${escape(p)}"></option>`).join('')}</datalist><div class="form-grid">${selectField('print_sides', 'Faces à imprimer', s.print_sides || 'printer', [['printer','Réglage de l’imprimante'],['one-sided','Recto seul'],['two-sided-long-edge','Recto verso · bord long (livre)'],['two-sided-short-edge','Recto verso · bord court (bloc-notes)']])}${selectField('print_color_mode', 'Couleur', s.print_color_mode || 'printer', [['printer','Réglage de l’imprimante'],['monochrome','Noir et blanc'],['color','Couleur']])}</div><p class="dialog-note">Ces choix s’appliquent aux prochaines impressions du mail et des pièces jointes cochées, selon les capacités de l’imprimante. Chaque document est imprimé séparément ; le recto verso concerne ses propres pages. Les fichiers archivés restent inchangés.</p><label class="checkbox-field"><input name="dry_run" type="checkbox" ${s.dry_run ? 'checked' : ''}><span>Simuler les impressions<small>Aucun papier n’est imprimé tant que cette option est activée.</small></span></label><label class="checkbox-field"><input name="print_attachments" type="checkbox" ${s.print_attachments ? 'checked' : ''}><span>Inclure les pièces jointes imprimables<small>Sélectionne les pièces jointes PDF, images et textes compatibles lors des prochains exports. Les images intégrées restent décochées par défaut ; les formats Word/Excel ne sont pas imprimables ici. Pour un mail déjà présent, utilisez les cases de chaque document.</small></span></label><p class="dialog-note">Le PDF du mail est coché par défaut. Dans le détail d’un mail, vous pouvez cocher ou décocher séparément son PDF et chaque pièce jointe imprimable.</p><p class="dialog-note">Les mails présents lors de la première relève sont historiques : ils ne sont jamais imprimés automatiquement. Une impression incertaine nécessite votre vérification.</p></fieldset><fieldset class="form-section"><legend>Relève automatique</legend>${settingField('poll_seconds', 'Intervalle entre les contrôles (secondes)', s.poll_seconds || 60, 'De 15 à 3 600 secondes. Le Mac doit rester allumé et le service lancé.', 'type="number" min="15" max="3600" required')}</fieldset></form>`, '<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" type="submit" form="settings-form">Enregistrer les réglages</button>', true);
    settingsVisibility(); namingPreview();
  }
  function settingsVisibility() {
    const source = $('[name="connector"]', modal)?.value;
    $('#apple-settings')?.classList.toggle('hidden', source !== 'apple_mail');
    $('#imap-settings')?.classList.toggle('hidden', source !== 'imap');
  }
  function namingPreview() {
    const prefix = $('[name="prefix_format"]', modal)?.value;
    const stamp = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Paris', year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const preview = $('#naming-preview');
    if (preview) preview.innerHTML = `<b>Aperçu</b> · ${escape(prefix === '%Y%m%d' ? stamp.replaceAll('-', '') : stamp)} - Nom du document.pdf`;
  }
  async function openHistory() {
    const client = currentClient();
    if (!client) throw new Error('Ouvrez d’abord le dossier d’un client.');
    modal.dataset.kind = 'history';
    openModal('Retrouver les PDF existants', `Associez explicitement les archives déjà présentes dans le dossier de ${client.name}.`, '<div id="history-content"><div class="empty-state"><span class="spinner"></span><p>Recherche des PDF non suivis…</p></div></div>', '<button class="button" data-action="close-modal">Fermer</button>', true);
    const result = await api(`/api/clients/${encodeURIComponent(client.id)}/history`);
    if (!modal.open || modal.dataset.kind !== 'history') return;
    model.history = result.candidates || [];
    const list = messages().filter(m => m.client_id === client.id);
    $('#history-content').innerHTML = `<p class="dialog-note">${escape(result.note || 'Les correspondances ne sont jamais devinées. Vérifiez le PDF et choisissez le mail auquel il appartient.')}</p>${model.history.length ? `<label class="field"><span>Mail auquel associer le PDF</span><select id="history-message"><option value="">Sélectionner une communication…</option>${list.map(m => `<option value="${escape(m.id)}" ${m.id === model.active ? 'selected' : ''}>${escape(dateLabel(m.date))} · ${escape(m.subject || 'Sans objet')}</option>`).join('')}</select></label><div class="history-list">${model.history.map((c,index) => `<div class="history-row"><span class="document-icon">PDF</span><div><p>${escape(c.name || leaf(c.path))}</p><small>${escape(c.path)} · ${Math.ceil((c.size || 0) / 1024)} Ko</small></div><button class="button small" data-action="associate-history" data-index="${index}">Associer…</button></div>`).join('')}</div>` : empty('Aucun PDF à rapprocher.', 'Les PDF du dossier sont déjà suivis, ou aucun ancien fichier n’a été trouvé.')}`;
  }
  function openPreview(id) {
    const doc = messages().flatMap(m => m.documents || []).find(d => d.id === id);
    if (!doc) throw new Error('Ce document est introuvable. Actualisez l’espace.');
    const file = `/api/documents/${encodeURIComponent(id)}/file`;
    const name = doc.name || leaf(doc.path) || doc.original_name || 'Document';
    const isPDF = /\.pdf$/i.test(name);
    const isImage = /\.(png|jpe?g|gif|webp)$/i.test(name);
    modal.dataset.kind = 'preview';
    openModal(name, doc.path || '', `<div class="preview-tools"><button class="button small" data-action="reveal" data-id="${escape(id)}">Afficher dans le Finder</button><a class="button small" href="${file}?download=true" download>Télécharger</a></div>${isPDF ? `<iframe class="pdf-preview" title="Aperçu du PDF ${escape(name)}" src="${file}"></iframe>` : isImage ? `<img src="${file}" alt="${escape(name)}" style="max-width:100%;max-height:60dvh;display:block;margin:auto">` : empty('Ce format s’ouvre dans son application.', 'Le fichier original est conservé. Téléchargez-le ou affichez-le dans le Finder pour le consulter.')}`, '<button class="button" data-action="close-modal">Fermer</button>', true);
  }
  function openReprint(id) {
    const m = messages().find(message => message.id === id);
    if (!m) return;
    modal.dataset.kind = 'reprint';
    openModal('Lancer une nouvelle impression ?', 'Cette action crée une nouvelle soumission, même si le document a déjà été envoyé à l’imprimante.', `<div class="notice warning"><span>${m.print_status === 'uncertain' ? 'Le résultat précédent est incertain. Vérifiez d’abord la file de l’imprimante et les feuilles déjà sorties.' : 'Vérifiez que vous avez besoin d’un nouvel exemplaire avant de continuer.'}</span></div><p class="dialog-note">${escape(m.subject || 'Sans objet')}</p><label class="checkbox-field"><input id="reprint-confirm" type="checkbox"><span>J’ai vérifié et je souhaite une nouvelle impression.</span></label>`, `<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" id="reprint-submit" data-action="confirm-reprint" data-id="${escape(id)}" disabled>Réimprimer</button>`);
  }
  function storedUpdate() {
    try {
      const item = JSON.parse(sessionStorage.getItem('autosecretaire.update') || 'null');
      return item && typeof item.target === 'string' && /^[a-f0-9]{40,64}$/i.test(item.target) ? item : null;
    } catch (_) { return null; }
  }
  function saveUpdateIntent(intent) {
    updateMonitor.intent = intent;
    try {
      if (intent) sessionStorage.setItem('autosecretaire.update', JSON.stringify(intent));
      else sessionStorage.removeItem('autosecretaire.update');
    } catch (_) { /* Reconnection still works if session storage is unavailable. */ }
  }
  function expectedUpdateRestart() { return !!updateMonitor.intent || UPDATE_RESTART.has(updateMonitor.state?.status); }
  function updatesLocked() { return expectedUpdateRestart(); }
  function scheduleUpdatePoll(delay) {
    clearTimeout(updateMonitor.timer);
    const active = expectedUpdateRestart() || UPDATE_BUSY.has(updateMonitor.state?.status);
    const open = modal.open && modal.dataset.kind === 'updates';
    if (!active && !open) return;
    updateMonitor.timer = setTimeout(pollUpdates, delay ?? (active ? 1500 : 5000));
  }
  function reloadUpdatedInterface() {
    if (updateMonitor.reloading) return;
    updateMonitor.reloading = true;
    saveUpdateIntent(null);
    try { sessionStorage.setItem('autosecretaire.reopen-updates', '1'); } catch (_) { /* Optional UI restoration. */ }
    window.location.reload();
  }
  function acceptUpdateState(next) {
    if (!next || typeof next.status !== 'string') return;
    updateMonitor.state = next;
    updateMonitor.offline = false; updateMonitor.disconnectedAt = 0;
    if (model.state) model.state.updates = next;
    const recovery = updateRecovery(next, updateMonitor.intent);
    if (recovery.reload) { reloadUpdatedInterface(); return; }
    if (recovery.intent !== updateMonitor.intent) saveUpdateIntent(recovery.intent);
    if (recovery.notice) updateMonitor.notice = recovery.notice;
    renderUpdateControls(); scheduleUpdatePoll();
  }
  function markUpdateOffline() {
    updateMonitor.offline = true;
    if (!updateMonitor.disconnectedAt) updateMonitor.disconnectedAt = Date.now();
    if (updateMonitor.intent) saveUpdateIntent({...updateMonitor.intent, hadDisconnection: true, sawRestart: updateMonitor.intent.sawRestart || updateMonitor.state?.status === 'restarting'});
    $('#connection-dot').classList.add('offline');
    $('#connection-label').innerHTML = expectedUpdateRestart() ? 'Reconnexion en cours<small>Mise à jour du service</small>' : 'Service déconnecté<small>Nouvel essai automatique</small>';
    renderUpdateControls(); scheduleUpdatePoll(1500);
  }
  async function pollUpdates() {
    if (updateMonitor.polling || updateMonitor.reloading) return;
    updateMonitor.polling = true;
    try {
      const next = await api('/api/updates');
      const wasDisconnected = updateMonitor.offline || disconnected;
      const restartFinished = expectedUpdateRestart() && !UPDATE_RESTART.has(next.status);
      if (wasDisconnected || restartFinished) {
        // Fetch a fresh session before enabling any mutation against the restarted worker.
        const fresh = await api('/api/state');
        if (!fresh.csrf_token || !Array.isArray(fresh.clients) || !Array.isArray(fresh.messages)) throw new Error('La reconnexion n’est pas encore prête.');
        model.state = fresh; disconnected = false;
        acceptUpdateState(fresh.updates || next);
        if (!updateMonitor.reloading) render();
      } else acceptUpdateState(next);
      updateMonitor.connectionError = '';
      renderUpdateControls();
    } catch (error) {
      updateMonitor.connectionError = expectedUpdateRestart() ? '' : error.message;
      markUpdateOffline();
    } finally { updateMonitor.polling = false; scheduleUpdatePoll(updateMonitor.offline ? 2000 : undefined); }
  }
  function renderUpdateControls() {
    const state = updateMonitor.state;
    const stalled = updateMonitor.offline && Date.now() - updateMonitor.disconnectedAt > 120000;
    const view = updateView(state, {offline: updateMonitor.offline, stalled});
    const active = updatesLocked();
    $('#updates-dot')?.classList.toggle('hidden', view.status !== 'available');
    $('#update-available-button')?.classList.toggle('hidden', view.status !== 'available' || active);
    const banner = $('#update-banner');
    if (banner) {
      banner.classList.toggle('hidden', !active);
      banner.innerHTML = `<span>${updateMonitor.offline ? 'Le service redémarre. Cette page se reconnectera automatiquement.' : 'Mise à jour en cours. Le classement et les réglages seront disponibles après le redémarrage.'}</span><button class="button quiet small" data-action="updates">Voir l’avancement</button>`;
    }
    $$('[data-action="sync"], [data-action="process"], [data-action="new-client"], [data-action="classify"], [data-action="print"], [data-action="reprint"]').forEach(button => {
      if (active) {
        if (!('updateWasDisabled' in button.dataset)) button.dataset.updateWasDisabled = String(button.disabled);
        button.disabled = true;
      } else if ('updateWasDisabled' in button.dataset) {
        button.disabled = button.dataset.updateWasDisabled === 'true'; delete button.dataset.updateWasDisabled;
      }
    });
    if (!modal.open || modal.dataset.kind !== 'updates') return;
    const panel = $('#update-status-panel');
    if (!panel) return;
    const progress = typeof state?.progress === 'string' ? state.progress : '';
    const error = state?.error || updateMonitor.connectionError || '';
    const stages = ['Vérification', 'Préparation', 'Redémarrage'];
    const stageIndex = view.status === 'checking' ? 0 : view.status === 'installing' ? 1 : view.status === 'restarting' || updateMonitor.offline && active ? 2 : ['updated', 'current'].includes(view.status) ? 3 : -1;
    const loading = view.busy || active;
    const icon = loading ? '<span class="spinner" aria-hidden="true"></span>' : `<span aria-hidden="true">${view.tone === 'success' ? '✓' : view.tone === 'error' ? '!' : '↻'}</span>`;
    const headline = !state ? 'Connexion au service de mise à jour…' : view.title;
    const content = `<div class="update-state ${view.tone}"><div class="update-state-icon">${icon}</div><div><h3>${escape(headline)}</h3><p>${escape(view.description)}</p></div></div>${loading ? `<ol class="update-steps" aria-label="Étapes de la mise à jour">${stages.map((name, i) => `<li class="${i < stageIndex ? 'done' : i === stageIndex ? 'active' : ''}" ${i === stageIndex ? 'aria-current="step"' : ''}><span>${i < stageIndex ? '✓' : i + 1}</span>${name}</li>`).join('')}</ol>` : ''}${progress ? `<p class="update-progress" role="status">${escape(progress)}</p>` : ''}${error ? `<div class="form-error" role="alert">${escape(error)}</div>` : ''}${updateMonitor.notice ? `<p class="dialog-note">${escape(updateMonitor.notice)}</p>` : ''}${state?.managed === false ? '<div class="notice warning"><span>La mise à jour en un clic n’est pas activée pour ce lancement. Utilisez le lanceur Auto-secrétaire installé sur le Mac pour l’activer.</span></div>' : ''}<div class="update-version-grid"><div><span>Version installée</span><strong title="${escape(state?.current_commit || '')}">${escape(state?.current_commit?.slice(0, 10) || 'Non identifiée')}</strong></div><div><span>Version publiée</span><strong title="${escape(state?.available_commit || '')}">${escape(state?.available_commit?.slice(0, 10) || 'À vérifier')}</strong></div></div><div class="update-action-row"><span class="subtle small">${state?.checked_at ? `Vérifié le ${escape(dateLabel(state.checked_at, true))}` : 'Aucune vérification pour le moment'}</span><div>${updateMonitor.offline ? '<button class="button small" data-action="updates-reconnect">Réessayer la connexion</button>' : `<button class="button small" data-action="updates-check" ${!view.canCheck || active ? 'disabled' : ''}>Vérifier les versions</button>${view.status === 'available' ? `<button class="button primary small" data-action="updates-install" data-commit="${escape(state.available_commit)}" ${!view.canInstall || active ? 'disabled' : ''}>Mettre à jour</button>` : ''}`}</div></div>`;
    if (panel.dataset.content !== content) { panel.innerHTML = content; panel.dataset.content = content; }
    $$('#updates-config-form input, #updates-config-form button').forEach(control => { control.disabled = view.busy || active; });
    const form = $('#updates-config-form');
    if (form) {
      form.setAttribute('aria-busy', String(view.busy || active));
      if (state && form.dataset.seeded !== 'true' && form.dataset.edited !== 'true') {
        $('[name="repository"]', form).value = state.repository || '';
        $('[name="branch"]', form).value = state.branch || 'main';
        form.dataset.seeded = 'true';
        if (state.repository) $('.update-config', modal).open = false;
      }
    }
  }
  function openUpdates() {
    if (modal.open && modal.dataset.kind === 'updates') { renderUpdateControls(); scheduleUpdatePoll(0); return; }
    const state = updateMonitor.state || model.state?.updates;
    modal.dataset.kind = 'updates';
    openModal('Mises à jour d’Auto-secrétaire', 'Les versions publiées sont vérifiées automatiquement. Vous choisissez quand les installer.', `<section id="update-status-panel" aria-label="État de la mise à jour" aria-live="polite"></section><details class="update-config" ${!state?.repository ? 'open' : ''}><summary>Source des mises à jour</summary><form id="updates-config-form"><label class="field"><span>Dépôt du projet</span><input name="repository" type="text" value="${escape(state?.repository || '')}" placeholder="https://github.com/organisation/auto-secretaire.git" required autocomplete="off" autocapitalize="off" spellcheck="false"><small>Adresse HTTPS ou SSH fournie par le mainteneur. N’incluez aucun mot de passe ni jeton d’accès dans cette adresse.</small></label><label class="field"><span>Branche publiée</span><input name="branch" value="${escape(state?.branch || 'main')}" required autocomplete="off" autocapitalize="off" spellcheck="false"><small>Gardez « main », sauf indication du mainteneur.</small></label><p class="dialog-note">Choisissez uniquement le dépôt de confiance fourni pour ce logiciel. L’accès à un dépôt privé se prépare une fois sur le Mac.</p><button class="button" type="submit">Enregistrer la source</button></form></details>`, '<button class="button quiet" data-action="close-modal">Fermer</button>');
    $('#updates-config-form').dataset.seeded = String(!!state);
    renderUpdateControls(); scheduleUpdatePoll(0);
  }
  async function beginUpdate(button) {
    const commit = button.dataset.commit;
    const view = updateView(updateMonitor.state, {offline: updateMonitor.offline});
    if (!view.canInstall || commit !== updateMonitor.state?.available_commit) throw new Error('Vérifiez de nouveau la version disponible avant de l’installer.');
    updateMonitor.notice = '';
    saveUpdateIntent({target: commit, startedAt: Date.now(), sawRestart: false, accepted: false});
    renderUpdateControls();
    try {
      const next = await api('/api/updates/install', 'POST', {commit});
      if (updateMonitor.intent) saveUpdateIntent({...updateMonitor.intent, accepted: true});
      acceptUpdateState(next);
    } catch (error) {
      if (error.networkUnavailable) {
        // The worker may already be restarting: observe its state, never resubmit this request.
        markUpdateOffline();
      } else {
        saveUpdateIntent(null); renderUpdateControls(); throw error;
      }
    }
    scheduleUpdatePoll(500);
  }

  function shortcuts() {
    modal.dataset.kind = 'shortcuts';
    openModal('Quelques raccourcis utiles', 'Ils sont actifs en dehors des champs de saisie.', '<dl class="shortcuts-list"><dt><kbd>/</kbd></dt><dd>Rechercher un client</dd><dt><kbd>J</kbd> / <kbd>K</kbd></dt><dd>Communication suivante / précédente</dd><dt><kbd>C</kbd></dt><dd>Choisir le dossier de destination</dd><dt><kbd>Espace</kbd></dt><dd>Ajouter ou retirer le mail de la sélection</dd><dt><kbd>⌘</kbd> + clic</dt><dd>Sélectionner plusieurs mails du même client</dd><dt><kbd>Échap</kbd></dt><dd>Fermer un dialogue ou vider la sélection</dd></dl>', '<button class="button" data-action="close-modal">Compris</button>');
  }
  function chooseClient(id) { model.client = id; model.active = null; model.selected.clear(); model.query = ''; $('#message-search').value = ''; model.filter = 'all'; render(); }
  function selectMessage(id, extend = false) {
    const m = messages().find(message => message.id === id);
    if (!m) return;
    if (extend) {
      const first = messages().find(message => model.selected.has(message.id));
      if (first && first.client_id !== m.client_id) { toast('Sélectionnez les mails d’un même client pour les actions groupées.', true); return; }
      if (model.selected.has(id)) model.selected.delete(id); else model.selected.add(id);
    }
    if (!extend) model.selected.clear();
    model.active = id; renderMessages(); renderDetail();
  }

  const actions = {
    updates: openUpdates,
    'updates-reconnect': pollUpdates,
    'updates-check': async () => {
      updateMonitor.notice = '';
      acceptUpdateState(await api('/api/updates/check', 'POST', {}));
      scheduleUpdatePoll(500);
    },
    'updates-install': beginUpdate,
    'all-clients': () => chooseClient(null),
    client: button => chooseClient(button.dataset.id),
    'new-client': newClient,
    template: openTemplate,
    settings: openSettings,
    shortcuts,
    'close-modal': closeModal,
    refresh: () => refresh({notify: true}),
    sync: async () => { await api('/api/sync', 'POST', {}); await refresh(); toast(model.state?.sync_error ? 'La relève a rencontré une erreur. Consultez le message affiché.' : 'Relève terminée. Votre espace est à jour.'); },
    process: async () => { await api('/api/process', 'POST', {}); await refresh(); toast('Contrôle terminé. Consultez les états des fichiers.'); },
    'reset-filters': () => { model.filter = 'all'; model.query = ''; $('#message-search').value = ''; renderMessages(); renderDetail(); },
    'clear-selection': () => { model.selected.clear(); renderMessages(); },
    'retry-client': async button => { await api(`/api/clients/${encodeURIComponent(button.dataset.id)}/retry`, 'POST', {}); await refresh(); toast('La création du client a été reprise.'); },
    classify: openClassify,
    'choose-folder': button => { model.destination = button.dataset.folder; renderFolders(); },
    'confirm-classify': async () => {
      if (!model.destination) throw new Error('Choisissez un dossier.');
      const ids = JSON.parse(modal.dataset.messages || '[]');
      await api('/api/classify', 'POST', {message_ids: ids, destination: model.destination});
      rememberFolder(modal.dataset.client, model.destination); closeModal(); model.selected.clear(); await refresh(); toast(`${ids.length} communication${ids.length > 1 ? 's' : ''} classée${ids.length > 1 ? 's' : ''}.`);
    },
    favorite: async button => {
      const client = clients().find(c => c.id === modal.dataset.client);
      if (!client) return;
      const favorites = new Set(client.favorites || []);
      if (favorites.has(button.dataset.folder)) favorites.delete(button.dataset.folder); else favorites.add(button.dataset.folder);
      const updated = await api(`/api/clients/${encodeURIComponent(client.id)}/favorites`, 'PUT', {folders: [...favorites]});
      Object.assign(client, updated); renderFolders();
    },
    print: async () => {
      const list = selectedMessages();
      if (!list.length) throw new Error('Sélectionnez d’abord une communication.');
      if (list.some(m => m.status !== 'ready')) throw new Error('Attendez la fin de l’export avant d’imprimer.');
      await api('/api/print', 'POST', {message_ids: list.map(m => m.id)}); await refresh();
      toast(model.state?.settings?.dry_run ? 'Demande simulée. Consultez les états d’impression.' : 'Demande traitée. Consultez les états d’impression.');
    },
    reprint: button => openReprint(button.dataset.id),
    'confirm-reprint': async button => { if (!$('#reprint-confirm')?.checked) return; await api(`/api/messages/${encodeURIComponent(button.dataset.id)}/reprint`, 'POST', {confirm: true}); closeModal(); await refresh(); toast('Nouvelle demande d’impression traitée.'); },
    reveal: async button => { await api(`/api/documents/${encodeURIComponent(button.dataset.id)}/reveal`, 'POST', {}); toast('Document révélé dans le Finder.'); },
    preview: button => openPreview(button.dataset.id),
    'refresh-folders': async () => {
      const result = await api('/api/folders'); model.state.folders = result.folders || [];
      const select = $('#mailbox-select');
      if (select) { const previous = select.value; select.innerHTML = '<option value="">Choisir un dossier…</option>' + model.state.folders.map(f => `<option value="${escape(f)}">${escape(f)}</option>`).join(''); select.value = previous; clientPreview(); }
      toast(`${model.state.folders.length} dossier${model.state.folders.length > 1 ? 's' : ''} trouvé${model.state.folders.length > 1 ? 's' : ''}.`);
    },
    'refresh-printers': async () => {
      const result = await api('/api/printers'); model.state.printers = result.printers || [];
      const list = $('#printers-list');
      if (list) list.innerHTML = model.state.printers.map(p => `<option value="${escape(p)}"></option>`).join('');
      toast(model.state.printers.length ? `${model.state.printers.length} imprimante${model.state.printers.length > 1 ? 's' : ''} trouvée${model.state.printers.length > 1 ? 's' : ''}.` : 'Aucune imprimante détectée. Vérifiez les réglages du Mac.');
    },
    'template-select': button => { model.templateSelected = button.dataset.folder; renderTemplate(); },
    'template-add-root': () => addTemplate(),
    'template-add-child': button => addTemplate(button.dataset.folder),
    'template-update': () => {
      const name = $('#template-name')?.value.trim();
      if (!name || name.includes('/')) throw new Error('Utilisez un nom de dossier simple, sans barre oblique.');
      const parent = $('#template-parent').value;
      const next = parent ? `${parent}/${name}` : name;
      model.template = changeBranch(model.template, model.templateSelected, next); model.templateSelected = next; model.templateDirty = true; renderTemplate();
    },
    'template-copy': () => {
      const path = model.templateSelected;
      let next = path + ' - copie'; let n = 2;
      while (model.template.includes(next)) next = `${path} - copie ${n++}`;
      model.template = changeBranch(model.template, path, next, true); model.templateSelected = next; model.templateDirty = true; renderTemplate();
    },
    'template-remove': () => {
      const path = model.templateSelected;
      if (!window.confirm(`Retirer « ${path} » et ses sous-dossiers du modèle ? Les dossiers des clients existants seront conservés.`)) return;
      model.template = model.template.filter(f => f !== path && !f.startsWith(path + '/')); model.templateSelected = null; model.templateDirty = true; renderTemplate();
    },
    'save-template': saveTemplate,
    'apply-template': async () => {
      if (model.templateDirty) throw new Error('Enregistrez d’abord les modifications du modèle.');
      const id = $('#template-client')?.value;
      if (!id) throw new Error('Sélectionnez un client.');
      await api(`/api/clients/${encodeURIComponent(id)}/template`, 'POST', {}); await refresh(); toast('Les dossiers manquants ont été ajoutés. Les fichiers existants sont conservés.');
    },
    history: openHistory,
    'associate-history': async button => {
      const id = $('#history-message')?.value;
      const candidate = model.history[Number(button.dataset.index)];
      if (!id) throw new Error('Choisissez le mail correspondant à ce PDF.');
      if (!candidate) throw new Error('Le PDF choisi n’est plus disponible.');
      if (!window.confirm(`Associer « ${candidate.name || leaf(candidate.path)} » au mail sélectionné ? Aucune impression ne sera lancée.`)) return;
      await api('/api/history/associate', 'POST', {message_id: id, path: candidate.path}); await refresh(); await openHistory(); toast('PDF associé au mail.');
    }
  };

  document.addEventListener('click', event => {
    const filter = event.target.closest('[data-filter]');
    if (filter) { model.filter = filter.dataset.filter; model.selected.clear(); renderMessages(); renderDetail(); return; }
    const button = event.target.closest('[data-action]');
    if (button && !button.disabled) {
      const handler = actions[button.dataset.action];
      if (handler) { event.preventDefault(); action(button.dataset.action, () => handler(button), button); }
      return;
    }
    const row = event.target.closest('[data-message]');
    if (row && !event.target.closest('input')) selectMessage(row.dataset.message, event.metaKey || event.ctrlKey);
  });
  document.addEventListener('input', event => {
    const element = event.target;
    if (element.closest('#updates-config-form')) $('#updates-config-form').dataset.edited = 'true';
    if (element.id === 'client-search') { model.clientQuery = element.value; renderClients(); }
    if (element.id === 'message-search') { model.query = element.value; renderMessages(); renderDetail(); }
    if (element.id === 'client-name') clientPreview();
    if (element.id === 'folder-search') { model.foldersQuery = element.value; renderFolders(); }
  });
  document.addEventListener('change', event => {
    const element = event.target;
    if (element.dataset.select) { selectMessage(element.dataset.select, true); return; }
    if (element.id === 'select-all') {
      const list = visibleMessages();
      if (new Set(list.map(m => m.client_id)).size > 1) { element.checked = false; toast('Ouvrez un client pour sélectionner tous ses mails.', true); return; }
      model.selected = element.checked ? new Set(list.map(m => m.id)) : new Set(); renderMessages(); return;
    }
    if (element.dataset.documentSelect) {
      action('document-select', async () => { await api(`/api/documents/${encodeURIComponent(element.dataset.documentSelect)}`, 'PUT', {selected: element.checked}); await refresh(); }, element).then(() => renderDetail()); return;
    }
    if (element.name === 'mailbox_mode') { $('#existing-mailbox').classList.toggle('hidden', element.value !== 'existing'); clientPreview(); }
    if (element.id === 'mailbox-select') clientPreview();
    if (element.name === 'connector') settingsVisibility();
    if (element.name === 'prefix_format') namingPreview();
    if (element.id === 'reprint-confirm') $('#reprint-submit').disabled = !element.checked;
  });
  document.addEventListener('submit', event => {
    if (event.target.id === 'updates-config-form') {
      event.preventDefault();
      action('updates-config', async () => {
        const data = new FormData(event.target);
        const repository = String(data.get('repository') || '').trim();
        const branch = String(data.get('branch') || 'main').trim();
        acceptUpdateState(await api('/api/updates/config', 'PUT', {repository, branch}));
        toast('Source enregistrée. Vous pouvez vérifier les versions.');
        scheduleUpdatePoll(500);
      }, event.submitter);
    }
    if (event.target.id === 'client-form') {
      event.preventDefault();
      action('create-client', async () => {
        const data = new FormData(event.target);
        const name = String(data.get('name') || '').trim();
        const existing = data.get('mailbox_mode') === 'existing';
        const mailbox = existing ? String(data.get('mailbox') || '') : '';
        if (existing && !mailbox) throw new Error('Sélectionnez le dossier mail existant, ou actualisez la liste.');
        const client = await api('/api/clients', 'POST', {name, mailbox});
        closeModal(); model.client = client.id; model.selected.clear(); model.filter = 'all'; await refresh();
        toast(client.status === 'ready' ? 'Client créé. Ses dossiers sont prêts.' : 'Client enregistré. Sa préparation doit être reprise.');
      }, event.submitter);
    }
    if (event.target.id === 'settings-form') {
      event.preventDefault();
      action('save-settings', async () => {
        const data = new FormData(event.target);
        const settings = Object.fromEntries(data.entries());
        for (const key of ['poll_seconds', 'imap_port']) if (key in settings) settings[key] = Number(settings[key]);
        settings.dry_run = data.has('dry_run'); settings.print_attachments = data.has('print_attachments');
        await api('/api/settings', 'PUT', settings); closeModal(); await refresh(); toast('Réglages enregistrés.');
      }, event.submitter);
    }
  });
  document.addEventListener('keydown', event => {
    const input = event.target.closest('input,textarea,select,[contenteditable=true]');
    if (modal.open) {
      if (modal.dataset.kind === 'classify' && event.key === 'Enter' && !event.target.closest('button')) { event.preventDefault(); $('#classify-confirm')?.click(); }
      return;
    }
    if (input || event.altKey || event.metaKey || event.ctrlKey) return;
    if (event.key === '/') { event.preventDefault(); $('#client-search').focus(); }
    if (event.key.toLowerCase() === 'c' && model.active) { event.preventDefault(); action('classify', openClassify); }
    if (['j','k'].includes(event.key.toLowerCase())) {
      const list = visibleMessages(); const at = list.findIndex(m => m.id === model.active);
      const next = list[Math.max(0, Math.min(list.length - 1, at + (event.key.toLowerCase() === 'j' ? 1 : -1)))];
      if (next) { event.preventDefault(); selectMessage(next.id); $$('.message-row').find(row => row.dataset.message === next.id)?.scrollIntoView({block: 'nearest'}); }
    }
    if (event.key === ' ' && model.active && !event.target.closest('button,a')) { event.preventDefault(); selectMessage(model.active, true); }
    if (event.key === 'Escape') { model.selected.clear(); renderMessages(); }
    if (event.key === 'Enter') { const row = event.target.closest('[data-message]'); if (row) selectMessage(row.dataset.message, event.metaKey || event.ctrlKey); }
  });
  let draggedPath = '';
  document.addEventListener('dragstart', event => {
    const node = event.target.closest('.template-node');
    if (!node) return;
    draggedPath = node.dataset.path;
    event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', draggedPath);
  });
  document.addEventListener('dragover', event => { const node = event.target.closest('.template-node'); if (node && draggedPath) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; node.classList.add('drag-over'); } });
  document.addEventListener('dragleave', event => event.target.closest('.template-node')?.classList.remove('drag-over'));
  document.addEventListener('dragend', () => { draggedPath = ''; $$('.drag-over').forEach(node => node.classList.remove('drag-over')); });
  document.addEventListener('drop', event => {
    const node = event.target.closest('.template-node');
    if (!node || !draggedPath) return;
    event.preventDefault();
    action('template-drop', () => {
      const next = `${node.dataset.path}/${leaf(draggedPath)}`;
      model.template = changeBranch(model.template, draggedPath, next); model.templateSelected = next; model.templateDirty = true; draggedPath = ''; renderTemplate();
    });
  });
  updateMonitor.intent = storedUpdate();
  let reopenUpdates = !!updateMonitor.intent;
  try { reopenUpdates ||= sessionStorage.getItem('autosecretaire.reopen-updates') === '1'; sessionStorage.removeItem('autosecretaire.reopen-updates'); } catch (_) { /* Optional restoration. */ }
  if (reopenUpdates) openUpdates();
  refresh();
  setInterval(() => { if (!document.hidden && !model.busy.size && !modal.open) refresh({quiet: true}); }, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { if (expectedUpdateRestart() || modal.dataset.kind === 'updates') scheduleUpdatePoll(0); if (!modal.open) refresh(); } });
})();
