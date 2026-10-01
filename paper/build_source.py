#!/usr/bin/env python3
"""Render canonical Markdown + approved publication data into IEEEtran LaTeX.
Only presentation: no statistics, evidence collection, network or input mutation.
"""
from pathlib import Path
import re,json,hashlib
P=Path(__file__).resolve().parent
TABLES=json.loads((P/'publication_data/TABLE_CATALOG.json').read_text())
CAPTIONS=json.loads((P/'publication_data/CAPTIONS.json').read_text())
# Layout weights only: all quantitative strings/rows originate in frozen catalog.
WEIGHTS={
 'table1_environments':[1.25,1.3,.8,1.55,.45,.45,.65,1.9],
 'table2_external_paired':[1.15,.45,.35,1.1,1.25,.95,1.55],
 'table3_interactions':[1.1,.7,1.3,1.6,1.1],
 'table4_failure_mechanisms':[1.15,.45,.85,.7,.6,.7,.55,.75,2.15],
 'table5_razorpay_stops':[.8,.9,.55,.55,.55,.8,.65,2.5,1.2],
 'tableA1_github_segments':[1.2,.65,.45,.35,.85,1.05,.85,1.5],
 'tableA2_descriptive_mcnemar':[1.75,.5,.45,1.0,2.0],
 'tableA3_study1_locked':[.4,.4,1.1,1.2,.95,1.5,.85,.85],
 'tableA4_razorpay_points':[1.0,.4,.35,.9,1.15,.9,1.5],
 'tableA5_razorpay_mechanisms':[1.3,.5,1.1,.75,.7,.75,.65,1.1]}
REFS={'1':'table1_environments','2':'table2_external_paired','3':'table3_interactions','4':'table4_failure_mechanisms','5':'table5_razorpay_stops','A1':'tableA1_github_segments','A2':'tableA2_descriptive_mcnemar','A3':'study1-results','A4':'tableA4_razorpay_points','A5':'tableA5_razorpay_mechanisms'}
def refs(s):
 for n,key in sorted(REFS.items(),key=lambda x:-len(x[0])):s=re.sub(r'\bTable '+n+r'\b',lambda m:'Table \\ref{tab:'+key+'}',s)
 return s

def inline(s):
 saved=[]
 def save(text):saved.append(text);return '\x01'+str(len(saved)-1)+'\x02'
 # Protect complete inline maths and citation/ref commands before escaping text.
 s=re.sub(r'\*\*([^*]+)\*\*',lambda m:save(r'\textbf{'+inline(m.group(1))+'}'),s)
 s=re.sub(r'\*([^*]+)\*',lambda m:save(r'\emph{'+inline(m.group(1))+'}'),s)
 s=re.sub(r'\$[^$]+\$|\\(?:cite|ref|label)\{[^}]+\}',lambda m:save(m.group()),s)
 s=re.sub(r'`([^`]+)`',lambda m:save(r'\nolinkurl{'+m.group(1)+'}'),s)
 # Long protocol status labels and arm identities break safely at punctuation.
 s=re.sub(r'\b(?:POST_INCIDENT_REPLICATION_NOT_PRIMARY_REPLACEMENT|STATE_CORRECT|DUPLICATE_EFFECT)\b',lambda m:save(r'\nolinkurl{'+m.group()+'}'),s)
 trans={'&':r'\&','%':r'\%','_':r'\_','#':r'\#','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}','—':'---','–':'--','−':'-','§':r'\S','→':r'$\to$','Δ':r'$\Delta$'}
 s=''.join(trans.get(c,c) for c in s)
 # Convert plain H0/H1 terminology consistently to mathematical hidden worlds.
 s=re.sub(r'\bH([01])\b',lambda m:save('$H_'+m.group(1)+'$'),s)
 for _ in range(8):
  if '\x01' not in s: return s
  s=re.sub(r'\x01(\d+)\x02',lambda m:saved[int(m.group(1))],s)
 raise ValueError('Unresolved inline presentation token')

def table(t):
 key=t['name'];is_main=key in ['table1_environments','table2_external_paired','table3_interactions','tableA3_study1_locked']
 env='table*' if is_main else 'table'
 label='study1-results' if key=='tableA3_study1_locked' else key
 title=re.sub(r'^Table \w+\. ','',t['title'])
 weights=WEIGHTS[key];total=sum(weights);n=len(weights)
 cols=''.join(r'>{\hsize='+f'{w*n/total:.5f}'+r'\hsize\raggedright\arraybackslash}X' for w in weights)
 placement='!t' if is_main else '!htbp'
 out=[r'\begin{'+env+'}['+placement+']',r'\centering',r'\caption{'+inline(title)+'}',r'\label{tab:'+label+'}',r'\begingroup\footnotesize\setlength{\tabcolsep}{3pt}\renewcommand{\arraystretch}{1.22}',r'\begin{tabularx}{\textwidth}{'+cols+'}',r'\toprule',' & '.join(r'\textbf{'+inline(str(x))+'}' for x in t['headers'])+r' \\',r'\midrule']
 for row in t['rows']:out.append(' & '.join(inline(str(x)) for x in row)+r' \\')
 out += [r'\bottomrule',r'\end{tabularx}',r'\par\smallskip\raggedright\footnotesize '+inline(refs(t['note'])),r'\endgroup',r'\end{'+env+'}']
 return '\n'.join(out)+'\n'

def generate_assets():
 for t in TABLES:
  name='study1_table' if t['name']=='tableA3_study1_locked' else t['name']
  (P/'tables'/f'{name}.tex').write_text(table(t))
 # Legacy placeholder input is superseded, kept as a compatible entry point.
 (P/'tables/study2_table.tex').write_text('% Study 2 pre-data placeholder superseded by approved external results.\n\\input{tables/table2_external_paired.tex}\n')
 (P/'tables/study1_overhead.tex').write_text(r'''\begin{table}[!t]
\centering
\caption{Study 1 descriptive recovery overhead}
\label{tab:study1-overhead}
\footnotesize
\begin{tabular}{llrr}
\toprule
World & Policy & Model calls & Tool calls \\
\midrule
$H_0$ & Exact Replay & 0.00 & 1.00 \\
$H_0$ & LLM Regeneration & 3.70 & 2.70 \\
$H_1$ & Exact Replay & 0.00 & 1.00 \\
$H_1$ & LLM Regeneration & 2.03 & 1.03 \\
\bottomrule
\end{tabular}
\par\smallskip\raggedright Descriptive means from the locked Study 1 observations; displayed to two decimal places. No additional analysis.
\end{table}
''')
 for key,cap in CAPTIONS.items():
  cap=re.sub(r'^Figure (?:\d+|S1)\. ','',cap)
  main=key in ['figure1','figure2','figure3','figure4'];env='figure*' if main else 'figure'
  width=r'0.9\textwidth' if main else r'0.92\textwidth'
  placement='!t' if main else '!htbp'
  (P/'figures'/f'{key}.tex').write_text('\n'.join([r'\begin{'+env+'}['+placement+']',r'\centering',r'\includegraphics[width='+width+']{figures/'+key+'.pdf}',r'\caption{'+inline(refs(cap))+'}',r'\label{fig:'+key+'}',r'\end{'+env+'}'])+'\n')

PREAMBLE=r'''% Generated by python3 paper/build_source.py from canonical manuscript.md.
\renewcommand{\rmdefault}{ppl}
\RequirePackage[T1]{fontenc}
\documentclass[10pt,journal,compsoc]{IEEEtran}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{array,tabularx}
\usepackage{hyperref}
\usepackage{url}
\hypersetup{hidelinks,pdftitle={Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes},pdfauthor={J. Rashne}}
\Urlmuskip=0mu plus 1mu
\emergencystretch=1.5em
\raggedbottom
\begin{document}
\title{Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes}
\author{J.~Rashne%
\IEEEcompsocitemizethanks{\IEEEcompsocthanksitem J. Rashne is an independent researcher. E-mail: rashne.jash@gmail.com}}
'''

def render_body(s):
 lines=s.splitlines();out=[];i=0;stack=[];appendix=False
 def close():
  while stack:out.append(r'\end{'+stack.pop()[1]+'}')
 while i<len(lines):
  line=lines[i]
  if not line.strip():i+=1;continue
  if line.startswith('## References'):break
  if line.startswith('```'):
   close();i+=1;code=[]
   while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
   # Wrap display of the synthetic error string while preserving its bytes in Markdown.
   code=['ToolError: The previous request timed out.','Its outcome is unknown.'] if len(code)==1 and len(code[0])>65 else code
   out.extend([r'\begingroup\footnotesize\begin{verbatim}','\n'.join(code),r'\end{verbatim}\endgroup']);i+=1;continue
  if line.strip().startswith('$$'):
   eq=line.strip()[2:];i+=1
   if not eq.endswith('$$'):
    while i<len(lines) and not eq.endswith('$$'):eq+='\n'+lines[i];i+=1
   out.append(r'\begin{equation}'+'\n'+eq[:-2]+'\n'+r'\end{equation}');continue
  if line.startswith('#'):
   close();m=re.match(r'(#+) (.*)',line);level=len(m[1]);title=m[2]
   if title.startswith('Appendix:'):
    if not appendix:out += [r'\clearpage\onecolumn',r'\appendices'];appendix=True
    elif title in ['Appendix: State defects and evaluability','Appendix: Razorpay observed prefixes and diagnostics']:out.append(r'\clearpage')
    title=title.replace('Appendix: ','')
   cmd={2:'section',3:'subsection',4:'subsubsection'}[level]
   out.append('\\'+cmd+'{'+inline(title)+'}');i+=1;continue
  if line.startswith('\\input') or line.startswith('\\label'):close();out.append(line);i+=1;continue
  if line.startswith('> '):close();out += [r'\begin{quote}',inline(line[2:]),r'\end{quote}'];i+=1;continue
  m=re.match(r'( *)(?:([-]) |(\d+)\. )(.*)',line)
  if m:
   indent=len(m[1]);env='itemize' if m[2] else 'enumerate'
   while stack and (indent<stack[-1][0] or (indent==stack[-1][0] and env!=stack[-1][1])):out.append(r'\end{'+stack.pop()[1]+'}')
   if not stack or indent>stack[-1][0]:out.append(r'\begin{'+env+'}');stack.append((indent,env))
   out.append(r'\item '+inline(m[4]));i+=1;continue
  # An indented paragraph belongs to the preceding nested item.
  if stack and not line.startswith(' '):close()
  paragraph=[line.strip()];i+=1
  while i<len(lines) and lines[i].strip() and not re.match(r'^(?:#|\$\$|```|\\(?:input|label)|>|\s*(?:- |\d+\. ))',lines[i]):paragraph.append(lines[i].strip());i+=1
  out.append(inline(' '.join(paragraph))+'\n')
 close();return '\n\n'.join(out)

def main():
 generate_assets();md=(P/'manuscript.md').read_text();abstract=md.split('## Abstract\n\n',1)[1].split('\n\n## Introduction',1)[0];body=md.split('## Introduction',1)[1]
 title=PREAMBLE+r'\IEEEtitleabstractindextext{'+ '\n'+r'\begin{abstract}'+ '\n'+inline(abstract)+'\n'+r'\end{abstract}'+'\n'+r'\begin{IEEEkeywords}LLM agents, tool calling, retry semantics, idempotence, distributed systems reliability, fault tolerance.\end{IEEEkeywords}}'+'\n'+r'\maketitle\IEEEdisplaynontitleabstractindextext\IEEEpeerreviewmaketitle'+'\n'
 tex=title+render_body('## Introduction'+body)+'\n'+r'\bibliographystyle{IEEEtran}\bibliography{../research/references}'+'\n'+r'\end{document}'+'\n'
 (P/'main.tex').write_text(tex)
 print('Generated main.tex, table and figure wrappers from canonical Markdown and approved data.')
if __name__=='__main__':main()
