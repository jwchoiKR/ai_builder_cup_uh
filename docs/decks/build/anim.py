"""Slide motion for our decks: when a slide opens, its boxes, table rows, images and arrows appear in reading order,
and red/green result boxes pulse once. Import after `from deck import *`: `import anim  # noqa`.

Motion is skipped for automated browsers (navigator.webdriver, used by the screenshot and layout checks) and for
prefers-reduced-motion, so checks and screenshots always see the final layout."""
import deck as _deck

_deck.CSS += """
@keyframes an-up { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
@keyframes an-pop { 0% { opacity: 0; transform: scale(.96); } 100% { opacity: 1; transform: none; } }
@keyframes an-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(0,0,0,0); } 40% { box-shadow: 0 0 0 10px var(--an-glow); } }
.an-item { animation: an-up .45s cubic-bezier(.2,.7,.2,1) both; }
.an-img { animation: an-pop .6s cubic-bezier(.2,.7,.2,1) both; }
.an-pulse { animation: an-up .45s cubic-bezier(.2,.7,.2,1) both, an-pulse 1.2s ease-out both; }
/* always-on motion while a slide is shown: arrows flow, a dot runs along them, AI badges breathe, flow steps light up in turn */
@keyframes an-dash { to { stroke-dashoffset: -28; } }
@keyframes an-breathe { 0%, 100% { box-shadow: 0 0 0 0 rgba(26,115,232,0); } 50% { box-shadow: 0 0 0 8px rgba(26,115,232,.16); } }
@keyframes an-step { 0%, 100% { box-shadow: 0 0 0 0 rgba(26,115,232,0); border-color: inherit; } 12%, 30% { box-shadow: 0 0 0 5px rgba(26,115,232,.22); } }
@keyframes an-run { from { offset-distance: 0%; opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } to { offset-distance: 100%; opacity: 0; } }
.an-arrow { position: relative; display: inline-flex; align-items: center; justify-content: center; line-height: 0; flex: none; align-self: center; }
@keyframes an-march { to { stroke-dashoffset: -11; } }
section.on .an-shaft { animation: an-march .55s linear infinite; }
"""

_deck.JS += r"""
(function(){
  const reduce = navigator.webdriver || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  const BOX = el => { const cs = getComputedStyle(el);
    const bg = cs.backgroundColor, bd = parseFloat(cs.borderTopWidth) || 0;
    return (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && bg !== 'rgb(255, 255, 255)') || bd > 0; };
  const GLOW = { 'rgb(252, 232, 230)': 'rgba(217,48,37,.25)', 'rgb(230, 244, 234)': 'rgba(30,142,62,.25)',
                 'rgb(254, 247, 224)': 'rgba(249,171,0,.3)' };
  function animate(sec){
    const bd = sec.querySelector('.bd'); if (!bd) return;
    sec.querySelectorAll('.an-item,.an-img,.an-pulse').forEach(e => { e.classList.remove('an-item','an-img','an-pulse'); e.style.animationDelay=''; });
    const picks = [];
    bd.querySelectorAll('div, tr, img, svg').forEach(el => {
      if (el.tagName === 'IMG') { picks.push([el, 'an-img']); return; }
      if (el.tagName === 'TR') { picks.push([el, 'an-item']); return; }
      if (el.tagName !== 'svg' && !BOX(el)) return;
      let p = el.parentElement, inner = false;
      while (p && p !== bd) { if (BOX(p) && p.tagName === 'DIV') { inner = true; break; } p = p.parentElement; }
      if (inner) return;
      if (el.tagName === 'svg') { picks.push([el, 'an-item']); return; }
      const bg = getComputedStyle(el).backgroundColor;
      if (GLOW[bg]) { el.style.setProperty('--an-glow', GLOW[bg]); picks.push([el, 'an-pulse']); }
      else picks.push([el, 'an-item']);
    });
    picks.forEach(([el]) => { el.dataset.anTop = Math.round(el.getBoundingClientRect().top / 40); el.dataset.anLeft = el.getBoundingClientRect().left; });
    picks.sort((a, b) => (a[0].dataset.anTop - b[0].dataset.anTop) || (a[0].dataset.anLeft - b[0].dataset.anLeft));
    picks.forEach(([el, cls], k) => { el.style.animationDelay = (0.08 * k).toFixed(2) + 's' + (cls === 'an-pulse' ? ', ' + (0.08 * k + 0.4).toFixed(2) + 's' : '');
                                      el.classList.add(cls); });
  }
  function live(sec){
    const bd = sec.querySelector('.bd'); if (!bd) return;
    bd.querySelectorAll('svg').forEach(sv => { const p = sv.querySelector('path'); if (!p) return;
      const st = p.getAttribute('stroke') || ''; if (st.toUpperCase() === '#9AA0A6') {
        if (!sv.parentElement.classList.contains('an-arrow')) {
          const wrap = document.createElement('span'); wrap.className = 'an-arrow';
          const holder = sv.parentElement;
          if (holder && holder.style && holder.style.paddingTop) { holder.style.paddingTop = '0'; holder.style.alignSelf = 'center'; holder.style.display = 'flex'; holder.style.alignItems = 'center'; }
          holder.insertBefore(wrap, sv); wrap.appendChild(sv);
          const d = p.getAttribute('d'); const segs = d.match(/M[^M]*/g) || [d];
          if (segs.length >= 2) {
            const NS = 'http://www.w3.org/2000/svg';
            p.setAttribute('d', segs[0]); p.classList.add('an-shaft');
            p.setAttribute('stroke-dasharray', '0.01 11'); p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-width', '4.5');
            const head = document.createElementNS(NS, 'path'); head.setAttribute('d', segs.slice(1).join(' '));
            head.setAttribute('stroke', p.getAttribute('stroke')); head.setAttribute('stroke-width', '3'); head.setAttribute('fill', 'none');
            head.setAttribute('stroke-linecap', 'round'); head.setAttribute('stroke-linejoin', 'round'); sv.appendChild(head);
          }
        } } });
    bd.querySelectorAll('div').forEach(g => { if (getComputedStyle(g).display === 'grid' && g.querySelector('.an-arrow')) g.style.alignItems = 'center'; });
    bd.querySelectorAll('div').forEach(el => { const cs = getComputedStyle(el);
      if (cs.backgroundColor === 'rgb(232, 240, 254)' && cs.borderRadius && parseFloat(cs.width) <= 90 && parseFloat(cs.width) >= 40 && Math.abs(parseFloat(cs.width) - parseFloat(cs.height)) < 4) el.classList.add('an-ai'); });
    bd.querySelectorAll('div').forEach(row => { const kids = [...row.children];
      const arrows = kids.filter(k => k.tagName === 'svg' && (k.querySelector('path')?.getAttribute('stroke') || '').toUpperCase() === '#9AA0A6');
      const boxes = kids.filter(k => k.tagName === 'DIV' && BOX(k));
      if (arrows.length >= 1 && boxes.length >= 2) boxes.forEach((b, k) => { b.classList.add('an-seq'); b.style.setProperty('--an-at', (k * 0.9).toFixed(1) + 's'); b.style.setProperty('--an-cycle', (boxes.length * 0.9 + 1.2).toFixed(1) + 's'); }); });
  }
  const base = show;
  show = function(n){ base(n); const cur = document.querySelector('section.on'); if (cur) requestAnimationFrame(() => { animate(cur); live(cur); }); };
  window.addEventListener('load', () => { const cur = document.querySelector('section.on'); if (cur) setTimeout(() => { animate(cur); live(cur); }, 300); });
})();
"""
