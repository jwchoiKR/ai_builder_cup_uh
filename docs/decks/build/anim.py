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
  const base = show;
  show = function(n){ base(n); const cur = document.querySelector('section.on'); if (cur) requestAnimationFrame(() => animate(cur)); };
  window.addEventListener('load', () => { const cur = document.querySelector('section.on'); if (cur) setTimeout(() => animate(cur), 300); });
})();
"""
