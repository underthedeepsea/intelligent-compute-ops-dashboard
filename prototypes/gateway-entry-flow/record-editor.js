(() => {
  'use strict';
  const C=GatewayDirectoryCore;
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  let context=null,dirty=false;
  const host=()=>document.querySelector('#record-editor');
  function show(options){
    context={...options,original:JSON.parse(JSON.stringify(options.row))};dirty=false;
    const {type,row,db}=context;
    host().innerHTML=`<div class="manager-heading"><div><p class="eyebrow">资源与关系目录 / ${esc(C.schemas[type].label)}</p><h1 id="editor-title" tabindex="-1">编辑${esc(C.schemas[type].label)}</h1><p class="muted">${esc(row.name||C.identity(type,row))}</p></div><button type="button" class="button" id="editor-back">返回目录</button></div><form id="record-edit-form"><section class="section"><div class="section-heading"><div><h2>基本信息与关联</h2><small>修改后会同步更新目录与网关总览。</small></div><span class="pill neutral">已保存记录</span></div><div id="editor-feedback" class="notice" role="status" hidden></div><div class="fields">${C.inputFields(type).map(field=>{
      const value=field.key==='environment'?C.environmentCode(row[field.key]):row[field.key]||'',locked=field.key==='code';
      let input;
      const attributes=`id="edit-${field.key}" name="${field.key}" ${field.required?'required':''}`;
      if(field.key==='environment')input=`<select ${attributes}>${C.environments.map(option=>`<option ${value===option?'selected':''}>${option}</option>`).join('')}</select>`;
      else if(field.ref)input=`<select ${attributes}><option value="">${field.required?'请选择':'不关联'}</option>${db[field.ref].map(option=>`<option value="${esc(option.code)}" ${value===option.code?'selected':''}>${esc(option.name)} · ${esc(option.code)}</option>`).join('')}</select>`;
      else if(field.values)input=`<select ${attributes}>${field.values.map(option=>`<option ${value===option?'selected':''}>${esc(option)}</option>`).join('')}</select>`;
      else if(field.array)input=`<textarea ${attributes} placeholder='["worker-01","worker-02"]'>${esc(JSON.stringify(row[field.key]||[]))}</textarea>`;else input=`<input ${attributes} value="${esc(value)}" ${locked?'readonly':''}>`;
      return `<div class="field"><label for="edit-${field.key}">${esc(field.label)}${field.required?'<span class="required">必填</span>':''}</label>${input}${locked?'<small class="hint">保留稳定身份，已有引用继续有效。</small>':''}</div>`;
    }).join('')}</div>${type==='keys'?'<p class="note">此处保存 Key 引用与配置意图；执行端未连接。</p>':''}${type==='runtimes'?'<p class="note">Pod / Node 历史记录只读；原始身份和来源保留。</p>':''}<details class="record-identity"><summary>记录身份（只读）</summary><code>${esc(row.code||C.identity(type,row))}</code></details><p class="editor-meta">录入来源：${esc(row._source||'浏览器录入')} · 最近修改：${esc(row._updated_at||'尚未修改')}</p></section><footer class="editor-actions"><span id="editor-state">尚未修改</span><div><button type="button" class="button" id="editor-cancel">取消</button><button type="submit" class="button primary">保存修改</button></div></footer></form>`;
    host().querySelector('#editor-back').onclick=()=>{if(canLeave())context.onCancel();};
    host().querySelector('#editor-cancel').onclick=()=>{if(canLeave())context.onCancel();};
    host().querySelector('form').oninput=()=>{dirty=true;host().querySelector('#editor-state').textContent='有未保存的修改';};
    host().querySelector('form').onsubmit=event=>{
      event.preventDefault();
      const feedback=host().querySelector('#editor-feedback');
      const formValues=Object.fromEntries(new FormData(event.target));const values=Object.fromEntries(C.inputFields(type).map(field=>[field.key,formValues[field.key]??row[field.key]]));
      const result=context.onSave(values,context.original);
      feedback.hidden=false;feedback.classList.toggle('failure',!result.ok);feedback.textContent=result.ok?'修改已保存，目录和总览已同步更新。':result.message;
      if(result.ok){context.original=JSON.parse(JSON.stringify(result.row));context.row=result.row;host().querySelector('.manager-heading .muted').textContent=result.row.name||C.identity(context.type,result.row);dirty=false;host().querySelector('#editor-state').textContent='已保存';host().querySelector('.editor-meta').textContent='录入来源：'+(result.row._source||'浏览器录入')+' · 最近修改：'+result.row._updated_at;}
      feedback.scrollIntoView({block:'center',behavior:'instant'});
    };
  }
  function canLeave(){if(!dirty)return true;if(!confirm('当前修改尚未保存，确定放弃修改并离开编辑页？'))return false;dirty=false;return true;}
  window.GatewayRecordEditor={show,canLeave,isDirty:()=>dirty};
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
})();
