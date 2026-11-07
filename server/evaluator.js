// Transparent, rule-based demo evaluator. Not an LLM, and never claims semantic accuracy.
const norm=t=>String(t||'').toLocaleLowerCase();
const contains=(t,terms)=>terms.some(w=>t.includes(w));
export function calculate(criteria,ratings){
  const applicable=criteria.filter(c=>c.weight>0 && ratings[c.id]?.answer!=='NA');
  const denominator=applicable.reduce((s,c)=>s+c.weight,0);
  const raw=applicable.reduce((sum,c)=>{
    const a=ratings[c.id]; if(!a)return sum;
    const ratio=c.type==='scale' ? Number(a.answer)/Math.max(...c.scale) : a.answer==='YES'?1:0;
    return sum + c.weight*Math.max(0,Math.min(1,ratio));
  },0);
  const total_score=denominator?Math.round(raw/denominator*10000)/100:null;
  const sections={};
  for(const c of criteria){if(c.weight<=0)continue;const s=c.section||'Прочее';(sections[s]??=[]).push(c);}
  const section_scores=Object.fromEntries(Object.entries(sections).map(([s,group])=>{
    const den=group.filter(c=>ratings[c.id]?.answer!=='NA').reduce((a,c)=>a+c.weight,0);
    const sum=group.reduce((a,c)=>{const r=ratings[c.id];if(!r||r.answer==='NA')return a;return a+c.weight*(c.type==='scale'?Number(r.answer)/Math.max(...c.scale):r.answer==='YES'?1:0);},0);
    return [s,den?Math.round(sum/den*10000)/100:null];
  }));
  return {total_score,section_scores,critical_error:criteria.some(c=>c.type==='critical'&&ratings[c.id]?.answer==='YES')};
}
export function evaluate(conversation,checklist){
  const messages=conversation.transcript||[];
  const op=messages.filter(m=>m.speaker==='operator');const client=messages.filter(m=>m.speaker==='client');
  const text=norm(op.map(m=>m.text).join(' '));const clientText=norm(client.map(m=>m.text).join(' '));
  const first=op[0],last=op[op.length-1],lastMsg=messages[messages.length-1];
  const evidence=m=>m?[{message_id:m.message_id,timestamp:m.timestamp,text:m.text}]:[];
  const yes=(b)=>b?'YES':'NO';
  const results={};
  for(const c of checklist.criteria){
    let answer=c.type==='scale'?0:'NO',reason='Автоматическая эвристика: требуется проверка экспертом.',ev=evidence(first||messages[0]);
    if(c.id==='contact'){
      const greeting=!!first&&contains(norm(first.text),['здравств','добрый','сәлем','қайырлы','hello','hi ','good morning','good afternoon']);
      const introduction=!!first&&contains(norm(first.text),['меня зовут','моё имя','мое имя','менің атым','my name is','это оператор','оператор ']);
      answer=yes(greeting&&introduction);reason=greeting&&!introduction?'Приветствие найдено, но самопредставление не обнаружено в первом ответе.':'Проверены приветствие и представление в первом ответе оператора.';
    }else if(c.id==='needs'){
      const q=op.find(m=>/[?？]/.test(m.text)||contains(norm(m.text),['уточните','подскажите','нақтыла','tell me','could you']));
      answer=q?'YES':(client.length&&clientText.length>80&&c.allow_na?'NA':'NO');ev=evidence(q||first);reason=q?'Обнаружен уточняющий вопрос.':'Уточняющего вопроса не найдено; N/A следует проверять по полноте исходных данных.';
    }else if(c.id==='identity'){
      const sensitive=contains(clientText,['мой счет','моего счёта','вывести деньги','перевести деньги','баланс счета','my account','withdraw','transfer funds','менің шотым']);
      const verified=messages.find(m=>contains(norm(m.text),['идентификац','личность подтвержд','проверка пройден','verified identity','identity verified','жеке басы растал']));
      answer=sensitive?yes(!!verified):'NA';ev=evidence(verified||client.find(m=>contains(norm(m.text),['счет','счёт','withdraw','account']))||client[0]);reason=sensitive?(verified?'В транскрипте есть отметка проверки личности.':'Запрос потенциально защищённый, подтверждение личности не найдено.'):'Обнаружен запрос без явной необходимости идентификации; N/A требует экспертной проверки.';
    }else if(c.id==='consultation'){
      answer=op.length? (contains(text,['пожалуйста','можете','необходимо','нужно','сделать','please','you can','керек','болады'])?15:10):0;ev=evidence(last);reason='Предварительная оценка по наличию содержательного ответа. Корректность финансовой консультации автоматически не подтверждена.';
    }else if(c.id==='empathy'){
      const rude=contains(text,['идиот','дурак','stupid','ақымақ']);answer=yes(!rude);ev=evidence(op.find(m=>contains(norm(m.text),['извин','понимаю','sorry','түсінем']))||first);reason=rude?'Найдена потенциально грубая формулировка.':'Не обнаружены известные оскорбления; реакцию на жалобу нужно проверить вручную.';
    }else if(c.id==='clarity'){
      answer=op.length?10:0;ev=evidence(last);reason='Эвристическая оценка связности, скорости и ясности; подтвердите вручную.';
    }else if(c.id==='closing'){
      const closed=!!last&&contains(norm(last.text),['до свидания','всего доброго','обращайтесь','рады помочь','сау болыңыз','рахмет','goodbye','have a nice day','anything else']);
      answer=lastMsg?.speaker==='system'&&contains(norm(lastMsg.text),['обрыв','disconnected'])?'NA':yes(closed);ev=evidence(last||lastMsg);reason=answer==='NA'?'Диалог прервался до завершения.':'Проверена последняя реплика оператора на прощание или предложение помощи.';
    }else if(c.id==='critical'){
      const suspicious=op.find(m=>contains(norm(m.text),['переведите мне лично','лично мне на карту','pay me privately','в обход компании']));answer=yes(!!suspicious);ev=evidence(suspicious||last);reason=suspicious?'Обнаружена фраза возможной услуги в обход компании.':'Грубое нарушение не обнаружено эвристикой; требуется ручная проверка.';
    }else{
      answer=c.type==='scale'?Math.max(...c.scale):'NO';reason='Новый критерий: автоматическое правило не настроено; обязательно пересмотрите оценку вручную.';
    }
    results[c.id]={criterion_id:c.id,name:c.name,answer,weight:c.weight,max_score:c.type==='scale'?Math.max(...c.scale||[0]):1,score:answer==='NA'?null:answer==='YES'?1:answer==='NO'?0:Number(answer),applicable:answer!=='NA',reason,evidence:ev,critical_error:c.type==='critical'&&answer==='YES',heuristic:true};
  }
  const summary=calculate(checklist.criteria,results);
  return {conversation_id:conversation.conversation_id,checklist_version:checklist.version,criteria:Object.values(results),...summary,reviewed:false,automated_method:'rule-based heuristic demo, not AI'};
}
