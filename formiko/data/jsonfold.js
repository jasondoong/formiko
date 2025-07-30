document.addEventListener('click',function(e){
  if(!e.target.classList.contains('jtoggler'))return;
  const block=e.target.parentElement;
  const collapsed=block.classList.toggle('collapsed');
  if(e.altKey){
    block.querySelectorAll('.jblock').forEach(function(el){
      if(el===block)return;
      if(collapsed)el.classList.add('collapsed');
      else el.classList.remove('collapsed');
    });
  }
});
