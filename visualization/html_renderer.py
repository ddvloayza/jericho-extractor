from __future__ import annotations

"""Intelica-branded HTML renderer — pure Python, no external dependencies.

Generates reports styled to match the Intelica design system:
  Plus Jakarta Sans + JetBrains Mono · brand colors · sticky topbar · hero stats
  tab navigation · cards / tiles / callouts · dark navy footer.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Brand palette
# ─────────────────────────────────────────────────────────────────────────────

RISK_META: dict[str, dict[str, str]] = {
    "critical": {"bg": "#FEF0F0", "text": "#C42626", "border": "#F04B4B"},
    "high":     {"bg": "#FFF7EE", "text": "#B86200", "border": "#FF860D"},
    "medium":   {"bg": "#FFFBE6", "text": "#856A00", "border": "#FBC02D"},
    "low":      {"bg": "#EEFBF1", "text": "#1F7A35", "border": "#64E386"},
    "info":     {"bg": "#F0F4FF", "text": "#21409A", "border": "#21409A"},
}

SUBNET_META: dict[str, dict[str, str]] = {
    "public":   {"cls": "pub",  "label": "Public"},
    "private":  {"cls": "priv", "label": "Private"},
    "isolated": {"cls": "iso",  "label": "Isolated"},
    "unknown":  {"cls": "unk",  "label": "Unknown"},
}

RESOURCE_META: dict[str, dict[str, str]] = {
    "ec2":    {"bg": "#FFF7EE", "text": "#B86200", "label": "EC2"},
    "alb":    {"bg": "#FCE5EE", "text": "#A11F58", "label": "ALB"},
    "nlb":    {"bg": "#E0EAFE", "text": "#1B3A8B", "label": "NLB"},
    "nat":    {"bg": "#E6F3F5", "text": "#0F6E78", "label": "NAT"},
    "vpce":   {"bg": "#E7E2FB", "text": "#4A3D9E", "label": "VPCE"},
    "eks":    {"bg": "#D8F3DE", "text": "#1F7A35", "label": "EKS"},
    "lambda": {"bg": "#FFF1E1", "text": "#B86200", "label": "λ"},
    "rds":    {"bg": "#E0EAFE", "text": "#1B3A8B", "label": "RDS"},
    "s3":     {"bg": "#D8F3DE", "text": "#1F7A35", "label": "S3"},
    "igw":    {"bg": "#F0F4FF", "text": "#21409A", "label": "IGW"},
    "tgw":    {"bg": "#FFF1E1", "text": "#B86200", "label": "TGW"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Intelica CSS design system
# ─────────────────────────────────────────────────────────────────────────────

_ITL_CSS = """\
:root{
  --ib:#21409A;--ib2:#2A4FBD;--io:#FF860D;--in:#0F1533;
  --ibg:#F0F4FF;--ibgs:#FDFDFF;
  --ig:#474D66;--ig2:#808599;--ig3:#B8BCCC;--ig4:#D8DDEF;
  --ip:#64E386;--ineg:#F04B4B;
  --fd:"Plus Jakarta Sans","Calibri",sans-serif;
  --fm:"JetBrains Mono","Consolas",monospace;
  --s1:0 1px 2px rgba(15,21,51,.04);
  --s2:0 4px 16px rgba(15,21,51,.06),0 1px 3px rgba(15,21,51,.04);
  --s3:0 12px 40px rgba(15,21,51,.08),0 4px 12px rgba(15,21,51,.04);
  --r1:6px;--r2:10px;--r3:16px;--r4:24px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:var(--fd);background:var(--ibgs);color:var(--in);
  line-height:1.6;font-weight:400;-webkit-font-smoothing:antialiased;
  min-height:100vh;overflow-x:hidden;
}
/* ── bg decor ── */
.bg-decor{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.bg-decor svg{position:absolute;opacity:.5}
.bg-decor .cv1{top:-200px;right:-300px;width:900px;height:900px}
.bg-decor .cv2{bottom:-400px;left:-200px;width:700px;height:700px}
.bg-decor .dots{top:40%;right:5%;width:200px;height:200px;opacity:.4}
main{position:relative;z-index:1}
/* ── topbar ── */
.topbar{
  background:rgba(255,255,255,.88);backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(33,64,154,.08);
  position:sticky;top:0;z-index:50;
}
.topbar-inner{
  max-width:1280px;margin:0 auto;padding:15px 40px;
  display:flex;align-items:center;justify-content:space-between;gap:24px;
}
.brand{display:flex;align-items:center;gap:14px;text-decoration:none}
.brand-iso{width:38px;height:38px;flex-shrink:0}
.brand-name{
  font-family:var(--fd);font-size:19px;font-weight:500;
  color:var(--in);letter-spacing:-.02em;line-height:1;
}
.brand-name span{font-weight:700;color:var(--ib)}
.topbar-meta{display:flex;align-items:center;gap:18px;font-size:13px;color:var(--ig)}
.topbar-meta .pill{
  background:var(--ibg);color:var(--ib);padding:5px 12px;
  border-radius:999px;font-weight:600;font-size:12px;letter-spacing:.02em;
}
/* ── hero ── */
.hero{max-width:1280px;margin:0 auto;padding:68px 40px 52px}
.hero-eyebrow{
  display:inline-flex;align-items:center;gap:8px;font-size:13px;
  font-weight:600;text-transform:uppercase;letter-spacing:.12em;
  color:var(--ib);margin-bottom:18px;
}
.hero-eyebrow::before{content:"";width:32px;height:2px;background:var(--io)}
.hero h1{
  font-family:var(--fd);font-size:clamp(30px,4.5vw,54px);font-weight:300;
  line-height:1.08;letter-spacing:-.032em;color:var(--in);
  margin-bottom:18px;max-width:800px;
}
.hero h1 strong{font-weight:700;color:var(--ib)}
.hero-sub{
  font-size:17px;line-height:1.6;color:var(--ig);
  max-width:680px;margin-bottom:42px;
}
.hero-grid{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));
  gap:14px;max-width:1100px;
}
.hero-stat{
  background:white;border:1px solid rgba(33,64,154,.08);
  padding:20px 24px;border-radius:var(--r3);box-shadow:var(--s1);
  transition:all .2s ease;
}
.hero-stat:hover{
  border-color:rgba(33,64,154,.18);transform:translateY(-2px);box-shadow:var(--s2);
}
.hs-label{
  font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;
  color:var(--ig2);margin-bottom:6px;
}
.hs-value{
  font-family:var(--fd);font-size:28px;font-weight:700;color:var(--in);
  letter-spacing:-.02em;line-height:1.1;
}
.hs-value small{font-size:13px;font-weight:500;color:var(--ig);margin-left:4px}
.hero-stat.st-alert .hs-value{color:#C42626}
.hero-stat.st-warn  .hs-value{color:#B86200}
.hero-stat.st-ok    .hs-value{color:#1F7A35}
/* ── tabnav ── */
.tabnav-wrap{
  position:sticky;top:69px;z-index:40;
  background:rgba(253,253,255,.92);backdrop-filter:blur(20px);
  -webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(33,64,154,.08);
}
.tabnav{
  max-width:1280px;margin:0 auto;padding:0 40px;
  display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;
}
.tabnav::-webkit-scrollbar{display:none}
.tab{
  font-family:var(--fd);background:transparent;border:none;
  padding:15px 20px;font-size:14px;font-weight:500;color:var(--ig);
  cursor:pointer;position:relative;transition:color .2s ease;
  white-space:nowrap;letter-spacing:-.005em;
}
.tab .tn{font-family:var(--fm);font-size:11px;color:var(--ig3);margin-right:8px;font-weight:500}
.tab:hover{color:var(--in)}
.tab.active{color:var(--ib);font-weight:600}
.tab.active .tn{color:var(--io)}
.tab.active::after{
  content:"";position:absolute;bottom:-1px;left:16px;right:16px;
  height:2px;background:var(--ib);border-radius:2px 2px 0 0;
}
/* ── content ── */
.content{max-width:1280px;margin:0 auto;padding:52px 40px 96px}
.panel{display:none;animation:fi .35s ease}
.panel.active{display:block}
@keyframes fi{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
/* ── section headings ── */
.sec-eyebrow{
  font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;
  color:var(--ib);margin-bottom:10px;
}
.sec-title{
  font-family:var(--fd);font-size:34px;font-weight:300;letter-spacing:-.025em;
  line-height:1.1;color:var(--in);margin-bottom:12px;
}
.sec-title strong{font-weight:700;color:var(--ib)}
.sec-intro{
  font-size:16px;color:var(--ig);max-width:740px;margin-bottom:38px;line-height:1.6;
}
h3.blk{
  font-family:var(--fd);font-size:21px;font-weight:600;letter-spacing:-.015em;
  color:var(--in);margin:42px 0 8px;
}
/* ── cards ── */
.card{
  background:white;border:1px solid rgba(33,64,154,.08);border-radius:var(--r3);
  padding:26px;box-shadow:var(--s1);transition:all .25s ease;
}
.card:hover{border-color:rgba(33,64,154,.16);box-shadow:var(--s2)}
.cgrid{display:grid;gap:16px;margin:18px 0}
.cgrid.c2{grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.cgrid.c3{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
/* ── tiles ── */
.tile{
  background:white;border:1px solid rgba(33,64,154,.08);
  border-radius:var(--r2);padding:20px;transition:all .2s ease;
  position:relative;overflow:hidden;
}
.tile::before{
  content:"";position:absolute;top:0;left:0;width:4px;height:0;
  background:var(--ib);transition:height .25s ease;
}
.tile:hover{border-color:rgba(33,64,154,.2);box-shadow:var(--s2);transform:translateY(-2px)}
.tile:hover::before{height:100%}
.tile.accent::before{background:var(--io);height:100%}
.tile.ok::before{background:var(--ip);height:100%}
.tile.warn::before{background:#FBC02D;height:100%}
.tile.alert::before{background:var(--ineg);height:100%}
.tile.muted::before{background:var(--ig3);height:100%}
.tkicker{
  font-family:var(--fm);font-size:11px;color:var(--ib);font-weight:600;
  letter-spacing:.04em;margin-bottom:5px;text-transform:uppercase;
}
.tile.accent .tkicker{color:var(--io)}
.ttitle{font-family:var(--fd);font-size:15px;font-weight:600;color:var(--in);margin-bottom:5px;line-height:1.3}
.tbody{font-size:14px;color:var(--ig);line-height:1.55}
.tmeta{
  margin-top:11px;padding-top:11px;border-top:1px solid rgba(33,64,154,.08);
  display:flex;flex-wrap:wrap;gap:4px 10px;
  font-size:12px;color:var(--ig2);font-family:var(--fm);
}
.tmeta strong{color:var(--in);font-weight:600}
/* ── callouts ── */
.callout{
  border-left:3px solid var(--io);background:#FFF7EE;
  padding:15px 20px;border-radius:0 var(--r2) var(--r2) 0;
  margin:18px 0;font-size:15px;color:var(--in);line-height:1.6;
}
.callout strong{color:var(--io)}
.callout.info{border-left-color:var(--ib);background:var(--ibg)}
.callout.info strong{color:var(--ib)}
.callout.ok{border-left-color:var(--ip);background:#EEFBF1}
.callout.ok strong{color:#1F7A35}
.callout.alert{border-left-color:var(--ineg);background:#FEF0F0}
.callout.alert strong{color:#C42626}
/* ── code ── */
pre{
  background:var(--in);color:#E8EBF4;padding:16px 20px;
  border-radius:var(--r2);font-family:var(--fm);font-size:13px;
  line-height:1.65;overflow-x:auto;margin:13px 0;
  border:1px solid rgba(33,64,154,.2);
}
code:not(pre code){
  font-family:var(--fm);font-size:.92em;background:var(--ibg);
  color:var(--ib);padding:2px 6px;border-radius:4px;font-weight:500;
}
/* ── tables ── */
.twrap{
  background:white;border:1px solid rgba(33,64,154,.08);
  border-radius:var(--r2);overflow:hidden;margin:18px 0;box-shadow:var(--s1);
}
table{width:100%;border-collapse:collapse;font-size:14px}
thead{background:var(--ibg);color:var(--ib)}
th{
  text-align:left;padding:12px 18px;font-weight:600;font-size:12px;
  text-transform:uppercase;letter-spacing:.06em;
  border-bottom:1px solid rgba(33,64,154,.12);
}
td{
  padding:12px 18px;border-bottom:1px solid rgba(33,64,154,.06);
  color:var(--in);vertical-align:top;
}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:rgba(240,244,255,.5)}
td code,td .mono{font-family:var(--fm);font-size:12.5px}
/* ── badges & chips ── */
.bdg{
  display:inline-block;padding:3px 10px;border-radius:999px;
  font-size:11px;font-weight:600;font-family:var(--fm);
  text-transform:uppercase;letter-spacing:.04em;
}
.bdg.critical{background:#FEF0F0;color:#C42626}
.bdg.high{background:#FFF7EE;color:#B86200}
.bdg.medium{background:#FFFBE6;color:#856A00}
.bdg.low{background:#EEFBF1;color:#1F7A35}
.bdg.info{background:#F0F4FF;color:#21409A}
.chip{
  display:inline-block;padding:2px 7px;border-radius:var(--r1);
  font-size:11px;font-weight:600;font-family:var(--fm);margin:2px;
}
/* ── VPC layout ── */
.vpc-card{
  background:white;border:1.5px solid rgba(33,64,154,.14);
  border-radius:var(--r3);padding:20px;margin-bottom:26px;box-shadow:var(--s1);
}
.vpc-header{
  display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;
}
.vpc-name{font-size:15px;font-weight:700;color:var(--ib)}
.az-col{flex:1;min-width:210px}
.az-label{
  font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
  color:var(--ib);margin-bottom:7px;
  font-family:var(--fm);
}
.sub-tile{
  border:1px solid #ddd;border-radius:var(--r1);
  padding:9px 11px;margin-bottom:7px;font-size:13px;
}
.sub-tile.pub{border-color:#64E386;background:#EEFBF1}
.sub-tile.priv{border-color:#FF860D;background:#FFF7EE}
.sub-tile.iso{border-color:#F04B4B;background:#FEF0F0}
.sub-tile.unk{border-color:#B8BCCC;background:#F8F9FA}
.sub-name{font-weight:600;color:var(--in);font-size:13px;margin-bottom:2px}
.sub-cidr{font-family:var(--fm);font-size:11px;color:var(--ig2);margin-bottom:5px}
.sub-res{display:flex;flex-wrap:wrap;gap:2px}
/* ── footer ── */
.foot{margin-top:80px;padding:52px 40px 32px;background:var(--in);color:#C0C7E0}
.foot-inner{
  max-width:1280px;margin:0 auto;
  display:grid;grid-template-columns:2fr 1fr 1fr;gap:44px;
}
.foot h5{
  font-family:var(--fd);font-size:13px;font-weight:600;text-transform:uppercase;
  letter-spacing:.08em;color:white;margin-bottom:13px;
}
.foot p,.foot a{font-size:14px;color:#A0A7CA;text-decoration:none;line-height:1.7}
.foot a:hover{color:var(--io)}
.foot-bottom{
  max-width:1280px;margin:40px auto 0;padding-top:20px;
  border-top:1px solid rgba(255,255,255,.08);
  display:flex;justify-content:space-between;font-size:12px;color:#7B83A8;
}
/* ── responsive ── */
@media(max-width:900px){
  .hero{padding:52px 24px 36px}
  .topbar-inner,.content,.tabnav{padding-left:24px;padding-right:24px}
  .foot{padding:40px 24px 28px}
  .foot-inner{grid-template-columns:1fr;gap:28px}
  .foot-bottom{flex-direction:column;gap:8px}
  .topbar-meta{display:none}
  .sec-title{font-size:26px}
  .card,.vpc-card{padding:16px}
  .hero-grid{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}
}"""

# ─────────────────────────────────────────────────────────────────────────────
# Static fragments
# ─────────────────────────────────────────────────────────────────────────────

_LOGO_SVG = (
    '<svg class="brand-iso" viewBox="0 0 100 100" aria-hidden="true">'
    '<defs><clipPath id="iso-clip"><circle cx="50" cy="50" r="42"/></clipPath></defs>'
    '<circle cx="50" cy="50" r="42" fill="#FF860D"/>'
    '<g clip-path="url(#iso-clip)" transform="rotate(-22 50 50)">'
    '<rect x="-5" y="22" width="120" height="3.5" fill="#21409A"/>'
    '<rect x="-5" y="37" width="120" height="3.5" fill="#21409A"/>'
    '<rect x="-5" y="52" width="120" height="3.5" fill="#21409A"/>'
    '<rect x="-5" y="67" width="120" height="3.5" fill="#21409A"/>'
    '<rect x="-5" y="82" width="120" height="3.5" fill="#21409A"/>'
    '</g></svg>'
)

_BG_DECOR = (
    '<div class="bg-decor" aria-hidden="true">'
    '<svg class="cv1" viewBox="0 0 900 900">'
    '<circle cx="450" cy="450" r="380" fill="none" stroke="#21409A" stroke-width="1" opacity="0.14"/>'
    '</svg>'
    '<svg class="cv2" viewBox="0 0 700 700">'
    '<circle cx="350" cy="350" r="300" fill="none" stroke="#FF860D" stroke-width="1" opacity="0.16"/>'
    '</svg>'
    '<svg class="dots" viewBox="0 0 160 160">'
    '<g fill="#21409A" opacity="0.28">'
    + "".join(
        f'<circle cx="{x}" cy="{y}" r="1.5"/>'
        for y in range(10, 161, 30)
        for x in range(10, 161, 30)
    )
    + '</g></svg></div>'
)

_TAB_JS = """\
<script>
function showTab(n,btn){
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active')});
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active')});
  var p=document.getElementById('p'+n);if(p){p.classList.add('active')}
  if(btn){btn.classList.add('active')}
}
document.addEventListener('DOMContentLoaded',function(){
  var f=document.querySelector('.tab');if(f){f.click()}
});
</script>"""


# ─────────────────────────────────────────────────────────────────────────────
# Core page template
# ─────────────────────────────────────────────────────────────────────────────

def _html_page(
    title: str,
    body: str,
    extra_css: str = "",
    account_name: str = "",
    hero_stats: list[dict] | None = None,
    hero_title: str = "",
    hero_sub: str = "",
    hero_eyebrow: str = "",
    tabs: list[str] | None = None,
) -> str:
    """Return a complete Intelica-branded HTML document."""
    now = datetime.now(timezone.utc)
    generated_at = now.strftime("%B %d, %Y")
    year = now.year

    # ── hero stats grid ──
    stats_html = ""
    if hero_stats:
        stats_html = '<div class="hero-grid">'
        for s in hero_stats:
            mod_cls = f" st-{s['mod']}" if s.get("mod") else ""
            small   = f'<small>{s["small"]}</small>' if s.get("small") else ""
            stats_html += (
                f'<div class="hero-stat{mod_cls}">'
                f'<div class="hs-label">{s["label"]}</div>'
                f'<div class="hs-value">{s["value"]}{small}</div>'
                f'</div>'
            )
        stats_html += "</div>"

    # ── tab nav ──
    tabnav_html = ""
    if tabs:
        tabnav_html = '<div class="tabnav-wrap"><nav class="tabnav" role="tablist">'
        for i, lbl in enumerate(tabs):
            num = str(i + 1).zfill(2)
            tabnav_html += (
                f'<button class="tab" role="tab" onclick="showTab({i+1},this)">'
                f'<span class="tn">{num}</span>{lbl}</button>'
            )
        tabnav_html += "</nav></div>"

    ey = hero_eyebrow or f"AWS Infrastructure · {generated_at}"
    ht = hero_title or (f"<strong>{account_name}</strong>" if account_name else title)
    hs = hero_sub or "Infrastructure report generated by Jericho Extractor."
    brand_sub = f" · {account_name}" if account_name else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
  <style>
{_ITL_CSS}
{extra_css}
  </style>
</head>
<body>
{_BG_DECOR}
<header class="topbar">
  <div class="topbar-inner">
    <a href="#" class="brand">
      {_LOGO_SVG}
      <div class="brand-name">intelica<span>{brand_sub}</span></div>
    </a>
    <div class="topbar-meta">
      <span>AWS Infrastructure Report</span>
      <span class="pill">Jericho Extractor</span>
    </div>
  </div>
</header>
<main>
<section class="hero">
  <div class="hero-eyebrow">{ey}</div>
  <h1>{ht}</h1>
  <p class="hero-sub">{hs}</p>
  {stats_html}
</section>
{tabnav_html}
<div class="content">
{body}
</div>
</main>
<footer class="foot">
  <div class="foot-inner">
    <div>
      <h5>Jericho Extractor</h5>
      <p>AWS infrastructure inventory and topology platform.<br/>
         Automated discovery of VPCs, EC2, EKS, Lambda, RDS,<br/>
         IAM, KMS, Secrets Manager and S3 resources.</p>
    </div>
    <div>
      <h5>Report</h5>
      <p>{account_name or "AWS Account"}<br/>Generated {generated_at}</p>
    </div>
    <div>
      <h5>Platform</h5>
      <p>Intelica<br/>Cloud Infrastructure</p>
    </div>
  </div>
  <div class="foot-bottom">
    <span>&copy; {year} Intelica &middot; Confidential</span>
    <span>Generated by Jericho Extractor &middot; {generated_at}</span>
  </div>
</footer>
{_TAB_JS}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _short(resource: dict, max_len: int = 26) -> str:
    name = (
        resource.get("tags", {}).get("Name")
        or resource.get("resource_name")
        or resource.get("resource_id", "")
    )
    return name if len(name) <= max_len else name[: max_len - 1] + "…"


def _risk_badge(risk: str) -> str:
    r = str(risk).lower()
    return f'<span class="bdg {r}">{r.upper()}</span>'


def _chip(label: str, bg: str, text: str) -> str:
    return (
        f'<span class="chip" style="background:{bg};color:{text}">'
        f'{label}</span>'
    )


def _resource_chip(type_key: str, name: str = "", max_len: int = 15) -> str:
    meta = RESOURCE_META.get(type_key, {"bg": "#F0F4FF", "text": "#21409A", "label": type_key.upper()})
    lbl  = meta["label"]
    if name:
        s = name if len(name) <= max_len else name[: max_len - 1] + "…"
        lbl = f"{lbl} {s}"
    return _chip(lbl, meta["bg"], meta["text"])


def _callout(text: str, kind: str = "") -> str:
    cls = f" {kind}" if kind else ""
    return f'<div class="callout{cls}">{text}</div>'


def _rules_summary(rules: list[dict]) -> str:
    lines = []
    for r in rules[:6]:
        proto    = r.get("protocol", "-1")
        fp       = r.get("from_port")
        tp       = r.get("to_port")
        cidrs    = ", ".join((r.get("cidrs") or [])[:2])
        tags     = r.get("risk_tags", [])
        risk     = str(r.get("risk_level", "info"))
        meta     = RISK_META.get(risk, RISK_META["info"])
        port_str = (
            f"{fp}–{tp}"
            if fp is not None and fp != tp
            else (str(fp) if fp is not None else "all")
        )
        tag_html = " ".join(
            f'<span class="chip" style="background:{meta["bg"]};color:{meta["text"]};'
            f'font-size:10px;padding:1px 5px">{t}</span>'
            for t in tags
        )
        lines.append(
            f'<span style="font-family:var(--fm);font-size:12px">{proto}/{port_str}</span>'
            f'<span style="color:var(--ig2);font-size:11px;margin-left:4px">{cidrs}</span>'
            f" {tag_html}"
        )
    if len(rules) > 6:
        lines.append(
            f'<span style="color:var(--ig2);font-size:11px">+{len(rules)-6} more</span>'
        )
    return "<br>".join(lines) or "—"


# ─────────────────────────────────────────────────────────────────────────────
# Security report
# ─────────────────────────────────────────────────────────────────────────────

def render_security_report(
    sg_analyses: list[dict[str, Any]],
    output_path: Path,
    account_name: str = "",
) -> None:
    risk_order = ["critical", "high", "medium", "low", "info"]
    sorted_sgs = sorted(
        sg_analyses,
        key=lambda a: (
            risk_order.index(str(a.get("overall_risk", "info")))
            if str(a.get("overall_risk", "info")) in risk_order
            else 99,
            -a.get("attached_count", 0),
        ),
    )

    counts = {
        r: sum(1 for a in sg_analyses if str(a.get("overall_risk")) == r)
        for r in risk_order
    }
    total = len(sg_analyses)

    # ── hero stats ──
    hero_stats = [
        {"label": "Critical", "value": counts["critical"],
         "mod": "alert" if counts["critical"] > 0 else ""},
        {"label": "High",     "value": counts["high"],
         "mod": "warn" if counts["high"] > 0 else ""},
        {"label": "Medium",   "value": counts["medium"]},
        {"label": "Low",      "value": counts["low"],  "mod": "ok"},
        {"label": "Info",     "value": counts["info"],  "mod": "ok"},
        {"label": "Total SGs", "value": total},
    ]

    # ── critical callout ──
    crit_sgs = [sg for sg in sorted_sgs if str(sg.get("overall_risk")) == "critical"]
    alert_html = ""
    if crit_sgs:
        names = ", ".join(
            f'<code>{sg.get("security_group_id", "")}</code>' for sg in crit_sgs[:5]
        )
        extra = f" and {len(crit_sgs)-5} more" if len(crit_sgs) > 5 else ""
        alert_html = _callout(
            f"<strong>{len(crit_sgs)} critical security group(s)</strong> with open "
            f"internet exposure detected: {names}{extra}.",
            "alert",
        )

    # ── high-risk callout ──
    high_sgs = [sg for sg in sorted_sgs if str(sg.get("overall_risk")) == "high"]
    warn_html = ""
    if high_sgs:
        names = ", ".join(
            f'<code>{sg.get("security_group_id", "")}</code>' for sg in high_sgs[:3]
        )
        extra = f" and {len(high_sgs)-3} more" if len(high_sgs) > 3 else ""
        warn_html = _callout(
            f"<strong>{len(high_sgs)} high-risk security group(s)</strong> require "
            f"attention: {names}{extra}.",
            "",  # orange left-border (default callout)
        )

    # ── SG table ──
    rows = ""
    for sg in sorted_sgs:
        risk  = str(sg.get("overall_risk", "info"))
        flags = sg.get("exposure_flags", [])
        meta  = RISK_META.get(risk, RISK_META["info"])
        flags_html = "".join(
            f'<span class="chip" style="background:{meta["bg"]};color:{meta["text"]}">{f}</span>'
            for f in flags
        )
        attached = "<br>".join(sg.get("attached_resources", [])[:4])
        if sg.get("attached_count", 0) > 4:
            attached += (
                f'<br><span style="color:var(--ig2);font-size:11px">'
                f'+{sg["attached_count"]-4} more</span>'
            )
        rows += (
            f"<tr>"
            f"<td><code>{sg.get('security_group_id','')}</code><br>"
            f'<span style="color:var(--ig2);font-size:12px">{sg.get("security_group_name","")}</span></td>'
            f"<td>{_risk_badge(risk)}</td>"
            f"<td>{flags_html or '<span style=\"color:var(--ig3)\">—</span>'}</td>"
            f'<td style="font-size:12px;color:var(--ig)">{attached or "—"}</td>'
            f"<td>{_rules_summary(sg.get('inbound_analysis', []))}</td>"
            f"<td>{_rules_summary(sg.get('outbound_analysis', []))}</td>"
            f"</tr>"
        )

    table_html = (
        '<div class="twrap"><table>'
        "<thead><tr>"
        "<th>Security Group</th><th>Risk</th><th>Exposure Flags</th>"
        "<th>Attached Resources</th><th>Inbound</th><th>Outbound</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
    )

    body = (
        '<div class="sec-eyebrow">Security Analysis</div>'
        f'<div class="sec-title">Security Groups &mdash; <strong>{total} reviewed</strong></div>'
        f'<div class="sec-intro">Risk assessment of all security groups in '
        f'<strong>{account_name}</strong>, ranked by exposure level.</div>'
        + alert_html
        + warn_html
        + f'<h3 class="blk">All Security Groups ({total})</h3>'
        + table_html
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _html_page(
            title=f"Security Report — {account_name}",
            body=body,
            account_name=account_name,
            hero_stats=hero_stats,
            hero_title=f"Security Posture &middot; <strong>{account_name}</strong>",
            hero_sub=(
                f"Risk assessment of {total} security groups. "
                f"{counts['critical']} critical &middot; {counts['high']} high "
                f"&middot; {counts['medium']} medium."
            ),
            hero_eyebrow=f"Security Analysis &middot; {account_name}",
        ),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# VPC topology report
# ─────────────────────────────────────────────────────────────────────────────

def render_vpc_report(
    inventory: dict[str, list[dict[str, Any]]],
    output_path: Path,
    account_name: str = "",
) -> None:
    vpcs    = inventory.get("vpcs", [])
    subnets = inventory.get("subnets", [])
    ec2     = [i for i in inventory.get("ec2", []) if i.get("state") != "terminated"]
    lbs     = inventory.get("load_balancers", [])
    nats    = inventory.get("nat_gateways", [])
    igws    = inventory.get("internet_gateways", [])
    eps     = inventory.get("vpc_endpoints", [])
    eks_res = inventory.get("eks", [])
    lambdas = inventory.get("lambdas", [])
    rds_res = inventory.get("rds", [])

    # ── indexes ──
    subs_by_vpc: dict[str, list] = {}
    for s in subnets:
        subs_by_vpc.setdefault(s.get("vpc_id", ""), []).append(s)

    ec2_by_sub: dict[str, list] = {}
    for i in ec2:
        ec2_by_sub.setdefault(i.get("subnet_id", ""), []).append(i)

    lb_by_sub: dict[str, list] = {}
    for lb in lbs:
        for az in lb.get("availability_zones", []):
            lb_by_sub.setdefault(az.get("SubnetId", ""), []).append(lb)

    nat_by_sub: dict[str, list] = {}
    for nat in nats:
        nat_by_sub.setdefault(nat.get("subnet_id", ""), []).append(nat)

    ep_by_sub: dict[str, list] = {}
    for ep in eps:
        for sid in ep.get("associated_subnet_ids", []):
            ep_by_sub.setdefault(sid, []).append(ep)

    igw_by_vpc: dict[str, list] = {}
    for igw in igws:
        for vid in igw.get("attached_vpc_ids", []):
            igw_by_vpc.setdefault(vid, []).append(igw)

    eks_by_vpc: dict[str, list] = {}
    for cl in eks_res:
        if cl.get("resource_type") == "aws::eks::cluster":
            eks_by_vpc.setdefault(cl.get("vpc_id", ""), []).append(cl)

    lambda_by_sub: dict[str, list] = {}
    for fn in lambdas:
        for sid in fn.get("subnet_ids", []):
            lambda_by_sub.setdefault(sid, []).append(fn)

    rds_by_sub: dict[str, list] = {}
    for db in rds_res:
        for sid in db.get("subnet_ids", []):
            rds_by_sub.setdefault(sid, []).append(db)

    # ── hero stats ──
    pub_count  = sum(1 for s in subnets if s.get("subnet_type") == "public")
    priv_count = sum(1 for s in subnets if s.get("subnet_type") == "private")
    iso_count  = sum(1 for s in subnets if s.get("subnet_type") == "isolated")

    hero_stats = [
        {"label": "VPCs",            "value": len(vpcs)},
        {"label": "Subnets",         "value": len(subnets)},
        {"label": "Public Subnets",  "value": pub_count,
         "mod": "alert" if pub_count > 0 else ""},
        {"label": "Private Subnets", "value": priv_count, "mod": "ok"},
        {"label": "EC2 Instances",   "value": len(ec2)},
        {"label": "Load Balancers",  "value": len(lbs)},
        {"label": "NAT Gateways",    "value": len(nats)},
        {"label": "VPC Endpoints",   "value": len(eps)},
    ]

    # ── VPC summary table ──
    sum_rows = "".join(
        f"<tr>"
        f"<td>{_short(v, 42)}</td>"
        f"<td><code>{v['resource_id']}</code></td>"
        f"<td><code>{v.get('cidr_block','')}</code></td>"
        f"<td>{len(subs_by_vpc.get(v['resource_id'],[]))}</td>"
        f"<td>{sum(len(ec2_by_sub.get(s['resource_id'],[]))for s in subs_by_vpc.get(v['resource_id'],[]))}</td>"
        f"<td>{'<span class=\"bdg info\">Yes</span>' if igw_by_vpc.get(v['resource_id']) else '—'}</td>"
        f"<td>{'<span class=\"bdg low\">Yes</span>' if eks_by_vpc.get(v['resource_id']) else '—'}</td>"
        f"</tr>"
        for v in vpcs
    )
    summary_table = (
        '<div class="twrap"><table>'
        "<thead><tr>"
        "<th>Name</th><th>VPC ID</th><th>CIDR</th>"
        "<th>Subnets</th><th>EC2</th><th>IGW</th><th>EKS</th>"
        "</tr></thead>"
        f"<tbody>{sum_rows or '<tr><td colspan=\"7\" style=\"color:var(--ig2)\">No VPCs found</td></tr>'}</tbody>"
        "</table></div>"
    )

    # ── per-VPC topology cards ──
    type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
    vpc_html = ""

    for vpc in vpcs:
        vid      = vpc["resource_id"]
        vname    = _short(vpc, 52)
        vcidr    = vpc.get("cidr_block", "")
        vpc_subs = subs_by_vpc.get(vid, [])
        n_igws   = len(igw_by_vpc.get(vid, []))
        n_eks    = len(eks_by_vpc.get(vid, []))

        hdr_extra = (
            f'<code style="font-family:var(--fm);font-size:12px;color:var(--ig2)">{vid}</code>'
            f'<code style="font-family:var(--fm);font-size:12px;color:var(--ib);margin-left:4px">{vcidr}</code>'
        )
        if n_igws:
            hdr_extra += _chip("Internet Gateway", "#F0F4FF", "#21409A")
        if n_eks:
            hdr_extra += _chip(f"EKS ({n_eks})", "#D8F3DE", "#1F7A35")

        # Group subnets by AZ
        az_map: dict[str, list] = {}
        for s in vpc_subs:
            az_map.setdefault(s.get("availability_zone", "?"), []).append(s)

        az_cols = ""
        for az_name in sorted(az_map.keys()):
            az_subs = sorted(
                az_map[az_name],
                key=lambda s: type_order.get(s.get("subnet_type", "unknown"), 3),
            )
            tiles = ""
            for sub in az_subs:
                sid   = sub["resource_id"]
                stype = sub.get("subnet_type", "unknown")
                sname = _short(sub, 32)
                scidr = sub.get("cidr_block", "")
                scls  = SUBNET_META.get(stype, SUBNET_META["unknown"])["cls"]

                chips = []
                for inst in ec2_by_sub.get(sid, []):
                    chips.append(_resource_chip("ec2", _short(inst, 14)))
                for lb in lb_by_sub.get(sid, []):
                    lb_type = "alb" if lb.get("type") == "application" else "nlb"
                    chips.append(_resource_chip(lb_type, _short(lb, 14)))
                for _ in nat_by_sub.get(sid, []):
                    chips.append(_resource_chip("nat"))
                for ep in ep_by_sub.get(sid, []):
                    svc = ep.get("service_name", "").split(".")[-1]
                    chips.append(_resource_chip("vpce", svc[:12]))
                for fn in lambda_by_sub.get(sid, []):
                    chips.append(_resource_chip("lambda", _short(fn, 12)))
                for db in rds_by_sub.get(sid, []):
                    chips.append(_resource_chip("rds", _short(db, 12)))

                res_html = (
                    "".join(chips)
                    or '<span style="color:var(--ig3);font-size:11px">empty</span>'
                )
                tiles += (
                    f'<div class="sub-tile {scls}">'
                    f'<div class="sub-name">{sname}</div>'
                    f'<div class="sub-cidr">{scidr} &middot; {stype}</div>'
                    f'<div class="sub-res">{res_html}</div>'
                    f"</div>"
                )
            az_cols += (
                f'<div class="az-col">'
                f'<div class="az-label">{az_name}</div>'
                f"{tiles}</div>"
            )

        vpc_html += (
            f'<div class="vpc-card">'
            f'<div class="vpc-header">'
            f'<span class="vpc-name">{vname}</span>'
            f"{hdr_extra}"
            f"</div>"
            f'<div style="display:flex;gap:14px;flex-wrap:wrap">{az_cols}</div>'
            f"</div>"
        )

    body = (
        '<div class="sec-eyebrow">Network Topology</div>'
        f'<div class="sec-title">VPC Architecture &middot; <strong>{account_name}</strong></div>'
        f'<div class="sec-intro">'
        f"{len(vpcs)} VPC(s) &middot; {len(subnets)} subnets "
        f"({pub_count} public, {priv_count} private, {iso_count} isolated) &middot; "
        f"{len(ec2)} EC2 &middot; {len(lbs)} load balancer(s)."
        f"</div>"
        + '<h3 class="blk">VPC Summary</h3>'
        + summary_table
        + f'<h3 class="blk">Topology Detail</h3>'
        + vpc_html
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _html_page(
            title=f"VPC Topology — {account_name}",
            body=body,
            account_name=account_name,
            hero_stats=hero_stats,
            hero_title=f"VPC Topology &middot; <strong>{account_name}</strong>",
            hero_sub=(
                f"{len(vpcs)} VPC(s) with {len(subnets)} subnets across "
                f"{len(set(s.get('availability_zone','') for s in subnets))} availability zones."
            ),
            hero_eyebrow=f"Network Topology &middot; {account_name}",
        ),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Graph analysis report
# ─────────────────────────────────────────────────────────────────────────────

def render_graph_report(
    graph_summary: dict[str, Any],
    internet_facing: list[dict[str, Any]],
    nat_dependents: list[dict[str, Any]],
    output_path: Path,
    account_name: str = "",
) -> None:
    n_internet = graph_summary.get("internet_facing_count", 0)
    n_nodes    = graph_summary.get("node_count", 0)
    n_edges    = graph_summary.get("edge_count", 0)
    n_pub      = graph_summary.get("public_subnet_count", 0)
    n_priv     = graph_summary.get("private_subnet_count", 0)
    n_comp     = graph_summary.get("connected_components", 0)

    hero_stats = [
        {"label": "Total Nodes",     "value": n_nodes},
        {"label": "Total Edges",     "value": n_edges},
        {"label": "Internet-Facing", "value": n_internet,
         "mod": "alert" if n_internet > 0 else ""},
        {"label": "Public Subnets",  "value": n_pub,
         "mod": "alert" if n_pub > 0 else ""},
        {"label": "Private Subnets", "value": n_priv, "mod": "ok"},
        {"label": "Components",      "value": n_comp},
    ]

    def _resource_table(resources: list[dict], heading: str) -> str:
        if not resources:
            return (
                f'<h3 class="blk">{heading}</h3>'
                + _callout("No resources found in this category.", "ok")
            )
        rows = "".join(
            f"<tr>"
            f"<td><code>{r.get('resource_id','')}</code></td>"
            f"<td><span class='bdg info'>"
            f"{r.get('resource_type','').split('::')[-1].upper()}</span></td>"
            f"<td>{r.get('tags',{}).get('Name') or r.get('resource_name','—')}</td>"
            f"<td>{r.get('region','—')}</td>"
            f"</tr>"
            for r in resources[:100]
        )
        if len(resources) > 100:
            rows += (
                f'<tr><td colspan="4" style="color:var(--ig2);font-style:italic">'
                f"+{len(resources)-100} more resources&hellip;</td></tr>"
            )
        return (
            f'<h3 class="blk">{heading} ({len(resources)})</h3>'
            '<div class="twrap"><table>'
            "<thead><tr>"
            "<th>Resource ID</th><th>Type</th><th>Name</th><th>Region</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table></div>"
        )

    body = (
        '<div class="sec-eyebrow">Graph Analysis</div>'
        f'<div class="sec-title">Dependency Graph &middot; <strong>{account_name}</strong></div>'
        f'<div class="sec-intro">'
        f"Network graph with {n_nodes} nodes and {n_edges} edges. "
        f"Highlights internet-exposed resources and NAT routing paths."
        f"</div>"
        + _resource_table(internet_facing, "Internet-Facing Resources")
        + _resource_table(nat_dependents,  "Resources Behind NAT")
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _html_page(
            title=f"Graph Analysis — {account_name}",
            body=body,
            account_name=account_name,
            hero_stats=hero_stats,
            hero_title=f"Dependency Graph &middot; <strong>{account_name}</strong>",
            hero_sub=(
                f"{n_nodes} nodes &middot; {n_edges} edges &middot; "
                f"{n_internet} internet-facing &middot; {n_comp} connected component(s)."
            ),
            hero_eyebrow=f"Graph Analysis &middot; {account_name}",
        ),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy report — VPC → AZ → Subnet → Resource → Security Groups
# ─────────────────────────────────────────────────────────────────────────────

_HIER_CSS = """\
/* ── hierarchy ── */
.hvpc{
  border:1.5px solid rgba(33,64,154,.15);border-radius:var(--r3);
  margin-bottom:28px;background:white;box-shadow:var(--s1);overflow:hidden;
}
.hvpc-hdr{
  background:linear-gradient(135deg,rgba(33,64,154,.05),rgba(255,134,13,.02));
  border-bottom:1px solid rgba(33,64,154,.10);padding:13px 18px;
  display:flex;align-items:center;gap:9px;flex-wrap:wrap;
}
.hvpc-name{font-weight:700;font-size:15px;color:var(--ib)}
.hvpc-global{
  border-bottom:1px solid rgba(33,64,154,.07);padding:8px 16px;
  display:flex;gap:6px;flex-wrap:wrap;align-items:center;
  background:rgba(240,244,255,.3);
}
.hvpc-global-lbl{
  font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ig2);font-family:var(--fm);margin-right:2px;
}
.haz-group{display:flex;flex-wrap:wrap;align-items:stretch}
.haz{
  flex:1;min-width:250px;border-right:1px solid rgba(33,64,154,.07);
  padding:12px 13px;
}
.haz:last-child{border-right:none}
.haz-label{
  font-family:var(--fm);font-size:11px;font-weight:700;
  text-transform:uppercase;letter-spacing:.07em;color:var(--ib);
  margin-bottom:10px;padding-bottom:6px;
  border-bottom:1px dashed rgba(33,64,154,.12);
}
.hsub{
  border:1.5px solid;border-radius:var(--r2);margin-bottom:8px;overflow:hidden;
}
.hsub.pub{border-color:#64E386}
.hsub.priv{border-color:#FF860D}
.hsub.iso{border-color:#F04B4B}
.hsub.unk{border-color:#B8BCCC}
.hsub-hdr{
  padding:7px 11px;display:flex;align-items:center;gap:7px;flex-wrap:wrap;
}
.hsub.pub  .hsub-hdr{background:#EEFBF1}
.hsub.priv .hsub-hdr{background:#FFF7EE}
.hsub.iso  .hsub-hdr{background:#FEF0F0}
.hsub.unk  .hsub-hdr{background:#F8F9FA}
.hsub-name{font-weight:600;font-size:13px;color:var(--in)}
.hsub-cidr{font-family:var(--fm);font-size:11px;color:var(--ig2)}
.hres-list{padding:5px 7px}
.hres-empty{padding:4px 6px;font-size:11px;color:var(--ig3);font-style:italic}
.hres{
  padding:6px 10px;border-radius:var(--r1);margin-bottom:4px;
  border:1px solid rgba(33,64,154,.07);background:var(--ibgs);
  transition:background .15s;
}
.hres:hover{background:var(--ibg)}
.hres-hdr{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.hres-name{font-size:13px;font-weight:600;color:var(--in)}
.hres-meta{font-size:11px;color:var(--ig2);font-family:var(--fm)}
.hres-sgs{
  display:flex;align-items:center;gap:4px;flex-wrap:wrap;margin-top:3px;
}
.hres-sgs .sg-lbl{
  font-size:10px;color:var(--ig2);font-family:var(--fm);
  text-transform:uppercase;letter-spacing:.04em;
}
.sg-ref{
  display:inline-block;padding:2px 8px;border-radius:999px;
  font-size:10px;font-weight:600;font-family:var(--fm);
  text-transform:uppercase;letter-spacing:.03em;cursor:default;
}
.sg-ref.critical{background:#FEF0F0;color:#C42626;border:1px solid rgba(240,75,75,.4)}
.sg-ref.high    {background:#FFF7EE;color:#B86200;border:1px solid rgba(255,134,13,.4)}
.sg-ref.medium  {background:#FFFBE6;color:#856A00;border:1px solid rgba(251,192,45,.4)}
.sg-ref.low     {background:#EEFBF1;color:#1F7A35;border:1px solid rgba(100,227,134,.4)}
.sg-ref.info    {background:#F0F4FF;color:#21409A;border:1px solid rgba(33,64,154,.25)}
.loose-sgs{
  border-top:1px solid rgba(33,64,154,.08);padding:10px 16px;
  background:rgba(240,244,255,.2);
}
.loose-sgs-lbl{
  font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ig2);font-family:var(--fm);margin-bottom:6px;
}"""


def _sg_inline(
    sg_ids: list[str],
    sg_risk_idx: dict[str, str],
    sg_name_idx: dict[str, str],
    max_show: int = 5,
) -> str:
    """Return inline SG risk badges for a resource."""
    if not sg_ids:
        return ""
    parts = []
    for sid in sg_ids[:max_show]:
        risk  = sg_risk_idx.get(sid, "info")
        name  = sg_name_idx.get(sid, sid)
        short = name[:24] + "…" if len(name) > 24 else name
        parts.append(
            f'<span class="sg-ref {risk}" title="{sid}">{short}</span>'
        )
    if len(sg_ids) > max_show:
        parts.append(
            f'<span style="color:var(--ig2);font-size:10px">+{len(sg_ids)-max_show}</span>'
        )
    return '<span class="sg-lbl">Security Groups:</span> ' + " ".join(parts)


def _h_resource(
    type_key: str,
    name: str,
    meta: str,
    sg_html: str,
    extra_html: str = "",
) -> str:
    """Render one resource row inside a subnet tile."""
    m = RESOURCE_META.get(type_key, {"bg": "#F0F4FF", "text": "#21409A", "label": type_key.upper()})
    type_chip = _chip(m["label"], m["bg"], m["text"])
    meta_span = f'<span class="hres-meta">{meta}</span>' if meta else ""
    sgs_div   = f'<div class="hres-sgs">{sg_html}</div>' if sg_html else ""
    return (
        f'<div class="hres">'
        f'<div class="hres-hdr">{type_chip}'
        f'<span class="hres-name">{name}</span>{meta_span}</div>'
        f"{sgs_div}{extra_html}"
        f"</div>"
    )


def render_hierarchy_report(
    inventory: dict[str, list[dict[str, Any]]],
    sg_analysis: list[dict[str, Any]],
    output_path: Path,
    account_name: str = "",
) -> None:
    """
    Hierarchical drill-down report: VPC → AZ → Subnet → Resource → Security Groups.

    Shows the full network topology as a structured document — matching the diagram
    layout but in readable, navigable HTML with risk levels shown inline.
    """
    # ── resource extraction ──────────────────────────────────────────────────
    vpcs      = inventory.get("vpcs", [])
    subnets   = inventory.get("subnets", [])
    ec2       = [i for i in inventory.get("ec2", []) if i.get("state") != "terminated"]
    lbs       = inventory.get("load_balancers", [])
    nats      = inventory.get("nat_gateways", [])
    igws      = inventory.get("internet_gateways", [])
    tgw_atts  = inventory.get("transit_gateway_attachments", [])
    eps       = inventory.get("vpc_endpoints", [])
    eks_res   = inventory.get("eks", [])
    lambdas   = inventory.get("lambdas", [])
    rds_res   = inventory.get("rds", [])
    sgs_inv   = inventory.get("security_groups", [])
    peerings  = inventory.get("vpc_peerings", [])

    # ── SG lookup tables ─────────────────────────────────────────────────────
    sg_risk_idx: dict[str, str] = {}
    sg_name_idx: dict[str, str] = {}
    for sg_a in sg_analysis:
        sid = sg_a.get("security_group_id", "")
        sg_risk_idx[sid] = str(sg_a.get("overall_risk", "info"))
        sg_name_idx[sid] = sg_a.get("security_group_name", sid)
    # fill in any SGs not in the analysis
    for sg in sgs_inv:
        sid = sg.get("resource_id", "")
        if sid not in sg_name_idx:
            sg_name_idx[sid] = sg.get("resource_name") or sg.get("group_name") or sid
        sg_risk_idx.setdefault(sid, "info")

    # ── subnet / VPC indexes ─────────────────────────────────────────────────
    subs_by_vpc: dict[str, list] = {}
    for s in subnets:
        subs_by_vpc.setdefault(s.get("vpc_id", ""), []).append(s)

    ec2_by_sub: dict[str, list] = {}
    for i in ec2:
        ec2_by_sub.setdefault(i.get("subnet_id", ""), []).append(i)

    # LBs: one entry per subnet they sit in (deduplicate per lb+subnet pair)
    lb_by_sub: dict[str, list] = {}
    _lb_seen: dict[str, set] = {}
    for lb in lbs:
        for az in lb.get("availability_zones", []):
            sid = az.get("SubnetId", "")
            if sid and lb["resource_id"] not in _lb_seen.get(sid, set()):
                _lb_seen.setdefault(sid, set()).add(lb["resource_id"])
                lb_by_sub.setdefault(sid, []).append(lb)

    nat_by_sub: dict[str, list] = {}
    for nat in nats:
        nat_by_sub.setdefault(nat.get("subnet_id", ""), []).append(nat)

    ep_by_sub: dict[str, list] = {}
    for ep in eps:
        for sid in ep.get("associated_subnet_ids", []):
            ep_by_sub.setdefault(sid, []).append(ep)

    lambda_by_sub: dict[str, list] = {}
    for fn in lambdas:
        for sid in fn.get("subnet_ids", []):
            lambda_by_sub.setdefault(sid, []).append(fn)

    rds_by_sub: dict[str, list] = {}
    for db in rds_res:
        for sid in db.get("subnet_ids", []):
            rds_by_sub.setdefault(sid, []).append(db)

    igw_by_vpc: dict[str, list] = {}
    for igw in igws:
        for vid in igw.get("attached_vpc_ids", []):
            igw_by_vpc.setdefault(vid, []).append(igw)

    tgw_by_vpc: dict[str, list] = {}
    for att in tgw_atts:
        vid = att.get("resource_id_ref", "") or att.get("vpc_id", "")
        if vid:
            tgw_by_vpc.setdefault(vid, []).append(att)

    peering_by_vpc: dict[str, list] = {}
    for p in peerings:
        for vpc_key in ("requester_vpc_info", "accepter_vpc_info"):
            vid = p.get(vpc_key, {}).get("VpcId", "")
            if vid:
                peering_by_vpc.setdefault(vid, []).append(p)

    eks_clusters   = [e for e in eks_res if e.get("resource_type") == "aws::eks::cluster"]
    eks_nodegroups = [e for e in eks_res if e.get("resource_type") == "aws::eks::nodegroup"]

    eks_by_vpc: dict[str, list] = {}
    for cl in eks_clusters:
        eks_by_vpc.setdefault(cl.get("vpc_id", ""), []).append(cl)

    ng_by_sub: dict[str, list] = {}
    for ng in eks_nodegroups:
        for sid in ng.get("subnet_ids", []):
            ng_by_sub.setdefault(sid, []).append(ng)

    sgs_by_vpc: dict[str, list] = {}
    for sg in sgs_inv:
        sgs_by_vpc.setdefault(sg.get("vpc_id", ""), []).append(sg)

    # Track which SG IDs appear on at least one resource
    attached_sg_ids: set[str] = set()
    for res_list in [ec2, lbs, lambdas, rds_res, eks_clusters]:
        for r in res_list:
            for sid in (r.get("security_group_ids") or []):
                if sid:
                    attached_sg_ids.add(sid)

    # ── hero stats ───────────────────────────────────────────────────────────
    crit_count = sum(1 for v in sg_risk_idx.values() if v == "critical")
    high_count = sum(1 for v in sg_risk_idx.values() if v == "high")
    total_res  = len(ec2) + len(lbs) + len(lambdas) + len(rds_res) + len(eks_clusters)

    hero_stats = [
        {"label": "VPCs",           "value": len(vpcs)},
        {"label": "Subnets",        "value": len(subnets)},
        {"label": "Resources",      "value": total_res},
        {"label": "Security Groups","value": len(sg_analysis)},
        {"label": "Critical SGs",   "value": crit_count,
         "mod": "alert" if crit_count > 0 else "ok"},
        {"label": "High-Risk SGs",  "value": high_count,
         "mod": "warn" if high_count > 0 else "ok"},
    ]

    # ── VPC ordering: subnets grouped by AZ ──────────────────────────────────
    type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
    _sub_bg  = {"pub": "#EEFBF1", "priv": "#FFF7EE", "iso": "#FEF0F0", "unk": "#F8F9FA"}
    _sub_txt = {"pub": "#1F7A35", "priv": "#B86200", "iso": "#C42626", "unk": "#808599"}

    vpc_html = ""

    for vpc in vpcs:
        vid      = vpc["resource_id"]
        vname    = _short(vpc, 56)
        vcidr    = vpc.get("cidr_block", "")
        vpc_subs = subs_by_vpc.get(vid, [])

        # ── VPC header row ───────────────────────────────────────────────────
        hdr = (
            f'<span class="hvpc-name">{vname}</span>'
            f'<code style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{vid}</code>'
            f'<code style="font-family:var(--fm);font-size:12px;color:var(--ib);margin-left:2px">{vcidr}</code>'
        )

        # ── VPC-level global resources bar ───────────────────────────────────
        global_items = ""

        for igw in igw_by_vpc.get(vid, []):
            igw_name = _short(igw, 28)
            global_items += _chip(f"IGW · {igw_name}", "#F0F4FF", "#21409A")

        for att in tgw_by_vpc.get(vid, []):
            tgw_id = att.get("transit_gateway_id", "?")
            state  = att.get("state", "")
            bg = "#EEFBF1" if state == "available" else "#FFF7EE"
            tx = "#1F7A35" if state == "available" else "#B86200"
            global_items += _chip(f"TGW · {tgw_id}", bg, tx)

        seen_peerings: set[str] = set()
        for p in peering_by_vpc.get(vid, []):
            pid = p.get("resource_id", "")
            if pid in seen_peerings:
                continue
            seen_peerings.add(pid)
            req = p.get("requester_vpc_info", {})
            acc = p.get("accepter_vpc_info", {})
            other = acc.get("VpcId", "") if req.get("VpcId") == vid else req.get("VpcId", "")
            global_items += _chip(f"Peering · {other}", "#E7E2FB", "#4A3D9E")

        # EKS clusters shown at VPC level (they span multiple subnets)
        eks_rows = ""
        for cl in eks_by_vpc.get(vid, []):
            cl_name  = _short(cl, 32)
            cl_ver   = cl.get("version", "")
            cl_sg    = _sg_inline(cl.get("security_group_ids", []), sg_risk_idx, sg_name_idx)
            cl_node_names = [
                ng.get("nodegroup_name", _short(ng, 20))
                for ng in eks_nodegroups
                if ng.get("cluster_arn") == cl.get("resource_id") or
                   ng.get("cluster_name") == cl.get("cluster_name")
            ]
            ng_chips = "".join(
                _chip(n[:20], "#D8F3DE", "#1F7A35") for n in cl_node_names[:6]
            )
            extra = f'<div style="margin-top:3px">{_chip("Node Groups:", "#F0F4FF","#21409A")} {ng_chips}</div>' if ng_chips else ""
            eks_rows += (
                f'<div style="margin-top:5px;width:100%">'
                + _h_resource("eks", cl_name, cl_ver, cl_sg, extra)
                + "</div>"
            )

        if global_items or eks_rows:
            global_section = (
                f'<div class="hvpc-global">'
                f'<span class="hvpc-global-lbl">VPC Resources:</span>'
                f"{global_items}{eks_rows}"
                f"</div>"
            )
        else:
            global_section = ""

        # ── AZ columns ───────────────────────────────────────────────────────
        az_map: dict[str, list] = {}
        for s in vpc_subs:
            az_map.setdefault(s.get("availability_zone", "?"), []).append(s)

        az_cols = ""
        for az_name in sorted(az_map.keys()):
            az_subs = sorted(
                az_map[az_name],
                key=lambda s: type_order.get(s.get("subnet_type", "unknown"), 3),
            )
            sub_tiles = ""

            for sub in az_subs:
                sid   = sub["resource_id"]
                stype = sub.get("subnet_type", "unknown")
                sname = _short(sub, 34)
                scidr = sub.get("cidr_block", "")
                scls  = SUBNET_META.get(stype, SUBNET_META["unknown"])["cls"]
                type_chip = _chip(
                    SUBNET_META.get(stype, SUBNET_META["unknown"])["label"],
                    _sub_bg[scls], _sub_txt[scls],
                )

                res_rows = ""

                # EC2 instances
                for inst in ec2_by_sub.get(sid, []):
                    res_rows += _h_resource(
                        "ec2",
                        _short(inst, 30),
                        " · ".join(filter(None, [
                            inst.get("instance_type", ""),
                            inst.get("private_ip", ""),
                        ])),
                        _sg_inline(inst.get("security_group_ids", []),
                                   sg_risk_idx, sg_name_idx),
                    )

                # Load balancers
                for lb in lb_by_sub.get(sid, []):
                    lb_type = "alb" if lb.get("type") == "application" else "nlb"
                    res_rows += _h_resource(
                        lb_type,
                        _short(lb, 30),
                        lb.get("scheme", ""),
                        _sg_inline(lb.get("security_group_ids", []),
                                   sg_risk_idx, sg_name_idx),
                    )

                # NAT gateways
                for nat in nat_by_sub.get(sid, []):
                    res_rows += _h_resource(
                        "nat", _short(nat, 30), nat.get("state", ""), "",
                    )

                # VPC endpoints
                for ep in ep_by_sub.get(sid, []):
                    svc = ep.get("service_name", "").split(".")[-1]
                    res_rows += _h_resource(
                        "vpce", svc, ep.get("endpoint_type", ""), "",
                    )

                # Lambda functions
                for fn in lambda_by_sub.get(sid, []):
                    res_rows += _h_resource(
                        "lambda",
                        _short(fn, 30),
                        fn.get("runtime", ""),
                        _sg_inline(fn.get("security_group_ids", []),
                                   sg_risk_idx, sg_name_idx),
                    )

                # RDS instances / clusters
                _seen_rds: set[str] = set()
                for db in rds_by_sub.get(sid, []):
                    if db["resource_id"] in _seen_rds:
                        continue
                    _seen_rds.add(db["resource_id"])
                    res_rows += _h_resource(
                        "rds",
                        _short(db, 30),
                        db.get("engine", ""),
                        _sg_inline(db.get("security_group_ids", []),
                                   sg_risk_idx, sg_name_idx),
                    )

                # EKS node groups
                _seen_ng: set[str] = set()
                for ng in ng_by_sub.get(sid, []):
                    if ng["resource_id"] in _seen_ng:
                        continue
                    _seen_ng.add(ng["resource_id"])
                    desired = ng.get("desired_size", "")
                    itypes  = ", ".join(ng.get("instance_types", [])[:2])
                    meta    = " · ".join(filter(None, [
                        itypes,
                        f"desired: {desired}" if desired != "" else "",
                    ]))
                    res_rows += _h_resource(
                        "eks",
                        ng.get("nodegroup_name") or _short(ng, 28),
                        meta, "",
                    )

                sub_tiles += (
                    f'<div class="hsub {scls}">'
                    f'<div class="hsub-hdr">'
                    f'<span class="hsub-name">{sname}</span>'
                    f'<span class="hsub-cidr">{scidr}</span>'
                    f"{type_chip}</div>"
                    f'<div class="hres-list">'
                    + (res_rows or '<div class="hres-empty">empty</div>')
                    + "</div></div>"
                )

            az_cols += (
                f'<div class="haz">'
                f'<div class="haz-label">{az_name}</div>'
                f"{sub_tiles}</div>"
            )

        # ── unattached (loose) SGs for this VPC ──────────────────────────────
        vpc_sg_set   = {sg.get("resource_id", "") for sg in sgs_by_vpc.get(vid, [])}
        loose_sg_ids = vpc_sg_set - attached_sg_ids

        loose_html = ""
        if loose_sg_ids:
            badges = "".join(
                f'<span class="sg-ref {sg_risk_idx.get(sid,"info")}" title="{sid}">'
                f'{(sg_name_idx.get(sid,sid))[:26]}</span> '
                for sid in sorted(loose_sg_ids)
            )
            loose_html = (
                f'<div class="loose-sgs">'
                f'<div class="loose-sgs-lbl">'
                f'Unattached Security Groups ({len(loose_sg_ids)})</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:4px">{badges}</div>'
                f"</div>"
            )

        vpc_html += (
            f'<div class="hvpc">'
            f'<div class="hvpc-hdr">{hdr}</div>'
            f"{global_section}"
            f'<div class="haz-group">{az_cols}</div>'
            f"{loose_html}"
            f"</div>"
        )

    # ── assemble page ────────────────────────────────────────────────────────
    pub_count  = sum(1 for s in subnets if s.get("subnet_type") == "public")
    priv_count = sum(1 for s in subnets if s.get("subnet_type") == "private")

    body = (
        '<div class="sec-eyebrow">Infrastructure Hierarchy</div>'
        f'<div class="sec-title">Network Hierarchy &middot; <strong>{account_name}</strong></div>'
        f'<div class="sec-intro">'
        f"Complete drill-down: VPC &rarr; Availability Zone &rarr; Subnet &rarr; Resource &rarr; Security Groups. "
        f"{len(vpcs)} VPC(s) &middot; {len(subnets)} subnets "
        f"({pub_count} public, {priv_count} private) &middot; "
        f"{total_res} resources &middot; {len(sg_analysis)} security groups."
        f"</div>"
        + vpc_html
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _html_page(
            title=f"Network Hierarchy — {account_name}",
            body=body,
            account_name=account_name,
            extra_css=_HIER_CSS,
            hero_stats=hero_stats,
            hero_title=f"Network Hierarchy &middot; <strong>{account_name}</strong>",
            hero_sub=(
                f"Full infrastructure map from VPC to security group. "
                f"{crit_count} critical &middot; {high_count} high-risk security groups highlighted inline."
            ),
            hero_eyebrow=f"Infrastructure Overview &middot; {account_name}",
        ),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Consolidated audit report — 6 tabs, single HTML file
# ─────────────────────────────────────────────────────────────────────────────

_DANGEROUS_PORTS = {
    22:    "SSH",     23:    "Telnet",    3389:  "RDP",
    1433:  "MSSQL",  3306:  "MySQL",     5432:  "PostgreSQL",
    27017: "MongoDB", 6379: "Redis",     9200:  "Elasticsearch",
    9300:  "Elasticsearch", 5984: "CouchDB",
    2181:  "Zookeeper", 11211: "Memcached",
}
_OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


def _is_open_to_internet(rule: dict) -> bool:
    return bool(set(rule.get("cidrs") or []) & _OPEN_CIDRS)


def _dangerous_open_ports(sg: dict) -> list[tuple]:
    hits: list[tuple] = []
    for rule in sg.get("inbound_analysis", []):
        if not _is_open_to_internet(rule):
            continue
        fp    = rule.get("from_port")
        tp    = rule.get("to_port")
        proto = rule.get("protocol", "-1")
        if proto in ("-1", "all"):
            hits.append((None, "ALL TRAFFIC"))
            continue
        if fp is not None:
            for port, svc in _DANGEROUS_PORTS.items():
                if fp <= port <= (tp or fp):
                    hits.append((port, svc))
    return hits


def _safe(v: Any, yes: str = "Yes", no: str = "No") -> str:
    if v is None:
        return '<span style="color:var(--ig3)">—</span>'
    return (
        f'<span class="chip" style="background:#EEFBF1;color:#1F7A35">{yes}</span>'
        if v
        else f'<span class="chip" style="background:#FEF0F0;color:#C42626">{no}</span>'
    )


# ── per-tab builders ──────────────────────────────────────────────────────────

def _tab_dashboard(
    inventory: dict, sg_analysis: list[dict],
    internet_facing: list[dict], account_name: str,
) -> str:
    risk_order = ["critical", "high", "medium", "low", "info"]
    counts = {r: sum(1 for a in sg_analysis if str(a.get("overall_risk")) == r) for r in risk_order}

    crit_sgs = [a for a in sg_analysis if str(a.get("overall_risk")) == "critical"]
    high_sgs = [a for a in sg_analysis if str(a.get("overall_risk")) == "high"]
    s3       = inventory.get("s3_buckets", [])
    kms      = inventory.get("kms", [])
    secrets  = inventory.get("secrets", [])
    ec2      = [i for i in inventory.get("ec2", []) if i.get("state") != "terminated"]
    rds      = inventory.get("rds", [])

    s3_exposed  = [b for b in s3 if b.get("acl_public") or b.get("bucket_policy_public")]
    s3_no_block = [b for b in s3 if not all([
        b.get("block_public_acls"), b.get("block_public_policy"),
        b.get("ignore_public_acls"), b.get("restrict_public_buckets"),
    ])]
    kms_no_rot  = [k for k in kms if k.get("key_manager") == "CUSTOMER" and not k.get("rotation_enabled")]
    sec_no_rot  = [s for s in secrets if not s.get("rotation_enabled")]
    rds_no_enc  = [db for db in rds if db.get("storage_encrypted") is False]

    callouts = ""
    if crit_sgs:
        ids   = ", ".join(f'<code>{sg.get("security_group_id","")}</code>' for sg in crit_sgs[:5])
        extra = f" +{len(crit_sgs)-5} more" if len(crit_sgs) > 5 else ""
        callouts += _callout(
            f"<strong>{len(crit_sgs)} critical security group(s)</strong> allow unrestricted "
            f"internet access to sensitive ports. Immediate remediation required: {ids}{extra}.", "alert")
    if s3_exposed:
        names = ", ".join(f'<code>{b.get("resource_name","")}</code>' for b in s3_exposed[:4])
        callouts += _callout(
            f"<strong>{len(s3_exposed)} S3 bucket(s) are publicly accessible</strong> via ACL "
            f"or bucket policy: {names}. Review and restrict access.", "alert")
    if high_sgs:
        callouts += _callout(
            f"<strong>{len(high_sgs)} high-risk security group(s)</strong> have elevated exposure. "
            f"Review and tighten ingress rules.")
    if s3_no_block:
        callouts += _callout(
            f"<strong>{len(s3_no_block)} S3 bucket(s)</strong> do not have all four public-access "
            f"block settings enabled (<code>BlockPublicAcls</code>, <code>BlockPublicPolicy</code>, "
            f"<code>IgnorePublicAcls</code>, <code>RestrictPublicBuckets</code>).", "info")
    if kms_no_rot:
        callouts += _callout(
            f"<strong>{len(kms_no_rot)} customer-managed KMS key(s)</strong> do not have automatic "
            f"rotation enabled. Enable yearly rotation.", "info")
    if sec_no_rot:
        callouts += _callout(
            f"<strong>{len(sec_no_rot)} secret(s)</strong> in Secrets Manager have no rotation "
            f"configured. Automate rotation to reduce credential exposure.", "info")
    if rds_no_enc:
        names = ", ".join(f'<code>{db.get("resource_name","")}</code>' for db in rds_no_enc[:3])
        callouts += _callout(
            f"<strong>{len(rds_no_enc)} RDS instance(s) not encrypted at rest:</strong> {names}. "
            f"Enable encryption for data-at-rest compliance.", "alert")
    if not callouts:
        callouts = _callout("<strong>No critical findings detected.</strong> Infrastructure appears well-configured.", "ok")

    risk_tiles = '<div class="cgrid c3" style="margin:20px 0">'
    for risk, clr, desc in [
        ("critical", "#C42626", "Unrestricted internet access to sensitive ports."),
        ("high",     "#B86200", "Broad access rules exposing sensitive resources."),
        ("medium",   "#856A00", "Moderately permissive; review recommended."),
        ("low",      "#1F7A35", "Restricted access; acceptable risk."),
        ("info",     "#21409A", "No significant exposure detected."),
    ]:
        cnt = counts[risk]
        risk_tiles += (
            f'<div class="tile" style="border-left:4px solid {clr}">'
            f'<div class="tkicker" style="color:{clr}">{risk.upper()}</div>'
            f'<div style="font-size:26px;font-weight:700;color:{clr};margin-bottom:4px">{cnt}</div>'
            f'<div class="tbody">{desc}</div></div>')
    risk_tiles += "</div>"

    eks_cls = [e for e in inventory.get("eks", []) if e.get("resource_type") == "aws::eks::cluster"]
    rows = "".join(
        f"<tr><td>{label}</td><td style='font-weight:600'>{count}</td></tr>"
        for label, count in [
            ("VPCs",              len(inventory.get("vpcs", []))),
            ("Subnets (Public)",  sum(1 for s in inventory.get("subnets",[]) if s.get("subnet_type") == "public")),
            ("Subnets (Private)", sum(1 for s in inventory.get("subnets",[]) if s.get("subnet_type") == "private")),
            ("EC2 Instances",     len(ec2)),
            ("Load Balancers",    len(inventory.get("load_balancers", []))),
            ("EKS Clusters",      len(eks_cls)),
            ("Lambda Functions",  len(inventory.get("lambdas", []))),
            ("RDS Instances",     len(rds)),
            ("S3 Buckets",        len(s3)),
            ("KMS Keys",          len(kms)),
            ("IAM Roles",         len(inventory.get("iam_roles", []))),
            ("Secrets",           len(secrets)),
            ("Security Groups",   len(sg_analysis)),
            ("Internet-Facing",   len(internet_facing)),
        ] if count > 0
    )

    if_rows = "".join(
        f"<tr>"
        f"<td>{r.get('tags',{}).get('Name') or r.get('resource_name','—')}<br>"
        f'<span style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{r.get("resource_id","")}</span></td>'
        f"<td><span class='bdg info'>{r.get('resource_type','').split('::')[-1].upper()}</span></td>"
        f"</tr>"
        for r in internet_facing[:12]
    ) + (f"<tr><td colspan='2' style='color:var(--ig2);font-style:italic'>+{len(internet_facing)-12} more…</td></tr>"
         if len(internet_facing) > 12 else "")

    inv_block = (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:8px">'
        f'<div class="twrap"><table><thead><tr><th>Resource Type</th><th>Count</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
        f'<div><h3 class="blk" style="margin-top:0">Internet-Facing Resources</h3>'
        + (
            f'<div class="twrap"><table><thead><tr><th>Resource</th><th>Type</th></tr></thead>'
            f"<tbody>{if_rows}</tbody></table></div>"
            if internet_facing
            else _callout("No internet-facing resources detected.", "ok")
        )
        + "</div></div>"
    )

    return (
        '<div class="sec-eyebrow">Audit Dashboard</div>'
        f'<div class="sec-title">Executive Summary &middot; <strong>{account_name}</strong></div>'
        '<div class="sec-intro">Critical findings ranked by severity. Remediate in order from top to bottom.</div>'
        + callouts
        + '<h3 class="blk">Security Group Risk Distribution</h3>'
        + risk_tiles
        + '<h3 class="blk">Resource Inventory &amp; Internet-Facing</h3>'
        + inv_block
    )


def _tab_security(sg_analysis: list[dict]) -> str:
    risk_order = ["critical", "high", "medium", "low", "info"]
    sorted_sgs = sorted(
        sg_analysis,
        key=lambda a: (
            risk_order.index(str(a.get("overall_risk","info"))) if str(a.get("overall_risk","info")) in risk_order else 99,
            -a.get("attached_count", 0),
        ),
    )
    rows = ""
    for sg in sorted_sgs:
        risk  = str(sg.get("overall_risk", "info"))
        flags = sg.get("exposure_flags", [])
        meta  = RISK_META.get(risk, RISK_META["info"])
        flags_html = "".join(
            f'<span class="chip" style="background:{meta["bg"]};color:{meta["text"]}">{f}</span>'
            for f in flags)
        attached = "<br>".join(sg.get("attached_resources", [])[:4])
        if sg.get("attached_count", 0) > 4:
            attached += f'<br><span style="color:var(--ig2);font-size:11px">+{sg["attached_count"]-4} more</span>'
        rows += (
            f"<tr>"
            f"<td><code>{sg.get('security_group_id','')}</code><br>"
            f'<span style="color:var(--ig2);font-size:12px">{sg.get("security_group_name","")}</span></td>'
            f"<td>{_risk_badge(risk)}</td>"
            f"<td>{flags_html or '<span style=\"color:var(--ig3)\">—</span>'}</td>"
            f'<td style="font-size:12px;color:var(--ig)">{attached or "—"}</td>'
            f"<td>{_rules_summary(sg.get('inbound_analysis', []))}</td>"
            f"<td>{_rules_summary(sg.get('outbound_analysis', []))}</td>"
            f"</tr>")
    return (
        '<div class="sec-eyebrow">Security Analysis</div>'
        f'<div class="sec-title">Security Groups &mdash; <strong>{len(sg_analysis)} reviewed</strong></div>'
        '<div class="sec-intro">All security groups ranked by risk level. '
        'Critical and High entries expose infrastructure to the internet or allow overly broad access. '
        'Verify that every open port is intentional and documented.</div>'
        '<div class="twrap"><table>'
        "<thead><tr><th>Security Group</th><th>Risk</th><th>Exposure Flags</th>"
        "<th>Attached Resources</th><th>Inbound Rules</th><th>Outbound Rules</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def _tab_internet_exposure(
    inventory: dict, sg_analysis: list[dict], internet_facing: list[dict],
) -> str:
    open_sg_rows = ""
    for sg in sg_analysis:
        dangerous = _dangerous_open_ports(sg)
        if not dangerous:
            continue
        risk  = str(sg.get("overall_risk", "info"))
        ports = "".join(
            f'<span class="chip" style="background:#FEF0F0;color:#C42626">'
            f'{"ALL" if p is None else p}/{svc}</span>'
            for p, svc in dangerous[:6])
        open_sg_rows += (
            f"<tr>"
            f"<td><code>{sg.get('security_group_id','')}</code><br>"
            f'<span style="color:var(--ig2);font-size:12px">{sg.get("security_group_name","")}</span></td>'
            f"<td>{_risk_badge(risk)}</td>"
            f"<td style='white-space:normal'>{ports}</td>"
            f"<td>{sg.get('attached_count',0)}</td>"
            f"</tr>")

    sgs_table = (
        '<div class="twrap"><table>'
        "<thead><tr><th>Security Group</th><th>Risk</th>"
        "<th>Dangerous Ports Open to Internet</th><th>Attached Resources</th></tr></thead>"
        f"<tbody>{open_sg_rows or '<tr><td colspan=\"4\" style=\"color:var(--ig2)\">'+'No SGs with dangerous open ports detected.</td></tr>'}</tbody>"
        "</table></div>")

    if_rows = "".join(
        f"<tr>"
        f"<td>{r.get('tags',{}).get('Name') or r.get('resource_name','—')}<br>"
        f'<span style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{r.get("resource_id","")}</span></td>'
        f"<td><span class='bdg info'>{r.get('resource_type','').split('::')[-1].upper()}</span></td>"
        f"<td>{r.get('region','—')}</td>"
        f"</tr>"
        for r in internet_facing)
    if_table = (
        '<div class="twrap"><table>'
        "<thead><tr><th>Resource</th><th>Type</th><th>Region</th></tr></thead>"
        f"<tbody>{if_rows or '<tr><td colspan=\"3\" style=\"color:var(--ig2)\">No internet-facing resources found.</td></tr>'}</tbody>"
        "</table></div>")

    pub_subs = [s for s in inventory.get("subnets", []) if s.get("subnet_type") == "public"]
    sub_rows = "".join(
        f"<tr><td>{_short(s, 36)}</td>"
        f"<td><code>{s.get('resource_id','')}</code></td>"
        f"<td><code>{s.get('cidr_block','')}</code></td>"
        f"<td>{s.get('availability_zone','')}</td></tr>"
        for s in pub_subs)
    pub_table = (
        '<div class="twrap"><table>'
        "<thead><tr><th>Subnet Name</th><th>ID</th><th>CIDR</th><th>AZ</th></tr></thead>"
        f"<tbody>{sub_rows or '<tr><td colspan=\"4\" style=\"color:var(--ig2)\">No public subnets found.</td></tr>'}</tbody>"
        "</table></div>")

    return (
        '<div class="sec-eyebrow">Internet Exposure</div>'
        '<div class="sec-title">Publicly Reachable Resources &amp; <strong>Open Ports</strong></div>'
        '<div class="sec-intro">Everything reachable from the public internet. '
        'Each entry is a potential attack surface — validate that every item is intentional, '
        'documented, and protected by a WAF or additional controls where appropriate.</div>'
        + _callout(
            f"<strong>{len(internet_facing)} resource(s) are reachable from the internet.</strong> "
            "Verify each one is intentional. Unexpected entries may indicate misconfigurations.",
            "alert" if internet_facing else "ok")
        + '<h3 class="blk">Security Groups with Dangerous Ports Open to 0.0.0.0/0</h3>'
        + sgs_table
        + f'<h3 class="blk">Internet-Facing Resources ({len(internet_facing)})</h3>'
        + if_table
        + f'<h3 class="blk">Public Subnets ({len(pub_subs)})</h3>'
        + pub_table
    )


def _tab_data_protection(inventory: dict) -> str:
    s3      = inventory.get("s3_buckets", [])
    kms     = inventory.get("kms", [])
    secrets = inventory.get("secrets", [])
    rds     = inventory.get("rds", [])

    s3_rows = ""
    for b in sorted(s3, key=lambda x: (not (x.get("acl_public") or x.get("bucket_policy_public")), x.get("resource_name",""))):
        exposed     = b.get("acl_public") or b.get("bucket_policy_public")
        all_blocked = all([b.get("block_public_acls"), b.get("block_public_policy"),
                           b.get("ignore_public_acls"), b.get("restrict_public_buckets")])
        s3_rows += (
            f"<tr>"
            f"<td>{b.get('resource_name','')}<br>"
            f'<span style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{b.get("region","")}</span></td>'
            f"<td><span class='chip' style='background:{'#FEF0F0' if exposed else '#EEFBF1'};color:{'#C42626' if exposed else '#1F7A35'}'>"
            f"{'PUBLIC' if exposed else 'Private'}</span></td>"
            f"<td>{_safe(all_blocked, 'Blocked', 'Not blocked')}</td>"
            f"<td><code>{b.get('encryption_type','—')}</code></td>"
            f"<td>{_safe(b.get('versioning_status') == 'Enabled', 'Enabled', b.get('versioning_status','Disabled'))}</td>"
            f"<td>{_safe(b.get('logging_enabled'))}</td>"
            f"</tr>")

    kms_cust = [k for k in kms if k.get("key_manager") == "CUSTOMER" and k.get("enabled")]
    kms_rows = "".join(
        f"<tr>"
        f"<td>{', '.join(k.get('aliases', [])) or k.get('resource_name','—')}<br>"
        f'<span style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{k.get("key_id","")}</span></td>'
        f"<td>{_safe(k.get('rotation_enabled'), 'Enabled', 'Disabled')}</td>"
        f"<td>{_safe(k.get('multi_region'), 'Multi-Region', 'Single-Region')}</td>"
        f"<td><code>{k.get('key_state','')}</code></td>"
        f"<td>{k.get('region','')}</td>"
        f"</tr>"
        for k in kms_cust)

    sec_rows = "".join(
        f"<tr>"
        f"<td>{s.get('resource_name','')}</td>"
        f"<td>{_safe(s.get('rotation_enabled'))}</td>"
        f"<td>{str(s.get('last_rotated_date','—'))[:10]}</td>"
        f"<td>{str(s.get('last_accessed_date','—'))[:10]}</td>"
        f"<td>{'<span class=\"chip\" style=\"background:#EEFBF1;color:#1F7A35\">Managed</span>' if s.get('owning_service') else '—'}</td>"
        f"</tr>"
        for s in sorted(secrets, key=lambda x: not x.get("rotation_enabled", False)))

    rds_rows = "".join(
        f"<tr>"
        f"<td>{db.get('resource_name','')}</td>"
        f"<td><code>{db.get('engine','')}</code></td>"
        f"<td>{_safe(db.get('storage_encrypted'), 'Encrypted', 'Not Encrypted')}</td>"
        f"<td>{db.get('backup_retention_period','—')} days</td>"
        f"<td>{db.get('region','')}</td>"
        f"</tr>"
        for db in sorted(rds, key=lambda x: not x.get("storage_encrypted", True)))

    def _tbl(cols: list[str], rows_html: str, empty: str) -> str:
        ths = "".join(f"<th>{c}</th>" for c in cols)
        return (
            '<div class="twrap"><table>'
            f"<thead><tr>{ths}</tr></thead>"
            f"<tbody>{rows_html or f'<tr><td colspan=\"{len(cols)}\" style=\"color:var(--ig2)\">{empty}</td></tr>'}</tbody>"
            "</table></div>")

    return (
        '<div class="sec-eyebrow">Data Protection</div>'
        '<div class="sec-title">Encryption &amp; <strong>Data Security Controls</strong></div>'
        '<div class="sec-intro">'
        'Encryption at rest, public data exposure, key rotation, and secret lifecycle management. '
        'These controls are required by SOC 2, ISO 27001, PCI-DSS and most data-protection regulations.'
        '</div>'
        + '<h3 class="blk">S3 Buckets</h3>'
        + _tbl(["Bucket", "Access", "Public Block", "Encryption", "Versioning", "Logging"], s3_rows, "No S3 buckets collected.")
        + f'<h3 class="blk">Customer-Managed KMS Keys ({len(kms_cust)})</h3>'
        + _tbl(["Key Alias / Name", "Auto-Rotation", "Scope", "State", "Region"], kms_rows, "No customer-managed KMS keys found.")
        + '<h3 class="blk">Secrets Manager</h3>'
        + _tbl(["Secret Name", "Auto-Rotation", "Last Rotated", "Last Accessed", "Managed By"], sec_rows, "No secrets collected.")
        + '<h3 class="blk">RDS Instances</h3>'
        + _tbl(["Instance / Cluster", "Engine", "Encryption", "Backup Retention", "Region"], rds_rows, "No RDS instances collected.")
    )


def _tab_iam_connectivity(inventory: dict) -> str:
    iam_roles = inventory.get("iam_roles", [])
    tgw_atts  = inventory.get("transit_gateway_attachments", [])
    peerings  = inventory.get("vpc_peerings", [])
    endpoints = inventory.get("vpc_endpoints", [])

    def _iam_sort(r: dict) -> tuple:
        return (len(r.get("trusted_accounts", [])) == 0, r.get("resource_name", ""))

    iam_rows = "".join(
        f"<tr>"
        f"<td>{r.get('resource_name','')}<br>"
        f'<span style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{(r.get("description","") or "")[:60] or "—"}</span></td>'
        f"<td>{''.join(_chip(s.split('.')[0], '#F0F4FF', '#21409A') for s in r.get('trusted_services',[])[:4])}</td>"
        f"<td>{''.join(_chip(a, '#FFF7EE', '#B86200') for a in r.get('trusted_accounts',[])[:4])}</td>"
        f"<td>{len(r.get('attached_policies',[]))} attached"
        + (f", {len(r.get('inline_policy_names', []))} inline" if r.get('inline_policy_names') else "")
        + "</td>"
        f"</tr>"
        for r in sorted(iam_roles, key=_iam_sort))

    tgw_rows = "".join(
        f"<tr>"
        f"<td><code>{att.get('transit_gateway_id','')}</code></td>"
        f"<td><code>{att.get('resource_id','')}</code></td>"
        f"<td><code>{att.get('resource_id_ref','')}</code></td>"
        f"<td>{att.get('state','')}</td>"
        f"</tr>"
        for att in tgw_atts)

    peer_rows = "".join(
        f"<tr>"
        f"<td><code>{p.get('resource_id','')}</code></td>"
        f"<td><code>{p.get('requester_vpc_info',{}).get('VpcId','')}</code> "
        f"<span style='font-size:11px;color:var(--ig2)'>{p.get('requester_vpc_info',{}).get('CidrBlock','')}</span></td>"
        f"<td><code>{p.get('accepter_vpc_info',{}).get('VpcId','')}</code> "
        f"<span style='font-size:11px;color:var(--ig2)'>{p.get('accepter_vpc_info',{}).get('CidrBlock','')}</span></td>"
        f"<td>{p.get('status','')}</td>"
        f"</tr>"
        for p in peerings)

    ep_rows = "".join(
        f"<tr>"
        f"<td>{ep.get('service_name','').split('.')[-1]}</td>"
        f"<td><code>{ep.get('service_name','')}</code></td>"
        f"<td>{ep.get('endpoint_type','')}</td>"
        f"<td><code>{ep.get('vpc_id','')}</code></td>"
        f"<td>{ep.get('state','')}</td>"
        f"</tr>"
        for ep in endpoints)

    def _tbl(cols: list[str], rows_html: str, empty: str) -> str:
        ths = "".join(f"<th>{c}</th>" for c in cols)
        return (
            '<div class="twrap"><table>'
            f"<thead><tr>{ths}</tr></thead>"
            f"<tbody>{rows_html or f'<tr><td colspan=\"{len(cols)}\" style=\"color:var(--ig2)\">{empty}</td></tr>'}</tbody>"
            "</table></div>")

    cross_account = [r for r in iam_roles if r.get("trusted_accounts")]
    return (
        '<div class="sec-eyebrow">Identity &amp; Connectivity</div>'
        '<div class="sec-title">IAM Roles &amp; <strong>Network Connectivity</strong></div>'
        '<div class="sec-intro">'
        'Identity access patterns and network connectivity paths. '
        'Cross-account IAM trusts and Transit Gateway connections define your blast radius '
        'in the event of a compromise. Validate every external trust is documented and justified.'
        '</div>'
        + (
            _callout(
                f"<strong>{len(cross_account)} IAM role(s) trust external AWS accounts.</strong> "
                "Validate these are expected and follow least-privilege principles.",
                "alert")
            if cross_account else ""
        )
        + f'<h3 class="blk">IAM Roles ({len(iam_roles)})</h3>'
        + _tbl(["Role Name", "Trusted Services", "Trusted Accounts", "Policies"], iam_rows, "No IAM roles collected.")
        + f'<h3 class="blk">Transit Gateway Attachments ({len(tgw_atts)})</h3>'
        + _tbl(["TGW ID", "Attachment ID", "VPC ID", "State"], tgw_rows, "No TGW attachments found.")
        + f'<h3 class="blk">VPC Peerings ({len(peerings)})</h3>'
        + _tbl(["Peering ID", "Requester VPC", "Accepter VPC", "Status"], peer_rows, "No VPC peerings found.")
        + f'<h3 class="blk">VPC Endpoints ({len(endpoints)})</h3>'
        + _tbl(["Service", "Full Service Name", "Type", "VPC", "State"], ep_rows, "No VPC endpoints found.")
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render_audit_report(
    inventory: dict[str, list[dict[str, Any]]],
    sg_analysis: list[dict[str, Any]],
    graph_summary: dict[str, Any],
    internet_facing: list[dict[str, Any]],
    output_path: Path,
    account_name: str = "",
) -> None:
    """
    Single-file audit report with 6 tabs:
      01 Dashboard · 02 Security Groups · 03 Internet Exposure
      04 Network Map · 05 Data Protection · 06 IAM & Access

    Designed for security auditors: shows findings, risk levels, and
    remediation context — not just raw inventory data.
    """
    risk_order = ["critical", "high", "medium", "low", "info"]
    counts = {r: sum(1 for a in sg_analysis if str(a.get("overall_risk")) == r) for r in risk_order}
    s3   = inventory.get("s3_buckets", [])
    ec2  = [i for i in inventory.get("ec2", []) if i.get("state") != "terminated"]

    hero_stats = [
        {"label": "Critical Findings", "value": counts["critical"],
         "mod": "alert" if counts["critical"] > 0 else "ok"},
        {"label": "High-Risk SGs",     "value": counts["high"],
         "mod": "warn" if counts["high"] > 0 else "ok"},
        {"label": "Internet-Facing",   "value": len(internet_facing),
         "mod": "alert" if internet_facing else "ok"},
        {"label": "S3 Buckets",        "value": len(s3)},
        {"label": "EC2 Instances",     "value": len(ec2)},
        {"label": "IAM Roles",         "value": len(inventory.get("iam_roles", []))},
    ]

    # Build SG indexes for the network map tab
    sg_risk_idx: dict[str, str] = {}
    sg_name_idx: dict[str, str] = {}
    for sg_a in sg_analysis:
        sid = sg_a.get("security_group_id", "")
        sg_risk_idx[sid] = str(sg_a.get("overall_risk", "info"))
        sg_name_idx[sid] = sg_a.get("security_group_name", sid)
    for sg in inventory.get("security_groups", []):
        sid = sg.get("resource_id", "")
        sg_name_idx.setdefault(sid, sg.get("resource_name") or sg.get("group_name") or sid)
        sg_risk_idx.setdefault(sid, "info")

    # Tab panels 1-3, 5-6
    p1 = _tab_dashboard(inventory, sg_analysis, internet_facing, account_name)
    p2 = _tab_security(sg_analysis)
    p3 = _tab_internet_exposure(inventory, sg_analysis, internet_facing)
    p5 = _tab_data_protection(inventory)
    p6 = _tab_iam_connectivity(inventory)

    # Tab 4 — Network Map (hierarchy, reuses existing logic)
    p4_header = (
        '<div class="sec-eyebrow">Network Topology</div>'
        '<div class="sec-title">Network Map &middot; <strong>Full Hierarchy</strong></div>'
        '<div class="sec-intro">'
        'VPC &rarr; AZ &rarr; Subnet &rarr; Resource &rarr; Security Groups. '
        'Use this view to trace network paths, validate segmentation, and verify '
        'that sensitive resources are in private or isolated subnets.'
        '</div>'
    )

    type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
    _sub_bg  = {"pub": "#EEFBF1", "priv": "#FFF7EE", "iso": "#FEF0F0", "unk": "#F8F9FA"}
    _sub_txt = {"pub": "#1F7A35", "priv": "#B86200", "iso": "#C42626", "unk": "#808599"}

    # Build all indexes needed for the hierarchy
    subs_by_vpc: dict[str, list] = {}
    for s in inventory.get("subnets", []):
        subs_by_vpc.setdefault(s.get("vpc_id",""), []).append(s)
    ec2_by_sub: dict[str, list] = {}
    for i in ec2:
        ec2_by_sub.setdefault(i.get("subnet_id",""), []).append(i)
    lb_by_sub: dict[str, list] = {}
    _lb_s: dict[str, set] = {}
    for lb in inventory.get("load_balancers",[]):
        for az in lb.get("availability_zones",[]):
            sid = az.get("SubnetId","")
            if sid and lb["resource_id"] not in _lb_s.get(sid, set()):
                _lb_s.setdefault(sid, set()).add(lb["resource_id"])
                lb_by_sub.setdefault(sid, []).append(lb)
    nat_by_sub: dict[str, list] = {}
    for nat in inventory.get("nat_gateways",[]):
        nat_by_sub.setdefault(nat.get("subnet_id",""), []).append(nat)
    ep_by_sub: dict[str, list] = {}
    for ep in inventory.get("vpc_endpoints",[]):
        for sid in ep.get("associated_subnet_ids",[]):
            ep_by_sub.setdefault(sid, []).append(ep)
    lambda_by_sub: dict[str, list] = {}
    for fn in inventory.get("lambdas",[]):
        for sid in fn.get("subnet_ids",[]):
            lambda_by_sub.setdefault(sid, []).append(fn)
    rds_by_sub: dict[str, list] = {}
    for db in inventory.get("rds",[]):
        for sid in db.get("subnet_ids",[]):
            rds_by_sub.setdefault(sid, []).append(db)
    igw_by_vpc: dict[str, list] = {}
    for igw in inventory.get("internet_gateways",[]):
        for vid in igw.get("attached_vpc_ids",[]):
            igw_by_vpc.setdefault(vid, []).append(igw)
    tgw_by_vpc: dict[str, list] = {}
    for att in inventory.get("transit_gateway_attachments",[]):
        vid = att.get("resource_id_ref","")
        if vid:
            tgw_by_vpc.setdefault(vid, []).append(att)
    eks_cls = [e for e in inventory.get("eks",[]) if e.get("resource_type") == "aws::eks::cluster"]
    eks_ngs = [e for e in inventory.get("eks",[]) if e.get("resource_type") == "aws::eks::nodegroup"]
    eks_by_vpc: dict[str, list] = {}
    for cl in eks_cls:
        eks_by_vpc.setdefault(cl.get("vpc_id",""), []).append(cl)
    ng_by_sub: dict[str, list] = {}
    for ng in eks_ngs:
        for sid in ng.get("subnet_ids",[]):
            ng_by_sub.setdefault(sid, []).append(ng)
    sgs_by_vpc: dict[str, list] = {}
    for sg in inventory.get("security_groups",[]):
        sgs_by_vpc.setdefault(sg.get("vpc_id",""), []).append(sg)
    attached_sg_ids: set[str] = set()
    for rl in [ec2, inventory.get("load_balancers",[]),
               inventory.get("lambdas",[]), inventory.get("rds",[]), eks_cls]:
        for r in rl:
            for sid in (r.get("security_group_ids") or []):
                if sid:
                    attached_sg_ids.add(sid)

    vpc_html_parts = [p4_header]
    for vpc in inventory.get("vpcs", []):
        vid   = vpc["resource_id"]
        vname = _short(vpc, 56)
        vcidr = vpc.get("cidr_block", "")
        hdr = (
            f'<span class="hvpc-name">{vname}</span>'
            f'<code style="font-family:var(--fm);font-size:11px;color:var(--ig2)">{vid}</code>'
            f'<code style="font-family:var(--fm);font-size:12px;color:var(--ib);margin-left:2px">{vcidr}</code>'
        )
        global_items = "".join(
            _chip(f"IGW · {_short(igw, 28)}", "#F0F4FF", "#21409A")
            for igw in igw_by_vpc.get(vid, [])
        ) + "".join(
            _chip(f"TGW · {att.get('transit_gateway_id','?')}",
                  "#EEFBF1" if att.get("state") == "available" else "#FFF7EE",
                  "#1F7A35" if att.get("state") == "available" else "#B86200")
            for att in tgw_by_vpc.get(vid, [])
        )
        eks_rows_h = "".join(
            f'<div style="margin-top:5px;width:100%">'
            + _h_resource("eks", _short(cl, 32), cl.get("version",""),
                _sg_inline(cl.get("security_group_ids",[]), sg_risk_idx, sg_name_idx),
                '<div style="margin-top:3px">' + _chip("Node Groups:","#F0F4FF","#21409A")
                + "".join(_chip(ng.get("nodegroup_name","NG")[:18],"#D8F3DE","#1F7A35")
                          for ng in eks_ngs if ng.get("cluster_name") == cl.get("cluster_name"))
                + "</div>")
            + "</div>"
            for cl in eks_by_vpc.get(vid, [])
        )
        g_sec = (
            f'<div class="hvpc-global"><span class="hvpc-global-lbl">VPC Resources:</span>'
            f"{global_items}{eks_rows_h}</div>"
        ) if (global_items or eks_rows_h) else ""

        az_map: dict[str, list] = {}
        for s in subs_by_vpc.get(vid, []):
            az_map.setdefault(s.get("availability_zone","?"), []).append(s)
        az_cols = ""
        for az_name in sorted(az_map.keys()):
            sub_tiles = ""
            for sub in sorted(az_map[az_name],
                              key=lambda s: type_order.get(s.get("subnet_type","unknown"), 3)):
                sid   = sub["resource_id"]
                stype = sub.get("subnet_type","unknown")
                scls  = SUBNET_META.get(stype, SUBNET_META["unknown"])["cls"]
                type_chip = _chip(SUBNET_META.get(stype, SUBNET_META["unknown"])["label"],
                                  _sub_bg[scls], _sub_txt[scls])
                res_rows = ""
                for inst in ec2_by_sub.get(sid,[]):
                    res_rows += _h_resource("ec2", _short(inst,30),
                        " · ".join(filter(None,[inst.get("instance_type",""), inst.get("private_ip","")])),
                        _sg_inline(inst.get("security_group_ids",[]), sg_risk_idx, sg_name_idx))
                for lb in lb_by_sub.get(sid,[]):
                    lb_t = "alb" if lb.get("type") == "application" else "nlb"
                    res_rows += _h_resource(lb_t, _short(lb,30), lb.get("scheme",""),
                        _sg_inline(lb.get("security_group_ids",[]), sg_risk_idx, sg_name_idx))
                for nat in nat_by_sub.get(sid,[]):
                    res_rows += _h_resource("nat", _short(nat,30), nat.get("state",""), "")
                for ep in ep_by_sub.get(sid,[]):
                    res_rows += _h_resource("vpce", ep.get("service_name","").split(".")[-1],
                        ep.get("endpoint_type",""), "")
                for fn in lambda_by_sub.get(sid,[]):
                    res_rows += _h_resource("lambda", _short(fn,30), fn.get("runtime",""),
                        _sg_inline(fn.get("security_group_ids",[]), sg_risk_idx, sg_name_idx))
                _seen_r: set[str] = set()
                for db in rds_by_sub.get(sid,[]):
                    if db["resource_id"] in _seen_r: continue
                    _seen_r.add(db["resource_id"])
                    res_rows += _h_resource("rds", _short(db,30), db.get("engine",""),
                        _sg_inline(db.get("security_group_ids",[]), sg_risk_idx, sg_name_idx))
                _seen_ng: set[str] = set()
                for ng in ng_by_sub.get(sid,[]):
                    if ng["resource_id"] in _seen_ng: continue
                    _seen_ng.add(ng["resource_id"])
                    res_rows += _h_resource("eks",
                        ng.get("nodegroup_name") or _short(ng,28),
                        " · ".join(filter(None,[", ".join(ng.get("instance_types",[])[:2]),
                            f"desired: {ng.get('desired_size','')}" if ng.get('desired_size') != '' else ""])), "")
                sub_tiles += (
                    f'<div class="hsub {scls}"><div class="hsub-hdr">'
                    f'<span class="hsub-name">{_short(sub,34)}</span>'
                    f'<span class="hsub-cidr">{sub.get("cidr_block","")}</span>{type_chip}</div>'
                    f'<div class="hres-list">'
                    + (res_rows or '<div class="hres-empty">empty</div>')
                    + "</div></div>")
            az_cols += f'<div class="haz"><div class="haz-label">{az_name}</div>{sub_tiles}</div>'

        vpc_sg_set = {sg.get("resource_id","") for sg in sgs_by_vpc.get(vid,[])}
        loose = vpc_sg_set - attached_sg_ids
        loose_html = ""
        if loose:
            badges = "".join(
                f'<span class="sg-ref {sg_risk_idx.get(sid,"info")}" title="{sid}">'
                f'{sg_name_idx.get(sid,sid)[:26]}</span> '
                for sid in sorted(loose))
            loose_html = (
                f'<div class="loose-sgs"><div class="loose-sgs-lbl">'
                f'Unattached Security Groups ({len(loose)})</div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:4px">{badges}</div></div>')

        vpc_html_parts.append(
            f'<div class="hvpc"><div class="hvpc-hdr">{hdr}</div>'
            f"{g_sec}"
            f'<div class="haz-group">{az_cols}</div>'
            f"{loose_html}</div>")

    p4 = "".join(vpc_html_parts)

    # Assemble tabbed page
    body = (
        f'<div class="panel" id="p1">{p1}</div>'
        f'<div class="panel" id="p2">{p2}</div>'
        f'<div class="panel" id="p3">{p3}</div>'
        f'<div class="panel" id="p4">{p4}</div>'
        f'<div class="panel" id="p5">{p5}</div>'
        f'<div class="panel" id="p6">{p6}</div>'
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _html_page(
            title=f"AWS Audit Report — {account_name}",
            body=body,
            account_name=account_name,
            extra_css=_HIER_CSS,
            hero_stats=hero_stats,
            hero_title=f"AWS Security Audit &middot; <strong>{account_name}</strong>",
            hero_sub=(
                "Consolidated infrastructure audit report. "
                "Review tabs in order: Dashboard → Security → Internet Exposure → Network Map → Data Protection → IAM."
            ),
            hero_eyebrow=f"Security Audit &middot; {account_name}",
            tabs=[
                "Dashboard",
                "Security Groups",
                "Internet Exposure",
                "Network Map",
                "Data Protection",
                "IAM & Access",
            ],
        ),
        encoding="utf-8",
    )
