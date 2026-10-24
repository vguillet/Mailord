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
  const searchKey = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr');
  function messageMatches(message, query, clientName = '') {
    const q = searchKey(query.trim());
    return !q || searchKey([message.subject, message.sender, message.body, clientName,
      ...(message.documents || []).flatMap(d => [d.original_name, d.name, d.destination])].join(' ')).includes(q);
  }
  function folderEntries(folders, query = '', expanded = []) {
    const all = sortFolders(folders);
    const q = searchKey(query.trim());
    const open = new Set(expanded);
    const matches = all.filter(path => searchKey(path).includes(q));
    return all.filter(path => {
      if (q) return matches.some(match => match === path || match.startsWith(path + '/'));
      for (let parent = parentPath(path); parent; parent = parentPath(parent)) if (!open.has(parent)) return false;
      return true;
    }).map(path => ({path, depth: path.split('/').length - 1, hasChildren: all.some(other => other.startsWith(path + '/')), expanded: !!q || open.has(path)}));
  }
  const sortClients = items => [...items].sort((a, b) => Number(b.starred === true) - Number(a.starred === true) || a.name.localeCompare(b.name, 'fr'));
  function documentPrintView(doc, jobs = []) {
    const own = jobs.filter(job => job.document_id === doc.id);
    const latest = own[own.length - 1];
    const reprint = own.some(job => ['submitted', 'simulated', 'uncertain', 'submitting'].includes(job.status));
    const sending = own.some(job => job.status === 'submitting');
    const status = latest?.status || 'pending';
    const description = {pending: 'Pas encore imprimé', preparing: 'Préparation en cours', submitting: 'Envoi en cours…', submitted: 'Envoyé à l’imprimante', simulated: 'Impression simulée', uncertain: 'Impression à vérifier', error: 'Échec de l’impression'};
    return {reprint, disabled: !doc.printable || sending, label: !doc.printable ? 'Format non imprimable' : sending ? 'Envoi en cours…' : reprint ? 'Réimprimer…' : status === 'error' ? 'Réessayer' : 'Imprimer', status, description: doc.printable ? description[status] || 'État à vérifier' : 'Format non imprimable ici', tone: ['uncertain', 'error'].includes(status) ? 'error' : '', error: latest?.error || ''};
  }
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
  if (typeof module !== 'undefined' && module.exports) module.exports = {escape, sortClients, documentPrintView, messageMatches, folderEntries, checkedFolder, withParents, changeBranch, updateView, updateRecovery, sessionRequest};
  if (typeof document === 'undefined') return;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const model = {state: null, client: null, active: null, selected: new Set(), filter: 'all', query: '', clientQuery: '', refreshing: false, busy: new Set(), template: [], templateDefaults: [], templateSelected: null, templateDirty: false, templateQuery: '', templateExpanded: new Set(), bodyCollapsed: new Set(), filing: null, recent: {}, history: [], previousFocus: null};
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
    const q = model.query;
    return scopeMessages().filter(m => (model.filter !== 'pending' || m.classification !== 'classified') && (model.filter !== 'error' || needsAttention(m)) && messageMatches(m, q, messageClient(m)?.name)).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }
  function selectedMessages() { const ids = model.selected.size ? model.selected : new Set([model.active]); return messages().filter(m => ids.has(m.id)); }
  function empty(title, description, extra = '') { return `<div class="empty-state"><span class="empty-icon" aria-hidden="true">▤</span><h3>${escape(title)}</h3><p>${escape(description)}</p>${extra}</div>`; }
  function chip(text, tone = '') { return `<span class="chip ${tone}">${escape(text)}</span>`; }
  function printLabel(status) { return ({pending: 'À imprimer', submitted: 'Envoyé à l’imprimante', simulated: 'Impression simulée', uncertain: 'Impression à vérifier', error: 'Erreur d’impression', historical: 'Historique · impression manuelle', partial: 'Impression partielle', mixed: 'Envois et simulations', not_selected: 'Aucun document choisi', preparing: 'Préparation en cours', submitting: 'Envoi en cours…'})[status] || 'À imprimer'; }
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
    const pending = scopeMessages().filter(m => m.classification !== 'classified').length;
    $('#page-title').textContent = client?.name || (pending ? `${pending} mail${pending > 1 ? 's' : ''} à classer` : messages().length ? 'Votre classement est à jour' : 'Votre espace documentaire');
    $('#page-subtitle').textContent = client ? 'Vos communications et documents, réunis dans le dossier de ce client.' : 'Choisissez un mail, puis classez ses documents.';
    $('#list-heading').textContent = client ? 'Communications du client' : 'Toutes les communications';
    $('#client-history').classList.toggle('hidden', !client);
    const notice = $('#context-notice');
    if (client && client.status !== 'ready') {
      notice.className = 'notice warning';
      notice.innerHTML = `<span><b>Création du client à terminer.</b> ${escape(client.error || 'La préparation des dossiers est en cours.')}</span><button class="button small" data-action="retry-client" data-id="${escape(client.id)}">Reprendre</button>`;
    } else if (state.settings?.connector === 'demo') {
      notice.className = 'notice';
      notice.innerHTML = '<span><b>Démonstration</b> · Messages fictifs, documents sur ce Mac.</span><button class="button quiet small" data-action="settings">Configurer ma messagerie ↗</button>';
    } else notice.className = 'notice hidden';
    renderClients(); renderSummary(); renderMessages(); renderDetail(); renderUpdateControls();
    $('#last-scan').textContent = relativeDate(state.last_scan);
  }
  function renderClients() {
    const q = model.clientQuery.toLocaleLowerCase('fr');
    const items = sortClients(clients().filter(c => c.name.toLocaleLowerCase('fr').includes(q)));
    const hasStars = items.some(c => c.starred);
    const focusedStar = document.activeElement?.dataset.action === 'star-client' ? document.activeElement.dataset.id : null;
    $('#client-list').innerHTML = items.length ? items.map((c, index) => {
      const count = messages().filter(m => m.client_id === c.id && m.classification !== 'classified').length;
      const heading = hasStars && (index === 0 || !!c.starred !== !!items[index - 1].starred) ? `<div class="client-group-label">${c.starred ? 'FAVORIS' : 'AUTRES CLIENTS'}</div>` : '';
      return `${heading}<div class="client-entry${model.client === c.id ? ' active' : ''}"><button class="client-item${model.client === c.id ? ' active' : ''}" data-action="client" data-id="${escape(c.id)}" aria-current="${model.client === c.id ? 'page' : 'false'}" title="${escape(c.name)}"><span class="client-initial" aria-hidden="true">${escape(initials(c.name))}</span><span class="client-name">${escape(c.name)}</span>${count ? `<span class="count" title="${count} à classer">${count}</span>` : ''}${c.status === 'error' ? '<span aria-label="Création incomplète">!</span>' : ''}</button><button class="icon-button client-star${c.starred ? ' starred' : ''}" data-action="star-client" data-id="${escape(c.id)}" aria-pressed="${!!c.starred}" title="${c.starred ? 'Retirer des clients favoris' : 'Ajouter aux clients favoris'}" aria-label="${c.starred ? 'Retirer des favoris' : 'Ajouter aux favoris'} : ${escape(c.name)}" ${model.busy.has('star-client:' + c.id) || updatesLocked() ? 'disabled' : ''}>${c.starred ? '★' : '☆'}</button></div>`;
    }).join('') : `<p class="subtle small loading-text">${q ? 'Aucun client ne correspond.' : 'Votre premier client commence ici.'}</p>`;
    if (focusedStar) $$('#client-list [data-action="star-client"]').find(button => button.dataset.id === focusedStar)?.focus({preventScroll: true});
  }
  function renderSummary() {
    const list = scopeMessages();
    const pending = list.filter(m => m.classification !== 'classified').length;
    const archived = list.filter(m => m.status === 'ready').length;
    const documents = list.flatMap(m => m.documents || []);
    const pendingDocuments = documents.filter(d => d.classification !== 'classified' || d.move_to).length;
    const attention = list.filter(needsAttention).length;
    const cards = [
      {label: 'Mails', value: list.length, note: currentClient() ? 'dans ce dossier client' : `${clients().length} client${clients().length > 1 ? 's' : ''} dans votre espace`, icon: '✉', filter: 'all'},
      {label: 'Documents à classer', value: pendingDocuments, note: pending ? `dans ${pending} mail${pending > 1 ? 's' : ''}` : 'classement à jour', icon: '▱', filter: 'pending', tone: 'amber'},
      {label: 'PDF de mails', value: archived, note: 'enregistrés sur ce Mac', icon: '✓', filter: 'all'},
      {label: 'À vérifier', value: attention, note: attention ? 'une action est nécessaire' : 'aucune anomalie', icon: '↻', filter: 'error', tone: attention ? 'error-card' : ''}
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
      return `<article class="message-row${model.active === m.id ? ' active' : ''}${model.selected.has(m.id) ? ' selected' : ''}" data-message="${escape(m.id)}" tabindex="0" aria-label="${escape(m.subject || 'Sans objet')}, ${escape(client?.name || '')}, ${escape(dateLabel(m.date))}" aria-current="${model.active === m.id ? 'true' : 'false'}"><input class="message-checkbox" type="checkbox" data-select="${escape(m.id)}" aria-label="Sélectionner ${escape(m.subject || 'ce mail')}" ${model.selected.has(m.id) ? 'checked' : ''}><span class="mail-avatar" aria-hidden="true">${escape(initials(client?.name || sender))}</span><div class="message-content"><div class="message-row-top"><span class="message-sender">${escape(model.client ? sender : client?.name || sender)}</span><time class="message-time" datetime="${escape(m.date)}">${escape(dateLabel(m.date))}</time></div><p class="message-subject">${escape(m.subject || 'Sans objet')}</p><p class="message-snippet">${escape(m.body?.replace(/\s+/g, ' ').slice(0, 120) || sender)}</p><div class="message-meta">${m.status === 'error' ? chip('Export à reprendre', 'error') : m.status === 'queued' ? chip('Export en attente', 'neutral') : chip('PDF disponible')}${chip(m.classification === 'classified' ? 'Classé' : `À classer · ${docs.filter(d => d.classification !== 'classified' || d.move_to).length}/${docs.length}`, m.classification === 'classified' ? '' : 'pending')}${needsAttention(m) && m.status !== 'error' ? chip('Impression à vérifier', 'error') : ''}${docs.length > 1 ? `<span class="attachment-count">↳ ${docs.length - 1} pièce${docs.length > 2 ? 's' : ''}</span>` : ''}</div></div></article>`;
    }).join('');
  }
  function filingBadge(d) {
    const pending = d.classification !== 'classified' || !!d.move_to;
    return `<span class="filing-status${pending ? ' pending' : ''}">${pending ? 'À classer' : '✓ Classé'}</span>`;
  }
  function documentCard(d, message) {
    const pending = d.classification !== 'classified' || !!d.move_to;
    const open = model.filing?.documentId === d.id;
    const print = documentPrintView(d, message.print_jobs);
    const printBusy = model.busy.has('print-document:' + d.id);
    const printerIcon = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v7H6zM18 12h.01"/></svg>';
    return `<div class="document${pending ? ' pending' : ''}" data-document-id="${escape(d.id)}"><div class="document-row"><span class="document-icon" aria-hidden="true">${escape(d.name.split('.').pop().slice(0, 4).toUpperCase())}</span><div class="document-info"><p class="document-name">${escape(d.name)}</p>${filingBadge(d)}${d.inline ? '<small>Image intégrée au message</small>' : ''}<small class="document-print-status ${print.tone}">${escape(print.description)}${print.error ? ` · ${escape(print.error)}` : ''}</small></div><div class="document-actions"><button class="icon-button" data-action="preview" data-id="${escape(d.id)}" title="Consulter le document" aria-label="Consulter ${escape(d.original_name || d.name)}">↗</button><button class="icon-button" data-action="reveal" data-id="${escape(d.id)}" title="Afficher dans le Finder" aria-label="Afficher dans le Finder">▱</button><button class="icon-button document-print" data-action="print-document" data-id="${escape(d.id)}" title="${escape(print.label)}" aria-label="${escape(print.label)} : ${escape(d.original_name || d.name)}" ${print.disabled || printBusy || message.status !== 'ready' || updatesLocked() ? 'disabled' : ''} ${printBusy ? 'aria-busy="true"' : ''}>${printerIcon}</button></div></div><button class="document-destination" data-action="classify-document" data-id="${escape(d.id)}" aria-expanded="${open}" aria-controls="filing-${escape(d.id)}" ${message.status !== 'ready' ? 'disabled' : ''}><span>${pending ? 'Choisir un dossier…' : `Dossier : ${escape(d.destination || parentPath(d.path))}`}</span><span aria-hidden="true">${open ? '⌃' : '⌄'}</span></button><div id="filing-${escape(d.id)}" class="filing-slot"></div><div class="document-options"><label class="print-inclusion"><input type="checkbox" data-document-select="${escape(d.id)}" aria-label="Inclure ${escape(d.original_name || d.name)} à l’impression automatique ou groupée" ${d.selected ? 'checked' : ''} ${!d.printable ? 'disabled' : ''}><span>Impression auto / groupée</span></label>${d.undo_filing && !d.move_to ? `<button class="button quiet small undo-filing" data-action="undo-filing" data-id="${escape(d.id)}" data-token="${escape(d.undo_filing.token)}" title="Rétablir le dossier précédent ; une impression déjà envoyée reste inchangée" ${updatesLocked() ? 'disabled' : ''}>Annuler le classement</button>` : ''}</div></div>`;
  }
  function renderDetail() {
    const m = activeMessage();
    const panel = $('#detail-panel');
    if (!m) { model.filing = null; panel.innerHTML = `<div class="empty-state detail-empty"><span class="empty-icon" aria-hidden="true">↗</span><h3>Le détail, en un clic.</h3><p>Sélectionnez une communication pour consulter ses documents et choisir où les ranger.</p></div>`; return; }
    const client = messageClient(m);
    const docs = m.documents || [];
    const email = docs.find(d => d.kind === 'email');
    if (model.filing && (model.filing.messageId !== m.id || !docs.some(d => d.id === model.filing.documentId))) model.filing = null;
    const candidate = $('#inline-filing');
    const previous = model.filing && candidate?.dataset.documentId === model.filing.documentId ? candidate : null;
    const focused = previous?.contains(document.activeElement) ? document.activeElement : null;
    const scroll = $('.detail-content', panel)?.scrollTop || 0;
    const pendingDocs = docs.filter(d => d.classification !== 'classified' || d.move_to).length;
    const progress = m.print_progress || {};
    const printSummary = progress.total ? `Envoyés ${progress.submitted || 0}/${progress.total}${progress.simulated ? ` · Simulés ${progress.simulated}/${progress.total}` : ''}` : 'Aucun document choisi';
    panel.innerHTML = `<div class="detail-header"><span>APERÇU DE LA COMMUNICATION</span>${email ? `<button class="button quiet small" data-action="preview" data-id="${escape(email.id)}">Ouvrir le PDF ↗</button>` : ''}</div><div class="detail-content"><h2 class="detail-subject">${escape(m.subject || 'Sans objet')}</h2><p class="detail-sender">${escape(m.sender || 'Expéditeur inconnu')} · ${escape(dateLabel(m.date))}</p><div class="detail-statuses">${chip(`Classés ${docs.length - pendingDocs}/${docs.length}`, pendingDocs ? 'pending' : '')}${chip(printSummary, printTone(m.print_status))}${['error', 'uncertain', 'preparing', 'submitting'].includes(m.print_status) ? chip(printLabel(m.print_status), printTone(m.print_status)) : ''}</div>${m.error ? `<div class="notice error"><span>${escape(m.error)}</span><button class="button small" data-action="process">Reprendre</button></div>` : ''}<details class="mail-body" data-body-message="${escape(m.id)}" ${model.bodyCollapsed.has(m.id) ? '' : 'open'}><summary>Contenu du mail</summary><dl class="detail-meta"><dt>De</dt><dd>${escape(m.sender || '—')}</dd><dt>À</dt><dd>${escape(Array.isArray(m.recipients) ? m.recipients.join(', ') : m.recipients || '—')}</dd><dt>Reçu</dt><dd>${escape(dateLabel(m.date, true))}</dd><dt>Client</dt><dd>${escape(client?.name || '—')}</dd></dl><div class="document-preview">${escape(m.body || 'Contenu disponible après export.')}</div></details><h3 class="mini-heading">DOCUMENTS <small>${docs.length} fichier${docs.length > 1 ? 's' : ''}</small></h3><div class="document-list">${docs.length ? docs.map(d => documentCard(d, m)).join('') : '<p class="small subtle">Les documents apparaîtront après l’export.</p>'}</div>${(m.print_jobs || []).length ? `<details class="print-history"><summary>Historique des impressions · ${m.print_jobs.length} tentative${m.print_jobs.length > 1 ? 's' : ''}</summary><p class="detail-note">Les anciens échecs restent dans cet historique. Le suivi courant utilise la dernière tentative de chaque document.</p>${[...m.print_jobs].reverse().map(job => `<p class="detail-note">${escape(docs.find(d => d.id === job.document_id)?.name || 'Document')} · ${escape(printLabel(job.status))}${job.job_id ? ` · ${escape(job.job_id)}` : ''}${job.error ? `<br><strong>${escape(job.error)}</strong>` : ''}</p>`).join('')}</details>` : ''}<p class="detail-note">L’icône imprimante imprime uniquement ce document. Les cases servent aux impressions automatiques ou des mails sélectionnés.</p><p class="detail-note">${m.historical ? 'Historique : aucune impression automatique. ' : ''}${model.state?.settings?.dry_run ? 'Simulation active : aucun papier imprimé. ' : ''}Un envoi à l’imprimante ne confirme pas la sortie du papier.</p></div>`;
    if (model.filing) {
      const slot = document.getElementById('filing-' + model.filing.documentId);
      if (previous) { slot.append(previous); if (focused) focused.focus({preventScroll: true}); renderFolders(); }
      else mountFiling(slot);
    }
    $('.detail-content', panel).scrollTop = scroll;
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
    const initialFolders = withParents(model.state?.template?.folders || []).map(f => `<label class="template-node" title="${escape(f)}"><span class="tree-indent" style="--indent:${(f.split('/').length - 1) * 19}px"></span><input type="checkbox" name="initial_folders" value="${escape(f)}" ${(model.state?.template?.initial_folders || []).includes(f) ? 'checked' : ''} aria-label="Créer ${escape(f)}"><span class="folder-icon" aria-hidden="true">▱</span><span>${escape(leaf(f))}</span></label>`).join('');
    const initialChooser = `<details style="margin:16px 0"><summary>Créer des dossiers dès maintenant <span id="initial-folder-summary"></span></summary><p class="dialog-note">Les cases reprennent les choix par défaut du modèle. Vous pouvez les modifier pour ce client, même tout décocher. Leurs dossiers parents seront créés automatiquement. Cocher un parent ne sélectionne pas ses sous-dossiers. Ces dossiers seront conservés même vides.</p><div class="field-row"><button class="button quiet" type="button" data-action="initial-folders-all">Tout cocher</button><button class="button quiet" type="button" data-action="initial-folders-none">Tout décocher</button></div><div class="template-tree" role="group" aria-label="Dossiers à créer dès maintenant">${initialFolders}</div></details>`;
    modal.dataset.kind = 'client';
    openModal('Un nouveau client', 'Son dossier mail et son espace documentaire seront reliés en une seule étape.', `<form id="client-form"><label class="field"><span>Nom du client / de l’affaire</span><input name="name" id="client-name" required maxlength="160" placeholder="Ex. DUPONT-MARTIN (div)" autofocus autocomplete="off"><small>Une entrée par affaire : NOM CLIENT-NOM PARTIE ADVERSE. Ajoutez les initiales si nécessaire et une mention div, succ, LRM ou saisie. Sans Me, M. ou Mme.</small></label><div class="radio-options"><label class="radio-option"><input type="radio" name="mailbox_mode" value="new" checked>Créer un dossier mail</label><label class="radio-option"><input type="radio" name="mailbox_mode" value="existing">Relier un dossier existant</label></div><div id="existing-mailbox" class="hidden"><div class="field-row"><label class="field"><span>Dossier dans la messagerie</span><select name="mailbox" id="mailbox-select"><option value="">Choisir un dossier…</option>${folderOptions}</select></label><button class="button" type="button" data-action="refresh-folders">Actualiser</button></div></div>${initialChooser}<div class="path-preview" id="client-path-preview">Saisissez un nom pour prévisualiser les dossiers.</div><div class="dialog-note">Le modèle courant (version ${escape(model.state?.template?.version || 1)}) sera proposé pour le classement. Sur le Mac, seuls les dossiers cochés ci-dessus seront créés immédiatement ; les autres le seront à leur premier document. Un dossier déjà présent sera réutilisé. En cas d’interruption, la création pourra être reprise.</div></form>`, '<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" type="submit" form="client-form">Créer le client</button>');
    clientPreview();
  }
  function clientPreview() {
    const name = $('#client-name')?.value.trim();
    const preview = $('#client-path-preview');
    if (!preview) return;
    const settings = model.state?.settings || {};
    const folder = (settings.client_folder_pattern || '{name}').replace('{name}', name || 'Nom du client');
    const existing = $('input[name="mailbox_mode"]:checked', modal)?.value === 'existing';
    const mail = existing ? $('#mailbox-select')?.value || 'Dossier existant à choisir' : name || 'Nom du client';
    const selected = $$('input[name="initial_folders"]:checked', modal).length;
    $('#initial-folder-summary').textContent = `· ${selected} sélectionné${selected > 1 ? 's' : ''}`;
    preview.innerHTML = `<b>Messagerie</b> · ${escape(mail)}<br><b>Sur votre Mac</b> · ${escape(settings.archive_root || '')}/${escape(folder)}<br><small>${selected ? `${selected} dossier(s) sélectionné(s) à créer maintenant, avec leurs parents` : 'Aucun dossier vide créé'} · les autres seront créés au premier document</small>`;
  }
  function openFiling(button) {
    if (updatesLocked()) return;
    if (model.filing?.busy) return;
    const m = activeMessage();
    const d = button?.dataset.id ? m?.documents.find(d => d.id === button.dataset.id) : m?.documents.find(d => d.classification !== 'classified') || m?.documents[0];
    if (!d || m.status !== 'ready') throw new Error('Attendez la fin du téléchargement de ce document.');
    if (model.filing?.documentId === d.id) { closeFiling(); return; }
    model.filing = {documentId: d.id, messageId: m.id, clientId: m.client_id, destination: '', query: '', expanded: new Set(), busy: false, error: ''};
    renderDetail();
    $('#folder-search').focus({preventScroll: true});
    $('#inline-filing').scrollIntoView({block: 'nearest'});
  }
  function closeFiling() {
    if (model.filing?.busy) return;
    const id = model.filing?.documentId;
    model.filing = null; renderDetail();
    $$('[data-action="classify-document"]').find(button => button.dataset.id === id)?.focus({preventScroll: true});
  }
  function mountFiling(slot) {
    slot.innerHTML = `<section id="inline-filing" class="inline-filing" data-document-id="${escape(model.filing.documentId)}" aria-label="Dossier de classement du document"><fieldset class="filing-controls"><legend>Choisir le dossier de ce document</legend><label class="search-field"><span aria-hidden="true">⌕</span><input id="folder-search" type="search" placeholder="Rechercher dans les dossiers…" aria-label="Rechercher un dossier de destination"></label><div id="folder-picker" class="folder-picker"></div><div id="filing-target" class="filing-target" aria-live="polite"></div><div class="filing-actions"><button class="button quiet small" data-action="cancel-filing">Annuler</button><button class="button primary small" id="classify-confirm" data-action="confirm-classify" disabled>Classer ici</button></div></fieldset><p id="filing-error" class="form-error hidden" role="alert"></p></section>`;
    $('#folder-search').value = model.filing.query;
    renderFolders();
  }
  function renderFolders() {
    const filing = model.filing;
    const picker = $('#folder-picker');
    if (!filing || !picker) return;
    const client = clients().find(c => c.id === filing.clientId);
    if (!client) return;
    const all = sortFolders(client.folders || []);
    const existing = new Set(client.existing_folders || []);
    const q = searchKey(filing.query.trim());
    const favorite = (client.favorites || []).filter(f => all.includes(f) && searchKey(f).includes(q));
    const recent = (Array.isArray(model.recent[client.id]) ? model.recent[client.id] : []).filter(f => all.includes(f) && !favorite.includes(f) && searchKey(f).includes(q)).slice(0, 3);
    const row = ({path, depth = 0, hasChildren = false, expanded = false}, shortcut = false) => `<div class="folder-row" style="--folder-depth:${depth}">${hasChildren && !shortcut ? `<button class="folder-toggle" data-action="toggle-folder" data-folder="${escape(path)}" aria-label="${expanded ? 'Replier' : 'Déplier'} ${escape(path)}" aria-expanded="${expanded}" ${q ? 'disabled' : ''}><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></button>` : '<span class="folder-toggle-spacer" aria-hidden="true"></span>'}<button class="folder-choice" data-action="choose-folder" data-folder="${escape(path)}" aria-pressed="${filing.destination === path}" title="${escape(path)}"><span class="folder-label">${escape(leaf(path))}${parentPath(path) ? `<span class="folder-parent">${escape(parentPath(path))}</span>` : ''}<span class="folder-existence">${existing.has(path) ? 'Sur le Mac' : 'Sera créé'}</span></span></button><button class="icon-button${(client.favorites || []).includes(path) ? ' favorite' : ''}" data-action="favorite" data-folder="${escape(path)}" aria-label="${(client.favorites || []).includes(path) ? 'Retirer des favoris' : 'Ajouter aux favoris'} : ${escape(path)}">${(client.favorites || []).includes(path) ? '★' : '☆'}</button></div>`;
    const section = (title, paths) => paths.length ? `<div class="folder-section-title">${title}</div>` + paths.map(path => row({path}, true)).join('') : '';
    const entries = folderEntries(all, filing.query, filing.expanded);
    const scroll = picker.scrollTop;
    const focused = picker.contains(document.activeElement) ? {action: document.activeElement.dataset.action, folder: document.activeElement.dataset.folder} : null;
    picker.innerHTML = section('FAVORIS', favorite) + section('RÉCENTS', recent) + (entries.length ? '<div class="folder-section-title">ARBORESCENCE COMPLÈTE</div>' + entries.map(entry => row(entry)).join('') : '<p class="folder-empty">Aucun dossier trouvé. Essayez un autre nom.</p>');
    picker.scrollTop = scroll;
    if (focused) $$('[data-action]', picker).find(button => button.dataset.action === focused.action && button.dataset.folder === focused.folder)?.focus({preventScroll: true});
    $('#filing-target').textContent = filing.destination ? `Destination : ${filing.destination}${existing.has(filing.destination) ? '' : ' · sera créée au classement'}` : 'Sélectionnez un dossier. Les branches absentes seront créées au classement.';
    $('#classify-confirm').disabled = filing.busy || updatesLocked() || !all.includes(filing.destination);
    $('#classify-confirm').textContent = filing.busy ? 'Classement en cours…' : 'Classer ici';
    $('.filing-controls').disabled = filing.busy || updatesLocked();
    $('#filing-error').textContent = filing.error;
    $('#filing-error').classList.toggle('hidden', !filing.error);
  }
  async function confirmFiling() {
    const filing = model.filing;
    if (!filing || filing.busy || !filing.destination || updatesLocked()) return;
    filing.busy = true; filing.error = ''; renderFolders();
    try {
      await api('/api/classify', 'POST', {message_ids: [filing.messageId], document_ids: [filing.documentId], destination: filing.destination});
      rememberFolder(filing.clientId, filing.destination);
      if (model.filing === filing) model.filing = null;
      await refresh();
      if (!model.filing) $$('[data-action="classify-document"]').find(button => button.dataset.id === filing.documentId)?.focus({preventScroll: true});
      toast('Document classé.');
    } catch (error) {
      filing.error = error.message || String(error);
      if (model.filing !== filing) toast(filing.error, true);
    } finally {
      filing.busy = false;
      if (model.filing === filing) renderFolders();
    }
  }
  function rememberFolder(client, folder) {
    model.recent[client] = [folder, ...(Array.isArray(model.recent[client]) ? model.recent[client] : []).filter(f => f !== folder)].slice(0, 5);
    try { localStorage.setItem('autosecretaire.recent', JSON.stringify(model.recent)); } catch (_) { /* Private mode may disable storage. */ }
  }
  function openTemplate() {
    model.template = withParents(model.state?.template?.folders || []);
    model.templateDefaults = [...(model.state?.template?.initial_folders || [])];
    model.templateSelected = null; model.templateDirty = false; model.templateQuery = ''; model.templateExpanded = new Set();
    modal.dataset.kind = 'template';
    openModal('Votre modèle de dossiers', 'Une structure commune pour chaque nouveau client. Adaptez-la à votre façon de travailler.', `<details class="dialog-note" style="margin:0 0 20px;font-size:12px;color:#51614e"><summary><b>Repères du modèle du cabinet</b></summary><p>Une entrée par affaire : <b>NOM CLIENT-NOM PARTIE ADVERSE</b>, avec les initiales et la mention div, succ, LRM ou saisie si utile.</p><p>Avant de créer une affaire, renommez <b>[JURIDICTION + lieu]</b> (ex. TJ Paris). Dupliquez cette branche pour plusieurs instances : ses 14 sous-dossiers seront repris. Le modèle courant est proposé pour tous les clients. Seules les branches utilisées sont créées sur le Mac, au premier document.</p><ul><li><b>01 CONSULTATIONS</b> : Word et PDF, jamais dans les correspondances.</li><li><b>02 CORRESPONDANCES</b> : par catégorie du destinataire, jamais par objet ; Avocat comprend les confrères et le postulant.</li><li><b>PDF des mails</b> : choisissez leur dossier de classement comme pour les pièces jointes. La rubrique 03 MAILS (PDF) reste disponible ; aucune destination n’est imposée.</li><li><b>04 PROCÉDURE</b> : LO et MED avec double en correspondances ; actes par juridiction. Dires et rapports d’expert en 11, actes de notaire en 12, lettres au juge en 13.</li><li><b>05 PIÈCES</b> : client, adverses et reçues à trier ; numérotation par bordereau et sous-pièces a, b, c…</li><li><b>06 PROJETS ET VERSIONS DÉFINITIVES</b> : PJT numéroté, initiales et date ; VD et date, AR24 si nécessaire.</li><li><b>07 FACTURES</b> : facture avec exemplaire du mail ou courrier d’envoi ; correspondance aussi en 02.</li><li><b>08 NOTES INTERNES</b> : dossier, objet, initiales de l’auteur et date.</li></ul><p><b>00 - À classer</b> est la zone d’attente des PDF de mails et des pièces jointes. Les noms exportés gardent le préfixe <b>AAAA-MM-JJ - nom d’origine</b>. Remplacez les / par des tirets dans les noms de documents.</p><p>Ces repères guident votre classement. Le dossier se choisit directement sous chaque PDF de mail ou pièce jointe. Les copies dans plusieurs rubriques et les noms détaillés des actes restent manuels.</p></details><div class="template-toolbar"><span class="version-tag" id="template-version">Version ${escape(model.state?.template?.version || 1)}</span><button class="button small" data-action="template-add-root">＋ Dossier à la racine</button></div><p class="dialog-note">Cochez dans l’arbre les dossiers à préparer par défaut pour un nouveau client. Ces choix pourront être décochés à sa création. Les autres dossiers seront créés au premier document.</p><div class="template-search-tools"><label class="search-field"><input id="template-search" type="search" placeholder="Rechercher dans le modèle…" aria-label="Rechercher dans le modèle"></label><button class="button quiet small" data-action="template-expand-all">Tout déplier</button><button class="button quiet small" data-action="template-collapse-all">Tout replier</button></div><div id="template-tree" class="template-tree" aria-label="Arborescence du modèle"></div><div id="template-editor" class="template-editor hidden"></div><p class="template-hint">Sélectionnez un dossier pour le renommer, le déplacer, le dupliquer ou ajouter un sous-dossier. Vous pouvez aussi le glisser dans un autre dossier.</p><h3 class="mini-heading" style="margin-top:20px">APERÇU POUR UN NOUVEAU CLIENT</h3><div id="template-preview" class="template-preview"></div>${clients().length ? `<div class="apply-template"><h3>Conserver ce modèle pour un client</h3><p>Toutes les destinations du modèle courant sont déjà proposées. Mémorisez-les pour ce client afin de les retrouver même si le modèle change ensuite. Aucun dossier vide ne sera créé.</p><div class="field-row"><label class="field"><span>Client</span><select id="template-client">${clients().map(c => `<option value="${escape(c.id)}" ${c.id === model.client ? 'selected' : ''}>${escape(c.name)} · v${escape(c.template_version || 1)}</option>`).join('')}</select></label><button class="button" data-action="apply-template">Mémoriser le modèle</button></div></div>` : ''}`, '<button class="button quiet" data-action="close-modal">Fermer</button><button class="button primary" data-action="save-template">Enregistrer le modèle</button>', true);
    renderTemplate();
  }
  function renderTemplate() {
    const entries = folderEntries(model.template, model.templateQuery, model.templateExpanded);
    $('#template-tree').innerHTML = entries.length ? entries.map(({path: f, depth, hasChildren, expanded}) => `<div class="template-node" draggable="true" data-path="${escape(f)}" aria-selected="${model.templateSelected === f}" style="--folder-depth:${depth}">${hasChildren ? `<button class="folder-toggle" data-action="template-toggle" data-folder="${escape(f)}" aria-expanded="${expanded}" aria-label="${expanded ? 'Replier' : 'Déplier'} ${escape(f)}" ${model.templateQuery ? 'disabled' : ''}><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4"><path d="m9 5 7 7-7 7"/></svg></button>` : '<span class="folder-toggle-spacer"></span>'}<input type="checkbox" data-template-default="${escape(f)}" ${model.templateDefaults.includes(f) ? 'checked' : ''} title="Créer par défaut pour un nouveau client" aria-label="Créer ${escape(f)} par défaut"><button class="tree-name" data-action="template-select" data-folder="${escape(f)}">${escape(leaf(f))}</button><button class="icon-button" data-action="template-add-child" data-folder="${escape(f)}" title="Ajouter un sous-dossier" aria-label="Ajouter un sous-dossier à ${escape(f)}">＋</button></div>`).join('') : '<p class="dialog-note folder-empty">Aucun dossier trouvé. Effacez la recherche ou ajoutez un dossier.</p>';
    const pattern = model.state?.settings?.client_folder_pattern || '{name}';
    $('#template-preview').textContent = pattern.replace('{name}', 'NOM CLIENT-NOM PARTIE ADVERSE') + '/\n' + model.template.map(f => '  '.repeat(f.split('/').length) + '└ ' + leaf(f) + '/').join('\n');
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
    model.template = withParents([...model.template, path]); model.templateSelected = path; model.templateDirty = true; model.templateQuery = ''; $('#template-search').value = ''; revealTemplate(path); renderTemplate();
  }
  function revealTemplate(path) {
    for (let parent = parentPath(path); parent; parent = parentPath(parent)) model.templateExpanded.add(parent);
  }
  function updateTemplateBranch(source, destination, copy = false) {
    const folders = changeBranch(model.template, source, destination, copy);
    const mapped = model.templateDefaults.filter(f => f === source || f.startsWith(source + '/')).map(f => destination + f.slice(source.length));
    model.templateDefaults = [...new Set([...(copy ? model.templateDefaults : model.templateDefaults.filter(f => f !== source && !f.startsWith(source + '/'))), ...mapped])];
    model.template = folders; revealTemplate(destination);
  }
  async function saveTemplate() {
    if (!model.template.length) throw new Error('Ajoutez au moins un dossier au modèle.');
    const template = await api('/api/template', 'PUT', {folders: model.template, initial_folders: model.templateDefaults});
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
    openModal('Les réglages de votre espace', 'Une configuration locale. La messagerie et l’imprimante restent sous votre contrôle.', `<form id="settings-form"><fieldset class="form-section"><legend>Messagerie & dossiers</legend>${selectField('connector', 'Source des mails', s.connector, [['demo','Démonstration · messages d’essai'],['imap','Orange / serveur IMAP'],['apple_mail','Apple Mail · dossiers locaux ou compte']], clients().length ? 'Des clients sont déjà liés à cet espace. Pour changer de source, démarrez un nouvel espace selon le guide d’installation.' : '', locked)}<div id="apple-settings">${settingField('mail_account', 'Compte Apple Mail', s.mail_account, 'Laissez vide pour les boîtes « Sur mon Mac ». Sinon, indiquez le nom exact du compte dans Mail.', locked)}</div><div id="imap-settings"><div class="form-grid">${settingField('imap_host', 'Serveur IMAP', s.imap_host, '', `autocomplete="off" ${locked}`)}${settingField('imap_port', 'Port sécurisé', s.imap_port || 993, '', `type="number" min="1" max="65535" ${locked}`)}</div>${settingField('imap_user', 'Adresse de la boîte mail', s.imap_user, '', `autocomplete="off" ${locked}`)}${settingField('imap_password_env', 'Nom de la variable du mot de passe', s.imap_password_env, 'Ne saisissez pas le mot de passe ici. Le guide explique la configuration sécurisée avant le lancement du service.', `autocomplete="off" ${locked}`)}</div>${settingField('archive_root', 'Dossier des documents sur le Mac', s.archive_root, clients().length ? 'La racine est fixée pour préserver les liens existants. Une migration nécessite un nouvel espace.' : 'Choisissez un dossier local que votre outil cloud synchronise déjà, si nécessaire.', locked)}${settingField('client_folder_pattern', 'Nom des dossiers clients', s.client_folder_pattern || '{name}', 'Utilisez {name} une seule fois, sans séparateur de chemin. Exemple : Client - {name}.', 'required')}<div class="dialog-note">Les règles d’expéditeur se configurent dans Apple Mail. Auto-secrétaire surveille le dossier dans lequel le mail arrive.</div></fieldset><fieldset class="form-section"><legend>Nom des documents</legend><div class="form-grid">${selectField('date_source', 'Date à utiliser', s.date_source, [['received','Date de réception'],['sent','Date d’envoi du mail']])}${selectField('prefix_format', 'Préfixe chronologique', s.prefix_format, [['%Y-%m-%d','AAAA-MM-JJ - nom du document'],['%Y%m%d','AAAAMMJJ - nom du document']])}</div><div class="path-preview" id="naming-preview"></div><p class="dialog-note">Ces réglages s’appliquent aux prochains exports. Le nom d’origine est conservé après le préfixe.</p></fieldset><fieldset class="form-section"><legend>Impression</legend>${selectField('print_policy', 'Quand imprimer les nouveaux mails ?', s.print_policy, [['manual','À ma demande'],['after_classify','Quand tous les documents sont classés'],['after_export','Dès que les fichiers sont exportés']])}<div class="field-row">${settingField('printer', 'Imprimante', s.printer, 'Choisissez le nom exact d’une imprimante du Mac ; nécessaire pour l’impression réelle.', 'list="printers-list" autocomplete="off"')}<button type="button" class="button" data-action="refresh-printers">Rechercher</button></div><datalist id="printers-list">${(model.state?.printers || []).map(p => `<option value="${escape(p)}"></option>`).join('')}</datalist><div class="form-grid">${selectField('print_sides', 'Faces à imprimer', s.print_sides || 'printer', [['printer','Réglage de l’imprimante'],['one-sided','Recto seul'],['two-sided-long-edge','Recto verso · bord long (livre)'],['two-sided-short-edge','Recto verso · bord court (bloc-notes)']])}${selectField('print_color_mode', 'Couleur', s.print_color_mode || 'printer', [['printer','Réglage de l’imprimante'],['monochrome','Noir et blanc'],['color','Couleur']])}</div><p class="dialog-note">Ces choix s’appliquent aux prochaines impressions du mail et des pièces jointes cochées, selon les capacités de l’imprimante. Chaque document est imprimé séparément ; le recto verso concerne ses propres pages. Les fichiers archivés restent inchangés.</p><label class="checkbox-field"><input name="dry_run" type="checkbox" ${s.dry_run ? 'checked' : ''}><span>Simuler les impressions<small>Aucun papier n’est imprimé tant que cette option est activée.</small></span></label><label class="checkbox-field"><input name="print_attachments" type="checkbox" ${s.print_attachments ? 'checked' : ''}><span>Inclure les pièces jointes imprimables<small>Sélectionne les pièces jointes PDF, images et textes compatibles lors des prochains exports. Les images intégrées restent décochées par défaut ; les formats Word/Excel ne sont pas imprimables ici. Pour un mail déjà présent, utilisez les cases de chaque document.</small></span></label><p class="dialog-note">Le PDF du mail est coché par défaut. Dans le détail d’un mail, vous pouvez cocher ou décocher séparément son PDF et chaque pièce jointe imprimable.</p><p class="dialog-note">Les mails présents lors de la première relève sont historiques : ils ne sont jamais imprimés automatiquement. Une impression incertaine nécessite votre vérification.</p></fieldset><fieldset class="form-section"><legend>Relève automatique</legend>${settingField('poll_seconds', 'Intervalle entre les contrôles (secondes)', s.poll_seconds || 60, 'De 15 à 3 600 secondes. Le Mac doit rester allumé et le service lancé.', 'type="number" min="15" max="3600" required')}</fieldset></form>`, '<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" type="submit" form="settings-form">Enregistrer les réglages</button>', true);
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
  function openDocumentReprint(doc, view) {
    modal.dataset.kind = 'document-reprint';
    openModal('Imprimer un nouvel exemplaire ?', 'Seul ce document sera imprimé, avec les réglages actuels.', `<div class="notice warning"><span>${view.status === 'uncertain' ? 'Le résultat précédent est incertain. Vérifiez d’abord la file de l’imprimante et les feuilles déjà sorties.' : 'Ce document a déjà fait l’objet d’une impression. Vérifiez que vous souhaitez un nouvel exemplaire.'}</span></div><p class="dialog-note">${escape(doc.name)}</p><label class="checkbox-field"><input id="reprint-confirm" type="checkbox"><span>J’ai vérifié et je souhaite une nouvelle impression.</span></label>`, `<button class="button quiet" data-action="close-modal">Annuler</button><button class="button primary" id="reprint-submit" data-action="confirm-document-reprint" data-id="${escape(doc.id)}" disabled>Réimprimer ce document</button>`);
  }
  async function submitDocumentPrint(id, reprint = false) {
    const job = await api(`/api/documents/${encodeURIComponent(id)}/${reprint ? 'reprint' : 'print'}`, 'POST', reprint ? {confirm: true} : {});
    if (modal.dataset.kind === 'document-reprint' && $('#reprint-submit')?.dataset.id === id) closeModal();
    await refresh();
    const failed = ['error', 'uncertain'].includes(job.status);
    toast(failed ? job.error || 'L’impression demande votre attention.' : job.status === 'simulated' ? 'Impression de ce document simulée.' : 'Document envoyé à l’imprimante.', failed);
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
    $$('[data-action="sync"], [data-action="process"], [data-action="new-client"], [data-action="confirm-classify"], [data-action="classify-document"], [data-action="print"], [data-action="print-document"], [data-action="confirm-document-reprint"], [data-action="star-client"]').forEach(button => {
      if (active) {
        if (!('updateWasDisabled' in button.dataset)) button.dataset.updateWasDisabled = String(button.disabled);
        button.disabled = true;
      } else if ('updateWasDisabled' in button.dataset) {
        button.disabled = button.dataset.updateWasDisabled === 'true'; delete button.dataset.updateWasDisabled;
      }
    });
    if ($('.filing-controls')) $('.filing-controls').disabled = active || !!model.filing?.busy;
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
    openModal('Quelques raccourcis utiles', 'Ils sont actifs en dehors des champs de saisie.', '<dl class="shortcuts-list"><dt><kbd>/</kbd></dt><dd>Rechercher un client</dd><dt><kbd>J</kbd> / <kbd>K</kbd></dt><dd>Communication suivante / précédente</dd><dt><kbd>C</kbd></dt><dd>Classer le premier document en attente du mail ouvert</dd><dt><kbd>Espace</kbd></dt><dd>Ajouter ou retirer le mail de la sélection</dd><dt><kbd>⌘</kbd> + clic</dt><dd>Sélectionner plusieurs mails du même client</dd><dt><kbd>Échap</kbd></dt><dd>Replier le sélecteur, fermer un dialogue ou vider la sélection</dd></dl>', '<button class="button" data-action="close-modal">Compris</button>');
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
    'star-client': async button => {
      const id = button.dataset.id;
      const client = clients().find(c => c.id === id);
      if (!client) throw new Error('Ce client est introuvable.');
      const updated = await api(`/api/clients/${encodeURIComponent(id)}/star`, 'PUT', {starred: !client.starred});
      const current = clients().find(c => c.id === id);
      if (current) current.starred = updated.starred;
    },
    'new-client': newClient,
    'initial-folders-all': () => { $$('input[name="initial_folders"]', modal).forEach(input => { input.checked = true; }); clientPreview(); },
    'initial-folders-none': () => { $$('input[name="initial_folders"]', modal).forEach(input => { input.checked = false; }); clientPreview(); },
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
    'classify-document': openFiling,
    'cancel-filing': closeFiling,
    'choose-folder': button => { if (!model.filing?.busy) { model.filing.destination = button.dataset.folder; model.filing.error = ''; renderFolders(); } },
    'toggle-folder': button => {
      const expanded = model.filing?.expanded;
      if (!expanded) return;
      if (expanded.has(button.dataset.folder)) expanded.delete(button.dataset.folder); else expanded.add(button.dataset.folder);
      renderFolders();
    },
    'confirm-classify': confirmFiling,
    'undo-filing': async button => {
      const id = button.dataset.id;
      await api(`/api/documents/${encodeURIComponent(id)}/undo-filing`, 'POST', {token: button.dataset.token});
      if (model.filing?.documentId === id) model.filing = null;
      await refresh(); toast('Classement annulé. Les impressions déjà envoyées restent inchangées.');
    },
    favorite: async button => {
      const filing = model.filing;
      const client = clients().find(c => c.id === filing?.clientId);
      if (!client) return;
      const favorites = new Set(client.favorites || []);
      if (favorites.has(button.dataset.folder)) favorites.delete(button.dataset.folder); else favorites.add(button.dataset.folder);
      try {
        const updated = await api(`/api/clients/${encodeURIComponent(client.id)}/favorites`, 'PUT', {folders: [...favorites]});
        const current = clients().find(c => c.id === client.id);
        if (current) current.favorites = updated.favorites;
        if (model.filing === filing) renderFolders();
      } catch (error) {
        if (model.filing === filing) { filing.error = error.message; renderFolders(); } else throw error;
      }
    },
    print: async () => {
      const list = selectedMessages();
      if (!list.length) throw new Error('Sélectionnez d’abord une communication.');
      if (list.some(m => m.status !== 'ready')) throw new Error('Attendez la fin de l’export avant d’imprimer.');
      await api('/api/print', 'POST', {message_ids: list.map(m => m.id)}); await refresh();
      toast(model.state?.settings?.dry_run ? 'Demande simulée. Consultez les états d’impression.' : 'Demande traitée. Consultez les états d’impression.');
    },
    'print-document': async button => {
      const id = button.dataset.id;
      const message = messages().find(m => m.documents.some(d => d.id === id));
      const doc = message?.documents.find(d => d.id === id);
      if (!doc) throw new Error('Ce document est introuvable.');
      const view = documentPrintView(doc, message.print_jobs);
      if (view.disabled) return;
      if (view.reprint) openDocumentReprint(doc, view);
      else await submitDocumentPrint(id);
    },
    'confirm-document-reprint': async button => { if ($('#reprint-confirm')?.checked) await submitDocumentPrint(button.dataset.id, true); },
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
    'template-toggle': button => { const f = button.dataset.folder; if (model.templateExpanded.has(f)) model.templateExpanded.delete(f); else model.templateExpanded.add(f); renderTemplate(); },
    'template-expand-all': () => { model.templateExpanded = new Set(model.template); renderTemplate(); },
    'template-collapse-all': () => { model.templateExpanded.clear(); renderTemplate(); },
    'template-select': button => { model.templateSelected = button.dataset.folder; renderTemplate(); },
    'template-add-root': () => addTemplate(),
    'template-add-child': button => addTemplate(button.dataset.folder),
    'template-update': () => {
      const name = $('#template-name')?.value.trim();
      if (!name || name.includes('/')) throw new Error('Utilisez un nom de dossier simple, sans barre oblique.');
      const parent = $('#template-parent').value;
      const next = parent ? `${parent}/${name}` : name;
      updateTemplateBranch(model.templateSelected, next); model.templateSelected = next; model.templateDirty = true; renderTemplate();
    },
    'template-copy': () => {
      const path = model.templateSelected;
      let next = path + ' - copie'; let n = 2;
      while (model.template.includes(next)) next = `${path} - copie ${n++}`;
      updateTemplateBranch(path, next, true); model.templateSelected = next; model.templateDirty = true; renderTemplate();
    },
    'template-remove': () => {
      const path = model.templateSelected;
      if (!window.confirm(`Retirer « ${path} » et ses sous-dossiers du modèle ? Les dossiers des clients existants seront conservés.`)) return;
      model.templateDefaults = model.templateDefaults.filter(f => f !== path && !f.startsWith(path + '/'));
      model.template = model.template.filter(f => f !== path && !f.startsWith(path + '/')); model.templateSelected = null; model.templateDirty = true; renderTemplate();
    },
    'save-template': saveTemplate,
    'apply-template': async () => {
      if (model.templateDirty) throw new Error('Enregistrez d’abord les modifications du modèle.');
      const id = $('#template-client')?.value;
      if (!id) throw new Error('Sélectionnez un client.');
      await api(`/api/clients/${encodeURIComponent(id)}/template`, 'POST', {}); await refresh(); toast('Le modèle est mémorisé pour ce client. Les dossiers seront créés au premier document.');
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
      if (handler) {
        event.preventDefault();
        const name = button.dataset.action;
        const restoreFocus = document.activeElement === button;
        const documentPrint = ['print-document', 'confirm-document-reprint'].includes(name);
        const key = documentPrint ? 'print-document:' + button.dataset.id : name === 'star-client' ? name + ':' + button.dataset.id : name;
        action(key, () => handler(button), button).then(() => {
          if (documentPrint) { renderDetail(); renderUpdateControls(); }
          if (name === 'star-client') { renderClients(); renderUpdateControls(); }
          if (restoreFocus && document.activeElement === document.body && (documentPrint || name === 'star-client')) {
            $$(`[data-action="${documentPrint ? 'print-document' : 'star-client'}"]`).find(item => item.dataset.id === button.dataset.id)?.focus({preventScroll: true});
          }
        });
      }
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
    if (element.id === 'template-search') { model.templateQuery = element.value; renderTemplate(); }
    if (element.id === 'client-name') clientPreview();
    if (element.id === 'folder-search' && model.filing) { model.filing.query = element.value; renderFolders(); }
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
    if (element.name === 'initial_folders') clientPreview();
    if (element.dataset.templateDefault) {
      const selected = new Set(model.templateDefaults);
      if (element.checked) selected.add(element.dataset.templateDefault); else selected.delete(element.dataset.templateDefault);
      model.templateDefaults = [...selected]; model.templateDirty = true;
    }
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
        const client = await api('/api/clients', 'POST', {name, mailbox, initial_folders: data.getAll('initial_folders')});
        closeModal(); model.client = client.id; model.selected.clear(); model.filter = 'all'; await refresh();
        toast(client.status === 'ready' ? (client.initial_folders?.length ? 'Client créé. Les dossiers sélectionnés sont prêts.' : 'Client créé. Ses dossiers seront créés au premier document.') : 'Client enregistré. Sa préparation doit être reprise.');
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
  document.addEventListener('toggle', event => {
    const id = event.target.dataset?.bodyMessage;
    if (id) { if (event.target.open) model.bodyCollapsed.delete(id); else model.bodyCollapsed.add(id); }
  }, true);
  document.addEventListener('keydown', event => {
    const input = event.target.closest('input,textarea,select,[contenteditable=true]');
    if (modal.open) return;
    if (event.key === 'Escape' && model.filing) { event.preventDefault(); closeFiling(); return; }
    if (event.target.closest('#inline-filing')) {
      if (event.key === 'Enter' && event.target.id === 'folder-search') { event.preventDefault(); $('#classify-confirm')?.click(); }
      return;
    }
    if (input || event.altKey || event.metaKey || event.ctrlKey) return;
    if (event.key === '/') { event.preventDefault(); $('#client-search').focus(); }
    if (event.key.toLowerCase() === 'c' && model.active) { event.preventDefault(); action('classify-document', () => openFiling()); }
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
      updateTemplateBranch(draggedPath, next); model.templateSelected = next; model.templateDirty = true; draggedPath = ''; renderTemplate();
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
