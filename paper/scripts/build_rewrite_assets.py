from pathlib import Path
import csv
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab
pdfmetrics.registerFont(TTFont("FigureSans", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
from reportlab.lib.colors import HexColor, white
P=Path(__file__).resolve().parent.parent
rows=list(csv.DictReader((P/'rewrite_plan/PASS_A_RESULTS_TABLES.csv').open()))[:8]
# Printed contrasts are display-rounding of retained estimates, never recomputed.
lines=[r'\begin{table*}[t]',r'\centering',r'\caption{Completed-study overview. Family counts describe linked original actions; GitHub has 63 not-executed pairs and 64 already-executed pairs. Sheets denotes the separate replication after the implementation fix.}',r'\label{tab:overview}',r'\begin{tabularx}{\textwidth}{@{}lXX Xr@{}}',r'\toprule',r'Study & Environment & Full model (Fireworks) & Purpose & Families \\',r'\midrule',r'Study 1A & Controlled ticket creation & DeepSeek V4 Flash (0731) & Primary controlled experiment & 160 \\',r'Study 1B & Controlled ticket creation & DeepSeek V4.1 Flash & Model-transition replication & 160 \\',r'Study 2: GitHub & External issue creation & DeepSeek V4.1 Flash & Descriptive external validation & 64 \\',r'Study 2: Sheets & External row append & DeepSeek V4.1 Flash & Separate external replication & 64 \\',r'\bottomrule',r'\end{tabularx}',r'\end{table*}']
(P/'tables/passb_overview.tex').write_text('\n'.join(lines)+'\n')
lines=[r'\begin{table*}[t]',r'\centering',r'\caption{Core final-state correctness. Counts use matched pairs in each execution situation. Differences and two-sided 95\% paired Newcombe method 10 intervals are in percentage points (pp), displayed to one decimal.}',r'\label{tab:results}',r'\begin{tabular}{@{}llrrrr@{}}',r'\toprule',r'Study & Execution situation & Matched $N$ & Replay correct & Regeneration correct & Difference [95\% CI] \\',r'\midrule']
for i,r in enumerate(rows):
    name={'Google Sheets replication':'Sheets replication'}.get(r['study'],r['study'])
    world='$H_0$' if r['world']=='H0' else '$H_1$'
    d,lo,hi=[float(r[k]) for k in ['difference_Replay_minus_Regeneration_pp','paired_CI_lower_pp','paired_CI_upper_pp']]
    lines.append(f"{name} & {world} & {r['N_pairs']} & {r['Replay_correct']}/{r['N_pairs']} & {r['Regeneration_correct']}/{r['N_pairs']} & {d:+.1f} [{lo:.1f}, {hi:.1f}]"+r' \\')
    if i%2 and i<7:lines.append(r'\addlinespace')
lines += [r'\bottomrule',r'\end{tabular}',r'\par\smallskip\raggedright $H_0$: Original action did not execute. $H_1$: Executed, acknowledgement lost. Difference = Replay minus Regeneration. GitHub has four missing Regeneration effects among 64 evaluable $H_0$ arms; three enter its 63 matched pairs. External intervals are descriptive. Perfect scores do not imply zero population risk; post-hoc marginal intervals are in the public artifact repository.',r'\end{table*}']
(P/'tables/passb_results.tex').write_text('\n'.join(lines)+'\n')

# Vector presentation figures, using retained numbers only.
def text(c,x,y,lines,size=10,align='center',leading=13):
    c.setFont('FigureSans',size)
    ls=lines.split('\n')
    for i,line in enumerate(ls):
        yy=y+(len(ls)-1)*leading/2-i*leading
        {'center':c.drawCentredString,'left':c.drawString,'right':c.drawRightString}[align](x,yy,line)
def box(c,x,y,w,h,label,color='#eef2f7'):
    c.setFillColor(HexColor(color));c.setStrokeColor(HexColor('#506076'));c.setLineWidth(.8)
    c.roundRect(x,y,w,h,6,fill=1,stroke=1);c.setFillColor(HexColor('#17273a'));text(c,x+w/2,y+h/2-3,label)
def arrow(c,a,b):
    from math import atan2,cos,sin,pi
    c.setStrokeColor(HexColor('#506076'));c.setFillColor(HexColor('#506076'));c.setLineWidth(.8)
    c.line(*a,*b);theta=atan2(b[1]-a[1],b[0]-a[0]);p=c.beginPath();p.moveTo(*b)
    for t in [theta+2.65,theta-2.65]:p.lineTo(b[0]+6*cos(t),b[1]+6*sin(t))
    p.close();c.drawPath(p,fill=1,stroke=0)
c=canvas.Canvas(str(P/'figures/passb_concept.pdf'),pagesize=(511,246),pageCompression=1,initialFontName='FigureSans')
box(c,2,200,107,43,'Original create\nrequest stored')
box(c,146,200,135,43,'Timeout: outcome\nunknown to agent','#fff0cc');arrow(c,(109,221),(142,221))
text(c,403,221,'Same action and ambiguity\nfor both policies',10)
# A branching connector stays entirely outside both state labels.
c.setStrokeColor(HexColor('#506076'));c.setLineWidth(.8)
c.line(214,200,214,185);c.line(111,185,399,185)
arrow(c,(111,185),(111,175));arrow(c,(399,185),(399,175))
box(c,2,125,218,46,'Original action did not execute\nNo intended effect exists')
box(c,290,125,218,46,'Executed, acknowledgement lost\nOne intended effect exists')
box(c,2,51,183,46,'Exact Replay\nSend stored request','#e7effc')
box(c,325,51,183,46,'LLM Regeneration\nRead, write, or stop','#e4f1ed')
for x in [111,399]:
    for xx in [94,417]:arrow(c,(x,123),(xx,101))
arrow(c,(94,49),(217,25));arrow(c,(417,49),(293,25))
c.setFillColor(HexColor('#17273a'))
text(c,255,10,'Score final state: exactly one intended effect and no unintended effects',10)
c.showPage();c.save()
c=canvas.Canvas(str(P/'figures/passb_completed_results.pdf'),pagesize=(511,190),pageCompression=1,initialFontName='FigureSans')
for k in range(2):
    left=132+k*190;right=left+175;bottom=40;top=140
    color=HexColor(['#245487','#147a63'][k])
    text(c,(left+right)/2,170,['Original action\ndid not execute','Executed,\nacknowledgement lost'][k],11)
    def xx(v):return left+(v+105)/125*(right-left)
    for tick in [-100,-50,0]:
        c.setStrokeColor(HexColor('#e0e3e6'));c.setLineWidth(.6);c.line(xx(tick),bottom,xx(tick),top)
        c.setFillColor(HexColor('#17273a'));text(c,xx(tick),26,str(tick),9)
    c.setStrokeColor(HexColor('#8993a0'));c.line(left,bottom,right,bottom)
    for i,r in enumerate(rows[k::2]):
        y=top-10-i*27
        if k==0:
            c.setFillColor(HexColor('#17273a'));text(c,121,y-3,['Study 1A','Study 1B','GitHub','Sheets replication'][i],10,'right')
        v,lo,hi=[float(r[t]) for t in ['difference_Replay_minus_Regeneration_pp','paired_CI_lower_pp','paired_CI_upper_pp']]
        c.setStrokeColor(color);c.setFillColor(color);c.setLineWidth(1.3);c.line(xx(lo),y,xx(hi),y)
        for h in [lo,hi]:c.line(xx(h),y-3,xx(h),y+3)
        c.circle(xx(v),y,3,fill=1,stroke=0)
c.setFillColor(HexColor('#17273a'));text(c,255,7,'Paired difference: Replay minus Regeneration (percentage points)',10)
c.showPage();c.save()
for name,asset,caption in [('figure1','passb_concept','An ambiguous timeout hides whether the original create happened. Each hidden situation is evaluated under both recovery policies using the same stored original semantic action in isolated state. Arrows show experimental comparisons, not their probabilities. Regeneration may inspect state; it is not forced to do so.'),('figure2','passb_completed_results','The policy contrast depends on hidden execution state. Points show Replay-minus-Regeneration correctness differences; bars are the retained 95\\% paired intervals, not marginal success intervals. External results are descriptive. GitHub uses 63 not-executed pairs and 64 already-executed pairs; the invalid first Sheets attempt and incomplete Razorpay collections are excluded. Counts appear in Table \\ref{tab:results}.')]:
    (P/f'figures/{name}.tex').write_text('\\begin{figure*}[t]\n\\centering\n\\includegraphics[width=\\textwidth]{figures/'+asset+'.pdf}\n\\caption{'+caption+'}\n\\label{fig:'+name+'}\n\\end{figure*}\n')
print('Generated 2 presentation figures and 2 main tables from stored data.')
