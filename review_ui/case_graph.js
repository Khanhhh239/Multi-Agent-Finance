/* Local Cytoscape rendering and graph models shared by both case views. */
"use strict";
globalThis.CaseGraph = (() => {
  const colors={employee:"#76a98e",vendor:"#7b91d1",bank:"#c9a46a",bank_account:"#c9a46a",phone:"#8e7cbb",address:"#9aa8b4",tax_code:"#67a9b7",transaction:"#8399ba",representative:"#a18dbb"};
  const kinds={employee:"Nhân viên",vendor:"Nhà cung cấp",bank_account:"Tài khoản ngân hàng",phone:"Số điện thoại",address:"Địa chỉ",tax_code:"Mã số thuế"};
  const mounted=new Map();
  function networkElements(network) {
    const elements=network.nodes.map(node=>({data:{id:node.id,label:String(node.label||node.entity_id||""),kind:node.type,
      color:colors[node.type]||"#8399ba",info:`${kinds[node.type]||node.type}: ${node.label||""}${node.entity_id?" · "+node.entity_id:""}${node.matchable===false?" · Chưa xác nhận định danh":""}`}}));
    const ids=new Set(network.nodes.map(node=>node.id));
    network.links.forEach((edge,i)=>{if(ids.has(edge.source)&&ids.has(edge.target))elements.push({data:{id:"edge:"+i,source:edge.source,target:edge.target,label:kinds[edge.relation]||edge.relation||"Quan hệ",weak:edge.strength==="weak_context"?1:0,info:`${kinds[edge.relation]||edge.relation} · ${edge.observed_at||""}`}});});
    return elements;
  }
  function evidenceElements(data, maximum=18) {
    const nodes=new Map(), edges=[];
    function add(id,kind,label,info){if(!nodes.has(id))nodes.set(id,{data:{id,kind,label:String(label),color:colors[kind]||colors.representative,info:info||String(label)}});}
    function entity(id){const raw=id.slice(id.indexOf(":")+1), known=data.entities[raw], kind=known?(known.vendor_id?"vendor":"employee"):id.startsWith("bank_account:")?"bank":id.startsWith("phone:")?"phone":"representative";add(id,kind,known?(known.name||known.full_name):raw,known?`${raw} · ${known.name||known.full_name}`:raw);}
    const seen=new Set();
    for(const edge of data.graph_edges){const key=JSON.stringify([edge.source,edge.target].sort());if(seen.has(key))continue;seen.add(key);entity(edge.source);entity(edge.target);edges.push({data:{id:"edge:"+edges.length,source:edge.source,target:edge.target,label:edge.link_type==="phone"?"Cùng SĐT":edge.link_type==="representative"?"Đại diện":"Cùng tài khoản",info:edge.observed_at||""}});}
    if(!edges.length)for(const tx of data.transactions.slice(0,6)) {
      const id="transaction:"+tx.transaction_id;add(id,"transaction",tx.transaction_id,`${tx.posted_at} · ${tx.amount_vnd} VND`);
      const recipient=tx.vendor_id||tx.employee_id||tx.creator_id;
      if(recipient){const other="entity:"+recipient;entity(other);edges.push({data:{id:"edge:"+edges.length,source:id,target:other,label:tx.vendor_id||tx.employee_id?"Đối tượng":"Người lập"}});
        if(tx.recipient_account){const bank="bank:"+(tx.recipient_bank_code||"unverified:"+recipient)+":"+tx.recipient_account;add(bank,"bank","TK · "+tx.recipient_account.slice(-8),`${tx.recipient_bank_code||"Chưa xác nhận ngân hàng"} · ${tx.recipient_account}`);edges.push({data:{id:"edge:"+edges.length,source:other,target:bank,label:"Thụ hưởng"}});}
      }
    }
    const visible=[...nodes.values()].slice(0,maximum), ids=new Set(visible.map(n=>n.data.id));
    return {elements:visible.concat(edges.filter(e=>ids.has(e.data.source)&&ids.has(e.data.target))),total:nodes.size,shown:visible.length};
  }
  function mount(container,elements,detail,network=false) {
    if(!container)return null;
    mounted.get(container.id)?.destroy();
    if(typeof cytoscape!=="function"){container.textContent="Chưa nạp được sơ đồ. Vui lòng tải lại trang.";return null;}
    const cy=cytoscape({container,elements,layout:{name:network?"breadthfirst":"grid",directed:false,padding:35,animate:false},minZoom:.2,maxZoom:3,wheelSensitivity:.2,
      style:[{selector:"node",style:{label:"data(label)","background-color":"data(color)",width:24,height:24,"font-size":11,"text-valign":"bottom","text-margin-y":7,"text-max-width":110,"text-wrap":"ellipsis",color:"#435571","border-width":2,"border-color":"#fff"}},
        {selector:"edge",style:{width:1.5,"line-color":"#becbdf","curve-style":"bezier"}},
        {selector:"edge[weak = 1]",style:{"line-style":"dashed","line-color":"#d6dee7"}},
        {selector:":selected",style:{"border-width":4,"border-color":"#3d648b","line-color":"#3d648b",width:30,height:30}}]});
    cy.on("tap","node, edge",event=>{if(detail){detail.textContent=event.target.data("info")||event.target.data("label");detail.classList.remove("hidden");}});
    mounted.set(container.id,cy);
    return cy;
  }
  function dispose(id){const cy=mounted.get(id);if(cy){cy.destroy();mounted.delete(id);}}
  return {networkElements,evidenceElements,mount,dispose};
})();
