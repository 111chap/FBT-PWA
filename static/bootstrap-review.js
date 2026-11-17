document.addEventListener('DOMContentLoaded',()=> {
  const form=document.querySelector('.auth-card form');
  let sending=false, reviewing=false;
  form.addEventListener('submit',async event=> {
    if(sending) return;
    event.preventDefault(); if(reviewing) return; reviewing=true;
    const draft=JSON.stringify(Array.from(new FormData(form).entries()));
    const accepted=await FBTReview({title:'Create your family administrator?',rows:[['Family name',form.elements.family_name.value],['Username',form.elements.username.value],['Access','Family administrator'],['Setup code and password','Hidden for your privacy']],action:'Create family workspace'});
    reviewing=false;
    if(accepted && draft===JSON.stringify(Array.from(new FormData(form).entries()))) { sending=true; form.requestSubmit(); }
  });
});
