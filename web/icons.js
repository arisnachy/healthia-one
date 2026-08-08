if (!window.__HEALTHIA_ICONS__) {
  window.__HEALTHIA_ICONS__ = true;
  (() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
    const paths = {
      sparkle:'<path d="M12 2.8c.7 4.3 2.9 6.5 7.2 7.2-4.3.7-6.5 2.9-7.2 7.2-.7-4.3-2.9-6.5-7.2-7.2 4.3-.7 6.5-2.9 7.2-7.2Z"/>',
      plus:'<path d="M12 5v14M5 12h14"/>', chat:'<path d="M7 18.5 3.5 20l1-3.5A8 8 0 1 1 7 18.5Z"/><path d="M8 10h8M8 14h5"/>',
      calendar:'<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M7 3v4M17 3v4M3.5 9.5h17"/>',
      activity:'<path d="M3 12h3l2-5 4 10 2.5-6H21"/>', chart:'<path d="M5 20V10M10 20V4M15 20v-7M20 20V7"/>',
      folder:'<path d="M3.5 7.5h6l2-2h9v13.5h-17Z"/>', family:'<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3.5 20v-2.5A4.5 4.5 0 0 1 8 13h2a4.5 4.5 0 0 1 4.5 4.5V20M15 14.5h1.5A4 4 0 0 1 20.5 18v2"/>',
      file:'<path d="M6 3.5h8l4 4V20H6Z"/><path d="M14 3.5V8h4M9 12h6M9 16h6"/>',
      heart:'<path d="M20.5 9.5c0 5-8.5 10-8.5 10s-8.5-5-8.5-10A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8.5 2.5Z"/><path d="M7.5 12h2l1.2-2.5 2.1 5 1.2-2.5h2.5"/>',
      pill:'<path d="m8.2 4.2 11.6 11.6a4.1 4.1 0 0 1-5.8 5.8L2.4 10a4.1 4.1 0 1 1 5.8-5.8Z"/><path d="m8.2 15.8 7.6-7.6"/>',
      appointment:'<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M7 3v4M17 3v4M3.5 9.5h17M8 14l2.2 2.2L16 11"/>',
      shield:'<path d="M12 3 20 6v5.5c0 4.6-3.1 7.7-8 9.5-4.9-1.8-8-4.9-8-9.5V6Z"/><path d="m9 12 2 2 4-4"/>',
      target:'<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
      bell:'<path d="M6 10a6 6 0 0 1 12 0c0 5 2 5.5 2 5.5H4S6 15 6 10Z"/><path d="M10 19h4"/>',
      scale:'<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9a3 3 0 0 1 6 0M12 9l2-2"/>',
      shoe:'<path d="M4 14c3.5.5 6-1 7-4l2 3c1.6 2.3 3.2 3.1 7 3.5V20H8c-2.5 0-4-1.7-4-4Z"/><path d="M12 14h3"/>',
      user:'<circle cx="12" cy="8" r="3.5"/><path d="M5 20v-2a7 7 0 0 1 14 0v2"/>',
      mic:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M9 21h6"/>',
      send:'<path d="M12 19V5M6.5 10.5 12 5l5.5 5.5"/>', panel:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
      result:'<path d="M6 3.5h9l3 3V20H6Z"/><path d="M15 3.5V7h3M9 15l2-2 2 1 3-4"/>', device:'<rect x="6" y="3" width="12" height="18" rx="3"/><path d="M10 17h4"/>'
    };
    const icon=(name,cls='v6-icon')=>`<span class="${cls}" aria-hidden="true"><svg viewBox="0 0 24 24">${paths[name]||paths.sparkle}</svg></span>`;
    const navMap={"HealthIA Chat":"chat","Hoy":"calendar","Mediciones":"activity","Resultados":"chart","Perfil del paciente":"user","Dispositivos":"device","Mi expediente":"folder","Genograma familiar":"family","Documentos":"file","Línea de salud":"heart","Tratamiento":"pill","Citas y consulta":"appointment","Permisos y privacidad":"shield","Misiones de salud":"target"};
    function decorate(){
      const primary=$('.primary-action > span');
      if(primary){
        primary.innerHTML=icon('plus');
        const button=primary.closest('button');
        if(button){ button.title='Nueva consulta'; button.setAttribute('aria-label','Nueva consulta'); }
      }
      $$('.main-nav button').forEach(button=>{
        const label=$('b',button)?.textContent?.trim();
        const holder=button.firstElementChild;
        if(!label||!holder)return;
        holder.className='nav-icon';
        holder.innerHTML=`<svg viewBox="0 0 24 24">${paths[navMap[label]||'sparkle']}</svg>`;
        button.title=label;
        button.dataset.tooltip=label;
        button.setAttribute('aria-label',label);
      });
      const orb=$('.health-orb'); if(orb) orb.innerHTML=icon('sparkle');
      const attach=$('.attach-button'); if(attach) attach.innerHTML=icon('plus');
      const voice=$('#voiceButton'); if(voice) voice.innerHTML=icon('mic');
      const send=$('#sendButton'); if(send) send.innerHTML=icon('send');
      const panel=$('#collapseRight'); if(panel) panel.innerHTML=icon('panel');
      const top=$('.topbar-title'); if(top&&!$('.kira-mark',top)) top.insertAdjacentHTML('afterbegin',icon('sparkle','kira-mark'));
    }
    function boot(){ requestAnimationFrame(decorate); }
    window.HealthIAIcons={decorate,icon};
    if(document.readyState==='loading') window.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
    document.addEventListener('healthia:ui-updated',()=>requestAnimationFrame(decorate));
  })();
}
