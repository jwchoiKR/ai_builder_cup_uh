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
.an-arrow .an-dot2 { position: absolute; width: 12px; height: 12px; border-radius: 50%; background: #1A73E8; box-shadow: 0 0 0 4px rgba(26,115,232,.18); opacity: 0; pointer-events: none; }
@keyframes an-run-h { 0% { left: -2px; opacity: 0; } 15% { opacity: 1; } 80% { opacity: 1; } 100% { left: calc(100% - 14px); opacity: 0; } }
@keyframes an-run-v { 0% { top: -2px; opacity: 0; } 15% { opacity: 1; } 80% { opacity: 1; } 100% { top: calc(100% - 14px); opacity: 0; } }
section.on .an-arrow.h .an-dot2 { top: 50%; margin-top: -6px; animation: an-run-h 1.5s cubic-bezier(.4,0,.2,1) infinite; }
section.on .an-arrow.v .an-dot2 { left: 50%; margin-left: -6px; animation: an-run-v 1.5s cubic-bezier(.4,0,.2,1) infinite; }
section.on .an-ai { animation: an-breathe 2.4s ease-in-out infinite; border-radius: 999px; }
section.on .an-seq { animation: an-step var(--an-cycle, 4s) ease-in-out infinite; animation-delay: var(--an-at, 0s); }
.an-dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; background: #1A73E8; top: 0; left: 0; pointer-events: none;
          offset-rotate: 0deg; animation: an-run 1.6s ease-in-out infinite; }
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
          const wrap = document.createElement('span'); const r = sv.getBoundingClientRect();
          wrap.className = 'an-arrow ' + (r.width >= r.height ? 'h' : 'v');
          const holder = sv.parentElement;
          if (holder && holder.style && holder.style.paddingTop) { holder.style.paddingTop = '0'; holder.style.alignSelf = 'center'; holder.style.display = 'flex'; holder.style.alignItems = 'center'; }
          sv.style.alignSelf = 'center';
          holder.insertBefore(wrap, sv); wrap.appendChild(sv);
          const dot = document.createElement('span'); dot.className = 'an-dot2'; wrap.appendChild(dot);
        } } });
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
