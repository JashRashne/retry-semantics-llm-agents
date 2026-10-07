from pathlib import Path
import csv
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import reportlab
pdfmetrics.registerFont(TTFont("FigureSans", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
from reportlab.lib.colors import HexColor, white
P=Path(__file__).resolve().parent.parent
def read_baseline_cells(path):
    """Read Success/Evaluable from the audited record; reject malformed strata."""
    record=path.read_text()
    heading='## No-model results\n'
    if record.count(heading)!=1:
        raise ValueError(f'{path}: expected one No-model results section')
    section=record.split(heading,1)[1].split('\n## ',1)[0]
    table=[line.strip() for line in section.splitlines() if line.strip().startswith('|')]
    headers=['Study','World','Scheduled','Evaluable','Success','Failure','UNKNOWN',
             'Effect already visible','Stored CREATE dispatched']
    def fields(line):
        if not line.endswith('|'):
            raise ValueError(f'{path}: incomplete baseline table row')
        return [cell.strip() for cell in line[1:-1].split('|')]
    if len(table)!=10 or fields(table[0])!=headers:
        raise ValueError(f'{path}: expected the nine-column, eight-stratum results table')
    separators=fields(table[1])
    if len(separators)!=len(headers) or any(cell.strip(':')!='---' for cell in separators):
        raise ValueError(f'{path}: invalid baseline table separator')
    study_names={'Study 1A':'Study 1A','Study 1B':'Study 1B','GitHub':'GitHub',
                 'Sheets valid replication':'Google Sheets replication'}
    expected={(study,world) for study in study_names.values() for world in ('H0','H1')}
    cells={}
    for line in table[2:]:
        row=fields(line)
        if len(row)!=len(headers) or row[0] not in study_names or row[1] not in ('H0','H1'):
            raise ValueError(f'{path}: unexpected baseline stratum: {row}')
        key=(study_names[row[0]],row[1])
        if key in cells or any(not value.isascii() or not value.isdecimal() for value in row[2:]):
            raise ValueError(f'{path}: duplicate stratum or invalid counts: {row}')
        scheduled,evaluable,success,failure,unknown,visible,dispatched=map(int,row[2:])
        if (evaluable<=0 or scheduled!=evaluable+unknown or evaluable!=success+failure
                or scheduled!=visible+dispatched):
            raise ValueError(f'{path}: inconsistent baseline counts: {row}')
        cells[key]=(success,evaluable)
    if set(cells)!=expected:
        raise ValueError(f'{path}: incomplete baseline strata')
    return cells

baseline_cells=read_baseline_cells(P.parent/'research/baselines/no_model/RESULTS.md')
rows=list(csv.DictReader((P/'rewrite_plan/PASS_A_RESULTS_TABLES.csv').open()))[:8]
# Completed-study overview; matched families remain distinct from reference cohorts.
lines=[r'\begin{table*}[t]',r'\centering',r'\caption{Completed-study overview. The model studies use two hosted versions of one DeepSeek family; all requested reasoning effort none. Family counts describe linked original actions; GitHub has 63 not-executed pairs and 64 already-executed pairs. Sheets denotes the valid fresh replication; the invalid first collection is documented in the supplement.}',r'\label{tab:overview}',r'\begin{tabularx}{\textwidth}{@{}lXX Xr@{}}',r'\toprule',r'Study & Environment & Full model (Fireworks) & Purpose & Families \\',r'\midrule',r'Study 1A & Controlled ticket creation & DeepSeek V4 Flash (0731) & Primary controlled experiment & 160 \\',r'Study 1B & Controlled ticket creation & DeepSeek V4.1 Flash & Model-transition replication & 160 \\',r'Study 2: GitHub & External issue creation & DeepSeek V4.1 Flash & Descriptive external validation & 64 \\',r'Study 2: Sheets & External row append & DeepSeek V4.1 Flash & Separate external replication & 64 \\',r'\bottomrule',r'\end{tabularx}',r'\end{table*}']
(P/'tables/passb_overview.tex').write_text('\n'.join(lines)+'\n')
# Main results use stored final-state counts, without recomputing estimators.
lines = [
    r'\begin{table}[t]', r'\centering', r'\small',
    r'\setlength{\tabcolsep}{3pt}',
    r'\caption{Final-state correctness (correct/evaluable). Replay is the semantic reference for unconditional redispatch. The deterministic verify-before-retry reference uses separately evaluated reference cohorts.}',
    r'\label{tab:results}',
    r'\begin{tabularx}{\columnwidth}{@{}lcrr|>{\centering\arraybackslash}X@{}}',
    r'\toprule',
    r' & & \multicolumn{2}{c|}{Matched comparison} & \shortstack{Separate frozen\\cohorts} \\',
    r'\cmidrule(lr){3-4}\cmidrule(l){5-5}',
    r'Study & World & Replay & \shortstack{Regen-\\eration} & \shortstack{Deterministic\\reference} \\',
    r'\midrule',
]
for i, row in enumerate(rows):
    name = {'Google Sheets replication': 'Sheets'}.get(row['study'], row['study'])
    world = {'H0': 'NE', 'H1': 'AE'}[row['world']]
    success, evaluable = baseline_cells[(row['study'], row['world'])]
    lines.append(f"{name} & {world} & {row['Replay_correct']}/{row['N_pairs']} & "
                 f"{row['Regeneration_correct']}/{row['N_pairs']} & {success}/{evaluable}" + r' \\')
    if i % 2 and i < 7:
        lines.append(r'\addlinespace')
lines += [r'\bottomrule', r'\end{tabularx}',
          r'\par\smallskip\raggedright GitHub NE: Replay/Regeneration use 63 matched pairs; one Replay outcome is unknown. Regeneration is 60/64 over all evaluable NE arms. The reference independently evaluates 64/64. Sheets denotes the valid replication.',
          r'\end{table}']
(P/'tables/passb_results.tex').write_text('\n'.join(lines)+'\n')

# Read archived path counts. No raw evidence, study outcomes, or statistics change.
evidence = (P/'rewrite_plan/PASS_A_EVIDENCE_REPORT.md').read_text()
paths = {}
for line in evidence.splitlines():
    fields = [s.strip() for s in line.strip().strip('|').split('|')]
    if len(fields) == 5 and fields[:2] == ['Study 1A', 'H1']:
        paths[fields[2]] = int(fields[3])
read_stop = paths['list_tickets -> MODEL_STOP']
write_read_stop = paths['create_ticket -> list_tickets -> MODEL_STOP']
write_stop = paths['create_ticket -> MODEL_STOP']
github = []
for line in evidence.splitlines():
    fields = [s.strip() for s in line.strip().strip('|').split('|')]
    if len(fields) == 8 and fields[0].startswith('gh-f'):
        github.append(fields)
no_write = sum(int(row[2]) == 0 for row in github)
failed_writes = sum(int(row[2]) == 1 and row[3] == '504' for row in github)
github_correct = int(next(row for row in rows if row['study']=='GitHub' and row['world']=='H0')['Regeneration_correct'])
github_evaluable = github_correct + len(github)
ne = sum(evaluable for (study, world), (success, evaluable) in baseline_cells.items() if world=='H0')
ae = sum(evaluable for (study, world), (success, evaluable) in baseline_cells.items() if world=='H1')
reference_total = ne + ae
reference_correct = sum(success for success, evaluable in baseline_cells.values())
if (read_stop, write_read_stop, write_stop, no_write, failed_writes,
        github_correct, github_evaluable, ne, ae, reference_correct, reference_total) != (
        151, 5, 4, 3, 1, 60, 64, 448, 448, 896, 896):
    raise ValueError('Stored recovery paths differ from the audited presentation counts')
if any(row[1] != '2' or not row[5].startswith('0 intended effects') for row in github):
    raise ValueError('Unexpected GitHub missing-effect trace')

# Deterministic vector output makes rerunning the presentation generator stable.
font_dir = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('FigureBold', str(font_dir/'VeraBd.ttf')))
INK = '#17273a'
EDGE = '#657488'
BLUE = '#e7effc'
GREEN = '#e4f1ed'
AMBER = '#fff0cc'
RED = '#fbe9e7'
def text(c, x, y, label, size=9, align='center', leading=12, bold=False):
    c.setFillColor(HexColor(INK))
    c.setFont('FigureBold' if bold else 'FigureSans', size)
    lines = label.split('\n')
    for i, line in enumerate(lines):
        yy = y + (len(lines)-1)*leading/2 - i*leading
        {'center': c.drawCentredString, 'left': c.drawString, 'right': c.drawRightString}[align](x, yy, line)
def box(c, x, y, w, h, label, color='#f7f9fc', size=9, bold=False):
    c.setFillColor(HexColor(color)); c.setStrokeColor(HexColor(EDGE)); c.setLineWidth(.7)
    c.roundRect(x,y,w,h,4,fill=1,stroke=1)
    text(c,x+w/2,y+h/2-2,label,size,leading=12,bold=bold)
def frame(c,x,y,w,h,dashed=False):
    c.setStrokeColor(HexColor(EDGE)); c.setLineWidth(.8)
    c.setDash(3,2) if dashed else c.setDash()
    c.roundRect(x,y,w,h,5,fill=0,stroke=1); c.setDash()
def arrow(c,a,b,dashed=False):
    from math import atan2,cos,sin
    c.setStrokeColor(HexColor(EDGE)); c.setFillColor(HexColor(EDGE)); c.setLineWidth(.7)
    c.setDash(3,2) if dashed else c.setDash()
    c.line(*a,*b); c.setDash()
    theta=atan2(b[1]-a[1],b[0]-a[0]); p=c.beginPath();p.moveTo(*b)
    for t in [theta+2.65,theta-2.65]:p.lineTo(b[0]+4*cos(t),b[1]+4*sin(t))
    p.close();c.drawPath(p,fill=1,stroke=0)
def pdf(name,size):
    return canvas.Canvas(str(P/'figures'/name),pagesize=size,pageCompression=1,
                         initialFontName='FigureSans',invariant=1)

# Figure 1 is designed at one IEEE column's native width.
c=pdf('passb_concept.pdf',(252,390))
box(c,51,353,150,33,'Stored correct CREATE',BLUE)
arrow(c,(126,353),(126,339))
box(c,51,306,150,33,'Ambiguous outcome: NE / AE',AMBER,size=8.5)
arrow(c,(126,306),(126,289))
frame(c,2,191,248,95)
text(c,126,273,'Matched Replay / Regeneration',9,bold=True)
box(c,9,206,108,49,'Exact Replay\nStored CREATE\nredispatched once',BLUE,size=8.5)
box(c,135,206,108,49,'LLM Regeneration\nObserve / write / stop\nunder bounded budget',GREEN,size=8.5)
c.setStrokeColor(HexColor(EDGE));c.line(63,262,189,262)
arrow(c,(63,262),(63,255));arrow(c,(189,262),(189,255))
# A separate dashed conceptual link and frame denote a separate evaluation.
arrow(c,(201,322),(247,322),dashed=True)
c.setStrokeColor(HexColor(EDGE));c.setDash(3,2);c.line(247,322,247,179);c.setDash()
frame(c,2,28,248,151,dashed=True)
text(c,126,165,'Separate frozen cohorts',9,bold=True)
text(c,126,149,'Deterministic verify-before-retry reference',8.5)
box(c,82,115,88,23,'Read once',GREEN,size=8.5)
# Three distinct branches; unusable observations were not exercised.
c.setStrokeColor(HexColor(EDGE));c.line(9,126,9,43)
arrow(c,(82,126),(9,126))
for y in [101,81,52]:arrow(c,(9,y),(16,y))
text(c,21,98,'Exact intended effect visible -> STOP',8,align='left')
text(c,21,78,'Effect absent -> stored CREATE once -> STOP',7.7,align='left')
text(c,21,55,'Observation unusable -> STOP',8,align='left')
text(c,21,42,'[Untested in the 896-case collection]',8,align='left')
text(c,126,10,'Request fidelity | Effect evidence | Mutation authorization',8)
c.showPage();c.save()

# Figure 2: observed paths, with no cross-panel pairing or comparative arrows.
c=pdf('passb_completed_results.pdf',(511,242))
for x in [1,174,347]:
    frame(c,x,24,163,215,dashed=(x==347))
text(c,82,221,'Study 1A | AE',10,bold=True)
text(c,82,205,'LLM Regeneration',9)
text(c,82,188,f'{read_stop+write_read_stop+write_stop} opportunities',9)
box(c,9,137,147,36,f'{read_stop} read -> STOP\nFinal state correct',GREEN)
box(c,9,82,147,36,f'{write_read_stop+write_stop} write first\nDuplicate ticket',RED)
c.setStrokeColor(HexColor(EDGE));c.line(5,180,5,100)
for y in [155,100]:arrow(c,(5,y),(9,y))
text(c,17,65,f'{write_read_stop} write -> read -> STOP',8.5,align='left')
text(c,17,45,f'{write_stop} write -> STOP',8.5,align='left')

text(c,255,221,'GitHub | NE',10,bold=True)
text(c,255,205,'LLM Regeneration',9)
text(c,255,188,f'{github_evaluable} evaluable arms',9)
box(c,182,149,147,25,f'{github_correct} final-state correct',GREEN)
box(c,182,97,147,40,f'{no_write} read -> read -> STOP\nNo write attempted\nRequired issue missing',RED,size=8.5)
box(c,182,35,147,50,f'{failed_writes} read -> read -> write\nCorrect write attempted\nHTTP 504; issue missing',AMBER,size=8.5)
# Branching counts: neither failures nor successes follow one another.
c.setStrokeColor(HexColor(EDGE));c.line(178,180,178,60)
for y in [162,117,60]:arrow(c,(178,y),(182,y))

text(c,429,221,'Separate frozen cohorts',9,bold=True)
text(c,429,202,'Deterministic reference',9,bold=True)
text(c,429,186,'Verify-before-retry',9)
box(c,355,126,147,42,f'{ne} NE: read absent\nStored CREATE once\nSTOP',GREEN,size=8.5)
box(c,355,75,147,36,f'{ae} AE: read effect visible\nSTOP; no recovery write',GREEN,size=8.5)
text(c,429,56,f'{reference_correct}/{reference_total} final-state correct',9,bold=True)
text(c,429,40,'All decision reads usable',8.5)
text(c,429,27,'Zero recovery model calls',8)
text(c,255,8,'Model-case paths and reference paths come from separate evaluations.',9)
c.showPage();c.save()

figures=[
    ('figure1','passb_concept','figure',r'Three controllers after an ambiguous stored CREATE. The solid panel is the matched comparison; the dashed panel is the separately evaluated deterministic verify-before-retry reference. The unusable-observation STOP branch was not exercised in the 896-case reference collection. Stored-request fidelity, effect evidence, and mutation authorization are the analytical lens.'),
    ('figure2','passb_completed_results','figure*',r'Observed recovery paths. Study 1A AE failures wrote before reading. GitHub NE separates stops without a write from a correct write attempt followed by HTTP 504. The deterministic reference uses separately evaluated reference cohorts, with zero recovery model calls; its successful writes do not establish resilience to the same transport failure.'),
]
for name,asset,environment,caption in figures:
    width=r'\columnwidth' if environment=='figure' else r'\textwidth'
    (P/f'figures/{name}.tex').write_text(
        '\\begin{'+environment+'}[t]\n\\centering\n'
        '\\includegraphics[width='+width+']{figures/'+asset+'.pdf}\n'
        '\\caption{'+caption+'}\n\\label{fig:'+name+'}\n\\end{'+environment+'}\n')
print('Generated count table and two recovery-control figures from stored evidence; no statistics recomputed.')
