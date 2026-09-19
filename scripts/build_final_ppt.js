const pptxgen = require('pptxgenjs');
const path = require('path');
const fs = require('fs');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = '第五个季节团队';
pptx.subject = '2026 EL 智能应用开发与创新大赛终审答辩';
pptx.title = '第五季·续种——校园未竟梦想的AI传承智能体';
pptx.company = '第五个季节';
pptx.lang = 'zh-CN';
pptx.theme = {
  headFontFace: 'Microsoft YaHei', bodyFontFace: 'Microsoft YaHei', lang: 'zh-CN'
};
pptx.defineLayout({ name: 'CUSTOM', width: 13.333, height: 7.5 });
pptx.layout = 'CUSTOM';

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, '决赛材料');
fs.mkdirSync(OUT, { recursive: true });
const intro = path.join(ROOT, 'docs', 'video_assets', 'screens', '01-intro.png');
const chat = path.join(ROOT, 'docs', 'video_assets', 'screens', '02-chat.png');
const preview = path.join(ROOT, 'docs', '_video_preview', 'final.png');

const C = { bg:'F7F7FB', ink:'182236', sub:'60708A', purple:'7257D5', lavender:'EEE9FF', green:'4E9E6B', mint:'E9F6EE', gold:'E0A235', orange:'D97444', blue:'5C86C4', white:'FFFFFF', line:'D9DDEA', red:'B44B5A' };
const S = pptx.ShapeType;

function base(slide, no, section) {
  slide.background = { color: C.bg };
  slide.addShape(S.rect, { x:0, y:0, w:13.333, h:0.09, line:{color:C.purple, transparency:100}, fill:{color:C.purple} });
  slide.addText(section, { x:0.55, y:7.05, w:5.2, h:0.18, fontFace:'Microsoft YaHei', fontSize:9, color:C.sub, margin:0 });
  slide.addText(String(no).padStart(2,'0') + ' / 07', { x:11.8, y:7.02, w:0.95, h:0.2, fontSize:9, bold:true, color:C.purple, align:'right', margin:0 });
}
function title(slide, kicker, heading, sub) {
  slide.addText(kicker, { x:0.68, y:0.42, w:4.8, h:0.23, fontSize:10, bold:true, color:C.purple, charSpacing:1.6, margin:0 });
  slide.addText(heading, { x:0.68, y:0.78, w:11.9, h:0.62, fontSize:26, bold:true, color:C.ink, margin:0, breakLine:false });
  if (sub) slide.addText(sub, { x:0.7, y:1.48, w:11.6, h:0.34, fontSize:12.5, color:C.sub, margin:0 });
}
function card(slide, x,y,w,h, fill=C.white, line=C.line, radius=0.16) {
  slide.addShape(S.roundRect, { x,y,w,h, rectRadius:radius, fill:{color:fill}, line:{color:line, width:1} });
}
function pill(slide, text, x,y,w, fill, color=C.ink) {
  slide.addShape(S.roundRect, { x,y,w,h:0.38, rectRadius:0.18, fill:{color:fill}, line:{color:fill} });
  slide.addText(text, { x:x+0.05,y:y+0.08,w:w-0.1,h:0.18,fontSize:10.5,bold:true,color,align:'center',margin:0 });
}
function note(slide, seconds, text) {
  slide.addNotes(`【建议用时 ${seconds} 秒】\n${text}`);
}

// 1 封面
{
  const s = pptx.addSlide(); base(s,1,'第五季·续种｜终审答辩');
  s.addImage({ path:intro, x:0, y:0.09, w:13.333, h:6.82, transparency:12 });
  s.addShape(S.rect,{x:0,y:0.09,w:13.333,h:6.82,fill:{color:'FFFFFF',transparency:28},line:{transparency:100}});
  pill(s,'2026 EL · AI 智能体创新专项组',0.72,0.68,3.15,C.lavender,C.purple);
  s.addText('第五季·续种', { x:0.72,y:1.55,w:7.3,h:0.9,fontSize:42,bold:true,color:C.ink,margin:0 });
  s.addText('校园未竟梦想的 AI 传承智能体', { x:0.76,y:2.58,w:7.3,h:0.44,fontSize:21,bold:true,color:C.purple,margin:0 });
  s.addText('让项目在毕业、换届与暂停之后，仍能被理解、被授权、被接续。', { x:0.76,y:3.22,w:7.6,h:0.5,fontSize:15,color:C.sub,margin:0 });
  pill(s,'四季状态机',0.76,4.14,1.55,C.mint,C.green); pill(s,'可解释匹配',2.45,4.14,1.68,C.lavender,C.purple); pill(s,'接续治理',4.27,4.14,1.55,'FFF2E8',C.orange);
  s.addText('团队：第五个季节', { x:0.76,y:5.07,w:3.2,h:0.26,fontSize:12,bold:true,color:C.ink,margin:0 });
  note(s,15,'各位评委老师好，我们是“第五个季节”。我们关注的不是如何再做一个校园项目，而是如何让已经投入过时间和热爱的项目，不因毕业和换届而归零。');
}

// 2 痛点
{
  const s = pptx.addSlide(); base(s,2,'问题定义'); title(s,'WHY NOW','项目真正的损失，不是暂停，而是经验一起消失','传统云盘保存文件，却保存不了“为什么这样做、下一步怎么走、谁能接得住”。');
  const items=[['毕业 / 换届','负责人离场，项目失去上下文',C.orange],['资料散落','成果、权限、联系人不可复用',C.blue],['新人断层','有兴趣的人找不到合适入口',C.green]];
  items.forEach((it,i)=>{const x=0.72+i*4.17;card(s,x,2.12,3.75,2.08);s.addShape(S.ellipse,{x:x+0.22,y:2.38,w:0.48,h:0.48,fill:{color:it[2]},line:{transparency:100}});s.addText(String(i+1),{x:x+0.22,y:2.48,w:0.48,h:0.16,fontSize:12,bold:true,color:C.white,align:'center',margin:0});s.addText(it[0],{x:x+0.88,y:2.31,w:2.45,h:0.32,fontSize:19,bold:true,color:C.ink,margin:0});s.addText(it[1],{x:x+0.25,y:3.02,w:3.18,h:0.72,fontSize:14,color:C.sub,breakLine:false,margin:0.02,valign:'mid'});});
  card(s,0.72,4.62,11.9,1.28,C.ink,C.ink);
  s.addText('我们的判断', {x:1.02,y:4.92,w:1.4,h:0.25,fontSize:12,bold:true,color:'B9C4D8',margin:0});
  s.addText('校园项目需要的不是“墓碑式归档”，而是一套能在合适时机重新启动的传承机制。',{x:2.45,y:4.81,w:9.55,h:0.45,fontSize:20,bold:true,color:C.white,margin:0});
  note(s,30,'校园项目常常不是做失败了，而是负责人毕业、社团换届或阶段性时间不足。资料还在网盘里，但经验、授权边界和下一步行动一起消失。我们的判断是：校园需要的不是墓碑式归档，而是可被重新启动的传承机制。');
}

// 3 方案
{
  const s = pptx.addSlide(); base(s,3,'解决方案'); title(s,'THE FIFTH SEASON','AI 接管的不是项目，而是“传承生命周期”','知颜把散落的信息变成结构化档案，并在合适的人出现时完成可解释的接续。');
  const stages=[['春','建档',C.green],['夏','执行',C.gold],['秋','沉淀',C.orange],['冬','休眠',C.blue],['第五季','接棒',C.purple]];
  stages.forEach((st,i)=>{const x=0.62+i*2.52;card(s,x,2.05,2.1,1.22,i===4?C.lavender:C.white,st[2]);s.addText(st[0],{x:x+0.12,y:2.25,w:1.86,h:0.32,fontSize:21,bold:true,color:st[2],align:'center',margin:0});s.addText(st[1],{x:x+0.12,y:2.72,w:1.86,h:0.2,fontSize:11.5,color:C.sub,align:'center',margin:0});if(i<4)s.addText('→',{x:x+2.1,y:2.44,w:0.42,h:0.25,fontSize:18,bold:true,color:C.sub,align:'center',margin:0});});
  const feats=[['交接包五件套','成果 · 经验 · 踩坑 · 遗留 · 资源'],['三层唤醒叙事','种子的故事 · 为什么是你 · 第一行动'],['全程留痕','匹配理由 · 状态变化 · 后续动态']];
  feats.forEach((f,i)=>{const x=0.72+i*4.02;card(s,x,3.72,3.62,1.48,i===0?C.mint:i===1?C.lavender:'FFF5E8');s.addText(f[0],{x:x+0.24,y:4.02,w:3.1,h:0.3,fontSize:16,bold:true,color:C.ink,margin:0});s.addText(f[1],{x:x+0.24,y:4.5,w:3.1,h:0.28,fontSize:11.5,color:C.sub,margin:0});});
  s.addText('26 个工具协同 · 14 张业务表 · Web 端自然语言完成全流程', {x:0.74,y:5.58,w:11.8,h:0.32,fontSize:13,bold:true,color:C.purple,align:'center',margin:0});
  note(s,35,'我们把项目生命周期设计成五个阶段：萌芽、执行、沉淀、休眠和第五季接棒。知颜通过自然语言完成建档、组队、动态记录、交接包、休眠和唤醒。重点不是功能多，而是每次接棒都留下三类证据：交接内容、匹配理由和后续动态。');
}

// 4 演示闭环
{
  const s = pptx.addSlide(); base(s,4,'核心演示'); title(s,'LIVE FLOW','一次接棒，系统做了哪四件关键事？','演示建议：现场用一句话触发“查看休眠项目 → 完整资料 → 匹配解释 → 确认接棒”。');
  s.addImage({path:chat,x:0.72,y:1.95,w:6.18,h:4.36});
  s.addShape(S.roundRect,{x:0.72,y:1.95,w:6.18,h:4.36,fill:{color:'FFFFFF',transparency:100},line:{color:C.purple,width:1.2}});
  const steps=[['01','读取完整档案','成员、动态、交接包'],['02','计算匹配证据','能力命中、缺口、不确定性'],['03','校验接续准备度','五件套 + 过程 + 治理声明'],['04','本人确认后接棒','变更负责人并生成传承故事']];
  steps.forEach((st,i)=>{const y=1.95+i*1.08;card(s,7.3,y,5.25,0.86,i===2?C.lavender:C.white,i===2?C.purple:C.line);pill(s,st[0],7.52,y+0.22,0.55,i===2?C.purple:C.ink,C.white);s.addText(st[1],{x:8.25,y:y+0.15,w:2.55,h:0.25,fontSize:15,bold:true,color:C.ink,margin:0});s.addText(st[2],{x:8.25,y:y+0.49,w:3.9,h:0.18,fontSize:10.5,color:C.sub,margin:0});});
  s.addText('演示底线：没有完整资料、不明确授权、不经本人确认，不执行正式唤醒。',{x:7.38,y:6.35,w:5.0,h:0.28,fontSize:11.5,bold:true,color:C.red,margin:0});
  note(s,50,'现场我们只演示一个闭环。用户说想接棒休眠项目，知颜先读取完整档案，再解释能力命中和缺口；随后检查交接包五件套、过程动态、授权范围、资源有效期和原团队权益。只有准备度满分且本人确认，系统才变更负责人并生成传承故事。我们的底线是：AI 推荐不等于AI替人做决定。');
}

// 5 匹配与治理
{
  const s = pptx.addSlide(); base(s,5,'技术创新'); title(s,'EXPLAINABLE AGENT','匹配可解释，接续有边界','把评委最担心的“黑箱推荐”和“资料滥用”做成系统约束。');
  card(s,0.72,2.0,5.75,3.86,C.white); s.addText('四维匹配评分',{x:1.0,y:2.3,w:2.4,h:0.32,fontSize:19,bold:true,color:C.ink,margin:0});
  const bars=[['技能互补',40,C.purple],['兴趣 / 议题',35,C.green],['传承准备度',15,C.orange],['时间投入',10,C.blue]];
  bars.forEach((b,i)=>{const y=2.95+i*0.62;s.addText(b[0],{x:1.0,y:y,w:1.25,h:0.2,fontSize:11,color:C.sub,margin:0});s.addShape(S.roundRect,{x:2.3,y:y+0.02,w:3.25,h:0.18,fill:{color:'E9ECF3'},line:{transparency:100}});s.addShape(S.roundRect,{x:2.3,y:y+0.02,w:3.25*b[1]/40,h:0.18,fill:{color:b[2]},line:{transparency:100}});s.addText(b[1]+'%',{x:5.65,y:y-0.01,w:0.5,h:0.2,fontSize:10,bold:true,color:b[2],margin:0});});
  s.addText('未知维度不补分｜显示命中证据、能力缺口与决策边界',{x:1.0,y:5.42,w:5.0,h:0.22,fontSize:10.5,bold:true,color:C.purple,margin:0});
  card(s,6.82,2.0,5.8,3.86,C.ink,C.ink);s.addText('100 分接续准备度',{x:7.12,y:2.3,w:3.4,h:0.32,fontSize:19,bold:true,color:C.white,margin:0});
  const checks=[['50','交接包五件套'],['20','过程动态可追溯'],['10','授权范围'],['10','资源有效期'],['10','原团队权益']];
  checks.forEach((c,i)=>{const y=2.92+i*0.52;pill(s,c[0],7.12,y,0.55,C.purple,C.white);s.addText(c[1],{x:7.88,y:y+0.09,w:3.9,h:0.2,fontSize:12.5,color:C.white,margin:0});});
  s.addText('未满 100 分：阻断正式唤醒，返回待补项',{x:7.12,y:5.48,w:4.9,h:0.22,fontSize:11,bold:true,color:'FFCFD6',margin:0});
  note(s,40,'匹配采用四维权重，技能四成、兴趣议题三成半、传承准备度一成半、时间投入一成。档案里没有时间投入就明确标为未知，不臆测补分。另一侧是接续治理：五件套、过程动态、授权、有效期、原团队权益合计一百分，未满分就阻断唤醒。');
}

// 6 证据边界
{
  const s = pptx.addSlide(); base(s,6,'验证与边界'); title(s,'EVIDENCE, NOT PROMISES','我们已经证明“流程可运行”，尚未声称“长期效果已成立”','这是对评审意见最直接的回应：运行证据与跨周期成效严格分开。');
  card(s,0.72,2.0,5.75,3.75,C.mint,'CDE8D7');s.addText('已经完成',{x:1.02,y:2.3,w:1.8,h:0.32,fontSize:20,bold:true,color:C.green,margin:0});
  ['四季状态机全链路','交接包与接棒记录可追溯','可解释匹配与缺项披露','验证中心实时聚合数据库口径'].forEach((t,i)=>{s.addText('✓',{x:1.04,y:2.98+i*0.55,w:0.3,h:0.2,fontSize:13,bold:true,color:C.green,margin:0});s.addText(t,{x:1.42,y:2.94+i*0.55,w:4.5,h:0.25,fontSize:13,color:C.ink,margin:0});});
  card(s,6.82,2.0,5.8,3.75,'FFF5E8','F1D3B4');s.addText('仍待真实试点',{x:7.12,y:2.3,w:2.4,h:0.32,fontSize:20,bold:true,color:C.orange,margin:0});
  ['首轮 3—5 个真实社团项目','8 周跟踪：0 周授权，1 周交接，2—8 周执行','资料可用率目标 ≥ 80%','30 天活跃率目标 ≥ 60%','样本少于 10：只作案例结论'].forEach((t,i)=>{s.addText('•',{x:7.14,y:2.91+i*0.5,w:0.26,h:0.2,fontSize:13,bold:true,color:C.orange,margin:0});s.addText(t,{x:7.5,y:2.9+i*0.5,w:4.6,h:0.25,fontSize:12.5,color:C.ink,margin:0});});
  s.addText('不把演示种子当试点，不用小样本推导普遍结论。',{x:0.76,y:6.08,w:11.8,h:0.28,fontSize:15,bold:true,color:C.purple,align:'center',margin:0});
  note(s,45,'我们认真接受评审对数据规模和长期效果的质疑。目前我们能证明的是流程可运行、数据可留痕，不能把演示库说成真实跨届成效。下一步首轮招募三到五个真实社团项目，连续八周跟踪资料可用率、三十天活跃率和首个里程碑。样本少于十，只做案例结论，不做普遍性推断。');
}

// 7 结尾
{
  const s = pptx.addSlide(); base(s,7,'结束');
  s.addImage({path:preview,x:0,y:0.09,w:13.333,h:6.82,transparency:30});
  s.addShape(S.rect,{x:0,y:0.09,w:13.333,h:6.82,fill:{color:'F7F7FB',transparency:18},line:{transparency:100}});
  pill(s,'OUR ANSWER',0.72,0.72,1.75,C.lavender,C.purple);
  s.addText('我们不承诺每颗种子都能重生。',{x:0.72,y:1.55,w:8.8,h:0.68,fontSize:31,bold:true,color:C.ink,margin:0});
  s.addText('但我们让每一次交接，都比“从零开始”更可靠。',{x:0.72,y:2.45,w:10.5,h:0.7,fontSize:29,bold:true,color:C.purple,margin:0});
  card(s,0.72,3.62,8.7,1.42,C.white,C.line);s.addText('建档可追溯  ·  匹配可解释  ·  授权有边界  ·  效果能复盘',{x:1.0,y:4.12,w:8.15,h:0.38,fontSize:17,bold:true,color:C.ink,align:'center',margin:0});
  s.addText('第五季·续种', {x:0.75,y:5.48,w:3.5,h:0.34,fontSize:18,bold:true,color:C.purple,margin:0});
  s.addText('让未完成的美好，拥有下一位同行者。',{x:0.75,y:5.94,w:5.8,h:0.3,fontSize:14,color:C.sub,margin:0});
  note(s,25,'我们不承诺每一颗种子都能重生，但我们希望每一次交接，都比从零开始更可靠：建档可追溯，匹配可解释，授权有边界，效果能复盘。第五季，让未完成的美好拥有下一位同行者。谢谢各位老师。');
}

pptx.writeFile({ fileName: path.join(OUT, '第五个季节_终审答辩_4分钟.pptx'), compression: true });
