// Minimal JS: drag & drop, file binding, show overlay on submit
document.addEventListener('DOMContentLoaded', function(){
  const drop = document.querySelector('.dropzone');
  const fileInput = document.querySelector('input[type=file]');
  const fileName = document.querySelector('.file-name');
  const previewImg = document.querySelector('.file-preview');
  const compressBtn = document.getElementById('compress-btn');
  const form = document.querySelector('form');
  const progressWrap = document.querySelector('.progress');
  const loadingOverlay = document.querySelector('.loading-overlay');
  const heroCta = document.getElementById('hero-cta');
  const navTry = document.getElementById('nav-try');
  const topNav = document.querySelector('.top-nav');
  const glassCard = document.querySelector('.glass-card');
  const cancelBtn = document.querySelector('.loader-cancel');
  const deleteBtn = document.getElementById('delete-upload-btn');
  let currentJobId = null;
  let pollTimer = null;

  function prevent(e){ e.preventDefault(); e.stopPropagation(); }

  ['dragenter','dragover','dragleave','drop'].forEach(evt=>{
    drop.addEventListener(evt, prevent);
  });

  drop.addEventListener('dragover', function(){ drop.classList.add('dragover'); });
  drop.addEventListener('dragleave', function(){ drop.classList.remove('dragover'); });

  drop.addEventListener('drop', function(e){
    drop.classList.remove('dragover');
    const dt = e.dataTransfer;
    if(!dt) return;
    const files = dt.files;
    if(files && files.length){
      fileInput.files = files;
      updateFileDisplay(files[0]);
    }
  });

  drop.addEventListener('click', ()=> fileInput.click());

  fileInput.addEventListener('change', function(e){
    const f = e.target.files[0];
    if(f) updateFileDisplay(f);
  });

  // initialize compress button state
  if(compressBtn) compressBtn.disabled = true;

  // show/hide validation error when file selected
  const formError = document.querySelector('.form-error');
  function showFormError(show){
    if(!formError) return;
    formError.style.display = show ? 'block' : 'none';
  }

  function updateFileDisplay(f){
    fileName.textContent = f.name;

    // image preview if image
    if(f.type && f.type.startsWith('image/')){
      const reader = new FileReader();
      reader.onload = function(ev){
        previewImg.src = ev.target.result;
        previewImg.style.display = 'block';
      }
      reader.readAsDataURL(f);
    } else {
      previewImg.style.display = 'none';
    }
    // enable compress button when a file is present
    if(compressBtn) compressBtn.disabled = false;
  }

  // On submit: start job and poll server for ffmpeg progress
  form.addEventListener('submit', function(e){
    e.preventDefault();

    if(!fileInput.files || !fileInput.files.length){
      // show inline validation instead of alert
      showFormError(true);
      drop.classList.add('dragover');
      setTimeout(()=> drop.classList.remove('dragover'), 1200);
      if(compressBtn) compressBtn.focus();
      return;
    }
    showFormError(false);

    // prepare UI
    loadingOverlay.classList.add('show');
    progressWrap.classList.add('animate');
    const circle = document.querySelector('.progress-value');
    const pct = document.querySelector('.progress-text');
    const timeLeft = document.querySelector('.time-left');
    const radius = circle.r.baseVal.value;
    const circumference = 2 * Math.PI * radius;
    circle.style.strokeDasharray = circumference;
    circle.style.strokeDashoffset = circumference;

    function setPercent(n){
      const clamped = Math.max(0, Math.min(100, Math.round(n)));
      const offset = circumference - (clamped / 100) * circumference;
      circle.style.strokeDashoffset = offset;
      pct.textContent = clamped + '%';
      if(clamped > 0) circle.classList.add('green'); else circle.classList.remove('green');
    }

    setPercent(0);

    const fd = new FormData(form);

    fetch('/start', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        if(data.error){
          alert('Failed to start job: ' + data.error);
          loadingOverlay.classList.remove('show'); progressWrap.classList.remove('animate');
          return;
        }

        currentJobId = data.job_id;

        // show cancel button and disable compress button while job runs
        if(cancelBtn){ cancelBtn.style.display = 'inline-block'; }
        if(compressBtn){ compressBtn.disabled = true; compressBtn.setAttribute('aria-busy', 'true'); }

        // poll for progress
        pollTimer = setInterval(function(){
          fetch('/progress/' + currentJobId).then(r=>r.json()).then(j=>{
            if(j.error){ return; }
              const pctv = j.percent || 0;
              setPercent(pctv);
              // also tint linear progress green when >0
              if(progressWrap){ if(pctv > 0) progressWrap.classList.add('green'); else progressWrap.classList.remove('green'); }
            if(j.time_left != null){
              const s = Math.max(0, Math.round(j.time_left));
              const mm = Math.floor(s/60).toString().padStart(2,'0');
              const ss = (s%60).toString().padStart(2,'0');
              timeLeft.textContent = 'Time left: ' + mm + ':' + ss;
            }
            if(j.status === 'done'){
              clearInterval(pollTimer);
              // download
              if(j.download_url){
                const a = document.createElement('a');
                a.href = j.download_url;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                a.remove();
              }
              // cleanup UI
              setTimeout(()=>{ loadingOverlay.classList.remove('show'); progressWrap.classList.remove('animate'); progressWrap.classList.remove('green'); setPercent(0); timeLeft.textContent='Time left: --:--'; if(cancelBtn) cancelBtn.style.display='none'; if(compressBtn){ compressBtn.disabled = false; compressBtn.removeAttribute('aria-busy'); } currentJobId=null; }, 800);
            }
          }).catch(()=>{});
        }, 900);

      }).catch(err => { alert('Network error starting job'); loadingOverlay.classList.remove('show'); progressWrap.classList.remove('animate'); });

    // cancel handler: send job_id to /cancel
    if(cancelBtn){
      cancelBtn.style.display = 'inline-block';
      cancelBtn.onclick = function(){
        if(currentJobId){
          fetch('/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id: currentJobId})}).catch(()=>{});
        }
        if(pollTimer) clearInterval(pollTimer);
        loadingOverlay.classList.remove('show'); progressWrap.classList.remove('animate'); progressWrap.classList.remove('green');
        const pctE = document.querySelector('.progress-text'); if(pctE) pctE.textContent = '0%';
        const tl = document.querySelector('.time-left'); if(tl) tl.textContent = 'Time left: --:--';
        if(cancelBtn){ cancelBtn.style.display='none'; }
        if(compressBtn){ compressBtn.disabled = false; compressBtn.removeAttribute('aria-busy'); }
        currentJobId = null;
      };
    }

    // delete-upload handler: best-effort request to remove files from server
    if(deleteBtn){
      deleteBtn.onclick = function(){
        if(!currentJobId){
          // nothing server-side yet
          deleteBtn.style.display = 'none';
          return;
        }
        fetch('/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({job_id: currentJobId})})
          .then(r=>r.json()).then(res=>{
            // hide delete and reset UI
            deleteBtn.style.display = 'none';
            if(cancelBtn) cancelBtn.style.display = 'none';
            if(compressBtn) { compressBtn.disabled = false; compressBtn.removeAttribute('aria-busy'); }
            currentJobId = null;
          }).catch(()=>{
            // best-effort: hide button
            deleteBtn.style.display = 'none';
            currentJobId = null;
          });
      };
    }
  });

  // Hero CTA: smooth scroll to form
  function scrollToForm(){
    if(!glassCard) return;
    const top = glassCard.getBoundingClientRect().top + window.scrollY - 20;
    window.scrollTo({top, behavior:'smooth'});
  }
  if(heroCta) heroCta.addEventListener('click', scrollToForm);
  if(navTry) navTry.addEventListener('click', function(e){ e.preventDefault(); scrollToForm(); });

  // Sticky nav behavior (adds small shadow on scroll)
  if(topNav){
    window.addEventListener('scroll', function(){
      if(window.scrollY > 40) topNav.classList.add('scrolled'); else topNav.classList.remove('scrolled');
    });
  }

  // Reveal animation for glass card when it enters viewport
  if(glassCard){
    glassCard.classList.add('reveal');
    const io = new IntersectionObserver((entries)=>{
      entries.forEach(ent=>{
        if(ent.isIntersecting){
          glassCard.classList.add('show');
          io.disconnect();
        }
      });
    }, {threshold:0.12});
    io.observe(glassCard);
  }
});