#!/usr/bin/env python3
"""Presentation-only Markdown to IEEE conference source. No evidence mutation."""
from pathlib import Path
import re
P=Path(__file__).resolve().parent
TITLE='Replay or Regenerate? Retry Semantics for State-Mutating LLM Agent Tool Calls Under Ambiguous Outcomes'
BIBLIOGRAPHY=r'\bibliographystyle{IEEEtran}\IfFileExists{research/references.bib}{\bibliography{research/references}}{\bibliography{../research/references}}'
def inline(s):
    saved=[]
    def save(v):
        saved.append(v)
        return '\x01'+str(len(saved)-1)+'\x02'
    s=re.sub(r'\*\*([^*]+)\*\*',lambda m:save(r'\textbf{'+inline(m[1])+'}'),s)
    s=re.sub(r'\*([^*]+)\*',lambda m:save(r'\emph{'+inline(m[1])+'}'),s)
    s=re.sub(r'\$[^$]+\$|\\(?:cite|ref|label)\{[^}]+\}',lambda m:save(m[0]),s)
    s=re.sub(r'`([^`]+)`',lambda m:save(r'\codeurl{'+m[1]+'}'),s)
    trans={'&':r'\&','%':r'\%','_':r'\_','#':r'\#','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}','—':'---','–':'--','−':'-','→':r'$\to$'}
    s=''.join(trans.get(c,c) for c in s)
    for _ in range(10):
        if '\x01' not in s: return s
        s=re.sub(r'\x01(\d+)\x02',lambda m:saved[int(m[1])],s)
    raise ValueError('Unresolved presentation token')
def render_body(s):
    out=[];paragraph=[];listing=False
    def flush():
        if paragraph:
            raw=' '.join(paragraph); rendered=inline(raw)
            if '`' in raw: rendered=r'{\raggedright '+rendered+r'\par}'
            out.append(rendered+'\n');paragraph.clear()
    for line in s.splitlines():
        if line.startswith('## References'):break
        if not line.strip():flush();continue
        if line.startswith('- '):
            flush()
            if not listing:out.append(r'\begin{itemize}');listing=True
            out.append(r'\item '+inline(line[2:]));continue
        if listing:out.append(r'\end{itemize}');listing=False
        if line.startswith('#'):
            flush();m=re.match(r'(#+) (.*)',line)
            out.append('\\'+{2:'section',3:'subsection',4:'subsubsection'}[len(m[1])]+'{'+inline(m[2])+'}')
        elif line.startswith('\\input') or line.startswith('\\label'):
            flush();out.append(line)
        else:paragraph.append(line.strip())
    flush()
    if listing:out.append(r'\end{itemize}')
    return '\n\n'.join(out)
PREAMBLE=r'''% Generated from manuscript.md by build_source.py; presentation only.
\documentclass[conference]{IEEEtran}
\usepackage{amsmath,amssymb}
\usepackage{graphicx,booktabs,array,tabularx}
\usepackage{url,hyperref}
\urlstyle{tt}
\newcommand{\codeurl}[1]{{\def\UrlFont{\ttfamily}\nolinkurl{#1}}}
\def\UrlBreaks{\do\/\do-\do\_\do.}
\hypersetup{hidelinks,pdftitle={'''+TITLE+r'''},pdfauthor={J. Rashne}}
\begin{document}
\title{'''+TITLE+r'''}
\author{\IEEEauthorblockN{J. Rashne}\IEEEauthorblockA{Independent researcher\\rashne.jash@gmail.com}}
\maketitle
'''
def main():
    md=(P/'manuscript.md').read_text()
    abstract=md.split('## Abstract\n\n',1)[1].split('\n\n## Introduction',1)[0]
    body='## Introduction'+md.split('## Introduction',1)[1]
    tex=PREAMBLE+'\\begin{abstract}\n'+inline(abstract)+'\n\\end{abstract}\n'
    tex+=r'\begin{IEEEkeywords}LLM agents, tool calls, retry semantics, state correctness, ambiguous outcomes.\end{IEEEkeywords}'+'\n'
    tex+=render_body(body)+'\n'+BIBLIOGRAPHY+'\n\\end{document}\n'
    (P/'main.tex').write_text(tex)
    supplement=P/'supplement/manuscript.md'
    if supplement.exists():
        smd=supplement.read_text();body='\n'.join(smd.splitlines()[2:])
        header=r'''% Separate supplement; not included in main-paper page count.
\documentclass[conference]{IEEEtran}
\usepackage{amsmath,amssymb,graphicx,booktabs,array,tabularx,url,hyperref}
\urlstyle{tt}
\newcommand{\codeurl}[1]{{\def\UrlFont{\ttfamily}\nolinkurl{#1}}}
\def\UrlBreaks{\do\/\do-\do\_\do.}
\hypersetup{hidelinks,pdftitle={Supplement: '''+TITLE+r'''}}
\begin{document}
\title{Supplement: '''+TITLE+r'''}
\author{\IEEEauthorblockN{J. Rashne}}
\maketitle
\raggedright
'''
        (P/'supplement.tex').write_text(header+render_body(body)+'\n\\end{document}\n')
    print('Rendered conference main.tex and separate supplement.tex; no statistics recomputed.')
if __name__=='__main__':main()
