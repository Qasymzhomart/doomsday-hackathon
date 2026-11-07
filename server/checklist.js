export const defaultChecklist = {
  id:'default', name:'Freedom Broker CQA', version:1,
  criteria:[
    {id:'contact',section:'Начало и понимание запроса',name:'Установление контакта',description:'Оператор поздоровался на языке клиента и представился в первом ответе.',weight:10,type:'boolean',allow_na:false},
    {id:'needs',section:'Начало и понимание запроса',name:'Выявление потребности',description:'Учитывает известные детали и уточняет недостающее. N/A — данных хватало изначально.',weight:15,type:'boolean',allow_na:true},
    {id:'identity',section:'Безопасность и решение',name:'Идентификация',description:'Проверка личности перед раскрытием защищённых данных или действием. N/A — запрос не требует идентификации.',weight:20,type:'boolean',allow_na:true},
    {id:'consultation',section:'Безопасность и решение',name:'Корректная и полная консультация',description:'Качество решения запроса: 20 всё закрыто, 15 основное решено, 10 частично, 5 общая подсказка, 0 нет ответа.',weight:20,type:'scale',scale:[0,5,10,15,20],allow_na:true},
    {id:'empathy',section:'Ведение и завершение диалога',name:'Эмпатия и клиентоориентированность',description:'Вежливость и реакция на конкретную жалобу или неудобство.',weight:15,type:'boolean',allow_na:false},
    {id:'clarity',section:'Ведение и завершение диалога',name:'Управление диалогом, скорость и грамотность',description:'10 ясно и связно; 7 один сбой; 4 нужны переспросы; 0 противоречивые реплики.',weight:15,type:'scale',scale:[0,4,7,10],allow_na:false},
    {id:'closing',section:'Ведение и завершение диалога',name:'Завершение',description:'Итог или дальнейшая помощь и прощание. N/A — чат оборвался.',weight:5,type:'boolean',allow_na:true},
    {id:'critical',section:'Грубые нарушения',name:'Грубые ошибки',description:'Оскорбление, платная услуга в обход компании или раскрытие конфиденциальных данных.',weight:0,type:'critical',allow_na:false}
  ]
};
export function validateChecklist(data){
  if(!data || !Array.isArray(data.criteria) || !data.criteria.length) throw Error('Добавьте минимум один критерий');
  const ids=new Set();
  return {...data,criteria:data.criteria.map(c=>{
    if(!/^[a-z0-9_-]+$/i.test(c.id||'')) throw Error('Некорректный ID критерия');
    if(ids.has(c.id)) throw Error('Повторяющийся ID: '+c.id);ids.add(c.id);
    if(!c.name?.trim() || !Number.isFinite(Number(c.weight)) || Number(c.weight)<0 || Number(c.weight)>100) throw Error('Проверьте название и вес');
    if(!['boolean','scale','critical'].includes(c.type)) throw Error('Неизвестный тип');
    if(c.type==='scale' && (!Array.isArray(c.scale)||c.scale.length<2||c.scale.some(n=>!Number.isFinite(Number(n))||Number(n)<0)||Math.min(...c.scale)!==0||new Set(c.scale).size!==c.scale.length)) throw Error('Шкала должна содержать 0 и уникальные числа');
    return {...c,weight:Number(c.weight),allow_na:!!c.allow_na,scale:c.type==='scale'?c.scale.map(Number).sort((a,b)=>a-b):undefined};
  })};
}
