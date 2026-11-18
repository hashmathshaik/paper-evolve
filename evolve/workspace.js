// Panel state follows the user's actions; resizing never discards an open reader.
export function createWorkspace() {
  const $ = id => document.getElementById(id),
    small = matchMedia('(max-width: 760px)');
  let explorerOpen = !small.matches,
    notesOpen = false,
    restoreExplorer = false;
  function paint() {
    document.body.classList.toggle('explorer-collapsed', !explorerOpen);
    document.body.classList.toggle('notes-collapsed', !notesOpen);
    $('explorer').hidden = !explorerOpen;
    $('details').hidden = !notesOpen;
    $('toggle-explorer').setAttribute('aria-expanded', String(explorerOpen));
    $('toggle-explorer').setAttribute('aria-label', explorerOpen ? 'Hide explorer' : 'Show explorer');
    $('toggle-notes').setAttribute('aria-expanded', String(notesOpen));
    $('toggle-notes').setAttribute('aria-label', notesOpen ? 'Hide paper details' : 'Show paper details');
    $('panel-backdrop').hidden = !(small.matches && (explorerOpen || notesOpen));
    if (!explorerOpen) document.dispatchEvent(new Event('explorer-closed'));
  }
  function setExplorer(open) {
    explorerOpen = open;
    if (open) {
      notesOpen = false;
      restoreExplorer = false;
    }
    paint();
  }
  function setNotes(open) {
    if (open && !notesOpen) {
      restoreExplorer = explorerOpen;
      explorerOpen = false;
    }
    if (!open && notesOpen) {
      explorerOpen = !small.matches && restoreExplorer;
      restoreExplorer = false;
    }
    notesOpen = open;
    paint();
    if (open) $('detail-content').focus({ preventScroll: true });
  }
  $('toggle-explorer').onclick = () => setExplorer(!explorerOpen);
  $('close-explorer').onclick = () => {
    setExplorer(false);
    $('toggle-explorer').focus();
  };
  $('toggle-notes').onclick = () => setNotes(!notesOpen);
  $('close-notes').onclick = () => {
    setNotes(false);
    $('toggle-notes').focus();
  };
  $('panel-backdrop').onclick = () => {
    explorerOpen = false;
    notesOpen = false;
    restoreExplorer = false;
    paint();
  };
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.defaultPrevented || !$('discovery-results').hidden) return;
    if (notesOpen) {
      setNotes(false);
      $('toggle-notes').focus();
    } else if (explorerOpen) {
      setExplorer(false);
      $('toggle-explorer').focus();
    }
  });
  small.addEventListener('change', paint);
  paint();
  return {
    openExplorer: () => setExplorer(true),
    openNotes: () => setNotes(true),
    closeNotes: () => setNotes(false),
    closeMobileExplorer: () => {
      if (small.matches) setExplorer(false);
    },
  };
}
