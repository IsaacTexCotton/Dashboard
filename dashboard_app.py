#!/usr/bin/env python3
"""Prévia local e somente-leitura do CAIXA FUTURO.

--demo monta um SQLite exclusivamente em memória a partir de amostra_resposta.json.
--db lê um arquivo SQLite existente em modo read-only e nunca cria/migra/backfilla.
O servidor vincula somente 127.0.0.1; não publica a interface na rede.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlsplit

import importar
from diagnosticar_banco import _diagnostico_coerencia_fase_monetaria
from migrar_schema_monetario import (
    ErroMigracaoMonetaria,
    ativar_triggers_obrigatoriedade,
    definir_fase_migracao,
    migrar_schema_monetario,
    validar_schema_monetario,
    verificar_conciliacao_monetaria,
)
from modelo_monetario import FATO_METRICAS_CENTAVOS, POSICAO_METRICAS_CENTAVOS
from precisao_monetaria import ErroMonetario, real_legado_para_centavos

ROOT = Path(__file__).resolve().parent
FACT_TYPES = {"deposito", "acordo", "promessa", "contato"}
FACT_REQUIRED_COLUMNS = {
    "data", "usuario", "tipo", "qtd", "qtd_unicos", "valor",
    "valor_pago", "valor_aberto", "valor_quebrado", "importado_em",
}
SNAPSHOT_REQUIRED_COLUMNS = {
    "capturado_em", "data", "recebido_periodo", "a_vencer", "vencido",
}

class ErroDashboard(RuntimeError):
    """Banco ou configuração não é seguro para a leitura solicitada."""


HTML = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CAIXA FUTURO — Prévia local</title>
<style>
:root{color-scheme:light;--ink:#152c3b;--muted:#667987;--line:#dce5e9;--paper:#f4f7f8;--card:#fff;--teal:#087e8b;--navy:#173b55;--soft:#e5f3f4}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1240px;margin:auto;padding:28px 22px 52px}.top{display:flex;gap:20px;align-items:flex-start;justify-content:space-between;margin-bottom:24px}.eyebrow{font-size:12px;letter-spacing:.13em;text-transform:uppercase;font-weight:750;color:var(--teal)}h1{font-size:clamp(28px,4vw,38px);line-height:1.15;letter-spacing:-.03em;margin:5px 0 7px}.sub{color:var(--muted);margin:0}.source{padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:#fff;font-size:12px;font-weight:700;white-space:nowrap}
.notice{border:1px solid #b9dfe1;background:#eef9f9;border-radius:12px;padding:12px 15px;margin:18px 0 22px;font-size:13px;color:#204c55}
.controls{display:flex;align-items:end;gap:12px;flex-wrap:wrap;background:var(--card);padding:16px;border:1px solid var(--line);border-radius:14px;margin-bottom:22px}.field{display:flex;flex-direction:column;gap:5px}.field label{font-size:12px;color:var(--muted);font-weight:700}.field input{font:inherit;color:var(--ink);border:1px solid #cbd8dd;border-radius:8px;padding:9px 10px;background:white}.btn{border:0;background:var(--navy);color:white;font-weight:700;font:inherit;border-radius:8px;padding:10px 16px;cursor:pointer}.btn:disabled{opacity:.5;cursor:wait}
.data-status-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 18px}.status-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:13px 15px;min-width:0}.status-card span{display:block;font-size:11px;color:var(--muted);font-weight:700}.status-card strong{display:block;font-size:14px;color:var(--ink);margin-top:4px;overflow-wrap:anywhere}.status-card small{display:block;color:var(--muted);font-size:10px;line-height:1.45;margin-top:5px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;min-width:0;box-shadow:0 1px 2px #163d4d08}.card h2{font-size:13px;color:var(--muted);font-weight:700;margin:0 0 10px}.big{font-weight:780;font-size:clamp(20px,2vw,27px);letter-spacing:-.035em;overflow-wrap:anywhere}.meta{font-size:12px;color:var(--muted);margin-top:6px}.split{display:flex;justify-content:space-between;gap:14px;margin-top:12px;padding-top:10px;border-top:1px solid #edf1f3;font-size:13px}.split strong{display:block;color:var(--ink);font-size:14px}.section{margin-top:22px}.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 10px}.section h2{font-size:18px;letter-spacing:-.02em;margin:0}.section-head p{color:var(--muted);font-size:12px;margin:0}.lower{display:grid;grid-template-columns:1.15fr 1fr;gap:14px}.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:18px;min-width:0}.bar-row{display:grid;grid-template-columns:100px 1fr minmax(100px,auto);align-items:center;gap:10px;margin:14px 0;font-size:12px}.bar-label{font-weight:650}.bar-track{height:10px;background:#edf2f4;border-radius:100px;overflow:hidden}.bar{height:100%;background:var(--teal);border-radius:100px;min-width:0}.bar-value{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:13px}th,td{text-align:right;padding:10px 9px;border-bottom:1px solid #edf1f3}th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.03em}th:first-child,td:first-child{text-align:left}tbody tr:last-child td{border-bottom:0}.snapshot-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.snapshot-metric{padding:12px;border-radius:10px;background:#f6f9fa}.snapshot-metric span{font-size:12px;color:var(--muted);display:block}.snapshot-metric strong{font-size:18px;display:block;overflow-wrap:anywhere;margin-top:4px}.small-note{font-size:12px;color:var(--muted);margin-top:12px}.comparison-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.comparison-card{border:1px solid var(--line);border-radius:11px;background:#fbfdfe;padding:14px;min-width:0}.comparison-card h3{margin:0 0 8px;font-size:12px;color:var(--muted);font-weight:750}.comparison-delta{font-size:clamp(18px,1.8vw,23px);line-height:1.2;font-weight:850;letter-spacing:-.035em;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.comparison-detail,.comparison-percent{margin-top:7px;font-size:11px;color:var(--muted);line-height:1.45}.comparison-note{margin-top:11px;font-size:11px;color:var(--muted);line-height:1.5}.status{min-height:22px;margin:8px 0;color:var(--muted);font-size:13px}.error{color:#a12d2d}.empty{color:var(--muted);padding:18px 0;font-size:13px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.data-status-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.comparison-grid{grid-template-columns:1fr}.lower{grid-template-columns:1fr}}
@media(max-width:520px){main{padding:20px 13px 36px}.top{display:block}.source{display:inline-block;margin-top:12px}.data-status-grid{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.snapshot-grid{grid-template-columns:1fr}.bar-row{grid-template-columns:78px 1fr;gap:8px}.bar-value{grid-column:2;text-align:left}.controls{align-items:stretch}.field{flex:1;min-width:130px}.field input{width:100%}}
</style>
</head>
<body>
<main>
<header class="top"><div><div class="eyebrow">Painel de cobrança</div><h1>CAIXA FUTURO</h1><p class="sub">Consolidado financeiro · visão por período</p></div><div class="source" id="sourceChip">Carregando…</div></header>
<div class="notice" id="notice">Carregando o painel local…</div>
<form class="controls" id="filters"><div class="field"><label for="inicio">Data inicial</label><input type="date" id="inicio" required></div><div class="field"><label for="fim">Data final</label><input type="date" id="fim" required></div><button class="btn" id="loadBtn" type="submit">Atualizar painel</button></form>
<div class="status" id="status" role="status"></div>
<section class="data-status-grid" aria-label="Atualização e registros de importação">
  <article class="status-card"><span>Última importação registrada</span><strong id="lastImportTime">—</strong><small id="lastImportDetail">Metadados ainda não carregados.</small></article>
  <article class="status-card"><span>Origem e período do último lote</span><strong id="lastImportSource">—</strong><small id="lastImportPeriod">—</small></article>
  <article class="status-card"><span>Datas com importação no filtro</span><strong id="periodImportCoverage">—</strong><small id="periodImportNote">A contagem não substitui um calendário esperado de carga.</small></article>
</section>
<section class="grid">
<article class="card"><h2>Depósitos</h2><div class="big" id="depositosValue">—</div><div class="meta" id="depositosMeta">Valor no período</div></article>
<article class="card"><h2>Acordos — valor de face</h2><div class="big" id="acordosValue">—</div><div class="split"><div>Pago<strong id="acordosPago">—</strong></div><div>Pendente<strong id="acordosPendente">—</strong></div></div></article>
<article class="card"><h2>Promessas — prometido</h2><div class="big" id="promessasValue">—</div><div class="split"><div>Cumprido<strong id="promessasCumpridas">—</strong></div><div>Em aberto<strong id="promessasAberto">—</strong></div></div><div class="meta" id="promessasQuebradas">Quebrado: —</div></article>
<article class="card"><h2>Contatos</h2><div class="big" id="contatosValue">—</div><div class="meta">Registros no período</div><div class="split"><div>Únicos por usuário<strong id="contatosUnicos">—</strong></div></div></article>
</section>
<section class="section" aria-label="Comparação temporal">
  <div class="section-head"><div><h2>Comparação com período anterior</h2><p>Movimentações em períodos equivalentes; a posição da carteira fica separada.</p></div><p id="comparisonPeriod">—</p></div>
  <div class="panel">
    <div class="empty" id="comparisonUnavailable" style="display:block">Aguardando dados suficientes para comparar períodos.</div>
    <div class="comparison-grid" id="comparisonGrid" hidden>
      <article class="comparison-card"><h3>Depósitos</h3><div class="comparison-delta" id="compareDepositosDelta">—</div><div class="comparison-detail" id="compareDepositosDetail">—</div><div class="comparison-percent" id="compareDepositosPercent">—</div></article>
      <article class="comparison-card"><h3>Acordos · valor de face</h3><div class="comparison-delta" id="compareAcordosDelta">—</div><div class="comparison-detail" id="compareAcordosDetail">—</div><div class="comparison-percent" id="compareAcordosPercent">—</div></article>
      <article class="comparison-card"><h3>Promessas · valor prometido</h3><div class="comparison-delta" id="comparePromessasDelta">—</div><div class="comparison-detail" id="comparePromessasDetail">—</div><div class="comparison-percent" id="comparePromessasPercent">—</div></article>
    </div>
    <p class="comparison-note" id="comparisonNote">A comparação não aparece quando a cobertura registrada dos períodos não é comparável.</p>
  </div>
</section>
<section class="section"><div class="section-head"><h2>Posição mais recente no período</h2><p id="snapshotStamp">—</p></div><div class="panel"><div class="snapshot-grid"><div class="snapshot-metric"><span>Recebido no período</span><strong id="snapRecebido">—</strong></div><div class="snapshot-metric"><span>A vencer</span><strong id="snapVencer">—</strong></div><div class="snapshot-metric"><span>Vencido</span><strong id="snapVencido">—</strong></div></div><p class="small-note">A posição representa uma captura, não uma soma de snapshots históricos.</p></div></section>
<section class="section"><div class="section-head"><h2>Movimento diário</h2><p>Valores agregados pelas métricas semânticas</p></div><div class="panel" id="dailyChart"><div class="empty">Sem dados no período.</div></div></section>
<section class="section"><div class="section-head"><h2>Resumo por usuário</h2><p id="periodLabel">—</p></div><div class="panel table-wrap"><table><thead><tr><th>Usuário</th><th>Depósitos</th><th>Acordos</th><th>Pagos</th><th>Pendentes</th><th>Prometido</th><th>Cumprido</th><th>Registros contato</th></tr></thead><tbody id="usersTable"><tr><td colspan="8">Sem dados.</td></tr></tbody></table></div><p class="small-note">“Únicos por usuário” é a soma dos contadores individuais; não representa total global deduplicado.</p></section>
<footer class="small-note">Prévia local. A demonstração usa dados fictícios; o modo de banco existente abre SQLite somente-leitura e não executa migração, backfill nem importação.</footer>
</main>
<script>
const $ = id => document.getElementById(id);
const nf = new Intl.NumberFormat("pt-BR");
function money(value) {
  if (value === null || value === undefined) return "—";
  try { let n = BigInt(value); const sign = n < 0n ? "-" : ""; if (n < 0n) n = -n; return sign + "R$ " + (n / 100n).toLocaleString("pt-BR") + "," + String(n % 100n).padStart(2,"0"); }
  catch { return "—"; }
}
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function count(value) { return nf.format(Number(value || 0)); }
function width(value, max) { try { let n=BigInt(value||"0"); if(n<0n)n=-n; let m=BigInt(max||"0"); if(m<0n)m=-m; if(m===0n)return 0; return Math.min(100,Number(n*10000n/m)/100); } catch { return 0; } }
async function load(inicio, fim) {
  $("loadBtn").disabled = true; $("status").className = "status"; $("status").textContent = "Atualizando…";
  try {
    const q = new URLSearchParams(); if(inicio)q.set("inicio",inicio); if(fim)q.set("fim",fim);
    const response = await fetch("/api/dashboard?" + q.toString(), {headers:{"Accept":"application/json"}});
    const data = await response.json(); if(!response.ok)throw new Error(data.error || "Não foi possível carregar o painel.");
    if(!$("inicio").value)$("inicio").value=data.periodo.inicio;
    if(!$("fim").value)$("fim").value=data.periodo.fim;
    render(data); $("status").textContent = "Dados atualizados.";
  } catch(error) { limparPainel(error.message || "Erro ao carregar o painel."); $("status").className = "status error"; $("status").textContent = error.message || "Erro ao carregar o painel."; }
  finally { $("loadBtn").disabled = false; }
}
function limparPainel(mensagem) {
  ["sourceChip","periodLabel","depositosValue","acordosValue","acordosPago","acordosPendente","promessasValue",
   "promessasCumpridas","promessasAberto","promessasQuebradas","contatosValue",
   "contatosUnicos","snapRecebido","snapVencer","snapVencido","snapshotStamp",
   "lastImportTime","lastImportDetail","lastImportSource","lastImportPeriod",
   "periodImportCoverage","periodImportNote","comparisonPeriod"].forEach(id=>$(id).textContent="—");
  $("comparisonGrid").hidden=true;
  $("comparisonUnavailable").style.display="block";
  $("comparisonUnavailable").textContent=mensagem;
  $("comparisonNote").textContent="A comparação foi removida porque a leitura do painel falhou.";
  $("depositosMeta").textContent="Dados indisponíveis para o filtro";
  $("notice").textContent="Não foi possível validar os dados para o período selecionado.";
  $("dailyChart").innerHTML='<div class="empty" style="display:block">'+esc(mensagem)+'</div>';
  $("usersTable").innerHTML='<tr><td colspan="8">'+esc(mensagem)+'</td></tr>';
}
function renderComparacao(c) {
  const grid=$("comparisonGrid"), unavailable=$("comparisonUnavailable");
  const periodoAtual=c?.periodo_atual, periodoAnterior=c?.periodo_anterior;
  if(!c || !c.disponivel) {
    grid.hidden=true;
    unavailable.style.display="block";
    unavailable.textContent=c?.motivo || "Comparação indisponível para esta seleção.";
    $("comparisonPeriod").textContent=periodoAnterior
      ? periodoAnterior.inicio+" a "+periodoAnterior.fim+" · período anterior calculado"
      : "Período anterior não disponível";
    $("comparisonNote").textContent="Não foi calculada variação porque não há evidência suficiente de cobertura comparável.";
    return;
  }
  grid.hidden=false;
  unavailable.style.display="none";
  $("comparisonPeriod").textContent=periodoAtual.inicio+" a "+periodoAtual.fim+
    " vs "+periodoAnterior.inicio+" a "+periodoAnterior.fim;
  const metrics=[
    ["depositos","compareDepositosDelta","compareDepositosDetail","compareDepositosPercent"],
    ["acordos","compareAcordosDelta","compareAcordosDetail","compareAcordosPercent"],
    ["promessas","comparePromessasDelta","comparePromessasDetail","comparePromessasPercent"]
  ];
  for(const [key,deltaId,detailId,percentId] of metrics) {
    const metric=c.metricas[key];
    const delta=BigInt(metric.delta_centavos);
    $(deltaId).textContent=(delta>0n?"+ ":"")+money(metric.delta_centavos);
    $(detailId).textContent="Atual "+money(metric.atual_centavos)+" · anterior "+money(metric.anterior_centavos);
    $(percentId).textContent=metric.variacao_percentual===null
      ? "Variação percentual não calculada: base anterior zero ou negativa."
      : "Variação: "+metric.variacao_percentual.replace(".",",")+"%";
  }
  $("comparisonNote").textContent=c.nota || "";
}
function render(d) {
  renderComparacao(d.comparacao);
  const s=d.resumo; $("sourceChip").textContent=d.modo;
  $("notice").textContent=d.demo ? "DEMONSTRAÇÃO — os valores abaixo vêm de amostra fictícia versionada. Não são dados da empresa." : "BANCO EXISTENTE — conexão somente-leitura. Fonte monetária: " + (d.leitura_centavos ? "INTEGER em centavos, com conciliação completa" : "REAL legado convertido para centavos para apresentação.");
  const a=d.atualizacao||{};
  if(d.demo) {
    $("lastImportTime").textContent="Não aplicável — demonstração";
    $("lastImportDetail").textContent="Amostra sintética em memória; não representa uma atualização operacional.";
    $("lastImportSource").textContent="Demonstração sintética";
    $("lastImportPeriod").textContent="Dados fictícios versionados";
    $("periodImportCoverage").textContent="Não avaliado";
    $("periodImportNote").textContent="A demonstração não mede a cobertura operacional.";
  } else if(a.disponivel) {
    const u=a.ultima_importacao;
    $("lastImportTime").textContent=u ? (u.quando||"Registro sem timestamp") : "Nenhuma importação registrada";
    $("lastImportDetail").textContent=u
      ? ((u.linhas===null||u.linhas===undefined?"":count(u.linhas)+" fatos no lote. ")+"O fuso do timestamp não é explicitado pelo campo.")
      : "O banco não contém registro de importação.";
    $("lastImportSource").textContent=u ? u.origem_rotulo : "—";
    $("lastImportPeriod").textContent=u
      ? "Período do último lote: "+(u.inicio||"—")+" a "+(u.fim||"—")
      : "Nenhum lote registrado";
    const importDays=a.dias_com_importacao_registrada;
    $("periodImportCoverage").textContent=(importDays===null||importDays===undefined)
      ? "—" : count(importDays)+" de "+count(a.dias_calendario_periodo)+" datas";
    $("periodImportNote").textContent="Registro histórico de importações; não confirma a cadência de carga esperada.";
  } else {
    $("lastImportTime").textContent="Indisponível";
    $("lastImportDetail").textContent=a.motivo||"Metadados de importação não disponíveis.";
    $("lastImportSource").textContent="—";
    $("lastImportPeriod").textContent="—";
    $("periodImportCoverage").textContent="—";
    $("periodImportNote").textContent="Sem metadados não é possível estimar recência ou cobertura.";
  }
  $("depositosValue").textContent=money(s.depositos_centavos); $("depositosMeta").textContent=count(s.depositos_quantidade)+" depósitos registrados";
  $("acordosValue").textContent=money(s.acordos_centavos); $("acordosPago").textContent=money(s.acordos_pagos_centavos); $("acordosPendente").textContent=money(s.acordos_pendentes_centavos);
  $("promessasValue").textContent=money(s.promessas_centavos); $("promessasCumpridas").textContent=money(s.promessas_cumpridas_centavos); $("promessasAberto").textContent=money(s.promessas_em_aberto_centavos); $("promessasQuebradas").textContent="Quebrado: "+money(s.promessas_quebradas_centavos);
  $("contatosValue").textContent=count(s.contatos_registros); $("contatosUnicos").textContent=count(s.contatos_unicos_por_usuario);
  $("periodLabel").textContent=d.periodo.inicio+" a "+d.periodo.fim;
  if(d.snapshot) {
    $("snapshotStamp").textContent="Captura "+d.snapshot.capturado_em;
    $("snapRecebido").textContent=money(d.snapshot.recebido_periodo_centavos);
    $("snapVencer").textContent=money(d.snapshot.a_vencer_centavos);
    $("snapVencido").textContent=money(d.snapshot.vencido_centavos);
  } else {
    $("snapshotStamp").textContent="Nenhuma captura no período";
    $("snapRecebido").textContent=$("snapVencer").textContent=$("snapVencido").textContent="—";
  }
  const daily=d.diario||[];
  let max=0n; daily.forEach(x=>["depositos_centavos","acordos_centavos","promessas_centavos"].forEach(k=>{try{let v=BigInt(x[k]||"0");if(v<0n)v=-v;if(v>max)max=v;}catch{}}));
  $("dailyChart").innerHTML=daily.length?daily.map(x=>'<div class="bar-row"><span class="bar-label">'+esc(x.data)+'</span><div><div class="bar-track" title="Depósitos"><div class="bar" style="width:'+width(x.depositos_centavos,max.toString())+'%"></div></div><div class="bar-track" title="Acordos" style="margin-top:4px"><div class="bar" style="width:'+width(x.acordos_centavos,max.toString())+'%;background:#173b55"></div></div><div class="bar-track" title="Promessas" style="margin-top:4px"><div class="bar" style="width:'+width(x.promessas_centavos,max.toString())+'%;background:#9ab9c4"></div></div></div><span class="bar-value">D '+money(x.depositos_centavos)+'<br>A '+money(x.acordos_centavos)+'<br>P '+money(x.promessas_centavos)+'</span></div>').join("")+'<div class="small-note">Barras: depósitos (verde-azulado), acordos (azul-escuro) e promessas (cinza-azulado).</div>':'<div class="empty">Sem movimento no período selecionado.</div>';
  $("usersTable").innerHTML=d.usuarios.length?d.usuarios.map(x=>'<tr><td>'+esc(x.nome)+'<div class="meta">'+esc(x.usuario)+'</div></td><td>'+money(x.depositos_centavos)+'</td><td>'+money(x.acordos_centavos)+'</td><td>'+money(x.acordos_pagos_centavos)+'</td><td>'+money(x.acordos_pendentes_centavos)+'</td><td>'+money(x.promessas_centavos)+'</td><td>'+money(x.promessas_cumpridas_centavos)+'</td><td>'+count(x.contatos_registros)+'</td></tr>').join(""):'<tr><td colspan="8">Nenhum registro no período.</td></tr>';
}
$("filters").addEventListener("submit", event => {event.preventDefault();load($("inicio").value,$("fim").value);});
load("","");
</script>
</body>
</html>
"""


def _canonical_date(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ErroDashboard(f"{field}: data inválida.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ErroDashboard(f"{field}: use AAAA-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ErroDashboard(f"{field}: use AAAA-MM-DD.")
    return value


def determinar_modo_leitura(env: dict[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    leitura = env.get("LEITURA_CENTAVOS", "0").strip()
    dupla = env.get("DUPLA_ESCRITA", "0").strip()
    if leitura not in ("0", "1"):
        raise ErroDashboard("LEITURA_CENTAVOS deve ser exatamente 0 ou 1.")
    if dupla not in ("0", "1"):
        raise ErroDashboard("DUPLA_ESCRITA deve ser exatamente 0 ou 1.")
    if leitura == "1" and dupla != "1":
        raise ErroDashboard("LEITURA_CENTAVOS=1 exige DUPLA_ESCRITA=1.")
    return leitura == "1"


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    if table not in {"usuarios", "fatos", "acordos_posicao", "importacoes"}:
        raise ErroDashboard("Tabela fora da lista permitida.")
    try:
        return {str(row[1]) for row in con.execute(f'PRAGMA table_info("{table}")')}
    except sqlite3.Error as exc:
        raise ErroDashboard(f"Não foi possível inspecionar a tabela {table}.") from exc


def validar_schema_base(con: sqlite3.Connection) -> None:
    missing_tables = [
        table for table in ("usuarios", "fatos", "acordos_posicao")
        if not _columns(con, table)
    ]
    if missing_tables:
        raise ErroDashboard("Schema de leitura incompleto: " + ", ".join(missing_tables))
    missing_facts = FACT_REQUIRED_COLUMNS - _columns(con, "fatos")
    missing_snapshot = SNAPSHOT_REQUIRED_COLUMNS - _columns(con, "acordos_posicao")
    if missing_facts or missing_snapshot:
        raise ErroDashboard(
            "Schema não corresponde ao contrato legado; ausentes: "
            + ", ".join(sorted(missing_facts | missing_snapshot))
        )


def validar_leitura_centavos(con: sqlite3.Connection) -> None:
    """A leitura por centavos só abre após conciliação integral, sem escrever."""
    try:
        fase = validar_schema_monetario(con)
        if fase != "backfill_conciliado":
            raise ErroDashboard(
                "LEITURA_CENTAVOS exige fase global backfill_conciliado; "
                f"fase atual: {fase}."
            )
        for table in ("fatos", "acordos_posicao"):
            count_rows = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE monetario_fase <> 'conciliado'"
            ).fetchone()[0]
            if count_rows:
                raise ErroDashboard(
                    f"LEITURA_CENTAVOS recusada: {count_rows} linha(s) de {table} "
                    "não estão na fase conciliado."
                )
        verificacao = verificar_conciliacao_monetaria(con)
        if verificacao["pendencias"] or verificacao["divergencias"]:
            raise ErroDashboard("A conciliação REAL/centavos tem pendências ou divergências.")
        check, _metrics = _diagnostico_coerencia_fase_monetaria(con)
        if check is None or check["status"] != "OK":
            raise ErroDashboard(
                "Diagnóstico de coerência não passou: "
                + (check["detail"] if check else "sem resultado")
            )
    except (ErroMigracaoMonetaria, ErroMonetario, sqlite3.Error) as exc:
        raise ErroDashboard(f"Schema/conciliação monetária não liberado para leitura: {exc}") from exc


def criar_conexao_demo() -> sqlite3.Connection:
    """Cria fixture visual sintética em memória; não toca em arquivo de banco."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    try:
        con.executescript(importar.SCHEMA)
        migrar_schema_monetario(con)
        resposta = importar._carregar_arquivo(str(ROOT / "amostra_resposta.json"))
        dia = resposta["data"]["inicio"]
        importar.gravar(con, dia, resposta, "demo-sintetica", dupla_escrita=True)
        definir_fase_migracao(con, "backfill_em_andamento")
        definir_fase_migracao(con, "backfill_conciliado")
        ativar_triggers_obrigatoriedade(con)
        validar_leitura_centavos(con)
        return con
    except BaseException:
        con.close()
        raise


def _amount(
    row: sqlite3.Row,
    legacy_column: str,
    cents_column: str,
    *,
    field: str,
    negatives_allowed: bool,
    read_cents: bool,
    nullable: bool = False,
) -> int | None:
    if read_cents:
        value = row[cents_column]
        if value is None and nullable:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ErroDashboard(f"{field}: centavos obrigatórios ausentes/não inteiros.")
        return value
    raw = row[legacy_column]
    if raw is None and nullable:
        return None
    try:
        value = real_legado_para_centavos(
            raw, campo=field, negativos_permitidos=negatives_allowed
        )
    except ErroMonetario as exc:
        raise ErroDashboard(str(exc)) from exc
    if value is None:
        raise ErroDashboard(f"{field}: valor monetário obrigatório ausente.")
    return value


def _empty_user(usuario: str, nome: str) -> dict[str, Any]:
    return {
        "usuario": usuario, "nome": nome or usuario,
        "depositos_centavos": 0, "acordos_centavos": 0,
        "acordos_pagos_centavos": 0, "acordos_pendentes_centavos": 0,
        "promessas_centavos": 0, "promessas_cumpridas_centavos": 0,
        "contatos_registros": 0,
    }


def _empty_day(day: str) -> dict[str, Any]:
    return {
        "data": day, "depositos_centavos": 0, "acordos_centavos": 0,
        "promessas_centavos": 0, "contatos_registros": 0,
    }



def _atualizacao_importacoes(
    con: sqlite3.Connection,
    inicio: str,
    fim: str,
    *,
    demo: bool,
) -> dict[str, Any]:
    """Resume metadados locais de importação sem inferir a cadência esperada.

    Não calcula idade relativa nem presume fuso horário. A tabela importacoes
    registra lotes concluídos; ausência dessa tabela não deve impedir leitura.
    """
    dias_periodo = (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1
    indisponivel: dict[str, Any] = {
        "disponivel": False,
        "demo": demo,
        "ultima_importacao": None,
        "importacoes_no_periodo": None,
        "dias_com_importacao_registrada": None,
        "dias_calendario_periodo": dias_periodo,
        "intervalos_importados_offsets": None,
    }
    if demo:
        indisponivel["motivo"] = "Amostra sintética em memória; sem recência operacional."
        return indisponivel

    colunas = _columns(con, "importacoes")
    obrigatorias = {"id", "quando", "origem", "inicio", "fim", "linhas"}
    if not obrigatorias.issubset(colunas):
        indisponivel["motivo"] = "Tabela importacoes ou colunas esperadas indisponíveis."
        return indisponivel

    try:
        ultima = con.execute(
            "SELECT quando, origem, inicio, fim, linhas "
            "FROM importacoes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        no_periodo = con.execute(
            "SELECT inicio, fim FROM importacoes "
            "WHERE fim >= ? AND inicio <= ? ORDER BY inicio, fim",
            (inicio, fim),
        ).fetchall()
    except sqlite3.Error:
        indisponivel["motivo"] = "Não foi possível consultar metadados de importação."
        return indisponivel

    ultimo_lote = None
    if ultima is not None:
        origem_raw = str(ultima["origem"] or "").strip().lower()
        origem_rotulo = {
            "api": "API/CRM",
            "arquivo": "Arquivo local",
            "demo-sintetica": "Demonstração sintética",
        }.get(origem_raw, "Outra origem registrada" if origem_raw else "Origem não registrada")
        ultimo_lote = {
            "quando": str(ultima["quando"]) if ultima["quando"] is not None else None,
            "origem_rotulo": origem_rotulo,
            "inicio": str(ultima["inicio"]) if ultima["inicio"] is not None else None,
            "fim": str(ultima["fim"]) if ultima["fim"] is not None else None,
            "linhas": int(ultima["linhas"]) if isinstance(ultima["linhas"], int) else None,
        }

    # Conta a união dos intervalos de importação que interceptam o filtro.
    # Não percorre dia a dia, evitando custo proporcional a intervalos enormes.
    inicio_periodo = date.fromisoformat(inicio)
    fim_periodo = date.fromisoformat(fim)
    intervalos: list[tuple[date, date]] = []
    for row in no_periodo:
        try:
            primeiro = date.fromisoformat(str(row["inicio"]))
            ultimo_dia = date.fromisoformat(str(row["fim"]))
        except (TypeError, ValueError):
            continue
        if primeiro.isoformat() != str(row["inicio"]) or ultimo_dia.isoformat() != str(row["fim"]):
            continue
        primeiro = max(primeiro, inicio_periodo)
        ultimo_dia = min(ultimo_dia, fim_periodo)
        if primeiro <= ultimo_dia:
            intervalos.append((primeiro, ultimo_dia))

    intervalos.sort()
    unidos: list[tuple[date, date]] = []
    for primeiro, ultimo_dia in intervalos:
        if unidos and (primeiro <= unidos[-1][1] or (unidos[-1][1] < date.max and primeiro == unidos[-1][1] + timedelta(days=1))):
            anterior_inicio, anterior_fim = unidos[-1]
            unidos[-1] = (anterior_inicio, max(anterior_fim, ultimo_dia))
        else:
            unidos.append((primeiro, ultimo_dia))
    dias_com_importacao = sum((b - a).days + 1 for a, b in unidos)

    return {
        "disponivel": True,
        "demo": False,
        "ultima_importacao": ultimo_lote,
        "importacoes_no_periodo": len(no_periodo),
        "dias_com_importacao_registrada": dias_com_importacao,
        "dias_calendario_periodo": dias_periodo,
        "intervalos_importados_offsets": [
            {"inicio_offset": (a - inicio_periodo).days, "fim_offset": (b - inicio_periodo).days}
            for a, b in unidos
        ],
        "nota": "Contagem de registros existentes; não prova a cadência de carga esperada.",
    }


def _percentual_variacao(delta: int, anterior: int) -> str | None:
    """Percentual com uma casa decimal; não define percentual para base <= 0."""
    if anterior <= 0:
        return None
    percentual = (
        Decimal(delta) * Decimal(100) / Decimal(anterior)
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(percentual, "f")


def _comparar_periodos(
    con: sqlite3.Connection,
    *,
    inicio: str,
    fim: str,
    resumo_atual: dict[str, Any],
    atualizacao_atual: dict[str, Any],
    leitura_centavos: bool,
    demo: bool,
) -> dict[str, Any]:
    """Compara fluxos somente se os registros de importação forem comparáveis."""
    tamanho = (date.fromisoformat(fim) - date.fromisoformat(inicio)).days + 1
    fim_anterior = date.fromisoformat(inicio) - timedelta(days=1)
    inicio_anterior = fim_anterior - timedelta(days=tamanho - 1)
    periodo_anterior = {
        "inicio": inicio_anterior.isoformat(),
        "fim": fim_anterior.isoformat(),
    }

    def indisponivel(motivo: str) -> dict[str, Any]:
        return {
            "disponivel": False,
            "motivo": motivo,
            "periodo_atual": {"inicio": inicio, "fim": fim},
            "periodo_anterior": periodo_anterior,
            "metricas": {},
        }

    if demo:
        return indisponivel(
            "Comparação histórica indisponível na demonstração: ela contém somente dados sintéticos de uma data."
        )

    if not atualizacao_atual.get("disponivel"):
        return indisponivel(
            "Comparação indisponível: não há metadados de importação suficientes para validar a cobertura do período atual."
        )

    intervalos_atuais = atualizacao_atual.get("intervalos_importados_offsets")
    dias_atuais = atualizacao_atual.get("dias_com_importacao_registrada") or 0
    if not intervalos_atuais or dias_atuais <= 0:
        return indisponivel(
            "Comparação indisponível: não há datas com importação registrada no período atual."
        )

    anterior = montar_dados_painel(
        con,
        inicio=periodo_anterior["inicio"],
        fim=periodo_anterior["fim"],
        leitura_centavos=leitura_centavos,
        demo=False,
        _incluir_comparacao=False,
    )
    atualizacao_anterior = anterior["atualizacao"]
    if not atualizacao_anterior.get("disponivel"):
        return indisponivel(
            "Comparação indisponível: não há metadados de importação suficientes no período anterior."
        )

    intervalos_anteriores = atualizacao_anterior.get("intervalos_importados_offsets")
    dias_anteriores = atualizacao_anterior.get("dias_com_importacao_registrada") or 0
    if not intervalos_anteriores or dias_anteriores <= 0:
        return indisponivel(
            "Comparação indisponível: não há datas com importação registrada no período anterior."
        )
    if intervalos_atuais != intervalos_anteriores:
        return indisponivel(
            "Comparação indisponível: as datas importadas não correspondem às mesmas posições relativas nos dois períodos."
        )

    resumo_anterior = anterior["resumo"]
    definicoes = {
        "depositos": "depositos_centavos",
        "acordos": "acordos_centavos",
        "promessas": "promessas_centavos",
    }
    metricas: dict[str, Any] = {}
    for nome, chave in definicoes.items():
        atual = int(resumo_atual[chave])
        base = int(resumo_anterior[chave])
        delta = atual - base
        metricas[nome] = {
            "atual_centavos": atual,
            "anterior_centavos": base,
            "delta_centavos": delta,
            "variacao_percentual": _percentual_variacao(delta, base),
        }

    return {
        "disponivel": True,
        "motivo": "",
        "periodo_atual": {"inicio": inicio, "fim": fim},
        "periodo_anterior": periodo_anterior,
        "dias_com_importacao_registrada": dias_atuais,
        "nota": (
            "Compara movimentações nos períodos de mesma duração, usando apenas quando "
            "os registros de importação têm o mesmo padrão relativo de datas. Isso não "
            "comprova a cadência operacional esperada. A posição da carteira não entra "
            "nesta comparação."
        ),
        "metricas": metricas,
    }


def montar_dados_painel(
    con: sqlite3.Connection,
    *,
    inicio: str | None = None,
    fim: str | None = None,
    leitura_centavos: bool = False,
    demo: bool = False,
    _incluir_comparacao: bool = True,
) -> dict[str, Any]:
    validar_schema_base(con)
    if leitura_centavos:
        validar_leitura_centavos(con)

    bounds = con.execute(
        "SELECT MIN(d), MAX(d) FROM ("
        "SELECT data AS d FROM fatos UNION ALL "
        "SELECT data AS d FROM acordos_posicao WHERE data IS NOT NULL)"
    ).fetchone()
    data_min, data_max = bounds[0], bounds[1]
    if not data_min or not data_max:
        data_min = data_max = date.today().isoformat()
    inicio = _canonical_date(inicio, "inicio") or data_min
    fim = _canonical_date(fim, "fim") or data_max
    if inicio > fim:
        raise ErroDashboard("Data inicial posterior à data final.")

    columns = [
        "f.data", "f.usuario", "COALESCE(u.nome, f.usuario) AS nome",
        "f.tipo", "f.qtd", "f.qtd_unicos",
        "f.valor", "f.valor_pago", "f.valor_aberto", "f.valor_quebrado",
    ]
    if leitura_centavos:
        columns += [f"f.{col}" for col in FATO_METRICAS_CENTAVOS]
        columns += ["f.monetario_fase"]
    facts = con.execute(
        "SELECT " + ",".join(columns) +
        " FROM fatos f LEFT JOIN usuarios u ON u.usuario=f.usuario "
        "WHERE f.data BETWEEN ? AND ? ORDER BY f.data,f.usuario,f.tipo",
        (inicio, fim),
    ).fetchall()

    resumo: dict[str, Any] = {
        "depositos_centavos": 0, "depositos_quantidade": 0,
        "acordos_centavos": 0, "acordos_pagos_centavos": 0,
        "acordos_pendentes_centavos": 0, "acordos_quantidade": 0,
        "promessas_centavos": 0, "promessas_cumpridas_centavos": 0,
        "promessas_em_aberto_centavos": 0, "promessas_quebradas_centavos": 0,
        "promessas_quantidade": 0, "contatos_registros": 0,
        "contatos_unicos_por_usuario": 0,
    }
    by_user: dict[str, dict[str, Any]] = {}
    by_day: dict[str, dict[str, Any]] = {}

    for row in facts:
        tipo = row["tipo"]
        if tipo not in FACT_TYPES:
            raise ErroDashboard(f"Tipo de fato desconhecido no banco: {tipo!r}.")
        usuario = row["usuario"]
        user = by_user.setdefault(usuario, _empty_user(usuario, row["nome"] or usuario))
        day = by_day.setdefault(row["data"], _empty_day(row["data"]))

        if tipo == "deposito":
            cents = _amount(row, "valor", "deposito_valor_centavos", field=f"fatos[{row['data']},{usuario}].deposito", negatives_allowed=True, read_cents=leitura_centavos)
            resumo["depositos_centavos"] += cents
            resumo["depositos_quantidade"] += row["qtd"]
            user["depositos_centavos"] += cents
            day["depositos_centavos"] += cents
        elif tipo == "acordo":
            face = _amount(row, "valor", "acordo_valor_centavos", field=f"fatos[{row['data']},{usuario}].acordo", negatives_allowed=False, read_cents=leitura_centavos)
            paid = _amount(row, "valor_pago", "acordo_pago_centavos", field=f"fatos[{row['data']},{usuario}].acordo_pago", negatives_allowed=False, read_cents=leitura_centavos)
            pending = _amount(row, "valor_aberto", "acordo_pendente_centavos", field=f"fatos[{row['data']},{usuario}].acordo_pendente", negatives_allowed=True, read_cents=leitura_centavos)
            resumo["acordos_centavos"] += face
            resumo["acordos_pagos_centavos"] += paid
            resumo["acordos_pendentes_centavos"] += pending
            resumo["acordos_quantidade"] += row["qtd"]
            user["acordos_centavos"] += face
            user["acordos_pagos_centavos"] += paid
            user["acordos_pendentes_centavos"] += pending
            day["acordos_centavos"] += face
        elif tipo == "promessa":
            face = _amount(row, "valor", "promessa_prometido_centavos", field=f"fatos[{row['data']},{usuario}].promessa", negatives_allowed=False, read_cents=leitura_centavos)
            done = _amount(row, "valor_pago", "promessa_cumprido_centavos", field=f"fatos[{row['data']},{usuario}].promessa_cumprido", negatives_allowed=False, read_cents=leitura_centavos)
            pending = _amount(row, "valor_aberto", "promessa_em_aberto_centavos", field=f"fatos[{row['data']},{usuario}].promessa_aberto", negatives_allowed=True, read_cents=leitura_centavos)
            broken = _amount(row, "valor_quebrado", "promessa_quebrado_centavos", field=f"fatos[{row['data']},{usuario}].promessa_quebrado", negatives_allowed=False, read_cents=leitura_centavos)
            resumo["promessas_centavos"] += face
            resumo["promessas_cumpridas_centavos"] += done
            resumo["promessas_em_aberto_centavos"] += pending
            resumo["promessas_quebradas_centavos"] += broken
            resumo["promessas_quantidade"] += row["qtd"]
            user["promessas_centavos"] += face
            user["promessas_cumpridas_centavos"] += done
            day["promessas_centavos"] += face
        else:
            resumo["contatos_registros"] += row["qtd"]
            resumo["contatos_unicos_por_usuario"] += row["qtd_unicos"]
            user["contatos_registros"] += row["qtd"]
            day["contatos_registros"] += row["qtd"]

    position_columns = ["capturado_em", "data", "recebido_periodo", "a_vencer", "vencido"]
    if leitura_centavos:
        position_columns += list(POSICAO_METRICAS_CENTAVOS) + ["monetario_fase"]
    snapshot_row = con.execute(
        "SELECT " + ",".join(position_columns) +
        " FROM acordos_posicao WHERE data BETWEEN ? AND ? ORDER BY capturado_em DESC LIMIT 1",
        (inicio, fim),
    ).fetchone()
    snapshot: dict[str, Any] | None = None
    if snapshot_row:
        snapshot = {
            "capturado_em": snapshot_row["capturado_em"],
            "recebido_periodo_centavos": _amount(snapshot_row, "recebido_periodo", "recebido_periodo_centavos", field=f"acordos_posicao[{snapshot_row['capturado_em']}].recebido_periodo", negatives_allowed=True, read_cents=leitura_centavos, nullable=True),
            "a_vencer_centavos": _amount(snapshot_row, "a_vencer", "a_vencer_centavos", field=f"acordos_posicao[{snapshot_row['capturado_em']}].a_vencer", negatives_allowed=False, read_cents=leitura_centavos, nullable=True),
            "vencido_centavos": _amount(snapshot_row, "vencido", "vencido_centavos", field=f"acordos_posicao[{snapshot_row['capturado_em']}].vencido", negatives_allowed=False, read_cents=leitura_centavos, nullable=True),
        }

    atualizacao = _atualizacao_importacoes(con, inicio, fim, demo=demo)
    resultado = {
        "demo": demo,
        "leitura_centavos": leitura_centavos,
        "modo": "INTEGER · centavos conciliados" if leitura_centavos else "REAL legado · leitura",
        "periodo": {"inicio": inicio, "fim": fim},
        "limites": {"inicio": data_min, "fim": data_max},
        "atualizacao": atualizacao,
        "resumo": resumo,
        "snapshot": snapshot,
        "diario": [by_day[d] for d in sorted(by_day)],
        "usuarios": sorted(
            by_user.values(),
            key=lambda x: (
                x["acordos_centavos"] + x["promessas_centavos"] + x["depositos_centavos"],
                x["usuario"],
            ),
            reverse=True,
        )[:100],
    }
    if _incluir_comparacao:
        resultado["comparacao"] = _comparar_periodos(
            con,
            inicio=inicio,
            fim=fim,
            resumo_atual=resumo,
            atualizacao_atual=atualizacao,
            leitura_centavos=leitura_centavos,
            demo=demo,
        )
    return resultado


def _wire(value: Any) -> Any:
    """Serializa INTEGER monetário como texto para não perder precisão no browser."""
    if isinstance(value, dict):
        return {
            key: (str(item) if key.endswith("_centavos") and isinstance(item, int) else _wire(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_wire(item) for item in value]
    return value


class DashboardStore:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        demo: bool = False,
        leitura_centavos: bool = False,
    ):
        self.demo = demo
        self.leitura_centavos = leitura_centavos
        self.demo_connection: sqlite3.Connection | None = None
        self.db_path: Path | None = None
        if demo:
            self.demo_connection = criar_conexao_demo()
        else:
            value = Path(db_path or os.environ.get("DASHBOARD_DB", "cobranca.db")).expanduser()
            self.db_path = value.resolve()
            if not self.db_path.is_file():
                raise ErroDashboard(
                    f"Banco não encontrado: {self.db_path}. Nenhum arquivo foi criado. "
                    "Use --demo para abrir a demonstração sintética."
                )
        with self.connection() as con:
            validar_schema_base(con)
            if leitura_centavos:
                validar_leitura_centavos(con)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.demo_connection is not None:
            yield self.demo_connection
            return
        assert self.db_path is not None
        con = sqlite3.connect(
            self.db_path.as_uri() + "?mode=ro", uri=True, timeout=5,
        )
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA query_only=ON")
            yield con
        finally:
            con.close()

    def data(self, inicio: str | None = None, fim: str | None = None) -> dict[str, Any]:
        with self.connection() as con:
            return montar_dados_painel(
                con, inicio=inicio, fim=fim,
                leitura_centavos=self.leitura_centavos, demo=self.demo,
            )


def _handler(store: DashboardStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CaixaFuturoLocal/1.0"

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/dashboard":
                query = parse_qs(parsed.query, strict_parsing=False)
                inicio = query.get("inicio", [None])[0]
                fim = query.get("fim", [None])[0]
                try:
                    payload = _wire(store.data(inicio, fim))
                    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                except ErroDashboard as exc:
                    body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                    self._send(400, body, "application/json; charset=utf-8")
                except (sqlite3.Error, ErroMigracaoMonetaria, ErroMonetario) as exc:
                    body = json.dumps({"error": f"Erro de leitura/validação do banco: {exc}"}, ensure_ascii=False).encode("utf-8")
                    self._send(500, body, "application/json; charset=utf-8")
                return
            self._send(404, b"Not found", "text/plain; charset=utf-8")

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[dashboard-local] " + fmt % args + "\n")

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Abre a prévia local do CAIXA FUTURO sem alterar o banco."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true", help="usa somente dados fictícios em SQLite na memória")
    group.add_argument("--db", help="caminho para SQLite existente; abrirá em modo somente-leitura")
    parser.add_argument("--port", type=int, default=8765, help="porta local (padrão: 8765)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port precisa estar entre 1 e 65535.")
    try:
        leitura_centavos = determinar_modo_leitura()
        store = DashboardStore(db_path=args.db, demo=args.demo, leitura_centavos=leitura_centavos)
        server = HTTPServer(("127.0.0.1", args.port), _handler(store))
    except (ErroDashboard, ErroMigracaoMonetaria, ErroMonetario, OSError, sqlite3.Error) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(f"CAIXA FUTURO disponível em http://127.0.0.1:{args.port}")
    print("Modo: demonstração sintética" if args.demo else f"Modo: banco existente somente-leitura ({store.db_path})")
    print("Leitura monetária: INTEGER em centavos conciliados" if leitura_centavos else "Leitura monetária: REAL legado")
    print("Pressione Ctrl+C para encerrar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando prévia local.")
    finally:
        server.server_close()
        if store.demo_connection is not None:
            store.demo_connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
