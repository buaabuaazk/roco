import { useEffect, useRef } from 'react'

export type DamageAnswer = {estimated_damage: number; damage_percent?: number; estimated_ko?: boolean; steps: {label: string; expression: string; value: number}[]; assumptions: string[]; matchup?: {attacker: {name: string}; defender: {name: string}; skill: {name: string}; channel: string}}
const number = (value: number) => value.toLocaleString('zh-CN', {maximumFractionDigits: 6})
export default function DamageResult({answer}: {answer?: DamageAnswer}) {
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {if (answer && window.innerWidth <= 1100) panel.current?.scrollIntoView({behavior: 'smooth', block: 'start'})}, [answer])
  return <section ref={panel} className="damage-result" aria-live="polite"><div className="damage-result-heading"><span className="section-kicker">ESTIMATE</span><h2>计算结果</h2><span>单次伤害 · 待游戏内实测验证</span></div>
    {answer ? <>{answer.matchup && <div className="matchup-summary"><strong>{answer.matchup.attacker.name} → {answer.matchup.defender.name}</strong><span>{answer.matchup.skill.name} · {answer.matchup.channel}</span></div>}<div className="damage-total"><small>最终估算伤害</small><strong>{number(answer.estimated_damage)}</strong>{answer.damage_percent !== undefined && <p>约占当前生命 <b>{answer.damage_percent.toFixed(1)}%</b><span className="damage-ko">{answer.estimated_ko ? '估算可击倒' : '估算未击倒'}</span></p>}</div><ol className="damage-steps">{answer.steps.map((step, index) => <li key={step.label}><i>{index + 1}</i><div><div className="damage-step-heading"><strong>{step.label}</strong><b>{number(step.value)}</b></div><p>{step.expression}</p></div></li>)}</ol><div className="damage-rounding">中间四舍五入采用半数进位，最终乘区后保留小数；游戏最终取整规则待实测。</div><details className="damage-assumptions"><summary>本次估算的适用条件</summary><ul>{answer.assumptions.map(text => <li key={text}>{text}</li>)}</ul></details></> : <div className="damage-result-empty"><span>ƒ</span><h3>完成配置，查看伤害</h3><p>完成参数配置后计算，查看本次使用的数值、倍率和伤害步骤。</p></div>}
    <div className="damage-source">公式依据：<a href="https://roco-showdown.com/battle-use-guide" target="_blank" rel="noreferrer">Roco Showdown 社区指南 ↗</a></div>
  </section>
}
