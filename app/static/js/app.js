document.addEventListener('DOMContentLoaded',()=>{
  const sidebar=document.querySelector('#sidebar');
  document.querySelector('[data-menu-toggle]')?.addEventListener('click',()=>sidebar?.classList.toggle('open'));
  document.querySelectorAll('[data-dismiss]').forEach(btn=>btn.addEventListener('click',()=>btn.parentElement?.remove()));
  document.querySelector('[data-password-toggle]')?.addEventListener('click',e=>{const input=document.querySelector('#password');if(!input)return;const shown=input.type==='text';input.type=shown?'password':'text';e.currentTarget.textContent=shown?'Show':'Hide';});
  const csrf=document.cookie.split('; ').find(x=>x.startsWith('csrf_token='))?.split('=')[1];
  document.querySelectorAll('[data-review-correction]').forEach(btn=>btn.addEventListener('click',async()=>{
    const id=btn.dataset.reviewCorrection;const decision=btn.dataset.decision;
    btn.disabled=true;
    const res=await fetch(`/api/corrections/${id}/review`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf||'')},body:JSON.stringify({decision})});
    if(res.ok) location.reload(); else {btn.disabled=false;alert('The correction could not be updated. Refresh and try again.');}
  }));
});
